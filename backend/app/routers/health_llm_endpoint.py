# health_llm_endpoint.py
"""
FastAPI endpoint: /health/llm
- Executes a tiny (~50 token) LLM call against OpenAI or Vertex
- Returns route metadata similar to your [LLM_ROUTE] plus duration/usage
- Honors environment proxies (trust_env=True) and supports a scoped SDK env-proxy for Vertex
"""
from __future__ import annotations

import os, time, traceback
from typing import Optional, Literal, Dict, Any
from contextlib import contextmanager
from urllib.parse import urlsplit

from fastapi import APIRouter, Query
from pydantic import BaseModel

# Import our existing adapters instead of raw clients
try:
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.adapters.vertex_adapter import VertexAdapter
    from app.llm.types import LLMRequest, VantagePolicy
except Exception as e:
    print(f"Warning: Could not import adapters: {e}")
    OpenAIAdapter, VertexAdapter, LLMRequest, VantagePolicy = None, None, None, None

router = APIRouter()


def _mask(uri: Optional[str]) -> Optional[str]:
    if not uri:
        return None
    try:
        p = urlsplit(uri)
        user = p.username or ""
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        return f"{p.scheme}://{user}:***@{host}{port}"
    except Exception:
        return "<masked>"


class LLMHealth(BaseModel):
    status: Literal["ok", "warn", "error"]
    vendor: Literal["openai", "vertex"]
    grounded: bool
    vantage_policy: Literal["NONE", "ALS_ONLY", "PROXY_ONLY", "ALS_PLUS_PROXY"]
    proxy_mode_hint: Optional[Literal["direct", "backbone", "rotating"]] = None
    proxy_env_masked: Dict[str, Optional[str]]
    sdk_env_proxy: bool = False
    cc: Optional[str] = None
    model: Optional[str] = None
    streaming: bool = False
    timeouts_s: Dict[str, int] = {"read": 30, "total": 30}
    duration_ms: Optional[int] = None
    usage: Dict[str, Optional[int]] = {"input_tokens": None, "output_tokens": None}
    finish_reason: Optional[str] = None
    text_preview: Optional[str] = None
    error: Optional[str] = None
    details: Dict[str, Any] = {}


