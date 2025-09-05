"""
Unified LLM adapter router for AI Ranker V2
Routes requests to appropriate provider and handles ALS, telemetry
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.types import LLMRequest, LLMResponse, ALSContext
from app.llm.models import validate_model, normalize_model
from app.llm.tool_detection import normalize_tool_detection, attest_two_step_vertex
from app.models.models import LLMTelemetry
from app.services.als.als_builder import ALSBuilder
from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)

# Timeout configuration
UNGROUNDED_TIMEOUT = int(os.getenv("LLM_TIMEOUT_UN", "60"))
GROUNDED_TIMEOUT = int(os.getenv("LLM_TIMEOUT_GR", "120"))

# Global proxy kill-switch (default: disabled)
DISABLE_PROXIES = os.getenv("DISABLE_PROXIES", "true").lower() in ("true", "1", "yes")

# Feature flags
# Route Gemini models via direct google-genai (instead of Vertex)
USE_GEMINI_DIRECT = os.getenv("USE_GEMINI_DIRECT", "false").lower() in ("true","1","yes","on")
# Relax REQUIRED for Google vendors (Vertex/Gemini-direct): allow pass when tool calls + unlinked URLs exist
REQUIRED_RELAX_FOR_GOOGLE = os.getenv("REQUIRED_RELAX_FOR_GOOGLE", "false").lower() in ("true","1","yes","on")
# Enable failover from Gemini Direct to Vertex on 503 errors
GEMINI_DIRECT_FAILOVER_TO_VERTEX = os.getenv("GEMINI_DIRECT_FAILOVER_TO_VERTEX", "false").lower() in ("true","1","yes","on")

# Circuit breaker configuration
CB_COOLDOWN_SECONDS = int(os.getenv("CB_COOLDOWN_SECONDS", "60"))
CB_FAILURE_THRESHOLD = int(os.getenv("CB_FAILURE_THRESHOLD", "3"))

# ALS configuration
ALS_HMAC_SECRET = os.getenv("ALS_HMAC_SECRET", "als_secret_key").encode('utf-8')



class UnifiedLLMAdapter:
    """
    Main router for LLM requests
    Responsibilities:
    - Route by vendor
    - Apply ALS (once, before routing)
    - Common timeout handling
    - Normalize responses
    - Emit telemetry
    - Capability gating (reasoning/thinking)
    - Circuit breaker (vendor:model)
    - Router pacing (Retry-After)
    """
    
    def __init__(self):
        # Lazy-init adapters to prevent boot failures when env vars missing
        self._openai_adapter = None
        self._vertex_adapter = None
        self._gemini_adapter = None
        self.als_builder = ALSBuilder()
        
        # Circuit breaker state per vendor:model
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}
        
        # Pacing map for rate-limited requests
        self._next_allowed_at: Dict[str, float] = {}
        
        # Circuit breaker open counter (monotonic)
        self._cb_open_count = 0
    
    @property
    def openai_adapter(self):
        """Lazy-init OpenAI adapter on first use"""
        if self._openai_adapter is None:
            from app.llm.adapters.openai_adapter import OpenAIAdapter
            self._openai_adapter = OpenAIAdapter()
        return self._openai_adapter
    
    @property
    def vertex_adapter(self):
        """Lazy-init Vertex adapter on first use"""
        if self._vertex_adapter is None:
            from app.llm.adapters.vertex_adapter import VertexAdapter
            self._vertex_adapter = VertexAdapter()
        return self._vertex_adapter

    @property
    def gemini_adapter(self):
        """Lazy-init Direct Gemini adapter on first use"""
        if self._gemini_adapter is None:
            from app.llm.adapters.gemini_adapter import GeminiAdapter
            self._gemini_adapter = GeminiAdapter()
        return self._gemini_adapter
    
    def _capabilities_for(self, vendor: str, model: str) -> Dict[str, Any]:
        """
        Determine capabilities for a given vendor:model pair.
        
        Returns:
            Dict with capability flags:
            - supports_reasoning_effort: OpenAI reasoning models only
            - supports_reasoning_summary: OpenAI reasoning models only
            - supports_thinking_budget: Gemini/Vertex thinking models
            - include_thoughts_allowed: Gemini/Vertex thinking models
        """
        caps = {
            "supports_reasoning_effort": False,
            "supports_reasoning_summary": False,
            "supports_thinking_budget": False,
            "include_thoughts_allowed": False
        }
        
        if vendor == "openai":
            # OpenAI reasoning models: GPT-5 family and o-series
            if (model.startswith("gpt-5") or 
                model.startswith("o3") or 
                model.startswith("o4-mini") or
                model.startswith("o1")):
                caps["supports_reasoning_effort"] = True
                caps["supports_reasoning_summary"] = True
            # gpt-4o* models do NOT support reasoning parameters
            
        elif vendor in ("gemini_direct", "vertex"):
            # Gemini 2.5 thinking-capable models
            bare_model = self._bare_gemini_model(model)
            if "2.5" in bare_model or "2-5" in bare_model:
                if "flash" in bare_model.lower() or "pro" in bare_model.lower():
                    caps["supports_thinking_budget"] = True
                    caps["include_thoughts_allowed"] = True
                    
                    # Note: Gemini 2.5 Pro cannot fully disable thinking
                    if "pro" in bare_model.lower():
                        caps["thinking_always_on"] = True
        
        return caps
    
    def _bare_gemini_model(self, model: str) -> str:
        """Extract bare model name from Gemini model path."""
        if model.startswith("publishers/google/models/"):
            model = model.split("publishers/google/models/", 1)[1]
        if model.startswith("models/"):
            model = model.split("models/", 1)[1]
        return model
    
    def _check_circuit_breaker(self, vendor: str, model: str) -> tuple[str, Optional[str]]:
        """
        Check circuit breaker status for vendor:model.
        
        Returns:
            (status, error_message): status is "closed", "open", or "half-open"
                                    error_message is set if breaker is open
        """
        cb_key = f"{vendor}:{model}"
        
        if cb_key not in self._circuit_breakers:
            return "closed", None
        
        breaker = self._circuit_breakers[cb_key]
        now = time.time()
        
        if breaker["state"] == "open":
            if now >= breaker["open_until"]:
                # Transition to half-open
                breaker["state"] = "half-open"
                logger.info(f"[CB] Circuit breaker {cb_key} transitioning to half-open")
                return "half-open", None
            else:
                remaining = int(breaker["open_until"] - now)
                return "open", f"Circuit breaker open for {cb_key}, retry in {remaining}s"
        
        return breaker["state"], None
    
    def _record_success(self, vendor: str, model: str):
        """Record successful call for circuit breaker."""
        cb_key = f"{vendor}:{model}"
        
        if cb_key in self._circuit_breakers:
            breaker = self._circuit_breakers[cb_key]
            if breaker["state"] in ("half-open", "open"):
                logger.info(f"[CB] Circuit breaker {cb_key} closing after success")
                breaker["state"] = "closed"
                breaker["consecutive_failures"] = 0
                breaker["last_error"] = None
    
    def _record_failure(self, vendor: str, model: str, error: Exception):
        """Record failure for circuit breaker."""
        cb_key = f"{vendor}:{model}"
        
        # Determine if this is a transient error that should trigger circuit breaker
        is_transient = self._is_transient_error(vendor, error)
        
        if not is_transient:
            return  # Non-transient errors don't affect circuit breaker
        
        if cb_key not in self._circuit_breakers:
            self._circuit_breakers[cb_key] = {
                "state": "closed",
                "consecutive_failures": 0,
                "open_until": 0,
                "last_error": None
            }
        
        breaker = self._circuit_breakers[cb_key]
        breaker["consecutive_failures"] += 1
        breaker["last_error"] = str(error)[:200]
        
        if breaker["consecutive_failures"] >= CB_FAILURE_THRESHOLD:
            # Open the breaker
            breaker["state"] = "open"
            breaker["open_until"] = time.time() + CB_COOLDOWN_SECONDS
            self._cb_open_count += 1
            logger.warning(f"[CB] Circuit breaker opened for {cb_key} after {CB_FAILURE_THRESHOLD} failures")
    
    def _is_transient_error(self, vendor: str, error: Exception) -> bool:
        """Determine if error is transient and should trigger circuit breaker."""
        error_str = str(error)
        error_type = type(error).__name__
        
        if vendor == "openai":
            # OpenAI transient errors
            if "RateLimitError" in error_type or "429" in error_str:
                return True
            if any(code in error_str for code in ["500", "502", "503", "504"]):
                return True
        
        elif vendor in ("vertex", "gemini_direct"):
            # Google transient errors
            if any(marker in error_str for marker in [
                "ServiceUnavailable", "TooManyRequests", "ResourceExhausted",
                "503", "429", "500", "502"
            ]):
                return True
        
        return False
    
    def _extract_retry_after(self, vendor: str, error: Exception) -> Optional[int]:
        """Extract Retry-After hint from error if available."""
        # Check if error has response attribute with headers
        if hasattr(error, 'response'):
            response = error.response
            if hasattr(response, 'headers'):
                headers = response.headers
                
                # Standard Retry-After header
                if 'Retry-After' in headers:
                    try:
                        return int(headers['Retry-After'])
                    except (ValueError, TypeError):
                        pass
                
                # OpenAI specific headers
                if vendor == "openai":
                    for header in ['x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens']:
                        if header in headers:
                            try:
                                reset_time = int(headers[header])
                                # If it's a timestamp, calculate seconds from now
                                if reset_time > time.time():
                                    return int(reset_time - time.time())
                            except (ValueError, TypeError):
                                pass
        
        return None
    
    def _check_pacing(self, vendor: str, model: str) -> float:
        """Check if request should be paced based on previous rate limits.
        Returns: delay in seconds to wait (0 if no pacing needed)
        """
        pace_key = f"{vendor}:{model}"
        
        if pace_key in self._next_allowed_at:
            next_allowed = self._next_allowed_at[pace_key]
            now = time.time()
            
            if now < next_allowed:
                wait_time = next_allowed - now
                return wait_time
        
        return 0.0
    
    def _update_pacing(self, vendor: str, model: str, error: Exception):
        """Update pacing based on rate limit errors."""
        retry_after = self._extract_retry_after(vendor, error)
        
        if retry_after and retry_after > 0:
            pace_key = f"{vendor}:{model}"
            self._next_allowed_at[pace_key] = time.time() + retry_after
            logger.info(f"[PACING] Set next allowed time for {pace_key}: +{retry_after}s")
    async def complete(
        self,
        request: LLMRequest,
        session: Optional[AsyncSession] = None
    ) -> LLMResponse:
        """
        Main entry point for LLM completions
        
        Args:
            request: Unified LLM request
            session: Optional database session for telemetry
            
        Returns:
            Unified LLM response
        """
        
        # Step 1: Apply ALS if context is provided and not already in messages
        # Check if ALS is already applied using stable flag (not fragile string check)
        als_already_applied = getattr(request, 'als_applied', False)
        
        # Apply ALS if we have context and it's not already applied
        if hasattr(request, 'als_context') and request.als_context and not als_already_applied:
            logger.debug(f"[ALS_DEBUG] Applying ALS: country={getattr(request.als_context, 'country_code', 'N/A')}")
            request = self._apply_als(request)
            logger.debug(f"[ALS_DEBUG] After _apply_als: metadata={getattr(request, 'metadata', {})}")
        
        # Step 2: Infer vendor if missing
        if not request.vendor:
            request.vendor = self.get_vendor_for_model(request.model)
            if not request.vendor:
                raise ValueError(f"Cannot infer vendor for model: {request.model}")
        
        # Step 2.5: Strict model validation with guardrails
        # Store original model before normalization for adjustment check
        original_model_pre_norm = request.model
        # Normalize model
        request.model = normalize_model(request.vendor, request.model)
        
        # Store original model in metadata for telemetry
        if not hasattr(request, 'metadata'):
            request.metadata = {}
        request.metadata['original_model'] = original_model_pre_norm
        
        
        def _bare_gemini_id(m: str) -> str:
            if m.startswith("publishers/google/models/"):
                m = m.split("publishers/google/models/", 1)[1]
            if m.startswith("models/"):
                m = m.split("models/", 1)[1]
            return m
# Hard guardrails for allowed models
        if request.vendor == "vertex":
            # Check against configurable allowlist
            allowed_models = os.getenv("ALLOWED_VERTEX_MODELS", 
                "publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash,publishers/google/models/gemini-1.5-pro,publishers/google/models/gemini-1.5-flash").split(",")
            if request.model not in allowed_models:
                raise ValueError(
                    f"Model not allowed: {request.model}\n"
                    f"Allowed models: {allowed_models}\n"
                    f"To use this model:\n"
                    f"1. Add to ALLOWED_VERTEX_MODELS env var\n"
                    f"2. Redeploy service\n"
                    f"Note: We don't silently rewrite models (Adapter PRD)"
                )
        elif request.vendor == "openai":
            # Check against configurable allowlist
            # Default includes pinned gpt-5-2025-08-07, dev models gpt-5-chat-latest and gpt-4o
            allowed_models = os.getenv("ALLOWED_OPENAI_MODELS", 
                "gpt-5-2025-08-07,gpt-5-chat-latest,gpt-4o").split(",")
            if request.model not in allowed_models:
                raise ValueError(
                    f"Model not allowed: {request.model}\n"
                    f"Allowed models: {allowed_models}\n"
                    f"To use this model:\n"
                    f"1. Add to ALLOWED_OPENAI_MODELS env var\n"
                    f"2. Redeploy service\n"
                    f"Note: We don't silently rewrite models (Adapter PRD)"
                )
        
        # Model adjustment for grounding has been REMOVED
        # We enforce strict model immutability - no silent rewrites
        
        # Double-check with centralized validation
        is_valid, error_msg = validate_model(request.vendor, request.model)
        if not is_valid:
            raise ValueError(f"MODEL_NOT_ALLOWED: {error_msg}")
        
        # Step 3: Validate vendor
        if request.vendor not in ("openai", "vertex", "gemini_direct"):
            raise ValueError(f"Unsupported vendor: {request.vendor}")
        
        # Step 3.1: Initialize variables needed throughout the function
        reasoning_hint_dropped = False
        thinking_hint_dropped = False
        cb_status = "closed"
        
        # Step 3.2: Compute capabilities and gate unsupported parameters
        caps = self._capabilities_for(request.vendor, request.model)
        
        # Store capabilities in metadata for adapter to use
        if not hasattr(request, 'metadata'):
            request.metadata = {}
        request.metadata["capabilities"] = caps
        
        # Gate reasoning parameters for OpenAI
        if request.vendor == "openai":
            if hasattr(request, 'meta') and request.meta:
                if 'reasoning_effort' in request.meta or 'reasoning_summary' in request.meta:
                    if not caps["supports_reasoning_effort"]:
                        # Drop reasoning parameters for non-reasoning models
                        if 'reasoning_effort' in request.meta:
                            del request.meta['reasoning_effort']
                        if 'reasoning_summary' in request.meta:
                            del request.meta['reasoning_summary']
                        reasoning_hint_dropped = True
                        logger.info(f"[CAPABILITY_GATE] Dropped reasoning params for {request.model}")
        
        # Gate thinking parameters for Gemini/Vertex
        if request.vendor in ("gemini_direct", "vertex"):
            if hasattr(request, 'meta') and request.meta:
                if 'thinking_budget' in request.meta or 'include_thoughts' in request.meta:
                    if not caps["supports_thinking_budget"]:
                        # Drop thinking parameters for non-thinking models
                        if 'thinking_budget' in request.meta:
                            del request.meta['thinking_budget']
                        if 'include_thoughts' in request.meta:
                            del request.meta['include_thoughts']
                        thinking_hint_dropped = True
                        logger.info(f"[CAPABILITY_GATE] Dropped thinking params for {request.model}")
        
        # Step 3.5: Check circuit breaker and pacing
        vendor = request.vendor
        model = request.model
        
        # Check circuit breaker
        cb_status, cb_message = self._check_circuit_breaker(vendor, model)
        if cb_status == "open":
            # Circuit breaker is open, fail fast
            response = LLMResponse(
                content="",
                success=False,
                vendor=vendor,
                model=model,
                error_type="CIRCUIT_BREAKER_OPEN",
                error_message=cb_message or f"Circuit breaker open for {vendor}:{model}",
                metadata={"circuit_breaker_status": "open"}
            )
            return response
        
        # Check pacing
        pacing_delay = self._check_pacing(vendor, model)
        if pacing_delay > 0:
            # Apply pacing delay
            logger.info(f"[PACING] Applying {pacing_delay:.2f}s delay for {vendor}:{model}")
            await asyncio.sleep(pacing_delay)
            if not hasattr(request, 'metadata'):
                request.metadata = {}
            request.metadata["router_pacing_delay"] = int(pacing_delay * 1000)  # ms
        
        # Step 3.6: Normalize vantage_policy - remove all proxy modes
        original_policy = str(getattr(request, 'vantage_policy', 'ALS_ONLY'))
        normalized_policy = original_policy
        proxies_normalized = False
        
        # Store original for telemetry tracking
        request.original_vantage_policy = original_policy
        
        if DISABLE_PROXIES and original_policy in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
            # Normalize proxy policies to ALS_ONLY
            normalized_policy = "ALS_ONLY"
            proxies_normalized = True
            request.proxy_normalization_applied = True
            logger.info(f"[PROXY_DISABLED] Normalizing vantage_policy: {original_policy} -> {normalized_policy}")
            request.vantage_policy = normalized_policy
        else:
            request.proxy_normalization_applied = False
        
        # Set flag to prevent any proxy usage downstream
        request.proxies_disabled = DISABLE_PROXIES
        
        # Step 3.8: Apply thinking defaults for Gemini-2.5-Pro
        if request.vendor in ("gemini_direct", "vertex"):
            bare_model = self._bare_gemini_model(request.model)
            if "gemini-2.5-pro" in bare_model.lower():
                # Only apply if capability is supported
                if caps.get("supports_thinking_budget", False):
                    # Apply thinking budget default if not specified
                    if not hasattr(request, 'meta') or not request.meta or request.meta.get("thinking_budget") is None:
                        default_thinking_budget = int(os.getenv("GEMINI_PRO_THINKING_BUDGET", "256"))
                        if not hasattr(request, 'metadata'):
                            request.metadata = {}
                        request.metadata["thinking_budget_tokens"] = default_thinking_budget
                        logger.debug(f"[GEMINI_PRO_DEFAULTS] Applied thinking_budget_tokens={default_thinking_budget}")
                    else:
                        # Use explicit value from request
                        if not hasattr(request, 'metadata'):
                            request.metadata = {}
                        request.metadata["thinking_budget_tokens"] = request.meta.get("thinking_budget")
                
                # Apply max_output_tokens default if not specified
                if not request.max_tokens:
                    if request.grounded:
                        default_max_tokens = int(os.getenv("GEMINI_PRO_MAX_OUTPUT_TOKENS_GROUNDED", "1536"))
                    else:
                        default_max_tokens = int(os.getenv("GEMINI_PRO_MAX_OUTPUT_TOKENS_UNGROUNDED", "768"))
                    request.max_tokens = default_max_tokens
                    logger.debug(f"[GEMINI_PRO_DEFAULTS] Applied max_tokens={default_max_tokens} (grounded={request.grounded})")
        
        # Step 4: Calculate timeout based on grounding
        timeout = GROUNDED_TIMEOUT if request.grounded else UNGROUNDED_TIMEOUT
        
        logger.info(f"Routing LLM request: vendor={request.vendor}, model={request.model}, "
                   f"grounded={request.grounded}, timeout={timeout}s, "
                   f"template_id={request.template_id}, run_id={request.run_id}")
        
        # Debug logging for grounding attempts
        if request.grounded:
            logger.debug(f"[GROUNDING_ATTEMPT] Attempting grounded request: vendor={request.vendor}, "
                        f"model={request.model}, json_mode={getattr(request, 'json_mode', False)}")
        
        # Track vendor path for failover
        vendor_path = [request.vendor]
        failover_applied = False
        failover_reason = None
        
        try:
            if request.vendor == "openai":
                response = await self.openai_adapter.complete(request, timeout=timeout)
                self._record_success(request.vendor, request.model)
            elif (
                request.vendor == "gemini_direct"
                or (
                    request.vendor == "vertex"
                    and USE_GEMINI_DIRECT
                    and str(request.model).startswith(("publishers/google/models/gemini-", "models/gemini-", "gemini-"))
                )
            ):
                try:
                    vendor_path.append("gemini_direct")
                    response = await self.gemini_adapter.complete(request, timeout=timeout)
                    self._record_success("gemini_direct", request.model)
                except Exception as e:
                    # Record failure and update pacing
                    self._record_failure("gemini_direct", request.model, e)
                    self._update_pacing("gemini_direct", request.model, e)
                    
                    error_str = str(e)
                    # Check if it's a circuit breaker open error and failover is enabled
                    transient = self._is_transient_error('gemini_direct', e)
                    if (
                        GEMINI_DIRECT_FAILOVER_TO_VERTEX
                        and (vendor_path and vendor_path[-1] == 'gemini_direct')
                        and ("Circuit breaker open" in error_str or transient)
                    ):
                        # Attempt failover to Vertex
                        logger.info(f"[FAILOVER] Attempting failover from gemini_direct to vertex due to circuit breaker")
                        vendor_path.append("vertex")
                        failover_applied = True
                        failover_reason = "503_circuit_open"
                        
                        # Create a copy of the request for Vertex
                        import copy
                        vertex_req = copy.deepcopy(request)
                        vertex_req.vendor = "vertex"
                        
                        # Ensure model format is correct for Vertex
                        if not vertex_req.model.startswith("publishers/google/models/"):
                            bare_model = vertex_req.model.replace("models/", "").replace("gemini-", "")
                            if "gemini" not in bare_model:
                                bare_model = f"gemini-{bare_model}"
                            vertex_req.model = f"publishers/google/models/{bare_model}"
                        
                        response = await self.vertex_adapter.complete(vertex_req, timeout=timeout)
                        self._record_success("vertex", vertex_req.model)
                        
                        # Add failover metadata
                        if not hasattr(response, "metadata"):
                            response.metadata = {}
                        response.metadata["vendor_path"] = vendor_path
                        response.metadata["failover_from"] = "gemini_direct"
                        response.metadata["failover_to"] = "vertex"
                        response.metadata["failover_reason"] = failover_reason
                    else:
                        # Re-raise if not a failover scenario
                        raise
            else:  # vertex - NO SILENT FALLBACKS, auth errors should surface
                response = await self.vertex_adapter.complete(request, timeout=timeout)
                self._record_success(request.vendor, request.model)
                
        except Exception as e:
            # Record failure and update pacing if we haven't already
            if not failover_applied:
                self._record_failure(request.vendor, request.model, e)
                self._update_pacing(request.vendor, request.model, e)
            
            # Convert adapter exceptions to LLM response format
            error_msg = str(e)
            logger.error(f"Adapter failed for vendor={request.vendor}: {error_msg}")
            
            # Debug logging for grounding failures
            if request.grounded:
                if "GROUNDING_NOT_SUPPORTED" in error_msg:
                    logger.debug(f"[GROUNDING_FALLBACK] Grounding not supported for {request.vendor}/{request.model}, "
                               f"will proceed ungrounded")
                else:
                    logger.debug(f"[GROUNDING_FAILED] Grounding attempt failed: {error_msg}")
            
            # ---- FAIL-CLOSED for Required grounding per PRD ----
            # If the caller requested REQUIRED grounding, we must not swallow grounding errors.
            grounding_mode = self._extract_grounding_mode(request)
            
            # Known grounding failure types to bubble up
            _fatal_markers = (
                "GROUNDING_NOT_SUPPORTED",
                "GROUNDING_REQUIRED_ERROR",
                "GROUNDING_EMPTY_RESULTS",
            )
            if (grounding_mode == "REQUIRED") and any(m in error_msg for m in _fatal_markers):
                # Re-raise so HTTP layer / test harness can fail the cell hard
                logger.debug(f"[GROUNDING_REQUIRED] Re-raising error for REQUIRED mode: {error_msg}")
                raise
            
            # Return error response instead of letting exception bubble up
            from app.llm.types import LLMResponse
            return LLMResponse(
                content="",
                model_version=request.model,
                model_fingerprint=None,
                grounded_effective=False,
                usage={},
                latency_ms=0,
                raw_response=None,
                success=False,
                vendor=request.vendor,
                model=request.model,
                error_type=type(e).__name__,
                error_message=error_msg
            )
        
        # Debug logging for successful grounding
        if request.grounded and hasattr(response, 'grounded_effective'):
            if response.grounded_effective:
                tool_count = response.metadata.get('tool_call_count', 0) if hasattr(response, 'metadata') else 0
                logger.debug(f"[GROUNDING_SUCCESS] Grounding successful: vendor={request.vendor}, "
                           f"model={request.model}, tool_calls={tool_count}")
            else:
                logger.debug(f"[GROUNDING_UNUSED] Request was grounded but no tools were invoked")
        
        # Add router-level metadata to response
        if not hasattr(response, 'metadata'):
            response.metadata = {}
        # Track the actual adapters used
        try:
            if isinstance(response.metadata, dict):
                response.metadata.setdefault('vendor_path', vendor_path)
        except Exception:
            pass
        
        # Add capability gating telemetry
        response.metadata['reasoning_hint_dropped'] = reasoning_hint_dropped
        response.metadata['thinking_hint_dropped'] = thinking_hint_dropped
        response.metadata['circuit_breaker_status'] = cb_status
        
        # Add pacing metadata if it was applied
        if hasattr(request, 'metadata') and request.metadata and 'router_pacing_delay' in request.metadata:
            response.metadata['router_pacing_delay'] = request.metadata['router_pacing_delay']
        
        # Post-validation for REQUIRED mode - enforce grounding requirement
        # This provides uniform enforcement across all providers, especially those that can't force tools
        grounding_mode = self._extract_grounding_mode(request)
        
        if grounding_mode == "REQUIRED" and request.grounded:
            # Check if grounding was effective and citations were extracted
            grounding_failed = False
            failure_reason = ""
            
            # Check grounding effectiveness
            if hasattr(response, 'grounded_effective') and not response.grounded_effective:
                # Relaxation for Google vendors if enabled
                is_google_vendor = request.vendor in ("vertex", "gemini_direct")
                tc = int((getattr(response, "metadata", {}) or {}).get("tool_call_count", 0) or 0)
                m = response.metadata or {}
                unlinked = int(m.get("unlinked_sources_count", (m.get("citation_count", 0) or 0) - (m.get("anchored_citations_count", 0) or 0)) or 0)
                if is_google_vendor and REQUIRED_RELAX_FOR_GOOGLE and tc > 0 and unlinked > 0:
                    grounding_failed = False
                    if response.metadata is None:
                        response.metadata = {}
                    response.metadata["required_pass_reason"] = response.metadata.get("required_pass_reason") or "unlinked_google"
                else:
                    grounding_failed = True
                    failure_reason = "Model did not invoke grounding tools"
            
            # Check for ANCHORED citations (unlinked-only is insufficient for REQUIRED by default)
            elif hasattr(response, 'citations'):
                citations = response.citations if response.citations else []
                
                # Get the explicit counts from metadata
                metadata = response.metadata if hasattr(response, 'metadata') and response.metadata else {}
                anchored_count = metadata.get('anchored_citations_count', 0)
                unlinked_count = metadata.get('unlinked_sources_count', 0)
                
                # Default policy: require anchored > 0 for REQUIRED mode
                if anchored_count == 0:
                    # Check if we should relax for Google vendors with unlinked evidence
                    is_google_vendor = request.vendor in ("vertex", "gemini_direct")
                    if is_google_vendor and REQUIRED_RELAX_FOR_GOOGLE and unlinked_count > 0:
                        # Allow unlinked-only pass for Google vendors when flag is on
                        grounding_failed = False
                        if response.metadata is None:
                            response.metadata = {}
                        response.metadata["required_pass_reason"] = "unlinked_google"
                    else:
                        grounding_failed = True
                        if not citations:
                            failure_reason = "Grounding tools invoked but no citations extracted"
                        else:
                            failure_reason = f"REQUIRED mode requires anchored citations (found {unlinked_count} unlinked only)"
                else:
                    # We have anchored citations - pass
                    grounding_failed = False
            else:
                # No metadata at all
                grounding_failed = True
                failure_reason = "No grounding metadata available"
            
            if grounding_failed:
                # REQUIRED mode but grounding was not effective or no citations - fail closed
                logger.error(f"[GROUNDING_REQUIRED] REQUIRED mode failed: "
                           f"vendor={request.vendor}, model={request.model}, reason={failure_reason}")
                
                # Import error class if needed
                try:
                    from app.llm.errors import GroundingRequiredFailedError
                    raise GroundingRequiredFailedError(
                        f"GROUNDING_REQUIRED_FAILED: {failure_reason}. "
                        f"Model: {request.model}, Vendor: {request.vendor}"
                    )
                except ImportError:
                    # Fallback to ValueError if error class not available
                    raise ValueError(
                        f"GROUNDING_REQUIRED_FAILED: {failure_reason}. "
                        f"Model: {request.model}, Vendor: {request.vendor}"
                    )
        
        # Step 3: Router-level ALS hardening - ensure ALS metadata is propagated BEFORE telemetry
        # This guarantees ALS visibility even if a provider adapter forgets to copy them
        try:
            if hasattr(request, 'metadata') and isinstance(request.metadata, dict) and request.metadata.get('als_present'):
                if not hasattr(response, 'metadata') or response.metadata is None:
                    response.metadata = {}
                for k in ('als_present', 'als_block_sha256', 'als_variant_id', 'seed_key_id',
                          'als_country', 'als_locale', 'als_nfc_length', 'als_template_id'):
                    if k in request.metadata and k not in response.metadata:
                        response.metadata[k] = request.metadata[k]
                response.metadata['als_mirrored_by_router'] = True
                logger.debug(f"[ALS_HARDENING] Propagated ALS metadata: als_present={response.metadata.get('als_present')}")
        except Exception as e:
            logger.warning(f"[ALS_HARDENING] Failed to propagate ALS metadata: {e}")
        
        # Step 4: Emit telemetry if session provided
        if session:
            await self._emit_telemetry(request, response, session)
        
        return response
    

def get_vendor_for_model(self, model: str) -> Optional[str]:
    """
    Infer vendor from model name (supports fully-qualified Vertex IDs).
    Returns "openai" | "vertex" | None.
    Note: "gemini_direct" is a routing flag; vendor remains "vertex".
    """
    if not model:
        return None
    m = str(model)
    ml = m.lower()
    # OpenAI models
    if ml.startswith("gpt-5") or m in ("gpt-5-chat-latest", "gpt-4o"):
        return "openai"
    # Vertex/Gemini models
    if "publishers/google/models/gemini-" in m or ml.startswith("gemini-") or ml.startswith("models/gemini-"):
        return "vertex"
    return None

    def _apply_als(self, request: LLMRequest) -> LLMRequest:
        """
        Apply Ambient Location Signals to the request
        Modifies the messages to include ALS context
        Enforces ≤350 NFC chars, persists complete provenance
        
        ALS Deterministic Builder Contract:
        1. Canonicalize locale (ISO uppercase, region handling)
        2. Select variant deterministically with HMAC(seed_key_id, template_id)
        3. Build ALS text without any runtime date/time
        4. Normalize to NFC, enforce ≤350 chars (fail-closed, no truncation)
        5. Compute SHA256 over NFC text
        6. Persist all provenance fields
        7. Insert in order: system → ALS → user
        """
        als_context = request.als_context
        
        if not als_context:
            return request
        
        # Step 1: Canonicalize locale (ISO uppercase)
        # Handle both dict and ALSContext object
        if isinstance(als_context, dict):
            country_code = als_context.get('country_code', 'US').upper()
            locale = als_context.get('locale', f'en-{country_code}')
        else:
            # ALSContext object
            country_code = getattr(als_context, 'country_code', 'US').upper()
            locale = getattr(als_context, 'locale', f'en-{country_code}')
        
        # Step 2: Deterministic variant selection using HMAC
        import hmac
        # Use a stable seed key and template identifier
        seed_key_id = 'v1_2025'  # This should come from config in production
        template_id = f'als_template_{country_code}'  # Stable template identifier
        
        # Generate deterministic seed using HMAC
        seed_data = f"{seed_key_id}:{template_id}:{country_code}".encode('utf-8')
        hmac_hash = hmac.new(ALS_HMAC_SECRET, seed_data, hashlib.sha256).hexdigest()
        
        # Convert hash to deterministic index
        # Get number of available variants from ALS builder
        tpl = self.als_builder.templates.TEMPLATES.get(country_code)
        if tpl and hasattr(tpl, 'phrases') and tpl.phrases:
            num_variants = len(tpl.phrases)
            # Use first 8 bytes of hash for variant selection
            variant_idx = int(hmac_hash[:8], 16) % num_variants
        else:
            variant_idx = 0
            num_variants = 1
        
        # Step 3: Build ALS block deterministically (no randomization, no timestamps)
        # Use a fixed date to ensure determinism (regulatory neutral date)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        # Fixed date for deterministic ALS generation (regulatory neutral)
        # This is a placeholder date that doesn't imply current time
        fixed_date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo('UTC'))
        
        # Build with specific variant using deterministic parameters
        from app.services.als.als_templates import ALSTemplates
        
        # For countries with multiple timezones, use deterministic selection
        # based on the HMAC hash to pick a consistent timezone
        tz_override = None
        tpl = self.als_builder.templates.TEMPLATES.get(country_code)
        if tpl and hasattr(tpl, 'timezone_samples') and tpl.timezone_samples:
            # Use HMAC to deterministically select timezone
            tz_idx = int(hmac_hash[8:12], 16) % len(tpl.timezone_samples)
            tz_override = tpl.timezone_samples[tz_idx]
        
        als_block = ALSTemplates.render_block(
            code=country_code,
            phrase_idx=variant_idx,
            include_weather=True,
            now=fixed_date,  # Pass fixed date for determinism
            tz_override=tz_override  # Pass deterministic timezone for multi-tz countries
        )
        
        # Step 4: NFC normalization and length check
        import unicodedata
        als_block_nfc = unicodedata.normalize('NFC', als_block)
        
        # Normalize whitespace: convert CRLF to LF, trim trailing whitespace
        als_block_nfc = als_block_nfc.replace('\r\n', '\n').rstrip()
        
        # Enforce 350 char limit - fail closed, no truncation
        if len(als_block_nfc) > 350:
            raise ValueError(
                f"ALS_BLOCK_TOO_LONG: {len(als_block_nfc)} chars exceeds 350 limit (NFC normalized)\n"
                f"No automatic truncation (immutability requirement)\n"
                f"Fix: Reduce ALS template configuration"
            )
        
        # Step 5: Compute SHA256 over final NFC text
        als_block_sha256 = hashlib.sha256(als_block_nfc.encode('utf-8')).hexdigest()
        
        # Use the deterministic variant info
        variant_id = f'variant_{variant_idx}'
        
        # Deep copy messages to avoid reference issues
        import copy
        modified_messages = copy.deepcopy(request.messages)
        
        # Prepend ALS to the first user message (maintains system → ALS → user order)
        for i, msg in enumerate(modified_messages):
            if msg.get('role') == 'user':
                original_content = msg['content']
                # Minimal guardrail to avoid "future date" refusals:
                # Prefer the user's explicit timeframe over any dates implied by ALS.
                _als_guard = ("Instruction: If the user's question includes an explicit date or timeframe, "
                              "ignore any dates implied by the ambient context below; use the question's timeframe.")
                modified_messages[i] = {
                    'role': 'user',
                    'content': f"{_als_guard}\n\n{als_block_nfc}\n\n{original_content}"
                }
                break
        
        # Update request with modified messages
        request.messages = modified_messages
        
        # Set flag to prevent reapplication
        request.als_applied = True
        
        # Step 6: Store complete ALS provenance metadata
        if not hasattr(request, 'metadata'):
            request.metadata = {}
        
        request.metadata.update({
            # Don't store raw ALS text to prevent location signal leaks
            # 'als_block_text': als_block_nfc,  # REMOVED for security
            'als_block_sha256': als_block_sha256,  # SHA256 of NFC text (sufficient for immutability)
            'als_variant_id': variant_id,  # Which variant was selected
            'seed_key_id': seed_key_id,  # Seed key used for HMAC
            'als_country': country_code,  # Canonicalized country
            'als_locale': locale,  # Full locale string
            'als_nfc_length': len(als_block_nfc),  # Length after NFC
            'als_present': True,
            'als_template_id': template_id  # Template identifier
        })
        
        return request
    
    async def _emit_telemetry(
        self,
        request: LLMRequest,
        response: LLMResponse,
        session: AsyncSession
    ):
        """Emit comprehensive telemetry row to database"""
        try:
            # Build comprehensive metadata JSON
            meta_json = {
                # ALS fields
                'als_present': request.metadata.get('als_present', False) if hasattr(request, 'metadata') else False,
                'als_block_sha256': request.metadata.get('als_block_sha256') if hasattr(request, 'metadata') else None,
                'als_variant_id': request.metadata.get('als_variant_id') if hasattr(request, 'metadata') else None,
                'seed_key_id': request.metadata.get('seed_key_id') if hasattr(request, 'metadata') else None,
                'als_country': request.metadata.get('als_country') if hasattr(request, 'metadata') else None,
                'als_nfc_length': request.metadata.get('als_nfc_length') if hasattr(request, 'metadata') else None,
                
                # Grounding fields - report actual requested mode
                'grounding_mode_requested': self._extract_grounding_mode(request),
                'grounded_effective': response.grounded_effective,
                'tool_call_count': response.metadata.get('tool_call_count', 0) if hasattr(response, 'metadata') else 0,
                'why_not_grounded': response.metadata.get('why_not_grounded') if hasattr(response, 'metadata') else None,
                
                # API versioning
                'response_api': response.metadata.get('response_api') if hasattr(response, 'metadata') else None,
                'provider_api_version': response.metadata.get('provider_api_version') if hasattr(response, 'metadata') else None,
                'region': response.metadata.get('region') if hasattr(response, 'metadata') else None,
                
                # Reasoning/Thinking parameters
                'reasoning_effort': request.meta.get('reasoning_effort') if hasattr(request, 'meta') and request.meta else None,
                'reasoning_summary_requested': request.meta.get('reasoning_summary', False) if hasattr(request, 'meta') and request.meta else False,
                'thinking_budget': request.meta.get('thinking_budget') if hasattr(request, 'meta') and request.meta else None,
                'include_thoughts': request.meta.get('include_thoughts', False) if hasattr(request, 'meta') and request.meta else False,
                'reasoning_hint_dropped': response.metadata.get('reasoning_hint_dropped', False) if hasattr(response, 'metadata') else False,
                'thinking_hint_dropped': response.metadata.get('thinking_hint_dropped', False) if hasattr(response, 'metadata') else False,
                
                # Circuit breaker and pacing
                'circuit_breaker_status': response.metadata.get('circuit_breaker_status', 'closed') if hasattr(response, 'metadata') else 'closed',
                'circuit_breaker_open_count': self._cb_open_count,
                'router_pacing_delay': response.metadata.get('router_pacing_delay', False) if hasattr(response, 'metadata') else False,
                
                
        # Direct Gemini allowlist (router is SSoT)
        # is_gemini_model = str(request.model).startswith(("publishers/google/models/gemini-", "models/gemini-", "gemini-"))
        # if request.vendor == "gemini_direct" or (request.vendor == "vertex" and USE_GEMINI_DIRECT and is_gemini_model):
            # allowed_direct_csv = os.getenv("ALLOWED_GEMINI_DIRECT_MODELS", "")
            # if allowed_direct_csv.strip():
                # allowed_direct = { _bare_gemini_id(x.strip()) for x in allowed_direct_csv.split(",") if x.strip() }
                # if _bare_gemini_id(request.model) not in allowed_direct:
                    # raise ValueError(
                        # f"Model not allowed for direct Gemini: {request.model}. "
                        # f"Allowed (direct): {sorted(allowed_direct)}"
                    # )
            # If not configured, we fall back implicitly to Vertex allowlist above
# Proxy normalization tracking
                'vantage_policy_before': getattr(request, 'original_vantage_policy', None),
                'vantage_policy_after': getattr(request, 'vantage_policy', 'ALS_ONLY'),
                'proxies_normalized': getattr(request, 'proxy_normalization_applied', False),
                
                # Model info
                'model_fingerprint': response.model_fingerprint if hasattr(response, 'model_fingerprint') else None,
                'normalized_model': request.model,
                'model_adjusted_for_grounding': request.metadata.get('model_adjusted_for_grounding', False) if hasattr(request, 'metadata') else False,
                'original_model': request.metadata.get('original_model') if hasattr(request, 'metadata') else None,
                
                # Feature flags for A/B testing
                'feature_flags': response.metadata.get('feature_flags') if hasattr(response, 'metadata') else {},
                'runtime_flags': response.metadata.get('runtime_flags') if hasattr(response, 'metadata') else {},
                
                # Citation metrics
                'citations_count': 0,  # Will be updated below
                'anchored_citations_count': response.metadata.get('anchored_citations_count', 0) if hasattr(response, 'metadata') else 0,
                'unlinked_sources_count': response.metadata.get('unlinked_sources_count', 0) if hasattr(response, 'metadata') else 0,
                'required_pass_reason': response.metadata.get('required_pass_reason') if hasattr(response, 'metadata') else None,
                
                # Evidence availability flag
                'grounded_evidence_unavailable': False,  # Will be set below if grounded but no anchored citations
                
                # Additional telemetry
                'web_search_count': response.metadata.get('web_search_count', 0) if hasattr(response, 'metadata') else 0,
                'web_grounded': response.metadata.get('web_grounded', False) if hasattr(response, 'metadata') else False,
                'synthesis_step_used': response.metadata.get('synthesis_step_used', False) if hasattr(response, 'metadata') else False,
                'extraction_path': response.metadata.get('extraction_path') if hasattr(response, 'metadata') else None,
                
                # Usage telemetry (pass through from adapters)
                'usage': response.metadata.get('usage') if hasattr(response, 'metadata') else None,
                'finish_reason': response.metadata.get('finish_reason') if hasattr(response, 'metadata') else None,
                
                # Thinking budget telemetry
                'thinking_budget_tokens': request.metadata.get('thinking_budget_tokens') if hasattr(request, 'metadata') else None
            }
            
            # Cheap derived metric for dashboards - citations count
            try:
                meta_json['citations_count'] = len(response.citations) if hasattr(response, 'citations') and isinstance(response.citations, list) else 0
            except Exception:
                meta_json['citations_count'] = 0
            
            # Set grounded_evidence_unavailable flag when grounded but no anchored citations
            if response.grounded_effective and meta_json['anchored_citations_count'] == 0:
                meta_json['grounded_evidence_unavailable'] = True
            
            # Log comprehensive telemetry
            logger.info(
                "LLM telemetry: vendor=%s model=%s grounded_requested=%s grounded_effective=%s "
                "als_present=%s tool_count=%s response_api=%s region=%s",
                request.vendor, request.model, request.grounded, response.grounded_effective,
                meta_json['als_present'], meta_json['tool_call_count'],
                meta_json['response_api'], meta_json['region']
            )
            
            # Persist comprehensive telemetry with metadata
            telemetry = LLMTelemetry(
                vendor=request.vendor,
                model=request.model,
                grounded=request.grounded,
                grounded_effective=response.grounded_effective,
                json_mode=request.json_mode,
                latency_ms=response.latency_ms,
                prompt_tokens=response.usage.get('prompt_tokens', 0),
                completion_tokens=response.usage.get('completion_tokens', 0),
                total_tokens=response.usage.get('total_tokens', 0),
                success=response.success,
                error_type=response.error_type,
                template_id=request.template_id,
                run_id=request.run_id,
                meta=meta_json  # Store rich metadata in JSONB column
            )
            
            # Log for debugging
            import json
            logger.debug(f"Telemetry metadata: {json.dumps(meta_json)}")
            
            session.add(telemetry)
            await session.flush()
            
        except Exception as e:
            # Log but don't fail the request
            logger.error(f"Failed to emit telemetry: {e}")
    
    # REMOVED: Shadow validate_model that differs from centralized validator
    # Use app.llm.models.validate_model instead
    
    def get_vendor_for_model(self, model: str) -> Optional[str]:
        """
        Infer vendor from model name (supports fully-qualified Vertex IDs)
        
        Args:
            model: Model identifier
            
        Returns:
            Vendor name or None if unknown
        """
        if not model:
            return None
