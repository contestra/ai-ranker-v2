"""
Lean Vertex adapter - shape conversion, policy enforcement, and telemetry only.
Transport/retries/backoff handled by SDK and router.
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlunparse

import google.genai as genai
from google.genai.types import (
    FunctionCallingConfig, FunctionDeclaration, GenerateContentConfig,
    GoogleSearch, HarmBlockThreshold, HarmCategory, SafetySetting, Schema,
    ThinkingConfig, Tool, ToolConfig
)

from app.core.config import settings
from app.llm.errors import GroundingRequiredFailedError
from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model

logger = logging.getLogger(__name__)

# Environment configuration  
# Vertex uses ADC/WIF for auth, project from env or settings
VERTEX_PROJECT = os.getenv("VERTEX_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or settings.google_cloud_project
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION") or settings.vertex_location or "europe-west4"
VERTEX_MAX_OUTPUT_TOKENS = int(os.getenv("VERTEX_MAX_OUTPUT_TOKENS", "8192"))
VERTEX_GROUNDED_MAX_TOKENS = int(os.getenv("VERTEX_GROUNDED_MAX_TOKENS", "6000"))


def _get_registrable_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        p = urlparse(url)
        domain = p.netloc.lower().replace("www.", "")
        
        # Keep full domain for Vertex redirects
        if 'vertexaisearch.cloud.google.com' in domain:
            return domain
        
        return domain if domain else "unknown"
    except Exception:
        return "unknown"


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    try:
        p = urlparse(url)
        p = p._replace(fragment="")
        if p.query:
            q = parse_qs(p.query, keep_blank_values=True)
            q = {k: v for k, v in q.items() if not k.lower().startswith("utm_")}
            if q:
                pairs = []
                for k, vs in q.items():
                    for v in vs:
                        pairs.append(f"{k}={v}")
                p = p._replace(query="&".join(pairs))
            else:
                p = p._replace(query="")
        return urlunparse(p._replace(netloc=p.netloc.lower()))
    except Exception:
        return url


def _extract_redirect_url(google_url: str) -> str:
    """Extract real URL from Google grounding redirect."""
    if "vertexaisearch.cloud.google.com/grounding-api-redirect/" in google_url:
        # This is a redirect URL, extract if possible
        # For now, return as-is; in production, decode the redirect
        return google_url
    return google_url


def _extract_text_from_response(response) -> str:
    """Extract text from Vertex response."""
    if not response or not getattr(response, "candidates", None):
        return ""
    buf: List[str] = []
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                t = getattr(part, "text", None)
                if isinstance(t, str):
                    buf.append(t)
    return "".join(buf).strip()


def _extract_function_call(response) -> Tuple[Optional[str], Optional[Dict]]:
    """Extract function call from response."""
    if not response or not getattr(response, "candidates", None):
        return None, None
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    func_name = getattr(fc, "name", None)
                    args = getattr(fc, "args", None)
                    return func_name, args
    return None, None


def _extract_citations_from_grounding(response) -> Tuple[List[Dict[str, Any]], int, int]:
    """Extract citations from grounding metadata.
    Returns: (citations list, anchored_count, unlinked_count)
    """
    citations = []
    anchored_count = 0
    unlinked_count = 0
    
    if not response or not getattr(response, "candidates", None):
        return citations, anchored_count, unlinked_count
    
    for cand in response.candidates or []:
        grounding_metadata = getattr(cand, "grounding_metadata", None)
        if not grounding_metadata:
            continue
            
        # Extract grounding_chunks (web search results) - these are unlinked
        grounding_chunks = getattr(grounding_metadata, "grounding_chunks", []) or []
        for chunk in grounding_chunks:
            web = getattr(chunk, "web", None)
            if web:
                uri = getattr(web, "uri", None)
                title = getattr(web, "title", None)
                if uri:
                    final_url = _extract_redirect_url(uri)
                    citations.append({
                        "url": final_url,
                        "title": title or "",
                        "source_type": "grounding_chunk",
                        "domain": _get_registrable_domain(final_url)
                    })
                    unlinked_count += 1  # Grounding chunks are unlinked evidence
        
        # Extract search_queries (what was searched) - these are also unlinked
        search_queries = getattr(grounding_metadata, "search_queries", []) or []
        for query in search_queries:
            citations.append({
                "query": query,
                "source_type": "search_query"
            })
            # Don't count queries toward unlinked_count as they're not sources
    
    return citations, anchored_count, unlinked_count


def _build_conversation_history(messages: List[Dict[str, str]], als_context: Dict = None) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Build conversation history preserving all messages.
    Returns: (system_instruction, conversation_messages)
    """
    system_content = None
    conversation_messages = []
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "system":
            # Combine system messages into instruction
            if system_content is None:
                system_content = content
            else:
                system_content += "\n" + content
        elif role == "user":
            # Add user message to conversation
            conversation_messages.append({
                "role": "user",
                "parts": [{"text": content}]
            })
        elif role == "assistant":
            # Add assistant message (model in Vertex)
            conversation_messages.append({
                "role": "model", 
                "parts": [{"text": content}]
            })
    
    # Add ALS block if provided to system instruction
    if als_context:
        als_block = f"\nUser location context: {als_context.get('country_code', 'unknown')}"
        if als_context.get('locale'):
            als_block += f", locale: {als_context['locale']}"
        if system_content:
            system_content = f"{system_content}\n{als_block}"
        else:
            system_content = f"You are a helpful assistant.{als_block}"
    
    # Ensure we have system content
    if not system_content:
        system_content = "You are a helpful assistant."
    
    # Ensure we have at least one message and it starts with user
    if not conversation_messages:
        raise ValueError("No user messages found")
    if conversation_messages[0]["role"] == "model":
        conversation_messages.insert(0, {
            "role": "user",
            "parts": [{"text": "Continue"}]
        })
    
    return system_content, conversation_messages


