"""
OpenAI Adapter (Live GPT-5 Implementation)
Uses Responses API for GPT-5
"""

import os
import time
import json
import logging
import random
import asyncio
import httpx
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager
from openai import AsyncOpenAI

from app.llm.types import LLMRequest, LLMResponse
from .grounding_detection_helpers import detect_openai_grounding
from app.core.config import get_settings
from app.prometheus_metrics import (
    inc_rate_limit as _inc_rl_metric,
    set_openai_active_concurrency, 
    set_openai_next_slot_epoch,
    inc_stagger_delays, 
    inc_tpm_deferrals
)

# --- Proxy/vantage helpers (Webshare) ---
def _normalize_cc(cc: str) -> str:
    if not cc:
        return "US"
    cc = cc.strip().upper()
    return "GB" if cc == "UK" else cc

def _extract_country_from_request(req) -> str:
    # Try several common spots; fall back to US
    for attr in ("country_code", "country", "locale_country"):
        val = getattr(req, attr, None)
        if isinstance(val, str) and val.strip():
            return _normalize_cc(val)
    # Try nested dict-like fields commonly used for routing
    for field in ("locale", "routing", "meta"):
        obj = getattr(req, field, None)
        if isinstance(obj, dict):
            for k in ("country_code", "country", "cc"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return _normalize_cc(v)
    return "US"

def _should_use_proxy(req) -> bool:
    vp = getattr(req, "vantage_policy", None)
    if not vp:
        meta = getattr(req, "meta", {}) if hasattr(req, "meta") else {}
        vp = meta.get("vantage_policy")
    if not vp:
        return False
    # Handle both enum and string representations
    vp_str = str(vp).upper().replace("VANTAGEPOLICY.", "")
    return vp_str in ("PROXY_ONLY", "ALS_PLUS_PROXY")

def _proxy_connection_mode(req) -> str:
    # 'rotating' (default) or 'backbone'
    # Use backbone for long responses (>2000 tokens) for stability
    max_tokens = getattr(req, "max_tokens", 6000)
    if max_tokens and max_tokens > 2000:
        # Long responses need stable connections
        default_mode = "backbone"
    else:
        # Short responses can use rotating
        default_mode = "rotating"
    
    meta = getattr(req, "meta", None)
    if not meta:
        return default_mode
    return str(meta.get("proxy_connection", default_mode)).lower()

def _build_webshare_proxy_uri(country_code: str, mode: str = "rotating") -> Optional[str]:
    """
    Build an HTTP CONNECT proxy URI for Webshare.io using username suffixes:
      Backbone: <USER>-CC
      Rotating: <USER>-CC-rotate
    """
    user = os.getenv("WEBSHARE_USERNAME")
    pwd = os.getenv("WEBSHARE_PASSWORD")
    host = os.getenv("WEBSHARE_HOST", "p.webshare.io")
    port = os.getenv("WEBSHARE_PORT", "80")
    if not (user and pwd):
        return None
    cc = _normalize_cc(country_code)
    # Webshare format: rotating uses -rotate, backbone uses numbered suffix
    if mode == "rotating":
        suffix = f"{user}-{cc}-rotate"
    else:  # backbone
        suffix = f"{user}-{cc}-1"  # Use -1 for stable backbone connection
    return f"http://{suffix}:{pwd}@{host}:{port}"
# --- end proxy helpers ---

# Provider minimum output tokens requirement
PROVIDER_MIN_OUTPUT_TOKENS = 16

logger = logging.getLogger(__name__)


class _OpenAIRateLimiter:
    """Process-wide rate limiter for OpenAI API calls with sliding window"""
    def __init__(self):
        s = get_settings()
        self._enabled = s.openai_gate_in_adapter
        self._sem = asyncio.Semaphore(max(1, s.openai_max_concurrency))
        self._tpm_limit = int(s.openai_tpm_limit)
        
        # Sliding window for token tracking
        self._window_lock = asyncio.Lock()
        self._window_start = time.time()
        self._tokens_used_this_minute = 0
        self._debt = 0  # Track underestimation debt
        
        # For concurrency tracking
        self._active_lock = asyncio.Lock()
        self._active = 0
        
        # Adaptive multiplier tracking for grounded calls
        self._grounded_ratios = []  # List of (actual/estimated) ratios
        self._grounded_ratios_max = 10  # Keep last 10 ratios
    
    async def await_tpm(self, estimated_tokens):
        """Wait until TPM budget allows next request with sliding window
        
        Args:
            estimated_tokens: Token estimate for this request
        """
        if not self._enabled or not estimated_tokens:
            return
        
        async with self._window_lock:
            now = time.time()
            
            # Reset window if more than 60 seconds have passed
            if now - self._window_start >= 60:
                self._window_start = now
                self._tokens_used_this_minute = self._debt  # Carry over debt
                self._debt = 0
            
            # Check if we have budget
            tokens_needed = estimated_tokens
            if self._tokens_used_this_minute + tokens_needed > self._tpm_limit:
                # Calculate how long to sleep
                time_in_window = now - self._window_start
                time_remaining = 60 - time_in_window
                
                if time_remaining > 0:
                    # Sleep until next window with jitter to prevent thundering herd
                    jitter = random.uniform(0.5, 0.75)  # 500-750ms jitter
                    sleep_time = time_remaining + 0.1 + jitter  # Buffer + jitter
                    logger.info(f"[RL_TPM] Sleeping {sleep_time:.1f}s (used {self._tokens_used_this_minute}/{self._tpm_limit} TPM, jitter={jitter:.3f}s)")
                    inc_tpm_deferrals()
                    await asyncio.sleep(sleep_time)
                    
                    # Reset window after sleep
                    self._window_start = time.time()
                    self._tokens_used_this_minute = self._debt
                    self._debt = 0
            
            # Reserve tokens
            self._tokens_used_this_minute += tokens_needed
            logger.debug(f"[RL_TPM] Reserved {tokens_needed} tokens (total: {self._tokens_used_this_minute}/{self._tpm_limit})")
    
    async def commit_actual_tokens(self, actual_tokens, estimated_tokens, is_grounded=False):
        """Commit actual token usage and track debt
        
        Args:
            actual_tokens: Actual tokens used from response.usage
            estimated_tokens: What we estimated before the call
            is_grounded: Whether this was a grounded request
        """
        if not self._enabled or not actual_tokens:
            return
        
        # Track ratio for grounded calls
        if is_grounded and estimated_tokens > 0:
            ratio = actual_tokens / estimated_tokens
            async with self._window_lock:
                self._grounded_ratios.append(ratio)
                # Keep only last N ratios
                if len(self._grounded_ratios) > self._grounded_ratios_max:
                    self._grounded_ratios.pop(0)
                logger.debug(f"[RL_ADAPTIVE] Grounded ratio {ratio:.2f} (history: {len(self._grounded_ratios)} samples)")
        
        debt = max(0, actual_tokens - estimated_tokens)
        if debt > 0:
            # We underestimated - add debt
            async with self._window_lock:
                self._debt += debt
                logger.info(f"[RL_DEBT] Underestimated by {debt} tokens (total debt: {self._debt})")
    
    def get_grounded_multiplier(self):
        """Get adaptive multiplier for grounded calls based on history"""
        if not self._grounded_ratios:
            return 1.15  # Default multiplier when no history
        
        # Use median of recent ratios, clamped to [1.0, 2.0]
        sorted_ratios = sorted(self._grounded_ratios)
        median_ratio = sorted_ratios[len(sorted_ratios) // 2]
        return max(1.0, min(2.0, median_ratio))
    
    async def acquire_slot(self):
        """Acquire concurrency slot"""
        if self._enabled:
            await self._sem.acquire()
    
    def release_slot(self):
        """Release concurrency slot"""
        if self._enabled:
            self._sem.release()
    
    async def handle_429(self, retry_after=None):
        """Handle rate limit error with exponential backoff
        
        Args:
            retry_after: Seconds to wait from Retry-After header
        """
        if not self._enabled:
            return
        
        async with self._window_lock:
            # Add penalty debt
            self._debt += 1000  # Penalty tokens for hitting limit
            
        if retry_after:
            await asyncio.sleep(retry_after)
        else:
            # Exponential backoff with jitter
            base_delay = 2.0
            jitter = random.random() * 2 - 1  # -1 to 1
            delay = min(30, base_delay * (2 ** random.randint(0, 3))) + jitter
            await asyncio.sleep(delay)
    
    @asynccontextmanager
    async def concurrency(self):
        """Context manager for OpenAI concurrency tracking"""
        if not self._enabled:
            yield
            return
        await self._sem.acquire()
        try:
            async with self._active_lock:
                self._active += 1
                set_openai_active_concurrency(self._active)
            yield
        finally:
            async with self._active_lock:
                self._active = max(0, self._active-1)
                set_openai_active_concurrency(self._active)
            self._sem.release()


# Singleton instance
_RL = _OpenAIRateLimiter()


def _extract_text_from_responses_obj(r) -> str:
    """Robustly extract assistant text from Responses API objects."""
    # 0) canonical fast-path
    txt = getattr(r, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt

    collected: List[str] = []

    def _as_dict(obj):
        # Best-effort: prefer SDK's model_dump_json (typed models), then .json(), else dir-walk
        try:
            if hasattr(obj, "model_dump_json"):
                return json.loads(obj.model_dump_json())
        except Exception:
            pass
        try:
            if hasattr(obj, "json"):
                return json.loads(obj.json())
        except Exception:
            pass
        return None

    # 1) Try typed access first: r.output[*].content[*]
    out = getattr(r, "output", None)
    if isinstance(out, list) and out:
        for item in out:
            # Skip reasoning items - they don't contain user-facing text
            item_type = getattr(item, "type", None)
            if item_type == "reasoning":
                continue
            
            # Handle message items which contain the actual text
            if item_type != "message":
                continue
                
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for blk in content:
                    # Check block type - we want output_text or redacted_text blocks
                    blk_type = getattr(blk, "type", None) or (blk.get("type") if isinstance(blk, dict) else None)
                    if blk_type not in {None, "text", "output_text", "redacted_text"}:
                        continue
                    
                    # typed class: blk.text or blk.text.value
                    t = getattr(blk, "text", None)
                    if isinstance(t, str) and t.strip():
                        collected.append(t)
                        continue
                    if hasattr(t, "value") and isinstance(t.value, str) and t.value.strip():
                        collected.append(t.value)
                        continue
                    # dict-shaped block
                    if isinstance(blk, dict):
                        t = blk.get("text")
                        if isinstance(t, str) and t.strip():
                            collected.append(t)
                            continue
                        if isinstance(t, dict):
                            v = t.get("value")
                            if isinstance(v, str) and v.strip():
                                collected.append(v)
                                continue

    if collected:
        return "\n".join(collected).strip()

    # 2) As a last resort, inspect dict form
    as_dict = _as_dict(r)
    if isinstance(as_dict, dict):
        try:
            for item in as_dict.get("output", []):
                # Skip reasoning items in dict form too
                if item.get("type") == "reasoning":
                    continue
                    
                # Handle message items explicitly
                if item.get("type") == "message":
                    for blk in item.get("content", []):
                        if blk.get("type") in {"text", "output_text", "redacted_text"}:
                            t = blk.get("text")
                            if isinstance(t, str) and t.strip():
                                collected.append(t)
                            elif isinstance(t, dict) and isinstance(t.get("value"), str) and t["value"].strip():
                                collected.append(t["value"])
                else:
                    # Generic content extraction
                    for blk in item.get("content", []):
                        t = blk.get("text")
                        if isinstance(t, str) and t.strip():
                            collected.append(t)
                        elif isinstance(t, dict) and isinstance(t.get("value"), str) and t["value"].strip():
                            collected.append(t["value"])
            if collected:
                return "\n".join(collected).strip()
        except Exception:
            pass

    # 3) Still nothing — log a compact dump
    safe_dump = None
    try:
        safe_dump = as_dict or _as_dict(r)
    except Exception:
        safe_dump = None
    logger.info("Responses extract: no text found. dump=%s",
                (json.dumps(safe_dump)[:2000] if isinstance(safe_dump, dict) else "unavailable"))
    return ""


def _split_messages(messages: List[Dict[str, Any]]) -> tuple[Optional[str], str]:
    """Split messages into instructions (system) and input (user) for Responses API"""
    sys_parts, user_parts = [], []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            sys_parts.append(content)
        elif role == "assistant":
            # Assistant messages become part of conversation context
            user_parts.append(f"Assistant: {content}")
        else:  # user
            user_parts.append(content)
    
    instructions = "\n\n".join(p for p in sys_parts if p).strip() or None
    user_input = "\n".join(p for p in user_parts if p).strip() or ""
    
    # Ensure there's always user input to trigger text generation
    if not user_input:
        user_input = "Please answer now in plain text."
    
    return instructions, user_input


def _is_empty(s: str | None) -> bool:
    """Check if string is empty or whitespace only"""
    return not s or not s.strip()


def _nudge_plain_text(user_input: str) -> str:
    """Add explicit instruction for plain text output"""
    return (user_input + "\n\n"
            "Answer in plain, concise text. Do not include tool plans or hidden reasoning.").strip()


def _had_reasoning_only(response) -> bool:
    """Check if response contains only reasoning items with no text"""
    output = getattr(response, "output", None)
    if not output:
        return False
    
    # Check if ALL items are reasoning type
    for item in output:
        item_type = getattr(item, "type", None)
        if not item_type:
            # Check dict form
            if isinstance(item, dict):
                item_type = item.get("type")
        if item_type != "reasoning":
            return False  # Found non-reasoning item
    
    # All items were reasoning type
    return True


class OpenAIAdapter:
    """Live OpenAI adapter using Responses API for GPT-5"""
    
    def __init__(self):
        # API Key required
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY required - set in backend/.env")
        
        # Configure timeouts
        connect_s = float(os.getenv("OPENAI_CONNECT_TIMEOUT_MS", "2000")) / 1000.0
        read_s = float(os.getenv("OPENAI_READ_TIMEOUT_MS", "60000")) / 1000.0
        
        # Create client with timeouts
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(
                connect=connect_s,
                read=read_s,
                write=read_s,
                pool=read_s
            )
        )
        
        # Parse and clean allowlist
        raw_allow = os.getenv("OPENAI_MODELS_ALLOWLIST", "gpt-5").split(",")
        self.allowlist = {m.strip() for m in raw_allow if m.strip()}
    
    def _detect_grounding(self, response) -> tuple[bool, int]:
        """
        Detect web search usage in Responses API output.
        Delegates to helper for testability.
        """
        return detect_openai_grounding(response)
    
    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        """
        Execute OpenAI API call with GPT-5 specific requirements.
        Uses Responses API with adaptive error handling and retry logic.
        
        Args:
            request: LLM request
            timeout: Timeout in seconds (60 for ungrounded, 120 for grounded)
        """
        # Calculate token estimate for rate limiting
        # Rough estimate: ~4 chars per token for input
        input_chars = sum(len(m.get("content", "")) for m in request.messages)
        estimated_input_tokens = input_chars // 4 + 100  # Add buffer for role/structure
        
        # Output tokens from request
        max_output_tokens = getattr(request, 'max_tokens', 2048)
        
        # Total estimate with safety margin
        estimated_tokens = int((estimated_input_tokens + max_output_tokens) * 1.2)
        
        # Add extra for grounded requests (search overhead) using adaptive multiplier
        if request.grounded:
            grounded_multiplier = _RL.get_grounded_multiplier()
            estimated_tokens = int(estimated_tokens * grounded_multiplier)
            logger.debug(f"[RL_ADAPTIVE] Using grounded multiplier: {grounded_multiplier:.2f}")
        
        # Check TPM budget before acquiring slot
        try:
            await _RL.await_tpm(estimated_tokens)
        except Exception as _e:
            logger.warning(f"[RL_WARN] Rate limiting issue: {_e}")
            raise
        
        # --- Per-run proxy wiring (Webshare) ---
        _proxy_client = None
        _client_for_call = self.client
        
        # Initialize tracking variables for logging/telemetry
        vantage_policy = str(getattr(request, 'vantage_policy', 'NONE')).upper().replace("VANTAGEPOLICY.", "")
        proxy_mode = None
        country_code = _extract_country_from_request(request) if hasattr(request, 'country_code') else None
        masked_proxy = None
        connect_s, read_s, total_s = 30, 60, timeout  # Default timeouts
        
        # Initialize metadata for error case
        metadata = {}
        
        try:
            proxy_needed = _should_use_proxy(request)
            
            # Increase timeout when using proxy
            if proxy_needed:
                timeout = max(timeout, 300)  # Ensure at least 300s for proxy requests
            if proxy_needed:
                country_code = _extract_country_from_request(request)
                proxy_mode = _proxy_connection_mode(request)
                _proxy_uri = _build_webshare_proxy_uri(country_code, proxy_mode)
                if _proxy_uri:
                    # Create masked proxy URL for logging
                    from urllib.parse import urlsplit
                    p = urlsplit(_proxy_uri)
                    masked_proxy = f"{p.scheme}://{p.username}:***@{p.hostname}:{p.port or ''}"
                    
                    # Update timeout values for telemetry
                    connect_s, read_s, total_s = 60, 240, 300
                    
                    # httpx uses 'proxy' not 'proxies'
                    # Use extended timeouts for proxy connections
                    # Long responses need much longer read timeouts
                    proxy_timeout = httpx.Timeout(
                        timeout=total_s,
                        connect=connect_s,
                        read=read_s,
                        write=60.0      # Write timeout: 1 minute
                    )
                    _proxy_client = httpx.AsyncClient(proxy=_proxy_uri, timeout=proxy_timeout)
                    # Build a per-run OpenAI client that uses the proxied transport
                    _client_for_call = AsyncOpenAI(
                        api_key=os.getenv('OPENAI_API_KEY'),
                        timeout=300.0,  # Match the proxy client timeout
                        http_client=_proxy_client,
                    )
        except Exception as _e:
            logger.warning(f"Proxy setup failed; proceeding without proxy: {_e}")
        # --- end proxy wiring ---
        
        # Enforce model allowlist
        if request.model not in self.allowlist:
            raise ValueError(
                f"MODEL_NOT_ALLOWED: {request.model} not in {sorted(self.allowlist)}"
            )
        
        # Split messages properly for Responses API
        instructions, user_input = _split_messages(request.messages)
        
        # Token configuration with environment defaults
        DEFAULT_MAX = int(os.getenv("OPENAI_DEFAULT_MAX_OUTPUT_TOKENS", "6000"))
        CAP = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS_CAP", "6000"))
        
        requested_tokens = request.max_tokens or DEFAULT_MAX
        effective_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, requested_tokens))
        
        # Build base parameters
        params: Dict[str, Any] = {
            "model": request.model,
            "input": user_input,
            "max_output_tokens": effective_tokens,
        }
        
        # Add instructions if present
        if instructions:
            params["instructions"] = instructions
        
        # Add grounding tools if requested
        grounded_effective = False
        tool_call_count = 0
        if request.grounded:
            tool_type = os.getenv("OPENAI_GROUNDING_TOOL", "web_search")
            params["tools"] = [{"type": tool_type}]
            params["tool_choice"] = os.getenv("OPENAI_TOOL_CHOICE", "auto")
            
            # Add guardrail instruction to ensure final message after tools
            grounding_instruction = (
                "After finishing any tool calls, you MUST produce a final assistant message "
                "containing the answer in plain text. Limit yourself to at most 2 web searches before answering."
            )
            if instructions:
                params["instructions"] = f"{instructions}\n\n{grounding_instruction}"
            else:
                params["instructions"] = grounding_instruction
        
        # GPT-5 specific parameters
        if request.model == "gpt-5":
            # MANDATORY: temperature=1.0 for GPT-5, especially with tools
            params["temperature"] = 1.0
        else:
            if request.temperature is not None:
                params["temperature"] = request.temperature
        
        # JSON mode
        if request.json_mode:
            params["response_format"] = {"type": "json_object"}
        else:
            params["text"] = {"verbosity": "medium"}
        
        # Track timing and retries
        t0 = time.perf_counter()
        retry_mode = "none"
        attempts = 0
        reasoning_only = False
        metadata = {
            "max_output_tokens_requested": requested_tokens,
            "max_output_tokens_effective": effective_tokens,
            "temperature_used": params.get("temperature"),
        }
        
        # [LLM_ROUTE] Log before API call
        route_info = {
            "vendor": "openai",
            "model": request.model,
            "vantage_policy": vantage_policy,
            "proxy_mode": proxy_mode if proxy_mode else "direct",
            "country": country_code if country_code else "none",
            "grounded": request.grounded,
            "max_tokens": effective_tokens,
            "timeouts_s": {"connect": connect_s, "read": read_s, "total": total_s}
        }
        logger.info(f"[LLM_ROUTE] {json.dumps(route_info)}")
        
        # Internal call function with error handling and timeout
        
        async def _call(call_params):
            """
            Robust call with parameter sanitation, 429 backoff/retry, and timeout logging.
            """
            max_attempts = int(os.getenv("OPENAI_RETRY_MAX_ATTEMPTS", "5"))
            base_backoff = float(os.getenv("OPENAI_BACKOFF_BASE_SECONDS", "2"))
            attempt = 0
            while True:
                attempt += 1
                try:
                    client_with_timeout = _client_for_call.with_options(timeout=timeout)
                    return await client_with_timeout.responses.create(
                        **{k: v for k, v in call_params.items() if v is not None}
                    )
                except Exception as e:
                    msg = str(e)
                    low = msg.lower()
                    # Parameter sanitation
                    if "unexpected keyword argument" in msg or "unknown parameter" in low:
                        import re
                        m = re.search(r"'(\w+)'", msg)
                        if m:
                            bad_param = m.group(1)
                            logger.info(f"Removing unsupported parameter: {bad_param}")
                            call_params = dict(call_params)
                            call_params.pop(bad_param, None)
                            attempt -= 1
                            continue
                    # 429 backoff
                    if "rate limit" in low or "429" in low or "quota" in low:
                        try:
                            _inc_rl_metric("openai")
                        except Exception:
                            pass
                        if attempt >= max_attempts:
                            raise RuntimeError(f"OPENAI_RATE_LIMIT_EXHAUSTED: {msg[:160]}") from e
                        
                        # Use rate limiter's 429 handler
                        retry_after = None
                        try:
                            retry_after = getattr(e, "retry_after", None)
                            if retry_after is not None:
                                retry_after = float(retry_after)
                        except Exception:
                            retry_after = None
                        
                        # Let rate limiter handle the backoff and debt
                        await _RL.handle_429(retry_after)
                        continue
                    is_timeout = "timeout" in low or "timed out" in low
                    timeout_info = {
                        "vendor": "openai",
                        "model": request.model,
                        "vantage_policy": vantage_policy,
                        "proxy_mode": proxy_mode if proxy_mode else "direct",
                        "country": country_code if country_code else "none",
                        "grounded": request.grounded,
                        "max_tokens": call_params.get("max_output_tokens", effective_tokens),
                        "timeouts_s": {"connect": connect_s, "read": read_s, "total": total_s},
                        "error_type": "timeout" if is_timeout else "error",
                        "error_msg": msg[:200]
                    }
                    logger.error(f"[LLM_TIMEOUT] {json.dumps(timeout_info)}")
                    raise RuntimeError(f"OPENAI_CALL_FAILED: {msg[:160]}") from e

        
        # First attempt (with concurrency limiting)
        async with _RL.concurrency():
            response = await _call(params)
        content = _extract_text_from_responses_obj(response)
        
        # Detect grounding if tools were used
        if request.grounded:
            grounded_effective, tool_call_count = self._detect_grounding(response)
        
        # Check if initial response had reasoning only
        if _had_reasoning_only(response):
            reasoning_only = True
        
        # First retry - only if NOT in JSON mode and content is empty
        if _is_empty(content) and "response_format" not in params:
            attempts = 1
            metadata["retry_reason"] = "reasoning_only" if reasoning_only else "no_text"
            metadata["reasoning_only_detected"] = reasoning_only
            
            # Bump token budget and add text nudge
            bumped_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, effective_tokens * 2))
            retry_params = dict(params)
            retry_params["max_output_tokens"] = bumped_tokens
            retry_params["input"] = _nudge_plain_text(user_input)
            retry_params["text"] = {"verbosity": "low"}
            
            try:
                r2 = await _call(retry_params)
                content2 = _extract_text_from_responses_obj(r2)
                if not _is_empty(content2):
                    content = content2
                    response = r2
                    effective_tokens = bumped_tokens
                    retry_mode = "responses_retry1"
                    reasoning_only = _had_reasoning_only(r2)
                    metadata["max_output_tokens_effective"] = bumped_tokens
            except Exception as e:
                logger.warning(f"First retry failed: {e}")
        
        # Second retry - only if still empty AND not in JSON mode
        if _is_empty(content) and "response_format" not in params:
            attempts = 2
            
            # Triple token budget and add stronger text instruction
            final_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, effective_tokens * 3))
            retry2_params = dict(params)
            retry2_params["max_output_tokens"] = final_tokens
            retry2_params["input"] = _nudge_plain_text(user_input) + " Respond with plain text only."
            retry2_params["text"] = {"verbosity": "low"}
            
            try:
                r3 = await _call(retry2_params)
                content3 = _extract_text_from_responses_obj(r3)
                if not _is_empty(content3):
                    content = content3
                    response = r3
                    effective_tokens = final_tokens
                    retry_mode = "responses_retry2"
                    reasoning_only = _had_reasoning_only(r3)
                    metadata["max_output_tokens_effective"] = final_tokens
            except Exception as e:
                logger.warning(f"Second retry failed: {e}")
        
        # Calculate final latency
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Extract usage - ChatGPT fix: flatten response.usage and sum numeric keys ending with _tokens
        usage = {}
        usage_source = "absent"
        if hasattr(response, 'usage'):
            resp_usage = response.usage
            if resp_usage:
                # Extract all token fields (input_tokens, output_tokens, reasoning_tokens)
                input_tokens = getattr(resp_usage, 'input_tokens', 0) or getattr(resp_usage, 'prompt_tokens', 0) or 0
                output_tokens = getattr(resp_usage, 'output_tokens', 0) or getattr(resp_usage, 'completion_tokens', 0) or 0
                reasoning_tokens = getattr(resp_usage, 'reasoning_tokens', 0) or 0
                total_tokens = getattr(resp_usage, 'total_tokens', 0) or (input_tokens + output_tokens + reasoning_tokens)
                
                usage = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "total_tokens": total_tokens
                }
                usage_source = "provider"
                
                # Commit actual token usage to rate limiter
                if total_tokens > 0:
                    await _RL.commit_actual_tokens(total_tokens, estimated_tokens, is_grounded=request.grounded)
        
        # If no usage from provider, use the estimate
        if not usage or usage.get('total_tokens', 0) == 0:
            usage = {
                "input_tokens": estimated_tokens // 3,  # Rough estimate
                "output_tokens": estimated_tokens * 2 // 3,  # Rough estimate
                "reasoning_tokens": 0,
                "total_tokens": estimated_tokens
            }
            usage_source = "estimate"
        
        # Enhanced fallback for grounded empty responses
        if not content and request.grounded:
            # NEVER access response.text - it's a config object, not content!
            # Try model_dump for additional extraction paths
            if hasattr(response, 'model_dump'):
                response_data = response.model_dump()
                
                # Try output_text from dict (backup to typed access)
                if not content:
                    output_text = response_data.get('output_text', '')
                    if isinstance(output_text, str) and output_text.strip():
                        content = output_text.strip()
                        metadata['extraction_path'] = 'output_text_dict'
                
                # Try message blocks from output array
                if not content:
                    for item in response_data.get('output', []) or []:
                        if item.get('type') == 'message':
                            # Extract from content blocks
                            item_content = item.get('content', [])
                            if isinstance(item_content, list):
                                for block in item_content:
                                    if isinstance(block, dict) and block.get('type') in {'output_text', 'redacted_text'}:
                                        text = block.get('text', '')
                                        if isinstance(text, str):
                                            content = text.strip()
                                            metadata['extraction_path'] = 'message_blocks'
                                            break
                            if content:
                                break
            
            if content:
                metadata['grounding_extraction_fallback'] = True
            else:
                # Log extraction failure for debugging
                logger.warning("Failed to extract content from grounded response - all paths exhausted")
                metadata['extraction_path'] = 'none'
                
                # Two-step safety net: If grounding happened but no message, request synthesis
                if grounded_effective and hasattr(response, 'model_dump'):
                    response_data = response.model_dump()
                    has_message = any(item.get('type') == 'message' for item in response_data.get('output', []))
                    
                    if not has_message:
                        metadata['why_no_content'] = 'no_message_items_after_tool_calls'
                        logger.warning("Grounding complete but no message - attempting synthesis step")
                        
                        # Step 2: Synthesis-only request (no tools)
                        # Use same token count as original request (ChatGPT recommendation: finalize_max_tokens = original_max_tokens)
                        synthesis_params = {
                            "model": request.model,
                            "input": user_input,
                            "instructions": (
                                "Based on the web searches just performed, synthesize a final answer to the user's question. "
                                "Provide a clear, concise response. Do not perform any additional searches."
                            ),
                            "max_output_tokens": effective_tokens,  # Same as original (6000 in our case)
                            "temperature": params.get("temperature", 1.0),
                            "text": {"verbosity": "medium"}
                        }
                        
                        try:
                            synthesis_response = await _call(synthesis_params)
                            synthesis_content = _extract_text_from_responses_obj(synthesis_response)
                            if not _is_empty(synthesis_content):
                                content = synthesis_content
                                response = synthesis_response
                                metadata['synthesis_step_used'] = True
                                metadata['extraction_path'] = 'synthesis_fallback'
                                logger.info("Synthesis step successful, content recovered")
                            else:
                                metadata['synthesis_step_failed'] = True
                                logger.error("Synthesis step failed to produce content")
                        except Exception as e:
                            logger.error(f"Synthesis step failed with error: {e}")
                            metadata['synthesis_step_error'] = str(e)
        
        # Get system fingerprint
        sys_fp = getattr(response, "system_fingerprint", None)
        
        # Add complete tracking to metadata
        metadata["retry_mode"] = retry_mode
        metadata["attempts"] = attempts
        metadata["reasoning_only_detected"] = reasoning_only
        metadata["had_text_after_retry"] = not _is_empty(content)
        metadata["response_format"] = params.get("response_format")
        
        # Add proxy telemetry with standardized keys
        if proxy_mode:
            metadata["vantage_policy"] = vantage_policy
            metadata["proxy_mode"] = proxy_mode
            metadata["proxy_country"] = country_code if country_code else "none"
            metadata["proxy_uri_masked"] = masked_proxy if masked_proxy else "none"
            metadata["timeouts_s"] = {
                "connect": connect_s,
                "read": read_s,
                "total": total_s
            }
        
        # Add shape summary to metadata for debugging
        if request.grounded and hasattr(response, 'model_dump'):
            response_data = response.model_dump()
            output_items = response_data.get('output', [])
            
            # Count output types
            type_counts = {}
            for item in output_items:
                item_type = item.get('type', 'unknown')
                type_counts[item_type] = type_counts.get(item_type, 0) + 1
            
            # Get last message content types if exists
            message_items = [item for item in output_items if item.get('type') == 'message']
            last_message_content_types = []
            if message_items:
                last_msg = message_items[-1]
                content_blocks = last_msg.get('content', [])
                last_message_content_types = [
                    block.get('type') for block in content_blocks 
                    if isinstance(block, dict)
                ]
            
            # Count URL citations
            url_citations = 0
            for item in message_items:
                for block in item.get('content', []):
                    if isinstance(block, dict):
                        annotations = block.get('annotations', [])
                        url_citations += sum(
                            1 for a in annotations 
                            if isinstance(a, dict) and a.get('type') == 'url_citation'
                        )
            
            metadata['shape_summary'] = {
                'output_types': type_counts,
                'last_message_content_types': last_message_content_types,
                'url_citations_count': url_citations,
                'extraction_path': metadata.get('extraction_path', 'unknown'),
                'why_no_content': metadata.get('why_no_content')
            }
        
        # Add usage tracking metadata
        metadata['usage_source'] = usage_source
        metadata['estimated_tokens'] = estimated_tokens
        metadata['actual_tokens'] = usage.get('total_tokens', 0)
        
        # Debug logging for grounding
        if request.grounded:
            logger.info(
                "OpenAI Grounding: requested=%s effective=%s tool_calls=%s shape=%s",
                request.grounded, grounded_effective, tool_call_count,
                metadata.get('shape_summary', {})
            )
        
        # Close proxy client if created
        if _proxy_client is not None:
            try:
                await _proxy_client.aclose()
            except Exception:
                pass
        
        # [LLM_RESULT] Log successful response
        result_info = {
            "vendor": "openai",
            "model": request.model,
            "vantage_policy": vantage_policy,
            "proxy_mode": proxy_mode if proxy_mode else "direct",
            "country": country_code if country_code else "none",
            "grounded": request.grounded,
            "grounded_effective": grounded_effective,
            "latency_ms": latency_ms,
            "usage": usage,
            "content_length": len(content) if content else 0,
            "retry_mode": retry_mode,
            "attempts": attempts
        }
        logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
        
        # Build response
        return LLMResponse(
            content=content,
            model_version=getattr(response, 'model', request.model),
            model_fingerprint=sys_fp,
            grounded_effective=grounded_effective,
            usage=usage,
            latency_ms=latency_ms,
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else None,
            success=True,
            vendor="openai",
            model=request.model,
            metadata=metadata
        )
    
    def supports_model(self, model: str) -> bool:
        """Check if model is in allowlist"""
        return model in self.allowlist