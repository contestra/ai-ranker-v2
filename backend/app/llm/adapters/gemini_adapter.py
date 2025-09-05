"""
Lean Gemini Direct adapter - shape conversion, policy enforcement, and telemetry only.
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
GEMINI_GROUNDED_MAX_TOKENS = int(os.getenv("GEMINI_GROUNDED_MAX_TOKENS", "6000"))


def _get_registrable_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        p = urlparse(url)
        domain = p.netloc.lower().replace("www.", "")
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
    """Extract text from Gemini response."""
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


def _detect_als_position(messages: List[Dict[str, str]], als_country: Optional[str]) -> int:
    """Detect ALS position in messages array."""
    if not als_country:
        return -1
    
    for i, msg in enumerate(messages):
        content = msg.get("content", "").lower()
        if als_country.lower() in content and i == 0:
            return 0
    return -1


def _extract_system_and_user_messages(messages: List[Dict[str, str]], als_position: int = -1) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Extract system instruction and format messages for Gemini API preserving full history.
    Returns: (system_instruction, conversation_messages)
    """
    system_content = None
    conversation_messages = []
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "system":
            # Combine all system messages into system instruction
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
            # Add assistant message to conversation (model in Gemini)
            conversation_messages.append({
                "role": "model",
                "parts": [{"text": content}]
            })
    
    # Ensure conversation starts with user (Gemini requirement)
    # If first message is model/assistant, prepend a minimal user message
    if conversation_messages and conversation_messages[0]["role"] == "model":
        conversation_messages.insert(0, {
            "role": "user",
            "parts": [{"text": "Continue"}]
        })
    
    return system_content, conversation_messages


class GeminiAdapter:
    """Lean Gemini Direct adapter using SDK-managed transport."""
    
    def __init__(self):
        """Initialize with SDK client."""
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY not set")
        
        # Simple SDK client initialization
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        
        logger.info("[gemini_direct_init] Lean adapter initialized")
    
    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete request using Gemini Direct API."""
        start_time = time.perf_counter()
        request_id = f"req_{int(time.time()*1000)}"
        
        # Validate model
        model_id = request.model
        if model_id.startswith("models/"):
            model_id = model_id.replace("models/", "")
        elif model_id.startswith("publishers/google/models/"):
            model_id = model_id.replace("publishers/google/models/", "")
        
        # Note: Flash models are allowed through Gemini Direct API
        # The router will handle policy decisions about which models to use
        
        is_valid, error_msg = validate_model("gemini_direct", f"publishers/google/models/{model_id}")
        if not is_valid:
            raise ValueError(f"Invalid Gemini model: {error_msg}")
        
        # Prepare metadata
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": "gemini_direct",
            "model": f"models/{model_id}",
            "response_api": "gemini_genai",
            "request_id": request_id
        }
        
        # Get capabilities from router
        caps = request.metadata.get("capabilities", {}) if hasattr(request, 'metadata') else {}
        
        # Detect ALS position
        als_country = None
        if hasattr(request, 'metadata') and request.metadata:
            als_country = request.metadata.get('als_country')
        als_position = _detect_als_position(request.messages, als_country)
        
        # Extract system instruction and user messages
        system_instruction, conversation_messages = _extract_system_and_user_messages(request.messages, als_position)
        
        # Build generation config
        max_tokens = request.max_tokens or 1024
        
        if request.grounded:
            max_tokens = min(max_tokens, GEMINI_GROUNDED_MAX_TOKENS)
        else:
            max_tokens = min(max_tokens, GEMINI_MAX_OUTPUT_TOKENS)
        
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
            response_mime_type="text/plain",
            safety_settings=safety_settings,
            system_instruction=system_instruction,  # Add system instruction to config
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
                # Grounded + JSON: Use FFC (schema-as-tool) with GoogleSearch
                # Create function declaration for the JSON schema
                emit_result_func = FunctionDeclaration(
                    name="emit_result",
                    description="Emit the structured result in the requested format",
                    parameters=json_schema['schema']
                )
                
                # Add both GoogleSearch and emit_result tools
                gen_config.tools = [
                    Tool(google_search=GoogleSearch()),
                    Tool(function_declarations=[emit_result_func])
                ]
                metadata["web_tool_type"] = "google_search"
                metadata["schema_tool_present"] = True
                
                # Force the model to call emit_result
                gen_config.tool_config = ToolConfig(
                    function_calling_config=FunctionCallingConfig(
                        mode="ANY",
                        allowed_function_names=["emit_result"]
                    )
                )
                metadata["grounding_mode_enforced"] = "FFC_ANY_with_schema"
            else:
                # Grounded without JSON: Regular grounding tools
                gen_config.tools = [Tool(google_search=GoogleSearch())]
                metadata["web_tool_type"] = "google_search"
                
                # Configure tool calling based on mode
                if grounding_mode == "REQUIRED":
                    # Force tool usage for REQUIRED mode
                    # Note: GoogleSearch doesn't support function_calling_config
                    # The model will be forced to use it through instruction
                    metadata["grounding_mode_enforced"] = "REQUIRED"
                # For AUTO mode, tool use is optional (default behavior)
        elif json_schema_requested:
            # Ungrounded + JSON: Use JSON Mode
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema['schema']
            metadata["json_mode_active"] = True
        
        # Make single SDK call
        try:
            response = await self.client.aio.models.generate_content(
                model=f"models/{model_id}",
                contents=conversation_messages,
                config=gen_config
            )
            
            # Extract content - check for emit_result function call first
            func_name, func_args = _extract_function_call(response)
            
            if func_name == "emit_result" and func_args:
                # Grounded + JSON case: extract structured data from function args
                content = json.dumps(func_args) if isinstance(func_args, dict) else str(func_args)
                metadata["schema_tool_invoked"] = True
            else:
                # Regular text extraction
                content = _extract_text_from_response(response)
                metadata["schema_tool_invoked"] = False
            
            # Extract citations if grounded
            citations = []
            tool_call_count = 0
            grounded_effective = False
            
            if request.grounded:
                citations, anchored_count, unlinked_count = _extract_citations_from_grounding(response)
                metadata["anchored_citations_count"] = anchored_count
                metadata["unlinked_sources_count"] = unlinked_count
                
                # Primary signal for Google grounding: grounding_metadata
                for cand in response.candidates or []:
                    grounding_meta = getattr(cand, "grounding_metadata", None)
                    if grounding_meta:
                        chunks = getattr(grounding_meta, "grounding_chunks", []) or []
                        queries = getattr(grounding_meta, "search_queries", []) or []
                        if chunks or queries:
                            tool_call_count = 1
                            grounded_effective = True
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
                model_version=f"models/{model_id}",
                model_fingerprint=None,
                grounded_effective=grounded_effective,
                usage=usage,
                latency_ms=latency_ms,
                raw_response=None,
                success=True,
                vendor="gemini_direct",
                model=request.model,
                metadata=metadata,
                citations=citations
            )
            
        except GroundingRequiredFailedError:
            raise
        except Exception as e:
            # Let SDK errors bubble up naturally
            logger.error(f"[gemini_direct] API error: {str(e)[:200]}")
            raise
    
    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        # All Gemini models supported through Direct API
        return "gemini" in model.lower()