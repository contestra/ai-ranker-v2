"""
Vertex AI adapter for Gemini 2.5-pro ONLY.
Supports both vertexai SDK and google-genai for API compatibility.
Implements two-step grounded JSON policy as required.
"""
import json
import os
import time
import logging
import asyncio
import hashlib
from typing import Any, Dict, List, Optional

import vertexai
from vertexai import generative_models as gm
from vertexai.generative_models import grounding
from vertexai.generative_models import Tool
from starlette.concurrency import run_in_threadpool

# Import google-genai for new API support
try:
    import google.genai as genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import VERTEX_ALLOWED_MODELS, VERTEX_DEFAULT_MODEL, validate_model
from .grounding_detection_helpers import detect_vertex_grounding

logger = logging.getLogger(__name__)

def _extract_vertex_citations2(resp) -> list:
    """
    Enhanced citation extractor that handles multiple field names including
    grounding_chunks and grounding_supports from the audit.
    """
    citations = []
    def add(item: dict):
        if not item: return
        if "url" in item and "uri" not in item:
            item["uri"] = item["url"]
        if "uri" in item:
            # Normalize to our standard format
            citations.append({
                "provider": "vertex",
                "url": item.get("uri"),
                "title": item.get("title"),
                "snippet": item.get("snippet") or item.get("text"),
                "source_type": "google_search",
                "rank": len(citations) + 1
            })
    
    try:
        cands = getattr(resp, "candidates", None) or []
        for cand in cands:
            gm = getattr(cand, "grounding_metadata", None) or getattr(cand, "groundingMetadata", None) or {}
            gm_dict = {}
            try:
                gm_dict = dict(gm)
            except Exception:
                for key in dir(gm):
                    if not key.startswith("_"):
                        try: gm_dict[key] = getattr(gm, key)
                        except Exception: pass
            
            # Check all possible field names
            pools = [
                gm_dict.get("citations"),
                gm_dict.get("cited_sources") or gm_dict.get("citedSources"),
                gm_dict.get("grounding_attributions") or gm_dict.get("groundingAttributions"),
                gm_dict.get("supporting_content") or gm_dict.get("supportingContent"),
                gm_dict.get("sources"),
                gm_dict.get("grounding_chunks") or gm_dict.get("groundingChunks"),
                gm_dict.get("grounding_supports") or gm_dict.get("groundingSupports"),
            ]
            
            for pool in pools:
                if not pool: continue
                for it in pool or []:
                    norm = {}
                    if isinstance(it, dict):
                        # Extract from flat dict fields
                        for k in ("uri","url","source_uri","title","license","snippet","text","pageUrl","sourceUrl"):
                            v = it.get(k)
                            if v:
                                if k in ("url","pageUrl","sourceUrl") and "uri" not in norm: 
                                    norm["uri"] = v
                                else: 
                                    norm[k] = v
                        
                        # Check nested structures
                        for subkey in ("source","web","reference"):
                            sub = it.get(subkey) if isinstance(it.get(subkey), dict) else None
                            if sub:
                                u = sub.get("uri") or sub.get("url")
                                if u and "uri" not in norm: norm["uri"] = u
                                ttl = sub.get("title")
                                if ttl and "title" not in norm: norm["title"] = ttl
                    else:
                        # Handle object-like items
                        for k in ("uri","url","source_uri","title","license","snippet","text","pageUrl","sourceUrl"):
                            try: v = getattr(it, k, None)
                            except Exception: v = None
                            if v:
                                if k in ("url","pageUrl","sourceUrl") and "uri" not in norm: 
                                    norm["uri"] = v
                                else: 
                                    norm[k] = v
                        
                        # Check nested object attributes
                        for subkey in ("source","web","reference"):
                            try: sub = getattr(it, subkey, None)
                            except Exception: sub = None
                            if sub:
                                u = getattr(sub, "uri", None) or getattr(sub, "url", None)
                                if u and "uri" not in norm: norm["uri"] = u
                                ttl = getattr(sub, "title", None)
                                if ttl and "title" not in norm: norm["title"] = ttl
                    
                    add(norm)
    except Exception as e:
        logger.debug(f"Error in _extract_vertex_citations2: {e}")
    
    return citations

def _audit_grounding_metadata(resp: Any) -> dict:
    """Forensic audit of grounding metadata structure when citations are missing."""
    audit = {"candidates": 0, "grounding_metadata_keys": [], "example": {}}
    try:
        if hasattr(resp, "candidates") and resp.candidates:
            audit["candidates"] = len(resp.candidates)
            cand = resp.candidates[0]
            gm = getattr(cand, "grounding_metadata", None) or getattr(cand, "groundingMetadata", None)
            if gm is None:
                return audit
            # Try to introspect available attributes / keys
            keys = set()
            try:
                gm_dict = dict(gm)  # works on some SDKs
                keys.update(gm_dict.keys())
                audit["example"] = {k: gm_dict[k] for k in list(gm_dict)[:3]}
            except Exception:
                for k in dir(gm):
                    if not k.startswith("_"):
                        keys.add(k)
                # sample a few attributes safely
                sample = {}
                for k in list(keys)[:5]:
                    try:
                        v = getattr(gm, k, None)
                        # avoid large dumps
                        if isinstance(v, (str, int, float, bool)) or v is None:
                            sample[k] = v
                    except Exception:
                        pass
                audit["example"] = sample
            audit["grounding_metadata_keys"] = sorted(list(keys))[:20]
    except Exception:
        pass
    return audit

# Models are now validated against allowlist in orchestrator
# No hard-coding or silent rewrites (Adapter PRD)

async def _call_vertex_model(model, *args, **kwargs):
    """
    Use async API if available, otherwise call the sync method in a thread.
    """
    gen_async = getattr(model, "generate_content_async", None)
    if gen_async and asyncio.iscoroutinefunction(gen_async):
        return await gen_async(*args, **kwargs)
    # fall back to sync generate_content in a thread
    gen_sync = getattr(model, "generate_content", None)
    if not gen_sync:
        raise RuntimeError("Vertex model has neither generate_content_async nor generate_content")
    return await run_in_threadpool(gen_sync, *args, **kwargs)

