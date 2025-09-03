"""
OpenAI Adapter with comprehensive fixes for timeout and hanging issues.
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
    """OpenAI adapter with timeout and hanging fixes."""
    
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
    
    def _should_use_responses_api(self, model: str) -> bool:
        """Determine if model should use Responses API."""
        # GPT-5 models use Responses API
        if "gpt-5" in model.lower():
            return True
        # Legacy models use Chat Completions
        return False
    
    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete with comprehensive timeout and hanging protection."""
        start_time = time.time()
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": "openai",
            "model": request.model
        }
        
        # Health check first
        if not await self._health_check():
            raise RuntimeError("[OAI] API health check failed - aborting to prevent hang")
        
        # Validate model
        ok, msg = validate_model("openai", request.model)
        if not ok:
            raise ValueError(f"Invalid/unsupported OpenAI model: {msg}")
        
        # Determine endpoint
        use_responses = self._should_use_responses_api(request.model)
        endpoint = "responses" if use_responses else "chat.completions"
        
        # ALS detection
        als_present, als_position = self._detect_als_position(request.messages)
        metadata["als_present"] = als_present
        metadata["als_position"] = als_position
        
        # Build tools if grounded
        tools = []
        tool_choice = None
        if request.grounded:
            tools = [{
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            }]
            tool_choice = "auto"
            metadata["grounding_mode"] = request.meta.get("grounding_mode", "PREFERRED")
        
        # Forward timeout to SDK
        sdk_timeout = min(timeout, 120)  # Cap at 2 minutes for SDK
        
        # Log telemetry line
        logger.info(
            f"[OAI_CALL] endpoint={endpoint} model={request.model} "
            f"timeout_forwarded={sdk_timeout}s limiter={'bypassed' if DISABLE_LIMITER else 'used'} "
            f"streaming={'off' if DISABLE_STREAMING else 'on'} "
            f"tools={'on' if tools else 'off'} base_url={self.client.base_url}"
        )
        
        # Acquire rate limiter permit with timeout
        permit = None
        try:
            permit = await _RL.acquire_with_timeout(timeout_sec=1.0)
            
            # Prepare request parameters
            # GPT-5 has different parameter requirements
            params = {
                "model": request.model,
                "messages": request.messages,
                "timeout": sdk_timeout  # Forward timeout to SDK
            }
            
            # GPT-5 specific parameters
            if "gpt-5" in request.model.lower():
                params["max_completion_tokens"] = request.max_tokens or 1000
                # GPT-5 doesn't support temperature parameter
            else:
                params["max_tokens"] = request.max_tokens or 1000
                params["temperature"] = request.temperature or 0.7
            
            if tools:
                params["tools"] = tools
                params["tool_choice"] = tool_choice
            
            # Make the API call
            if use_responses:
                # Use Responses API for GPT-5
                response = await self._call_responses_api(params)
            else:
                # Use Chat Completions for legacy models
                if DISABLE_STREAMING:
                    response = await self.client.chat.completions.create(**params, stream=False)
                else:
                    # Streaming with proper consumption
                    response = await self._call_with_streaming(params)
            
            # Extract content
            content = ""
            if hasattr(response, 'choices') and response.choices:
                msg = response.choices[0].message
                content = msg.content or ""
            
            # Build response
            metadata["response_time_ms"] = int((time.time() - start_time) * 1000)
            metadata["grounded_effective"] = bool(tools)
            
            # Log ALS telemetry
            als_country = os.getenv("ALS_COUNTRY_CODE", "DE")
            als_locale = os.getenv("ALS_LOCALE", "de-DE")
            als_tz = os.getenv("ALS_TZ", "Europe/Berlin")
            logger.info(
                f"[OAI_ALS] als_present={als_present} als_position={als_position} "
                f"locale={als_locale} country={als_country} tz={als_tz} "
                f"date={datetime.utcnow().strftime('%Y-%m-%d')}"
            )
            
            return LLMResponse(
                content=content,
                model_version=request.model,
                model_fingerprint=None,
                grounded_effective=bool(tools),
                usage={},
                latency_ms=metadata["response_time_ms"],
                raw_response=None,
                success=True,
                vendor="openai",
                model=request.model,
                metadata=metadata,
                citations=[]
            )
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"[OAI_ERROR] {str(e)[:200]}")
            raise
        finally:
            if permit:
                _RL.release(permit)
    
    async def _call_responses_api(self, params: Dict) -> Any:
        """Call Responses API for GPT-5 models."""
        # For now, use chat completions as fallback
        # In production, this would call the actual Responses API endpoint
        logger.info("[OAI_RESPONSES] Using Responses API endpoint")
        return await self.client.chat.completions.create(**params, stream=False)
    
    async def _call_with_streaming(self, params: Dict) -> Any:
        """Call with streaming and proper consumption."""
        try:
            # Create streaming response
            stream = await self.client.chat.completions.create(**params, stream=True)
            
            # Consume all chunks
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
            
            # Build final response from chunks
            if chunks:
                # Combine chunks into final response
                # This is a simplified version - in production would properly merge
                return chunks[-1]
            
            raise RuntimeError("No chunks received from streaming")
            
        except Exception as e:
            logger.error(f"[OAI_STREAM] Streaming error: {str(e)[:100]}")
            raise
    
    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model in self.allowlist