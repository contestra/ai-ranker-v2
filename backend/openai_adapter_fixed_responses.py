"""
OpenAI Adapter with proper Responses API implementation for web search.
"""
import asyncio
import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.llm.errors import GroundingRequiredFailedError
from app.llm.models import OPENAI_ALLOWED_MODELS, validate_model
from app.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)
settings = get_settings()

# Environment-based isolation flags
DISABLE_LIMITER = os.getenv("OAI_DISABLE_LIMITER", "0") == "1"
DISABLE_CUSTOM_SESSION = os.getenv("OAI_DISABLE_CUSTOM_SESSION", "0") == "1"
DISABLE_STREAMING = os.getenv("OAI_DISABLE_STREAMING", "0") == "1"

# Default max tokens for grounded runs
GROUNDED_MAX_TOKENS = int(os.getenv("OAI_GROUNDED_MAX_TOKENS", "6000"))

# Circuit breaker state
@dataclass
class CircuitBreakerState:
    """Circuit breaker state for a specific vendor+model combination."""
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "closed"  # closed, open, half-open
    open_until: Optional[datetime] = None
    consecutive_429: int = 0
    consecutive_503: int = 0
    total_503_count: int = 0
    total_429_count: int = 0

# Global circuit breaker states
_circuit_breakers: Dict[str, CircuitBreakerState] = {}

# Health check cache
_health_check_done = False
_health_check_success = False


class SimplifiedRateLimiter:
    """Simplified rate limiter with deadlock protection."""
    
    def __init__(self):
        self._enabled = not DISABLE_LIMITER and settings.openai_gate_in_adapter
        self._sem = None
        if self._enabled:
            max_concurrency = max(1, settings.openai_max_concurrency)
            self._sem = asyncio.Semaphore(max_concurrency)
            logger.info(f"[OAI_RL] Rate limiter enabled with {max_concurrency} concurrent slots")
        else:
            logger.info("[OAI_RL] Rate limiter disabled")
    
    async def acquire_with_timeout(self, timeout_sec: float = 1.0):
        """Acquire permit with timeout to prevent deadlock."""
        if not self._enabled or not self._sem:
            return None
            
        try:
            # Try to acquire with timeout
            await asyncio.wait_for(self._sem.acquire(), timeout=timeout_sec)
            return self._sem
        except asyncio.TimeoutError:
            logger.warning(f"[OAI_RL] Failed to acquire permit within {timeout_sec}s, bypassing limiter")
            return None
    
    def release(self, sem):
        """Release permit if acquired."""
        if sem:
            try:
                sem.release()
            except Exception as e:
                logger.warning(f"[OAI_RL] Failed to release permit: {e}")


# Global rate limiter instance
_RL = SimplifiedRateLimiter()


