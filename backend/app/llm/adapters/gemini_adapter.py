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
    Tool, ToolConfig
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


def _extract_citations_from_grounding(response) -> List[Dict[str, Any]]:
    """Extract citations from grounding metadata."""
    citations = []
    
    if not response or not getattr(response, "candidates", None):
        return citations
    
    for cand in response.candidates or []:
        grounding_metadata = getattr(cand, "grounding_metadata", None)
        if not grounding_metadata:
            continue
            
        # Extract grounding_chunks (web search results)
        grounding_chunks = getattr(grounding_metadata, "grounding_chunks", [])
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
        
        # Extract search_queries (what was searched)
        search_queries = getattr(grounding_metadata, "search_queries", [])
        for query in search_queries:
            citations.append({
                "query": query,
                "source_type": "search_query"
            })
    
    return citations


def _detect_als_position(messages: List[Dict[str, str]], als_country: Optional[str]) -> int:
    """Detect ALS position in messages array."""
    if not als_country:
        return -1
    
    for i, msg in enumerate(messages):
        content = msg.get("content", "").lower()
        if als_country.lower() in content and i == 0:
            return 0
    return -1


def _shape_messages_for_gemini(messages: List[Dict[str, str]], als_position: int = -1) -> List[Dict[str, Any]]:
    """Shape messages for Gemini API (system + user only)."""
    system_content = None
    user_content = None
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "system":
            if system_content is None:
                system_content = content
            else:
                system_content += "\n" + content
        elif role == "user":
            if als_position == 0 and i == 0:
                # This is the ALS block
                if user_content is None:
                    user_content = content
                else:
                    user_content = content + "\n\n" + user_content
            else:
                if user_content is None:
                    user_content = content
                else:
                    user_content += "\n" + content
    
    # Build final messages
    result = []
    if system_content:
        result.append({
            "role": "user",
            "parts": [{"text": f"System: {system_content}"}]
        })
    
    if user_content:
        if result:
            # If we have system message, append user as second turn
            result.append({
                "role": "model",
                "parts": [{"text": "I understand the system instructions. How can I help you?"}]
            })
        result.append({
            "role": "user",
            "parts": [{"text": user_content}]
        })
    
    return result


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
        
        # Shape messages for Gemini
        shaped_messages = _shape_messages_for_gemini(request.messages, als_position)
        
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
        
        gen_config = GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=request.temperature if hasattr(request, 'temperature') else 0.7,
            top_p=request.top_p if hasattr(request, 'top_p') else 0.95,
            response_mime_type="text/plain",
            safety_settings=safety_settings
        )
        
        # Add thinking configuration if supported
        if caps.get("supports_thinking_budget"):
            thinking_budget = request.meta.get("thinking_budget") if hasattr(request, 'meta') and request.meta else None
            if thinking_budget is not None:
                # Note: Gemini SDK doesn't have direct thinking budget yet
                # This is placeholder for when SDK adds support
                metadata["thinking_budget_requested"] = thinking_budget
        
        if caps.get("include_thoughts_allowed"):
            include_thoughts = request.meta.get("include_thoughts", False) if hasattr(request, 'meta') and request.meta else False
            if include_thoughts:
                metadata["include_thoughts_requested"] = True
        
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
                    # Force function calling for REQUIRED mode
                    gen_config.tool_config = ToolConfig(
                        function_calling_config=FunctionCallingConfig(
                            mode="ANY",
                            allowed_function_names=["google_search"]
                        )
                    )
                    metadata["grounding_mode_enforced"] = "FFC_ANY"
                else:
                    # AUTO mode - let model decide
                    gen_config.tool_config = ToolConfig(
                        function_calling_config=FunctionCallingConfig(mode="AUTO")
                    )
        elif json_schema_requested:
            # Ungrounded + JSON: Use JSON Mode
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema['schema']
            metadata["json_mode_active"] = True
        
        # Make single SDK call
        try:
            response = await self.client.aio.models.generate_content(
                model=f"models/{model_id}",
                contents=shaped_messages,
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
                citations = _extract_citations_from_grounding(response)
                
                # Check for GoogleSearch invocation
                if func_name == "google_search":
                    tool_call_count = 1
                    grounded_effective = True
                
                # Also check grounding metadata
                if not grounded_effective:
                    for cand in response.candidates or []:
                        if getattr(cand, "grounding_metadata", None):
                            chunks = getattr(cand.grounding_metadata, "grounding_chunks", [])
                            if chunks:
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
            
            # Extract usage
            usage = {}
            if hasattr(response, 'usage_metadata'):
                usage_meta = response.usage_metadata
                usage = {
                    "prompt_tokens": getattr(usage_meta, 'prompt_token_count', 0),
                    "completion_tokens": getattr(usage_meta, 'candidates_token_count', 0),
                    "total_tokens": getattr(usage_meta, 'total_token_count', 0)
                }
            
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