@router.get("/health/llm", response_model=LLMHealth)
async def health_llm(
    vendor: Literal["openai", "vertex"] = Query("openai"),
    grounded: bool = Query(False),
    cc: Optional[str] = Query(None, min_length=2, max_length=2, description="ALS country code, e.g., US/DE"),
    proxy_mode_hint: Optional[Literal["direct", "backbone", "rotating"]] = Query(None),
    sdk_env_proxy: bool = Query(False, description="Use per-run env proxy for Vertex SDK path"),
    model: Optional[str] = Query(None),
    max_tokens: int = Query(50, ge=16, le=400),
    timeout_s: int = Query(30, ge=5, le=120),
    streaming: bool = Query(False),
    proxy_uri: Optional[str] = Query(None, description="Optional explicit proxy URI for scoped Vertex SDK calls"),
):
    # Build vantage_policy from ALS (cc) and proxy env presence
    has_proxy = any(os.getenv(k) for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY")) or bool(proxy_uri)
    has_als = bool(cc)
    
    # Determine vantage policy
    if has_als and has_proxy:
        vantage_policy_str = "ALS_PLUS_PROXY"
        vantage_policy_enum = VantagePolicy.ALS_PLUS_PROXY if VantagePolicy else None
    elif has_proxy:
        vantage_policy_str = "PROXY_ONLY"
        vantage_policy_enum = VantagePolicy.PROXY_ONLY if VantagePolicy else None
    elif has_als:
        vantage_policy_str = "ALS_ONLY"
        vantage_policy_enum = VantagePolicy.ALS_ONLY if VantagePolicy else None
    else:
        vantage_policy_str = "NONE"
        vantage_policy_enum = VantagePolicy.NONE if VantagePolicy else None

    proxy_env_masked = {
        "HTTPS_PROXY": _mask(os.getenv("HTTPS_PROXY")),
        "HTTP_PROXY": _mask(os.getenv("HTTP_PROXY")),
        "ALL_PROXY": _mask(os.getenv("ALL_PROXY")),
        "NO_PROXY": os.getenv("NO_PROXY") or None,
    }

    # Simple prompts for health check
    messages = []
    
    # Add ALS if needed
    if cc and vantage_policy_enum in [VantagePolicy.ALS_ONLY, VantagePolicy.ALS_PLUS_PROXY]:
        if cc == "US":
            messages.append({"role": "system", "content": "You are in the United States."})
        elif cc == "DE":
            messages.append({"role": "system", "content": "You are in Germany."})
    
    messages.append({"role": "user", "content": f"Health check: Respond with 'OK {cc or 'WORLD'}' and nothing else."})

    t0 = time.perf_counter()
    result = LLMHealth(
        status="error", vendor=vendor, grounded=grounded, vantage_policy=vantage_policy_str,
        proxy_mode_hint=proxy_mode_hint, proxy_env_masked=proxy_env_masked,
        sdk_env_proxy=sdk_env_proxy, cc=cc, model=model, streaming=streaming,
        timeouts_s={"read": timeout_s, "total": timeout_s},
    )

    try:
        # Use our existing adapters for consistency
        if not OpenAIAdapter or not VertexAdapter or not LLMRequest:
            raise RuntimeError("Adapters not available - check imports")
        
        # Build LLM request
        use_model = model or (os.getenv("OPENAI_MODEL", "gpt-5") if vendor == "openai" else os.getenv("VERTEX_MODEL", "gemini-2.5-pro"))
        
        request = LLMRequest(
            vendor=vendor,
            model=use_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
            grounded=grounded,
            vantage_policy=vantage_policy_enum,
            country_code=cc
        )
        
        # Select adapter
        if vendor == "openai":
            adapter = OpenAIAdapter()
        else:
            adapter = VertexAdapter()
            # Set SDK env proxy flag if requested
            if sdk_env_proxy and proxy_uri:
                os.environ['VERTEX_PROXY_VIA_SDK'] = 'true'
                # Note: The adapter will handle the proxy_uri internally
        
        # Execute health check
        response = await adapter.complete(request, timeout=timeout_s)
        
        duration_ms = int((time.perf_counter() - t0) * 1000)
        
        # Extract results
        result.status = "ok" if response.content else "warn"
        result.duration_ms = duration_ms
        result.text_preview = (response.content or "")[:100]
        result.model = use_model
        
        # Extract usage if available
        if hasattr(response, 'usage') and response.usage:
            result.usage = {
                "input_tokens": response.usage.get("prompt_tokens") or response.usage.get("input_tokens"),
                "output_tokens": response.usage.get("completion_tokens") or response.usage.get("output_tokens")
            }
        
        # Extract metadata
        if hasattr(response, 'metadata') and response.metadata:
            result.details = {
                "proxy_mode": response.metadata.get("proxy_mode"),
                "grounded_effective": response.metadata.get("grounded_effective", grounded),
                "path": "sdk" if sdk_env_proxy else "direct"
            }
            
            # Update proxy mode hint from actual response
            if response.metadata.get("proxy_mode"):
                result.proxy_mode_hint = response.metadata.get("proxy_mode")
        
        # Check for grounding effectiveness
        if grounded and hasattr(response, 'grounded_effective'):
            if not response.grounded_effective:
                result.status = "warn"
                result.details["warning"] = "Grounding requested but not effective"
        
    except Exception as e:
        result.status = "error"
        result.error = str(e)[:500]
        result.duration_ms = int((time.perf_counter() - t0) * 1000)
        result.details["traceback"] = traceback.format_exc()[:1000]
        
        # Check for rate limit error and increment counter
        if "429" in str(e) or "rate limit" in str(e).lower():
            try:
                from app.prometheus_metrics import inc_rate_limit
                inc_rate_limit(vendor)
            except Exception:
                pass
    finally:
        # Clean up SDK env proxy flag
        if sdk_env_proxy:
            os.environ.pop('VERTEX_PROXY_VIA_SDK', None)
    
    # Update Prometheus metrics
    try:
        from app.prometheus_metrics import observe_llm
        observe_llm(result.dict())
    except Exception:
        pass  # Don't fail health check if metrics unavailable
    
    return result