import json
import os
import time
import logging
import asyncio
from typing import Any, Dict, List
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Tool, grounding
from starlette.concurrency import run_in_threadpool

from app.llm.types import LLMRequest, LLMResponse
from .grounding_detection_helpers import detect_vertex_grounding

# --- Proxy support removed ---
# All proxy functionality has been disabled via DISABLE_PROXIES=true
# Locale/region is now handled via API parameters, not network egress
# --- end proxy removal ---

logger = logging.getLogger(__name__)

def _extract_vertex_usage(resp: Any) -> Dict[str, int]:
    """Return prompt/completion/total token counts, defaulting to 0."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # 1) Newer Generative API: resp.usage_metadata is an object with attributes
    meta = getattr(resp, "usage_metadata", None)
    if meta:
        for src, dst in [
            ("prompt_token_count", "prompt_tokens"),
            ("candidates_token_count", "completion_tokens"),
            ("total_token_count", "total_tokens"),
        ]:
            val = getattr(meta, src, None)
            if val:
                usage[dst] = int(val)

    # 2) Older LLM API: resp._prediction_response has a 'metadata' dict
    #    with 'tokenMetadata' containing 'inputTokenCount' / 'outputTokenCount'
    pred_resp = getattr(resp, "_prediction_response", None)
    if pred_resp:
        pred_meta = getattr(pred_resp, "metadata", {})
        token_data = pred_meta.get("tokenMetadata", {})
        inp = token_data.get("inputTokenCount", {})
        out = token_data.get("outputTokenCount", {})

        input_tokens = 0
        if isinstance(inp, dict):
            input_tokens = inp.get("totalTokens", 0)
        elif isinstance(inp, int):
            input_tokens = inp

        output_tokens = 0
        if isinstance(out, dict):
            output_tokens = out.get("totalTokens", 0)
        elif isinstance(out, int):
            output_tokens = out

        if input_tokens or output_tokens:
            usage["prompt_tokens"] = input_tokens
            usage["completion_tokens"] = output_tokens
            usage["total_tokens"] = input_tokens + output_tokens

    return usage


def _extract_text_from_candidates(resp: Any) -> str:
    """Return the concatenated text from resp.candidates or resp.text, defaulting to ''."""
    
    # First, try resp.text (simple shortcut)
    if hasattr(resp, 'text'):
        try:
            txt = resp.text  # This may raise on safety filters
            if txt:
                return txt.strip()
        except Exception as e:
            # Log safety filter or other errors
            logger.warning(f"Failed to get resp.text: {e}")

    # Second, try to collect from all candidates
    collected = []
    candidates = getattr(resp, 'candidates', [])
    for candidate in candidates:
        # Try candidate.text (newer API)
        if hasattr(candidate, 'text'):
            txt = getattr(candidate, 'text', '')
            if txt:
                collected.append(txt)
            continue
            
        # Try candidate.content.parts (current API)
        if hasattr(candidate, 'content'):
            content = candidate.content
            if hasattr(content, 'parts'):
                for part in content.parts:
                    if hasattr(part, 'text'):
                        txt = getattr(part, 'text', '')
                        if txt:
                            collected.append(txt)

    if collected:
        return "\n".join(collected).strip()

    # No text found
    return ""


class VertexAdapter:
    """
    Vertex AI adapter for Gemini models with grounding support.
    Proxies have been disabled - all requests go direct.
    """
    
    def __init__(self):
        # Initialize Vertex AI with project and location from env
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", "contestra-ai")
        self.location = os.getenv("VERTEX_LOCATION", "europe-west4")
        
        # Initialize once for the process
        vertexai.init(project=self.project, location=self.location)
        
        # Model allowlist
        self.allowlist = {
            # Newer models with grounding support
            "gemini-2.5-pro",
            "gemini-2.0-flash-exp",
            "gemini-exp-1206",
            # Legacy models (may not support grounding)
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.0-pro",
            "gemini-pro",
        }
        
        logger.info("Vertex adapter initialized: project=%s location=%s", self.project, self.location)
        # Ensure metadata endpoints are never proxied (safe on any platform)
        os.environ.setdefault("NO_PROXY", "metadata.google.internal,169.254.169.254,localhost,127.0.0.1")
    
    def _is_structured_output(self, req) -> bool:
        """Check if request wants JSON/structured output"""
        # Check response_format
        rf = getattr(req, 'response_format', None)
        if rf and isinstance(rf, dict):
            if rf.get('type') == 'json_object':
                return True
        # Check messages for JSON instruction
        messages = getattr(req, 'messages', [])
        for msg in messages:
            content = msg.get('content', '').lower()
            if 'json' in content and ('format' in content or 'output' in content):
                return True
        return False
    
    def _create_generation_config(self, req: LLMRequest) -> GenerationConfig:
        """Create generation config from request parameters"""
        config_dict = {}
        
        # Map common parameters
        if hasattr(req, 'temperature') and req.temperature is not None:
            config_dict['temperature'] = float(req.temperature)
        if hasattr(req, 'max_tokens') and req.max_tokens:
            config_dict['max_output_tokens'] = int(req.max_tokens)
        if hasattr(req, 'top_p') and req.top_p is not None:
            config_dict['top_p'] = float(req.top_p)
        
        # Handle structured output
        if self._is_structured_output(req):
            config_dict['response_mime_type'] = 'application/json'
            logger.info("Vertex: Structured output requested, setting response_mime_type=application/json")
        
        return GenerationConfig(**config_dict) if config_dict else None
    
    def _create_grounding_tools(self) -> List[Tool]:
        """Create grounding tools for Google Search"""
        try:
            google_search_tool = Tool.from_google_search_retrieval(
                google_search_retrieval=grounding.GoogleSearchRetrieval()
            )
            return [google_search_tool]
        except Exception as e:
            logger.warning(f"Failed to create grounding tools: {e}")
            return []
    
    async def _complete_with_genai(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete using Google GenAI SDK with grounding support (proxies disabled)"""
        from google import genai
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool as GenAITool, HttpOptions
        
        t0 = time.perf_counter()
        
        # Initialize tracking variables for logging/telemetry
        vantage_policy = str(getattr(req, 'vantage_policy', 'NONE')).upper().replace("VANTAGEPOLICY.", "")
        metadata = {
            "proxies_enabled": False,
            "proxy_mode": "disabled"
        }
        
        # Build HTTP options without proxy
        http_options = HttpOptions(api_version="v1")
        
        # [LLM_ROUTE] Log before API call
        route_info = {
            "vendor": "vertex_genai",
            "model": getattr(req, "model", "gemini-2.5-pro"),
            "vantage_policy": vantage_policy,
            "proxy_mode": "disabled",
            "grounded": req.grounded,
            "max_tokens": getattr(req, "max_tokens", 6000),
            "timeouts_s": {"connect": 30, "read": 60, "total": timeout}
        }
        logger.info(f"[LLM_ROUTE] {json.dumps(route_info)}")
        
        # Create GenAI client with custom HTTP options
        try:
            client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                http_options=http_options
            )
        finally:
            # No proxy env vars to clean up anymore
            pass
        
        # Get model name
        raw_model = getattr(req, "model", None) or "gemini-2.5-pro"
        model_name = raw_model.replace("gemini-2.5", "gemini-2.0") if "gemini-2.5" in raw_model else raw_model
        
        # Build generation config
        config = GenerateContentConfig(
            temperature=getattr(req, "temperature", 0.7),
            top_p=getattr(req, "top_p", 0.95),
            max_output_tokens=getattr(req, "max_tokens", 6000),
            response_modalities=["TEXT"]
        )
        
        # Handle structured output
        is_structured = self._is_structured_output(req)
        if is_structured:
            config.response_mime_type = "application/json"
            logger.info("GenAI: Structured output requested, setting response_mime_type=application/json")
        
        # Build contents from messages
        contents = []
        for msg in req.messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if text:
                # GenAI SDK expects "user" or "model" roles
                if role == "system":
                    # Prepend system message to first user message
                    if contents and contents[0].get("role") == "user":
                        contents[0]["parts"][0]["text"] = f"{text}\n\n{contents[0]['parts'][0]['text']}"
                    else:
                        contents.insert(0, {"role": "user", "parts": [{"text": text}]})
                elif role == "assistant":
                    contents.append({"role": "model", "parts": [{"text": text}]})
                else:  # user
                    contents.append({"role": "user", "parts": [{"text": text}]})
        
        # Build tools for grounding if requested
        tools = []
        if req.grounded:
            # IMPORTANT: JSON output and grounding cannot be used together
            if is_structured:
                logger.warning("Vertex GenAI: Cannot use grounding with structured output - disabling grounding")
                req.grounded = False
            else:
                google_search_tool = GenAITool(google_search=GoogleSearch())
                tools.append(google_search_tool)
                logger.info("GenAI grounding enabled with GoogleSearch tool")
        
        try:
            # Call the API with timeout
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                    tools=tools if tools else None
                ),
                timeout=timeout
            )
            
            # Extract text and usage
            text = _extract_text_from_candidates(response)
            usage = _extract_vertex_usage(response)
            
            # Check if grounding was actually used
            grounded_effective = detect_vertex_grounding(response) if req.grounded else False
            
            # Populate metadata
            metadata["vantage_policy"] = vantage_policy
            metadata["proxies_enabled"] = False
            metadata["proxy_mode"] = "disabled"
            metadata["timeouts_s"] = {
                "connect": 30,
                "read": 60,
                "total": timeout
            }
            
            # [LLM_RESULT] Log successful response
            result_info = {
                "vendor": "vertex_genai",
                "model": model_name,
                "vantage_policy": vantage_policy,
                "proxy_mode": "disabled",
                "grounded": req.grounded,
                "grounded_effective": grounded_effective,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "usage": usage,
                "content_length": len(text) if text else 0
            }
            logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
            
            return LLMResponse(
                content=text,
                model_version=model_name,
                model_fingerprint=f"vertex-genai-{model_name}",
                grounded_effective=grounded_effective,
                usage=usage,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                raw_response=response,
                metadata=metadata
            )
            
        except asyncio.TimeoutError:
            logger.error(f"GenAI timeout after {timeout}s")
            # [LLM_RESULT] Log timeout
            result_info = {
                "vendor": "vertex_genai",
                "model": model_name,
                "vantage_policy": vantage_policy,
                "proxy_mode": "disabled",
                "grounded": req.grounded,
                "grounded_effective": False,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error": f"TIMEOUT after {timeout}s",
                "content_length": 0
            }
            logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
            raise
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Main entry point for Vertex adapter with proxy support removed"""
        
        # Determine if we need the GenAI SDK path
        use_genai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"
        
        # Route to GenAI SDK if grounding (proxies no longer supported)
        if use_genai and req.grounded:
            logger.info("Using Google GenAI SDK for grounded request")
            return await self._complete_with_genai(req, timeout)
        
        # Use standard Vertex SDK path (no proxy support)
        t0 = time.perf_counter()
        
        # Initialize tracking variables for logging/telemetry
        vantage_policy = str(getattr(req, 'vantage_policy', 'NONE')).upper().replace("VANTAGEPOLICY.", "")
        metadata = {
            "proxies_enabled": False,
            "proxy_mode": "disabled"
        }
        
        # Get model name
        raw_model = getattr(req, "model", None) or "gemini-1.5-pro"
        # Handle model name normalization
        model_name = raw_model
        if "gemini-2.5" in raw_model:
            model_name = raw_model.replace("gemini-2.5", "gemini-2.0")
            logger.info(f"Normalized model name: {raw_model} -> {model_name}")
        
        # [LLM_ROUTE] Log before API call
        route_info = {
            "vendor": "vertex",
            "model": model_name,
            "vantage_policy": vantage_policy,
            "proxy_mode": "disabled",
            "grounded": req.grounded,
            "max_tokens": getattr(req, "max_tokens", 6000),
            "timeouts_s": {"connect": 30, "read": 60, "total": timeout}
        }
        logger.info(f"[LLM_ROUTE] {json.dumps(route_info)}")
        
        # Create model
        model = GenerativeModel(model_name)
        
        # Create generation config
        generation_config = self._create_generation_config(req)
        
        # Build contents from messages
        contents = []
        for msg in req.messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if text:
                # Vertex expects "user" or "model" roles
                if role == "system":
                    # Prepend system message to first user message
                    if contents and contents[0]["role"] == "user":
                        contents[0]["parts"][0].text = f"{text}\n\n{contents[0]['parts'][0].text}"
                    else:
                        contents.insert(0, {"role": "user", "parts": [text]})
                elif role == "assistant":
                    contents.append({"role": "model", "parts": [text]})
                else:  # user
                    contents.append({"role": "user", "parts": [text]})
        
        # Create grounding tools if requested
        tools = []
        is_structured = self._is_structured_output(req)
        
        if req.grounded:
            # Check for incompatible combination
            if is_structured:
                logger.warning("Vertex: Cannot use grounding with structured output (JSON mode) - disabling grounding")
                req.grounded = False
            else:
                tools = self._create_grounding_tools()
                if tools:
                    logger.info("Vertex grounding enabled with %d tool(s)", len(tools))
        
        # Call Vertex with timeout (no proxy context needed)
        try:
            # Enforce per-call timeout via asyncio
            resp = await asyncio.wait_for(
                run_in_threadpool(
                    model.generate_content,
                    contents=contents,
                    generation_config=generation_config,
                    tools=tools if tools else None
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - t0
            logger.error(
                "[VERTEX_TIMEOUT] Request timed out after %.2fs (limit=%ds). Model=%s, grounded=%s",
                elapsed, timeout, model_name, req.grounded
            )
            # [LLM_RESULT] Log timeout
            result_info = {
                "vendor": "vertex",
                "model": model_name,
                "vantage_policy": vantage_policy,
                "proxy_mode": "disabled",
                "grounded": req.grounded,
                "grounded_effective": False,
                "latency_ms": int(elapsed * 1000),
                "error": f"TIMEOUT after {timeout}s",
                "content_length": 0
            }
            logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
            raise TimeoutError(f"Vertex request timed out after {timeout} seconds")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(
                "[VERTEX_ERROR] Request failed after %.2fs. Model=%s, error=%s",
                elapsed, model_name, str(e)
            )
            raise
        
        # Extract response
        text = _extract_text_from_candidates(resp)
        usage = _extract_vertex_usage(resp)
        
        # Check if grounding was effective
        grounded_effective = detect_vertex_grounding(resp) if req.grounded else False
        
        # Log if grounding was requested but not effective
        if req.grounded and not grounded_effective:
            logger.warning(
                "Vertex grounding requested but not detected in response. Model=%s",
                model_name
            )
        
        # Add telemetry metadata
        metadata["vantage_policy"] = vantage_policy
        metadata["proxies_enabled"] = False
        metadata["proxy_mode"] = "disabled"
        
        # [LLM_RESULT] Log successful response
        result_info = {
            "vendor": "vertex",
            "model": model_name,
            "vantage_policy": vantage_policy,
            "proxy_mode": "disabled",
            "grounded": req.grounded,
            "grounded_effective": grounded_effective,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "usage": usage,
            "content_length": len(text) if text else 0
        }
        logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
        
        return LLMResponse(
            content=text,
            model_version=model_name,
            model_fingerprint=f"vertex-{model_name}-{self.location}",
            grounded_effective=grounded_effective,
            usage=usage,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            raw_response=resp,
            metadata=metadata
        )