class VertexAdapter:
    """Lean Vertex adapter using SDK-managed transport."""
    
    def __init__(self):
        """Initialize with SDK client."""
        if not VERTEX_PROJECT:
            raise ValueError("VERTEX_PROJECT, GCP_PROJECT, or GOOGLE_CLOUD_PROJECT not set")
        
        # Simple SDK client initialization
        self.client = genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT,
            location=VERTEX_LOCATION
        )
        
        logger.info(f"[vertex_init] Lean adapter initialized - project: {VERTEX_PROJECT}, location: {VERTEX_LOCATION}")
    
    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete request using Vertex API."""
        start_time = time.perf_counter()
        request_id = f"req_{int(time.time()*1000)}"
        
        # Validate model
        model_id = request.model
        if not model_id.startswith("publishers/google/models/"):
            model_id = f"publishers/google/models/{model_id}"
        
        is_valid, error_msg = validate_model("vertex", model_id)
        if not is_valid:
            raise ValueError(f"Invalid Vertex model: {error_msg}")
        
        # Prepare metadata
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": "vertex",
            "model": model_id,
            "response_api": "vertex_genai",
            "request_id": request_id,
            "region": VERTEX_LOCATION
        }
        
        # Get capabilities from router
        caps = request.metadata.get("capabilities", {}) if hasattr(request, 'metadata') else {}
        
        # Build conversation history
        als_context = getattr(request, 'als_context', None)
        system_content, conversation_messages = _build_conversation_history(request.messages, als_context)
        
        # Build generation config
        max_tokens = request.max_tokens or 1024
        
        if request.grounded:
            max_tokens = min(max_tokens, VERTEX_GROUNDED_MAX_TOKENS)
        else:
            max_tokens = min(max_tokens, VERTEX_MAX_OUTPUT_TOKENS)
        
        # Safety settings
        safety_settings = [
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH
            )
        ]
        
        # Configure thinking based on router capabilities
        thinking_config = None
        if caps.get("supports_thinking_budget", False):
            # Read thinking budget from metadata (router provides it)
            thinking_budget = request.metadata.get("thinking_budget_tokens") if hasattr(request, 'metadata') else None
            include_thoughts = False
            
            # Check if include_thoughts is allowed and requested
            if caps.get("include_thoughts_allowed", False):
                if hasattr(request, 'meta') and request.meta:
                    include_thoughts = request.meta.get("include_thoughts", False)
            
            if thinking_budget is not None:
                thinking_config = ThinkingConfig(
                    thinking_budget=thinking_budget,
                    include_thoughts=include_thoughts
                )
                metadata["thinking_budget_tokens"] = thinking_budget
                metadata["include_thoughts"] = include_thoughts
        
        gen_config = GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=request.temperature if hasattr(request, 'temperature') else 0.7,
            top_p=request.top_p if hasattr(request, 'top_p') else 0.95,
            system_instruction=system_content,
            safety_settings=safety_settings,
            thinking_config=thinking_config  # Add thinking config with correct snake_case
        )
        
        # Determine if we need JSON output and how to achieve it
        json_schema_requested = False
        json_schema = None
        if hasattr(request, 'meta') and request.meta and request.meta.get('json_schema'):
            json_schema = request.meta['json_schema']
            if 'schema' in json_schema:
                json_schema_requested = True
        
        # Handle grounding and JSON mode based on combination
        grounding_mode = None
        
        if request.grounded:
            grounding_mode = request.meta.get("grounding_mode", "AUTO") if hasattr(request, 'meta') and request.meta else "AUTO"
            metadata["grounding_mode_requested"] = grounding_mode
            
            if json_schema_requested:
                # Grounded + JSON: VERTEX LIMITATION - Cannot mix GoogleSearch with function declarations
                # API Error: "Multiple tools are supported only when they are all search tools"
                # Must use two-step approach or response_schema (which may not execute search)
                
                # Option 1: Try response_schema with GoogleSearch (may not execute)
                # Option 2: Two-step - grounding first, then JSON synthesis
                
                # For now, use GoogleSearch with instruction to output JSON
                gen_config.tools = [Tool(google_search=GoogleSearch())]
                
                # Add JSON instruction to prompt
                json_inst = f"\n\nIMPORTANT: You must search for current information first, then output your response as valid JSON data (not the schema) that conforms to this structure:\n{json.dumps(json_schema['schema'], indent=2)}\n\nDo not output the schema itself - output actual data matching the schema."
                if gen_config.system_instruction:
                    gen_config.system_instruction = gen_config.system_instruction + json_inst
                else:
                    gen_config.system_instruction = json_inst
                
                metadata["web_tool_type"] = "google_search"
                metadata["grounding_with_json_instruction"] = True
                metadata["vertex_limitation"] = "cannot_mix_search_and_functions"
                metadata["grounding_mode_enforced"] = "POST_CALL"
            else:
                # Grounded without JSON: Regular grounding tools
                gen_config.tools = [Tool(google_search=GoogleSearch())]
                metadata["web_tool_type"] = "google_search"
                
                # Configure tool calling - GoogleSearch is a built-in tool, not a function
                # Both AUTO and REQUIRED modes use AUTO for tool selection
                # REQUIRED enforcement happens post-call in the router
                gen_config.tool_config = ToolConfig(
                    function_calling_config=FunctionCallingConfig(mode="AUTO")
                )
                metadata["grounding_mode_enforced"] = "POST_CALL"  # Router enforces REQUIRED
        elif json_schema_requested:
            # Ungrounded + JSON: Use JSON Mode
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema['schema']
            metadata["json_mode_active"] = True
        
        # Make single SDK call (no retry loop - SDK handles that)
        try:
            response = await self.client.aio.models.generate_content(
                model=model_id,
                contents=conversation_messages,
                config=gen_config
            )
            
            # Extract content - check for emit_result function call first
            func_name, func_args = _extract_function_call(response)
            
            # Extract content
            content = _extract_text_from_response(response)
            
            # For grounded+JSON, try to extract JSON from response
            if metadata.get("grounding_with_json_instruction"):
                # Try to find JSON in the response (may be wrapped in markdown)
                if content:
                    # Remove markdown code block if present
                    if content.strip().startswith('```json'):
                        content = content.strip()[7:]  # Remove ```json
                        if content.endswith('```'):
                            content = content[:-3]  # Remove trailing ```
                        content = content.strip()
                    elif content.strip().startswith('```'):
                        content = content.strip()[3:]  # Remove ```
                        if content.endswith('```'):
                            content = content[:-3]  # Remove trailing ```
                        content = content.strip()
                    
                    try:
                        # Validate it's proper JSON
                        json.loads(content)
                        metadata["json_extracted"] = True
                    except:
                        metadata["json_extracted"] = False
            
            # Extract citations if grounded
            citations = []
            tool_call_count = 0
            grounded_effective = False
            
            if request.grounded:
                citations, anchored_count, unlinked_count = _extract_citations_from_grounding(response)
                metadata["anchored_citations_count"] = anchored_count
                metadata["unlinked_sources_count"] = unlinked_count
                
                # Primary signal: Check grounding metadata (not function names)
                # Vertex populates grounding_metadata when GoogleSearch runs
                grounded_effective = False
                for cand in response.candidates or []:
                    grounding_meta = getattr(cand, "grounding_metadata", None)
                    if grounding_meta:
                        # Check for actual grounding evidence
                        chunks = getattr(grounding_meta, "grounding_chunks", []) or []
                        queries = getattr(grounding_meta, "search_queries", []) or []
                        if chunks or queries:
                            grounded_effective = True
                            tool_call_count = 1  # GoogleSearch ran
                            break
                
                metadata["tool_call_count"] = tool_call_count
                metadata["grounded_evidence_present"] = grounded_effective
                
                # REQUIRED mode enforcement
                if grounding_mode == "REQUIRED" and not grounded_effective:
                    metadata["why_not_grounded"] = "No GoogleSearch invoked despite REQUIRED mode"
                    raise GroundingRequiredFailedError(
                        f"REQUIRED grounding specified but no grounding evidence found. "
                        f"Tool calls: {tool_call_count}"
                    )
            else:
                # Not grounded - set citation counts to 0
                metadata["anchored_citations_count"] = 0
                metadata["unlinked_sources_count"] = 0
            
            # Extract usage with thinking tokens
            usage = {}
            if hasattr(response, 'usage_metadata'):
                usage_meta = response.usage_metadata
                usage = {
                    "prompt_tokens": getattr(usage_meta, 'prompt_token_count', 0),
                    "completion_tokens": getattr(usage_meta, 'candidates_token_count', 0),
                    "total_tokens": getattr(usage_meta, 'total_token_count', 0)
                }
                # Add thinking tokens to metadata for telemetry
                metadata["usage"] = {
                    "thoughts_token_count": getattr(usage_meta, 'thoughts_token_count', None),
                    "input_token_count": getattr(usage_meta, 'prompt_token_count', 0),
                    "output_token_count": getattr(usage_meta, 'candidates_token_count', 0),
                    "total_token_count": getattr(usage_meta, 'total_token_count', 0)
                }
            
            # Add finish reason to metadata
            if response and hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'finish_reason'):
                        metadata["finish_reason"] = str(candidate.finish_reason)
                        break
            
            # Calculate latency
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            metadata["latency_ms"] = latency_ms
            
            return LLMResponse(
                content=content,
                model_version=model_id,
                model_fingerprint=None,
                grounded_effective=grounded_effective,
                usage=usage,
                latency_ms=latency_ms,
                raw_response=None,
                success=True,
                vendor="vertex",
                model=request.model,
                metadata=metadata,
                citations=citations
            )
            
        except GroundingRequiredFailedError:
            raise
        except Exception as e:
            # Let SDK errors bubble up naturally
            logger.error(f"[vertex] API error: {str(e)[:200]}")
            raise
    
    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        # All Gemini models supported through Vertex
        return "gemini" in model.lower()