class GroundingRequiredError(Exception):
    """Raised when grounding is REQUIRED but not achieved"""
    pass

def _extract_vertex_usage(resp: Any) -> Dict[str, int]:
    """Extract token usage from Vertex response and normalize keys for telemetry."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    meta = getattr(resp, "usage_metadata", None)
    if meta:
        usage["prompt_tokens"] = getattr(meta, "prompt_token_count", 0)
        usage["completion_tokens"] = getattr(meta, "candidates_token_count", 0) 
        usage["total_tokens"] = getattr(meta, "total_token_count", 0)
    
    # Add synonyms for cross-adapter parity
    usage["input_tokens"] = usage["prompt_tokens"]
    usage["output_tokens"] = usage["completion_tokens"]
    
    return usage

def _extract_text_from_candidates(resp: Any) -> str:
    """Extract text from Vertex response - checks ALL candidates and ALL parts."""
    text_pieces = []
    
    try:
        # Check ALL candidates, not just first
        if hasattr(resp, "candidates") and resp.candidates:
            for idx, candidate in enumerate(resp.candidates):
                if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    parts = candidate.content.parts
                    if parts:
                        # Collect text from ALL parts in this candidate
                        for part_idx, part in enumerate(parts):
                            # Try text first
                            if hasattr(part, "text") and part.text:
                                text_pieces.append(part.text)
                                logger.debug(f"Found text in candidate[{idx}].part[{part_idx}]")
                            
                            # Try JSON data parts (for JSON mode responses)
                            elif hasattr(part, "json_data") and part.json_data is not None:
                                import json
                                json_text = json.dumps(part.json_data, ensure_ascii=False)
                                text_pieces.append(json_text)
                                logger.debug(f"Found json_data in candidate[{idx}].part[{part_idx}]")
                            
                            # Try inline_data (base64 encoded)
                            elif hasattr(part, "inline_data") and hasattr(part.inline_data, "data"):
                                try:
                                    import base64
                                    raw = base64.b64decode(part.inline_data.data)
                                    # Try to parse as JSON first
                                    try:
                                        parsed = json.loads(raw)
                                        text_pieces.append(json.dumps(parsed, ensure_ascii=False))
                                        logger.debug(f"Found inline JSON in candidate[{idx}].part[{part_idx}]")
                                    except:
                                        decoded = raw.decode("utf-8", errors="ignore")
                                        text_pieces.append(decoded)
                                        logger.debug(f"Found inline text in candidate[{idx}].part[{part_idx}]")
                                except Exception as e:
                                    logger.debug(f"Could not decode inline_data: {e}")
                else:
                    # Candidate has no parts - check for finish_reason
                    if hasattr(candidate, "finish_reason"):
                        logger.debug(f"Candidate[{idx}] has no parts, finish_reason: {candidate.finish_reason}")
        
        # If we got text from candidates, return it
        if text_pieces:
            return "\n".join(text_pieces)
        
        # Fallback to resp.text property (may raise ValueError)
        if hasattr(resp, "text"):
            try:
                return resp.text
            except ValueError as e:
                # Handle safety filters or empty response
                logger.warning(f"Could not extract text via .text property: {e}")
                
                # Log detailed response structure for debugging
                if hasattr(resp, "candidates") and resp.candidates:
                    for idx, cand in enumerate(resp.candidates):
                        if hasattr(cand, "finish_reason"):
                            logger.debug(f"Candidate[{idx}] finish_reason: {cand.finish_reason}")
                        if hasattr(cand, "safety_ratings"):
                            logger.debug(f"Candidate[{idx}] has safety_ratings")
                
    except Exception as e:
        logger.warning(f"Error extracting text from response: {e}")
        # Compact audit dump
        try:
            import json
            audit = {
                "has_candidates": hasattr(resp, "candidates"),
                "num_candidates": len(resp.candidates) if hasattr(resp, "candidates") else 0,
                "has_text": hasattr(resp, "text"),
                "error": str(e)
            }
            logger.debug(f"Extraction audit: {json.dumps(audit)}")
        except:
            pass
    
    return ""

def _sha256_text(text: str) -> str:
    """Generate SHA256 hash of text for attestation."""
    return hashlib.sha256(text.encode()).hexdigest()

def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Remove SDK objects from metadata to prevent serialization issues."""
    clean_metadata = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            clean_metadata[key] = value
        elif isinstance(value, dict):
            clean_metadata[key] = _sanitize_metadata(value)
        elif isinstance(value, list):
            # Deep-sanitize lists: recursively clean nested dicts
            clean_list = []
            for item in value:
                if isinstance(item, (str, int, float, bool, type(None))):
                    clean_list.append(item)
                elif isinstance(item, dict):
                    # Recursively sanitize nested dict
                    clean_list.append(_sanitize_metadata(item))
                elif isinstance(item, list):
                    # Handle nested lists recursively
                    clean_list.append(_sanitize_list(item))
                # Skip SDK objects
            clean_metadata[key] = clean_list
        # Skip SDK objects like Tool, FunctionTool, GoogleSearch, etc.
    return clean_metadata

def _sanitize_list(items: list) -> list:
    """Helper to recursively sanitize lists"""
    clean_list = []
    for item in items:
        if isinstance(item, (str, int, float, bool, type(None))):
            clean_list.append(item)
        elif isinstance(item, dict):
            clean_list.append(_sanitize_metadata(item))
        elif isinstance(item, list):
            clean_list.append(_sanitize_list(item))
        # Skip SDK objects
    return clean_list