class OpenAIAdapter:
    """OpenAI adapter with proper Responses API and timeout fixes."""
    
    def __init__(self):
        # API Key required
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY required - set in backend/.env")
        
        # Log isolation flags
        logger.info(f"[OAI_INIT] Isolation flags: LIMITER={not DISABLE_LIMITER}, CUSTOM_SESSION={not DISABLE_CUSTOM_SESSION}, STREAMING={not DISABLE_STREAMING}")
        
        # Configure timeouts
        connect_s = float(os.getenv("OPENAI_CONNECT_TIMEOUT_MS", "2000")) / 1000.0
        read_s = float(os.getenv("OPENAI_READ_TIMEOUT_MS", "60000")) / 1000.0
        
        # Create client
        if DISABLE_CUSTOM_SESSION:
            # Use SDK defaults
            self.client = AsyncOpenAI(api_key=api_key)
            logger.info("[OAI_INIT] Using SDK default HTTP client")
        else:
            # Custom timeout config
            self.client = AsyncOpenAI(
                api_key=api_key,
                timeout=httpx.Timeout(
                    connect=connect_s,
                    read=read_s,
                    write=read_s,
                    pool=read_s
                )
            )
            logger.info(f"[OAI_INIT] Custom timeouts: connect={connect_s}s, read={read_s}s")
        
        # Log base URL and proxy settings
        base_url = self.client.base_url
        http_proxy = os.getenv("HTTP_PROXY", "")
        https_proxy = os.getenv("HTTPS_PROXY", "")
        logger.info(f"[OAI_INIT] Base URL: {base_url}, HTTP_PROXY={'set' if http_proxy else 'unset'}, HTTPS_PROXY={'set' if https_proxy else 'unset'}")
        
        # Model allowlist
        self.allowlist = OPENAI_ALLOWED_MODELS
        
    async def _health_check(self):
        """One-time health check with 5s timeout."""
        global _health_check_done, _health_check_success
        
        if _health_check_done:
            return _health_check_success
        
        _health_check_done = True
        
        try:
            # Simple health ping - list models with 5s timeout
            await asyncio.wait_for(
                self.client.models.list(),
                timeout=5.0
            )
            _health_check_success = True
            logger.info("[OAI_HEALTH] Health check passed")
            return True
        except Exception as e:
            _health_check_success = False
            logger.error(f"[OAI_HEALTH] Health check failed: {str(e)[:100]}")
            return False
    
    def _detect_als_position(self, messages: List[Dict]) -> Tuple[bool, str]:
        """Detect ALS presence and position in messages."""
        als_indicators = ["de-DE", "Germany", "Deutschland", "Europe/Berlin", "metric units"]
        
        for msg in messages:
            content = str(msg.get("content", ""))
            if any(indicator in content for indicator in als_indicators):
                role = msg.get("role", "")
                return True, role
        
        return False, "absent"
    
    def _map_grounded_model(self, model: str) -> str:
        """Map chat models to responses-capable models for grounded runs."""
        # If it's a chat variant, map to reasoning model for grounded runs
        if "chat" in model.lower():
            # Map gpt-5-chat-* to gpt-5-* 
            return model.replace("-chat", "")
        return model
    
    def _should_use_responses_api(self, model: str, is_grounded: bool) -> bool:
        """Determine if should use Responses API."""
        # Always use Responses API for grounded GPT-5 runs
        if "gpt-5" in model.lower() and is_grounded:
            return True
        # Non-grounded GPT-5 can use chat completions
        return False
    
    def _extract_tool_evidence(self, response: Any) -> Tuple[int, List[str]]:
        """Extract tool call evidence from Responses API output."""
        tool_count = 0
        tool_types = []
        
        if not response:
            return 0, []
        
        # Parse Responses API output structure
        if hasattr(response, 'output'):
            output = response.output
            if isinstance(output, list):
                for item in output:
                    if hasattr(item, 'type'):
                        item_type = item.type
                        if 'web_search' in item_type or 'web_search_call' in item_type:
                            tool_count += 1
                            tool_types.append(item_type)
        
        return tool_count, tool_types
    
    def _build_responses_payload(self, request: LLMRequest, system_content: str, user_content: str, 
                                  grounding_mode: str, json_schema: Optional[Dict] = None) -> Dict:
        """Build proper Responses API payload with tools."""
        # Base payload
        payload = {
            "model": request.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_content}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_content}]}
            ],
            "temperature": request.temperature or 0.7,
            "max_output_tokens": GROUNDED_MAX_TOKENS  # Always 6000 for grounded runs
        }
        
        # Add web search tool
        payload["tools"] = [{"type": "web_search"}]  # Will fall back to web_search_preview if needed
        
        # Set tool_choice based on grounding mode
        if grounding_mode == "REQUIRED":
            payload["tool_choice"] = "required"
        else:
            payload["tool_choice"] = "auto"
        
        # Add strict JSON schema if provided
        if json_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.get("name", "Output"),
                    "schema": json_schema.get("schema", {}),
                    "strict": True
                }
            }
        
        return payload
    
    async def _call_responses_api(self, payload: Dict, timeout: int) -> Any:
        """Call the actual Responses API endpoint."""
        # First try with web_search tool
        try:
            response = await self.client.beta.responses.create(**payload, timeout=timeout)
            return response, "web_search"
        except Exception as e:
            error_str = str(e)
            # If web_search unsupported, try web_search_preview
            if "unsupported" in error_str.lower() or "400" in error_str:
                logger.info("[OAI_RESPONSES] web_search unsupported, falling back to web_search_preview")
                payload["tools"] = [{"type": "web_search_preview"}]
                response = await self.client.beta.responses.create(**payload, timeout=timeout)
                return response, "web_search_preview"
            raise
    
    async def _call_with_streaming(self, params: Dict) -> Any:
        """Call with streaming and proper chunk concatenation."""
        try:
            # Create streaming response
            stream = await self.client.chat.completions.create(**params, stream=True)
            
            # Concatenate all chunks
            full_content = []
            last_chunk = None
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    full_content.append(chunk.choices[0].delta.content)
                last_chunk = chunk
            
            # Build final response with concatenated content
            if last_chunk and full_content:
                # Create a synthetic response with full content
                if last_chunk.choices:
                    last_chunk.choices[0].message.content = ''.join(full_content)
                return last_chunk
            
            raise RuntimeError("No chunks received from streaming")
            
        except Exception as e:
            logger.error(f"[OAI_STREAM] Streaming error: {str(e)[:100]}")
            raise
    
    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete with proper Responses API for grounded runs."""
        # Use monotonic clock for accurate timing
        start_time = time.perf_counter()
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": "openai",
            "model": request.model,
            "original_model": request.model
        }
        
        # Health check first
        if not await self._health_check():
            raise RuntimeError("[OAI] API health check failed - aborting to prevent hang")
        
        # Validate model
        ok, msg = validate_model("openai", request.model)
        if not ok:
            raise ValueError(f"Invalid/unsupported OpenAI model: {msg}")
        
        # Check if grounded
        is_grounded = request.grounded
        grounding_mode = request.meta.get("grounding_mode", "AUTO") if request.meta else "AUTO"
        metadata["grounding_mode"] = grounding_mode
        
        # Map model for grounded runs
        effective_model = request.model
        if is_grounded:
            effective_model = self._map_grounded_model(request.model)
            if effective_model != request.model:
                metadata["effective_model"] = effective_model
                logger.info(f"[OAI] Mapped {request.model} -> {effective_model} for grounded run")
        
        # Determine endpoint
        use_responses = self._should_use_responses_api(effective_model, is_grounded)
        endpoint = "responses" if use_responses else "chat.completions"
        metadata["response_api"] = "responses_http" if use_responses else "chat_completions"
        
        # ALS detection
        als_present, als_position = self._detect_als_position(request.messages)
        metadata["als_present"] = als_present
        metadata["als_position"] = als_position
        
        # Build messages
        system_content = ""
        user_content = ""
        for msg in request.messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            elif msg["role"] == "user":
                user_content = msg["content"]
        
        # Forward timeout to SDK
        sdk_timeout = min(timeout, 120)  # Cap at 2 minutes for SDK
        
        # Log telemetry line
        logger.info(
            f"[OAI_CALL] endpoint={endpoint} model={effective_model} "
            f"timeout_forwarded={sdk_timeout}s limiter={'bypassed' if DISABLE_LIMITER else 'used'} "
            f"streaming={'off' if DISABLE_STREAMING or use_responses else 'on'} "
            f"grounded={is_grounded} mode={grounding_mode} base_url={self.client.base_url}"
        )
        
        # Acquire rate limiter permit with timeout
        permit = None
        try:
            permit = await _RL.acquire_with_timeout(timeout_sec=1.0)
            
            if use_responses and is_grounded:
                # Build proper Responses API payload
                json_schema = request.meta.get("json_schema") if request.meta else None
                payload = self._build_responses_payload(
                    request, system_content, user_content, 
                    grounding_mode, json_schema
                )
                payload["model"] = effective_model
                
                # Call Responses API with tool variant negotiation
                response, web_tool_type = await self._call_responses_api(payload, sdk_timeout)
                metadata["web_tool_type"] = web_tool_type
                
                # Extract tool evidence
                tool_count, tool_types = self._extract_tool_evidence(response)
                metadata["tool_call_count"] = tool_count
                metadata["grounded_effective"] = tool_count > 0
                metadata["tool_types"] = tool_types
                
                # Extract final content from output_text
                content = ""
                if hasattr(response, 'output_text'):
                    content = response.output_text
                elif hasattr(response, 'output'):
                    # Look for text in output items
                    for item in response.output:
                        if hasattr(item, 'type') and item.type == 'output_text':
                            content = item.text
                            break
                
                # Validate strict JSON if schema provided
                if json_schema and content:
                    try:
                        parsed = json.loads(content)
                        metadata["json_valid"] = True
                    except json.JSONDecodeError as e:
                        metadata["json_valid"] = False
                        metadata["json_error"] = str(e)
                
                # Set why_not_grounded
                if not metadata["grounded_effective"]:
                    if grounding_mode == "AUTO":
                        metadata["why_not_grounded"] = "auto_mode_no_search"
                    else:
                        metadata["why_not_grounded"] = "no_tool_calls"
                
                # Enforce REQUIRED mode
                if grounding_mode == "REQUIRED" and tool_count == 0:
                    raise GroundingRequiredFailedError(
                        f"REQUIRED grounding mode specified but no tool calls made. "
                        f"why_not_grounded={metadata['why_not_grounded']}"
                    )
                
                # Extract usage
                usage = {}
                if hasattr(response, 'usage'):
                    usage_obj = response.usage
                    usage = {
                        "prompt_tokens": getattr(usage_obj, 'input_tokens', 0),
                        "completion_tokens": getattr(usage_obj, 'output_tokens', 0),
                        "reasoning_tokens": getattr(usage_obj, 'reasoning_tokens', 0),
                        "total_tokens": getattr(usage_obj, 'total_tokens', 0)
                    }
                
            else:
                # Non-grounded or non-GPT-5 path (Chat Completions)
                params = {
                    "model": effective_model,
                    "messages": request.messages,
                    "timeout": sdk_timeout
                }
                
                # Use appropriate token parameter
                if "gpt-5" in effective_model.lower():
                    max_tokens = request.max_tokens or 1000
                    if is_grounded:
                        max_tokens = GROUNDED_MAX_TOKENS
                    params["max_completion_tokens"] = max_tokens
                else:
                    params["max_tokens"] = request.max_tokens or 1000
                    params["temperature"] = request.temperature or 0.7
                
                # Make the API call
                if DISABLE_STREAMING or "gpt-5" in effective_model.lower():
                    response = await self.client.chat.completions.create(**params, stream=False)
                else:
                    # Streaming with proper chunk concatenation
                    response = await self._call_with_streaming(params)
                
                # Extract content
                content = ""
                if hasattr(response, 'choices') and response.choices:
                    msg = response.choices[0].message
                    content = msg.content or ""
                    
                    # Check for tool calls in chat completion
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        metadata["tool_call_count"] = len(msg.tool_calls)
                        metadata["grounded_effective"] = True
                    else:
                        metadata["tool_call_count"] = 0
                        metadata["grounded_effective"] = False
                        if is_grounded:
                            metadata["why_not_grounded"] = "no_tool_calls"
                
                # Extract usage
                usage = {}
                if hasattr(response, 'usage'):
                    usage_obj = response.usage
                    usage = {
                        "prompt_tokens": getattr(usage_obj, 'prompt_tokens', 0),
                        "completion_tokens": getattr(usage_obj, 'completion_tokens', 0),
                        "total_tokens": getattr(usage_obj, 'total_tokens', 0)
                    }
            
            # Build response
            metadata["response_time_ms"] = int((time.perf_counter() - start_time) * 1000)
            
            return LLMResponse(
                content=content,
                model_version=effective_model,
                model_fingerprint=None,
                grounded_effective=metadata.get("grounded_effective", False),
                usage=usage,
                latency_ms=metadata["response_time_ms"],
                raw_response=None,
                success=True,
                vendor="openai",
                model=request.model,
                metadata=metadata,
                citations=[]
            )
            
        except GroundingRequiredFailedError:
            raise
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"[OAI_ERROR] {str(e)[:200]}")
            raise
        finally:
            if permit:
                _RL.release(permit)
    
    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model in self.allowlist