def _extract_vertex_citations(resp: Any) -> list:
    """
    Collect grounding attributions from Vertex/Gemini grounded responses (Step-1).
    Returns normalized list:
      {provider:"vertex", url, title, snippet/evidence_text, source_type, rank}
    Enhanced to handle multiple SDK variants and field names including grounding_chunks and grounding_supports.
    """
    out = []
    try:
        rank = 1
        # 1) SDK typed path - try multiple attribute names
        if hasattr(resp, "candidates") and resp.candidates:
            cand = resp.candidates[0]
            meta = getattr(cand, "grounding_metadata", None)
            
            # Try standard grounding_attributions first
            atts = getattr(meta, "grounding_attributions", None)
            if atts:
                for a in atts:
                    # Different SDKs may expose .web.uri or .uri directly
                    url = None
                    if hasattr(a, "web") and hasattr(a.web, "uri"):
                        url = a.web.uri
                    elif hasattr(a, "uri"):
                        url = a.uri
                    
                    title = getattr(a, "title", None)
                    snippet = getattr(a, "snippet", None) or getattr(a, "passage", None)
                    
                    if url:
                        out.append({
                            "provider": "vertex",
                            "url": url,
                            "title": title,
                            "snippet": snippet,
                            "source_type": "google_search",
                            "rank": rank
                        })
                        rank += 1
            
            # Try grounding_chunks if grounding_attributions wasn't found
            if not out:
                chunks = getattr(meta, "grounding_chunks", None)
                if chunks:
                    for chunk in chunks:
                        # Extract URL from various possible locations
                        url = None
                        if hasattr(chunk, "web") and hasattr(chunk.web, "uri"):
                            url = chunk.web.uri
                        elif hasattr(chunk, "web") and hasattr(chunk.web, "url"):
                            url = chunk.web.url
                        elif hasattr(chunk, "reference") and hasattr(chunk.reference, "url"):
                            url = chunk.reference.url
                        elif hasattr(chunk, "source") and hasattr(chunk.source, "url"):
                            url = chunk.source.url
                        elif hasattr(chunk, "uri"):
                            url = chunk.uri
                        elif hasattr(chunk, "url"):
                            url = chunk.url
                        
                        title = getattr(chunk, "title", None)
                        snippet = getattr(chunk, "snippet", None) or getattr(chunk, "text", None) or getattr(chunk, "content", None)
                        
                        if url:
                            out.append({
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            })
                            rank += 1
            
            # Try grounding_supports if no citations found yet
            if not out:
                supports = getattr(meta, "grounding_supports", None)
                if supports:
                    for support in supports:
                        # Extract URL from various possible locations
                        url = None
                        if hasattr(support, "web") and hasattr(support.web, "uri"):
                            url = support.web.uri
                        elif hasattr(support, "web") and hasattr(support.web, "url"):
                            url = support.web.url
                        elif hasattr(support, "reference") and hasattr(support.reference, "url"):
                            url = support.reference.url
                        elif hasattr(support, "source") and hasattr(support.source, "url"):
                            url = support.source.url
                        elif hasattr(support, "uri"):
                            url = support.uri
                        elif hasattr(support, "url"):
                            url = support.url
                        
                        title = getattr(support, "title", None)
                        snippet = getattr(support, "snippet", None) or getattr(support, "text", None) or getattr(support, "content", None)
                        
                        if url:
                            out.append({
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            })
                            rank += 1
        
        # 2) Dict/camelCase path (google-genai model_dump)
        if hasattr(resp, "model_dump") and not out:  # Only if SDK path didn't find citations
            d = resp.model_dump()
            cands = d.get("candidates") or []
            if cands:
                # Try both camelCase and snake_case
                gm = cands[0].get("groundingMetadata") or cands[0].get("grounding_metadata") or {}
                atts = gm.get("groundingAttributions") or gm.get("grounding_attributions") or []
                for a in atts:
                    web = a.get("web") or {}
                    url = web.get("uri") or a.get("uri")
                    title = a.get("title")
                    snippet = a.get("snippet") or a.get("passage")
                    if url:
                        out.append({
                            "provider": "vertex",
                            "url": url,
                            "title": title,
                            "snippet": snippet,
                            "source_type": "google_search",
                            "rank": rank
                        })
                        rank += 1
                
                # Also check for grounding_chunks and grounding_supports in dict format
                if not out:
                    # Try grounding_chunks
                    chunks = gm.get("groundingChunks") or gm.get("grounding_chunks") or []
                    for chunk in chunks:
                        web = chunk.get("web") or {}
                        url = (web.get("uri") or web.get("url") or 
                               chunk.get("uri") or chunk.get("url") or
                               (chunk.get("reference") or {}).get("url") or
                               (chunk.get("source") or {}).get("url"))
                        
                        title = chunk.get("title")
                        snippet = chunk.get("snippet") or chunk.get("text") or chunk.get("content")
                        
                        if url:
                            out.append({
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            })
                            rank += 1
                
                # Try grounding_supports if still no citations
                if not out:
                    supports = gm.get("groundingSupports") or gm.get("grounding_supports") or []
                    for support in supports:
                        web = support.get("web") or {}
                        url = (web.get("uri") or web.get("url") or 
                               support.get("uri") or support.get("url") or
                               support.get("pageUrl") or support.get("sourceUrl") or
                               (support.get("reference") or {}).get("url") or
                               (support.get("source") or {}).get("url"))
                        
                        title = support.get("title")
                        snippet = support.get("snippet") or support.get("text") or support.get("content")
                        
                        if url:
                            out.append({
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            })
                            rank += 1
    except Exception as e:
        logger.debug(f"Error extracting Vertex citations: {e}")
    return out

def _make_google_search_tool():
    """Create GoogleSearch tool using google-genai SDK for API v1 compatibility."""
    try:
        # Use google-genai SDK which supports the new google_search field
        from google.genai import types
        return types.Tool(google_search=types.GoogleSearch())
    except ImportError:
        logger.warning("google-genai SDK not available, falling back to deprecated method")
        # Fall back to old SDK (will likely fail with API v1)
        try:
            return Tool.from_google_search_retrieval(
                grounding.GoogleSearchRetrieval()
            )
        except TypeError:
            return Tool.from_google_search_retrieval(
                google_search_retrieval=grounding.GoogleSearchRetrieval()
            )

class VertexAdapter:
    """
    Vertex AI adapter using ONLY publishers/google/models/gemini-2.5-pro.
    Implements two-step grounded JSON policy.
    """
    
    def __init__(self):
        """Initialize Vertex AI with project and location."""
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("VERTEX_PROJECT_ID"))
        self.location = os.getenv("VERTEX_LOCATION", "europe-west4")
        
        if not self.project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT or VERTEX_PROJECT_ID required - set in backend/.env"
            )
        
        # Initialize Vertex AI
        vertexai.init(project=self.project, location=self.location)
        
        # Initialize google-genai client if available and enabled
        self.use_genai = os.getenv("VERTEX_USE_GENAI_CLIENT", "true").lower() == "true" and GENAI_AVAILABLE
        self.genai_client = None
        
        if self.use_genai:
            try:
                # Create genai client in Vertex mode
                self.genai_client = genai.Client(
                    vertexai=True,
                    project=self.project,
                    location=self.location,
                    http_options=genai_types.HttpOptions(api_version="v1")
                )
                logger.info(f"Initialized google-genai client for Vertex (project={self.project}, location={self.location})")
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai client: {e}, falling back to vertexai SDK")
                self.use_genai = False
        
        # Log SDK version for debugging
        try:
            import google.cloud.aiplatform as aiplat
            sdk_info = f"google-cloud-aiplatform={aiplat.__version__}"
            if self.use_genai:
                sdk_info += f", google-genai={genai.__version__ if hasattr(genai, '__version__') else 'unknown'}"
            logger.info(f"Vertex adapter initialized: project={self.project}, location={self.location}, {sdk_info}")
        except:
            logger.info(f"Vertex adapter initialized: project={self.project}, location={self.location}")
    
    def _build_content_with_als(self, messages: List[Dict], als_block: str = None) -> tuple[str, List[gm.Content]]:
        """
        Build Vertex Content objects from messages.
        Returns (system_instruction, contents).
        Keeps system separate, ALS goes in first user message.
        Order: system → ALS → user (ALS is in user message, not system).
        """
        contents = []
        system_text = None
        user_texts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            
            if not text:
                continue
            
            if role == "system":
                # Keep system text separate for system_instruction
                if system_text is None:
                    system_text = text
                else:
                    system_text = f"{system_text}\n\n{text}"
            elif role == "user":
                # For first user message, prepend ALS if provided
                if als_block and not user_texts and not contents:
                    # ALS goes BEFORE user content in the user message
                    user_texts.append(als_block)
                user_texts.append(text)
            elif role == "assistant":
                # First, add any accumulated user text
                if user_texts:
                    user_part = gm.Part.from_text("\n\n".join(user_texts))
                    user_content = gm.Content(role="user", parts=[user_part])
                    contents.append(user_content)
                    user_texts = []
                
                # Then add assistant message as model role
                assistant_part = gm.Part.from_text(text)
                assistant_content = gm.Content(role="model", parts=[assistant_part])
                contents.append(assistant_content)
        
        # Add any remaining user text
        if user_texts:
            user_part = gm.Part.from_text("\n\n".join(user_texts))
            user_content = gm.Content(role="user", parts=[user_part])
            contents.append(user_content)
        
        return system_text, contents
    
    def _create_generation_config_step1(self, req: LLMRequest) -> gm.GenerationConfig:
        """Create generation config for Step 1 (grounded, NO JSON)."""
        # For ungrounded requests, ensure minimum tokens to avoid empty responses
        # Vertex doesn't return partial content when hitting MAX_TOKENS
        requested_tokens = getattr(req, "max_tokens", 6000)
        is_grounded = getattr(req, "grounded", False)
        
        # Apply minimum only for ungrounded to avoid empty responses
        if not is_grounded and requested_tokens < 500:
            logger.warning(f"Increasing max_tokens from {requested_tokens} to 500 for Vertex ungrounded (avoids empty responses)")
            max_tokens = 500
        else:
            max_tokens = requested_tokens
            
        config_dict = {
            "temperature": getattr(req, "temperature", 0.7),
            "top_p": getattr(req, "top_p", 0.95),
            "max_output_tokens": max_tokens,
        }
        # Step 1: NO response_mime_type - we want prose with citations
        return gm.GenerationConfig(**config_dict)
    
    def _create_generation_config_step2_json(self) -> gm.GenerationConfig:
        """Create generation config for Step 2 (JSON reshape, NO tools)."""
        return gm.GenerationConfig(
            temperature=0.1,  # Low temp for consistent JSON
            max_output_tokens=6000,
            response_mime_type="application/json"  # JSON only in Step 2
        )
    
    async def _step1_grounded(self, model: gm.GenerativeModel, contents: List[gm.Content], 
                             generation_config: gm.GenerationConfig, timeout: int, 
                             mode: str = "AUTO") -> tuple[Any, bool, int]:
        """
        Step 1: Generate grounded response with GoogleSearch tool.
        Returns (response, grounded_effective, tool_call_count).
        """
        # Create GoogleSearch tool for grounding (Step-1 ONLY)
        # Use version-tolerant helper
        tools = [_make_google_search_tool()]
        
        # [WIRE_DEBUG] Log what we're sending
        logger.debug(f"[WIRE_DEBUG] Vertex Step-1 grounded call:")
        logger.debug(f"  Tool class: {type(tools[0])}")
        logger.debug("  Using: Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())")
        logger.debug(f"  Mode: {mode}")
        logger.debug(f"  Generation config has JSON mime: {hasattr(generation_config, 'response_mime_type')}")
        
        # Add tool_config for REQUIRED mode
        tool_config = None
        if mode == "REQUIRED":
            # Try to import ToolConfig from vertexai
            try:
                from vertexai.generative_models import ToolConfig
                # For REQUIRED mode, we need to enforce at least one tool call
                tool_config = ToolConfig(
                    function_calling_config=ToolConfig.FunctionCallingConfig(
                        mode=ToolConfig.FunctionCallingConfig.Mode.ANY
                    )
                )
            except ImportError:
                # Fallback if ToolConfig not available
                logger.warning("ToolConfig not available in vertexai SDK, REQUIRED mode may not enforce tool calls")
        
        try:
            call_kwargs = {
                "contents": contents,
                "generation_config": generation_config,
                "tools": tools
            }
            if tool_config:
                call_kwargs["tool_config"] = tool_config
                
            response = await asyncio.wait_for(
                _call_vertex_model(model, **call_kwargs),
                timeout=timeout
            )
            
            # Check if grounding was actually used
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            
            # Count tool calls (grounding citations)
            tool_call_count = 0
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "grounding_metadata"):
                    meta = candidate.grounding_metadata
                    if hasattr(meta, "grounding_attributions"):
                        tool_call_count = len(meta.grounding_attributions)
            
            # REQUIRED mode enforcement
            if mode == "REQUIRED" and not grounded_effective:
                raise GroundingRequiredError(
                    f"No Vertex grounding evidence found (mode=REQUIRED). "
                    f"tool_call_count={tool_call_count}"
                )
            
            return response, grounded_effective, grounding_count
            
        except asyncio.TimeoutError:
            raise
        except GroundingRequiredError:
            raise
        except Exception as e:
            logger.error(f"Step 1 grounded generation failed: {e}")
            raise
    
    async def _step2_reshape_json(self, model: gm.GenerativeModel, step1_text: str, 
                                  original_request: str, timeout: int) -> tuple[Any, Dict]:
        """
        Step 2: Reshape to JSON without tools.
        Returns (response, attestation).
        """
        # Build reshape prompt
        reshape_prompt = f"""Based on this grounded answer, provide a structured JSON response.

Original Question: {original_request}

Grounded Answer: {step1_text}

Provide your response as valid JSON with appropriate keys for the information."""
        
        # Create content for reshape - single user message
        reshape_part = gm.Part.from_text(reshape_prompt)
        reshape_content = gm.Content(role="user", parts=[reshape_part])
        
        # JSON config for Step 2
        json_config = self._create_generation_config_step2_json()
        
        # [WIRE_DEBUG] Log Step-2 config
        logger.debug(f"[WIRE_DEBUG] Vertex Step-2 JSON reshape:")
        logger.debug(f"  Tools: None (enforced)")
        logger.debug(f"  Response mime type: application/json")
        logger.debug(f"  Temperature: {json_config.temperature if hasattr(json_config, 'temperature') else 'default'}")
        
        try:
            # Step 2 MUST have NO tools
            response = await asyncio.wait_for(
                _call_vertex_model(
                    model,
                    contents=[reshape_content],
                    generation_config=json_config,
                    tools=None  # NO TOOLS in step 2 - enforced
                ),
                timeout=timeout
            )
            
            # Verify no tools were invoked (they shouldn't be since we passed None)
            tools_invoked = False
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "function_calls") and candidate.function_calls:
                    tools_invoked = True
                    logger.error("VIOLATION: Tools invoked in Step 2 (should be impossible)")
            
            # Create attestation
            attestation = {
                "step2_tools_invoked": tools_invoked,  # Must be false
                "step2_source_ref": _sha256_text(step1_text)
            }
            
            return response, attestation
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Step 2 JSON reshape failed: {e}")
            raise
    
    async def _step1_grounded_genai(self, req: LLMRequest, contents: List[gm.Content], 
                                    generation_config: gm.GenerationConfig, timeout: int, 
                                    mode: str = "AUTO", system_instruction: str = None) -> tuple[Any, bool, int]:
        """
        Step 1 using google-genai: Generate grounded response with GoogleSearch tool.
        Returns (response, grounded_effective, tool_call_count).
        """
        # Build messages in genai format - use passed system_instruction
        combined_text = []
        
        for content in contents:
            text = content.parts[0].text if content.parts else ""
            if text:
                combined_text.append(text)
        
        # Create genai contents format with parts
        final_text = "\n\n".join(combined_text)
        contents_genai = [{"role": "user", "parts": [{"text": final_text}]}]
        
        # Create GoogleSearch tool using genai
        tools = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
        
        # Create generation config
        # Map our mode to SDK mode: REQUIRED -> ANY (at least one tool call), AUTO -> AUTO
        sdk_mode = "ANY" if mode == "REQUIRED" else "AUTO"
        config_params = {
            "temperature": generation_config.temperature if hasattr(generation_config, 'temperature') else 0.7,
            "top_p": generation_config.top_p if hasattr(generation_config, 'top_p') else 0.95,
            "max_output_tokens": generation_config.max_output_tokens if hasattr(generation_config, 'max_output_tokens') else 6000,
            "tools": tools,
            "tool_config": genai_types.ToolConfig(function_calling_config={"mode": sdk_mode})
        }
        
        # Add system instruction to config if available
        if system_instruction:
            config_params["system_instruction"] = system_instruction
            
        config = genai_types.GenerateContentConfig(response_mime_type='text/plain', **config_params)
        
        # Wire debug logging
        logger.debug(f"[GENAI] Step-1 grounded call:")
        logger.debug(f"  contents[0].keys(): {list(contents_genai[0].keys())}")
        logger.debug(f"  contents[0].role: {contents_genai[0]['role']}")
        logger.debug(f"  len(contents[0].parts): {len(contents_genai[0]['parts'])}")
        logger.debug(f"  text preview: {final_text[:120]}...")
        logger.debug(f"  tools: {[type(t).__name__ for t in tools]}")
        logger.debug(f"  system_instruction length: {len(system_instruction) if system_instruction else 0}")
        
        try:
            # Use genai client to generate
            response = await asyncio.wait_for(
                self.genai_client.aio.models.generate_content(
                    model=req.model,
                    contents=contents_genai,
                    config=config
                ),
                timeout=timeout
            )
            
            # Check if grounding was actually used - use existing detector for genai responses
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            
            logger.debug(f"[GENAI] Step-1 grounding detection: used={grounded_effective}, count={grounding_count}")
            
            # REQUIRED mode enforcement
            if mode == "REQUIRED" and not grounded_effective:
                raise GroundingRequiredError(
                    f"No grounding evidence found (mode=REQUIRED). "
                    f"tool_call_count={grounding_count}"
                )
            
            return response, grounded_effective, grounding_count
            
        except asyncio.TimeoutError:
            raise
        except GroundingRequiredError:
            raise
        except Exception as e:
            logger.error(f"[GENAI] Step 1 grounded generation failed: {e}")
            raise
    
    async def _step2_reshape_json_genai(self, req: LLMRequest, step1_text: str, 
                                        original_request: str, timeout: int) -> tuple[Any, Dict]:
        """
        Step 2 using google-genai: Reshape to JSON without tools.
        Returns (response, attestation).
        """
        # Build reshape prompt
        reshape_prompt = f"""Based on this grounded answer, provide a structured JSON response.

Original Question: {original_request}

Grounded Answer: {step1_text}

Provide your response as valid JSON with appropriate keys for the information."""
        
        contents_genai = [{"role": "user", "parts": [{"text": reshape_prompt}]}]
        
        # JSON config for Step 2 - EXPLICITLY NO TOOLS
        config = genai_types.GenerateContentConfig(
            temperature=0.1,  # Low temp for consistent JSON
            max_output_tokens=6000,
            response_mime_type="application/json",
            tools=[]  # Explicitly empty tools list
        )
        
        logger.debug(f"[GENAI] Step-2 JSON reshape:")
        logger.debug(f"  tools explicitly set to: []")
        logger.debug(f"  response_mime_type: application/json")
        
        try:
            response = await asyncio.wait_for(
                self.genai_client.aio.models.generate_content(
                    model=req.model,
                    contents=contents_genai,
                    config=config
                ),
                timeout=timeout
            )
            
            # Verify no tools were invoked using existing detector
            tools_invoked_result, tool_count = detect_vertex_grounding(response)
            tools_invoked = tools_invoked_result  # Should be False for Step-2
            
            if tools_invoked:
                logger.error(f"[GENAI] VIOLATION: Tools invoked in Step 2 (count={tool_count})")
            else:
                logger.debug(f"[GENAI] Step-2 verification: no tools invoked (as expected)")
            
            # Create attestation
            attestation = {
                "step2_tools_invoked": tools_invoked,  # Must be false
                "step2_source_ref": _sha256_text(step1_text)
            }
            
            return response, attestation
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"[GENAI] Step 2 JSON reshape failed: {e}")
            raise
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """
        Complete request using Vertex AI with Gemini 2.5-pro ONLY.
        Implements two-step grounded JSON policy when needed.
        """
        t0 = time.perf_counter()
        
        # Use the requested model (already validated in orchestrator)
        model_id = req.model
        logger.info(f"Using requested model: {model_id}")
        
        # Double-check validation (belt and suspenders)
        is_valid, error_msg = validate_model("vertex", model_id)
        if not is_valid:
            raise ValueError(f"MODEL_NOT_ALLOWED: {error_msg}")
        
        # Initialize metadata
        metadata = {
            "model": model_id,
            "response_api": "vertex_genai",
            "provider_api_version": "vertex:genai-v1",
            "region": os.getenv("VERTEX_LOCATION", "europe-west4"),  # Match init default
            "proxies_enabled": False,
            "proxy_mode": "disabled",
            "vantage_policy": str(getattr(req, "vantage_policy", "NONE"))
        }
        
        # Extract ALS block if present (should be in messages already)
        als_block = None
        # ALS is handled at template_runner level, included in messages
        
        # Build contents and extract system instruction
        # Returns (system_text, contents) - system separate, ALS in user message
        system_instruction, contents = self._build_content_with_als(req.messages, als_block)
        
        # Create model with system_instruction if present
        if system_instruction:
            model = gm.GenerativeModel(model_id, system_instruction=system_instruction)
            logger.debug(f"Using system_instruction: {len(system_instruction)} chars")
        else:
            model = gm.GenerativeModel(model_id)
        
        # Check if JSON mode is needed
        is_json_mode = getattr(req, "json_mode", False)
        is_grounded = getattr(req, "grounded", False)
        
        # Extract grounding mode (AUTO or REQUIRED)
        grounding_mode = getattr(req, "grounding_mode", "AUTO")
        if hasattr(req, "meta") and isinstance(req.meta, dict):
            grounding_mode = req.meta.get("grounding_mode", grounding_mode)
        # Surface requested mode for QA/telemetry parity
        metadata["grounding_mode_requested"] = grounding_mode
        
        # Determine two-step requirement
        needs_two_step = is_grounded and is_json_mode
        
        if needs_two_step:
            logger.info(f"Two-step grounded JSON mode activated (mode={grounding_mode})")
            logger.debug(f"[VERTEX_GROUNDING] Attempting two-step grounded JSON: model={req.model}, mode={grounding_mode}")
            
            # Step 1: Grounded generation (NO JSON)
            generation_config = self._create_generation_config_step1(req)
            if self.use_genai and self.genai_client:
                logger.debug(f"[VERTEX_GROUNDING] Using genai client for Step 1 grounding")
                step1_resp, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                    req, contents, generation_config, timeout, mode=grounding_mode, 
                    system_instruction=system_instruction
                )
            else:
                logger.debug(f"[VERTEX_GROUNDING] Using vertex SDK for Step 1 grounding")
                step1_resp, grounded_effective, tool_call_count = await self._step1_grounded(
                    model, contents, generation_config, timeout, mode=grounding_mode
                )
            
            logger.debug(f"[VERTEX_GROUNDING] Step 1 complete: grounded_effective={grounded_effective}, "
                        f"tool_calls={tool_call_count}")
            
            # Citations from Step-1
            step1_citations = _extract_vertex_citations2(step1_resp)
            step1_text = _extract_text_from_candidates(step1_resp)
            
            # Step 2: Reshape to JSON (NO TOOLS)
            # Get the last USER message (not just last message which could be assistant)
            original_request = ""
            for msg in reversed(req.messages):
                if msg.get("role") == "user":
                    original_request = msg.get("content", "")
                    break
            logger.debug(f"[VERTEX_GROUNDING] Starting Step 2 JSON reshape")
            if self.use_genai and self.genai_client:
                step2_resp, attestation = await self._step2_reshape_json_genai(
                    req, step1_text, original_request, timeout
                )
            else:
                step2_resp, attestation = await self._step2_reshape_json(
                    model, step1_text, original_request, timeout
                )
            logger.debug(f"[VERTEX_GROUNDING] Step 2 complete: tools_invoked={attestation.get('step2_tools_invoked', False)}")
            
            # Use step2 response as final
            response = step2_resp
            text = _extract_text_from_candidates(step2_resp)
            
            # Update metadata
            metadata["two_step_used"] = True
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = tool_call_count
            metadata.update(attestation)
            if step1_citations:
                metadata["citations"] = step1_citations
            else:
                # Forensic audit when tools were used but no citations found
                if metadata.get("tool_call_count", 0) > 0:
                    metadata["why_not_grounded"] = "citations_missing_in_metadata"
                    audit = _audit_grounding_metadata(step1_resp)
                    metadata["citations_audit"] = audit
                    
                    # Structured log for easy grep
                    structured_log = {
                        "vendor": "vertex",
                        "tool_calls": tool_call_count,
                        "citations": 0,
                        "keys": audit.get("grounding_metadata_keys", []),
                        "why_not_grounded": "citations_missing_in_metadata"
                    }
                    logger.info(f"[VERTEX_CITATION_AUDIT] {json.dumps(structured_log)}")
            
        elif is_grounded:
            # Single-step grounded (non-JSON)
            logger.debug(f"[VERTEX_GROUNDING] Attempting single-step grounding: model={req.model}, mode={grounding_mode}")
            generation_config = self._create_generation_config_step1(req)
            if self.use_genai and self.genai_client:
                logger.debug(f"[VERTEX_GROUNDING] Using genai client for single-step grounding")
                response, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                    req, contents, generation_config, timeout, mode=grounding_mode,
                    system_instruction=system_instruction
                )
            else:
                logger.debug(f"[VERTEX_GROUNDING] Using vertex SDK for single-step grounding")
                response, grounded_effective, tool_call_count = await self._step1_grounded(
                    model, contents, generation_config, timeout, mode=grounding_mode
                )
            
            logger.debug(f"[VERTEX_GROUNDING] Single-step complete: grounded_effective={grounded_effective}, "
                        f"tool_calls={tool_call_count}")
            
            text = _extract_text_from_candidates(response)
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = tool_call_count
            
            # Citations from Step-1
            try:
                cits = _extract_vertex_citations2(response)
                if cits:
                    metadata["citations"] = cits
                else:
                    # Forensic audit when tools were used but no citations found
                    if metadata.get("tool_call_count", 0) > 0:
                        metadata["why_not_grounded"] = "citations_missing_in_metadata"
                        audit = _audit_grounding_metadata(response)
                        metadata["citations_audit"] = audit
                        
                        # Structured log for easy grep
                        structured_log = {
                            "vendor": "vertex",
                            "tool_calls": tool_call_count,
                            "citations": 0,
                            "keys": audit.get("grounding_metadata_keys", []),
                            "why_not_grounded": "citations_missing_in_metadata"
                        }
                        logger.info(f"[VERTEX_CITATION_AUDIT] {json.dumps(structured_log)}")
            except Exception:
                pass
            
            # Add finish_reason for grounded responses too
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason"):
                    metadata["finish_reason"] = str(candidate.finish_reason)
            
        else:
            # Regular generation (no grounding, may have JSON)
            logger.debug(f"[VERTEX_GROUNDING] Ungrounded request: model={req.model}, json_mode={is_json_mode}")
            if is_json_mode:
                generation_config = self._create_generation_config_step2_json()
                max_tokens_used = 6000  # JSON mode uses fixed 6000
            else:
                generation_config = self._create_generation_config_step1(req)
                # Track the actual max_tokens used (may have been increased from 200 to 500)
                requested_tokens = getattr(req, "max_tokens", 6000)
                max_tokens_used = max(requested_tokens, 500) if requested_tokens < 500 else requested_tokens
            
            # First attempt with normal settings
            try:
                response = await asyncio.wait_for(
                    _call_vertex_model(
                        model,
                        contents=contents,
                        generation_config=generation_config,
                        tools=None  # No tools for ungrounded
                    ),
                    timeout=timeout
                )
                text = _extract_text_from_candidates(response)
                metadata["grounded_effective"] = False
                metadata["tool_call_count"] = 0
                
                # Check if we need to retry
                should_retry = False
                retry_reason = ""
                
                # Get token count and finish reason
                candidates_token_count = 0
                if hasattr(response, "usage_metadata"):
                    candidates_token_count = getattr(response.usage_metadata, "candidates_token_count", 0)
                
                finish_reason = None
                if hasattr(response, "candidates") and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, "finish_reason"):
                        finish_reason = candidate.finish_reason
                
                # Determine if retry is needed
                if not text:
                    should_retry = True
                    retry_reason = "empty_text"
                elif candidates_token_count == 0:
                    should_retry = True
                    retry_reason = "zero_tokens"
                elif finish_reason and (str(finish_reason) == "2" or 
                                       finish_reason == 2 or
                                       "MAX_TOKENS" in str(finish_reason)):
                    should_retry = True
                    retry_reason = f"max_tokens_hit (finish_reason={finish_reason})"
                
                # Perform retry if needed (SDK-only, no JSON mode)
                if should_retry and not is_json_mode:
                    logger.info(f"Retrying Vertex ungrounded due to: {retry_reason}")
                    metadata["retry_attempted"] = True
                    metadata["retry_reason"] = retry_reason
                    
                    # Create retry config with text/plain and increased tokens
                    # Use request temperature, slightly reduced
                    original_temp = getattr(req, "temperature", 0.7)
                    retry_temp = min(original_temp * 0.9, 0.6)  # Slight reduction, but stay user-like
                    
                    # Increase tokens more aggressively on retry (2x instead of 1.5x)
                    retry_max_tokens = min(int(max_tokens_used * 2), 2000)  # Double, but cap at 2000
                    
                    retry_config = gm.GenerationConfig(
                        temperature=retry_temp,
                        top_p=getattr(req, "top_p", 0.95),
                        max_output_tokens=retry_max_tokens,
                        response_mime_type="text/plain"  # Force single text part
                    )
                    
                    logger.debug(f"Retry config: temp={retry_temp}, max_tokens={retry_max_tokens}, mime=text/plain")
                    
                    try:
                        retry_response = await asyncio.wait_for(
                            _call_vertex_model(
                                model,
                                contents=contents,
                                generation_config=retry_config,
                                tools=None
                            ),
                            timeout=timeout
                        )
                        retry_text = _extract_text_from_candidates(retry_response)
                        
                        if retry_text:
                            text = retry_text
                            response = retry_response  # Use retry response for metadata
                            metadata["retry_successful"] = True
                            logger.info("Retry successful, got text response")
                        else:
                            metadata["retry_successful"] = False
                            logger.warning("Retry still produced empty text")
                            
                    except Exception as retry_error:
                        logger.error(f"Retry failed: {retry_error}")
                        metadata["retry_error"] = str(retry_error)
                        metadata["retry_successful"] = False
                
            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - t0
                logger.error(f"Vertex timeout after {elapsed:.2f}s")
                raise
        
        # Add finish_reason to metadata if available
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "finish_reason"):
                metadata["finish_reason"] = str(candidate.finish_reason)
        
        # Extract usage
        usage = _extract_vertex_usage(response)
        
        # Calculate latency
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Add model version if available (Gemini fingerprint)
        if hasattr(response, "_raw_response"):
            raw = response._raw_response
            if hasattr(raw, "model_version"):
                metadata["modelVersion"] = raw.model_version
        elif hasattr(response, "model_version"):
            metadata["modelVersion"] = response.model_version
        
        # Log telemetry
        logger.info(
            f"Vertex completed in {latency_ms}ms, "
            f"grounded={is_grounded}, grounded_effective={metadata.get('grounded_effective', False)}, "
            f"tool_calls={metadata.get('tool_call_count', 0)}, "
            f"usage={usage}"
        )
        
        # Sanitize metadata to remove SDK objects
        clean_metadata = _sanitize_metadata(metadata)
        
        # Extract commonly-read fields for telemetry parity
        grounded_effective_flag = bool(clean_metadata.get("grounded_effective", False))
        
        # Determine success based on content
        success = True
        error_type = None
        why_no_content = None
        
        if not text:
            success = False
            error_type = "EMPTY_COMPLETION"
            
            # Build detailed why_no_content
            reasons = []
            if clean_metadata.get("retry_attempted"):
                reasons.append(f"retry_attempted={clean_metadata.get('retry_successful', False)}")
            if clean_metadata.get("retry_reason"):
                reasons.append(f"retry_reason={clean_metadata['retry_reason']}")
            if clean_metadata.get("finish_reason"):
                reasons.append(f"finish_reason={clean_metadata['finish_reason']}")
            if usage and usage.get("candidates_token_count") == 0:
                reasons.append("candidates_token_count=0")
            
            why_no_content = " | ".join(reasons) if reasons else "extraction_empty_all_parts"
            clean_metadata["error_type"] = error_type
            clean_metadata["why_no_content"] = why_no_content
            
            logger.warning(f"Returning empty response: {why_no_content}")
        
        # Final success/empty evaluation
        success_flag = success  # Keep existing success value
        error_type = clean_metadata.get("error_type", None)
        error_message = None
        
        # Additional check for truly empty ungrounded responses
        if not is_grounded and (not text or not str(text).strip()):
            if success_flag:  # Only override if not already marked as failure
                success_flag = False
                error_type = "EMPTY_COMPLETION"
                # Try to attach a concise reason if available
                try:
                    reason = None
                    if hasattr(response, "candidates") and response.candidates:
                        fr = getattr(response.candidates[0], "finish_reason", None)
                        reason = str(fr) if fr is not None else None
                    meta_reason = "unknown"
                    if usage.get("completion_tokens", 0) == 0:
                        meta_reason = "candidates_token_count=0"
                    clean_metadata.setdefault("why_no_content", reason or meta_reason)
                except Exception:
                    pass
        
        # --- ALS propagation into response metadata ---
        try:
            req_meta = getattr(req, 'metadata', {}) or {}
            if isinstance(req_meta, dict) and req_meta.get('als_present'):
                # copy whitelisted ALS fields
                for k in ('als_present','als_block_sha256','als_variant_id','seed_key_id','als_country','als_locale','als_nfc_length','als_template_id'):
                    if k in req_meta:
                        clean_metadata[k] = req_meta[k]
        except Exception as _:
            pass
        
        return LLMResponse(
            content=text,
            model_version=model_id,
            model_fingerprint=clean_metadata.get("modelVersion"),
            grounded_effective=grounded_effective_flag,
            usage=usage,
            latency_ms=latency_ms,
            raw_response=None,
            success=success_flag,  # truthy empty handling
            vendor="vertex",
            model=model_id,
            metadata=clean_metadata,
            error_type=error_type,
            error_message=error_message
        )