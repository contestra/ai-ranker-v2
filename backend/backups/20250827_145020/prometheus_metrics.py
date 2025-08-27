# prometheus_metrics.py
"""
Prometheus metrics for auth/proxy/LLM health + a /metrics endpoint.
- Minimal label cardinality
- Safe to mount in FastAPI
"""

from __future__ import annotations
from typing import Dict, Any, Optional

from prometheus_client import CollectorRegistry, Gauge, Histogram, Counter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
try:
    from fastapi import APIRouter
    from starlette.responses import Response
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore

# Single process registry (keep it simple)
REGISTRY = CollectorRegistry()

# --- Metrics ---

# Auth
AUTH_SECONDS_REMAINING = Gauge(
    "contestra_auth_token_seconds_remaining",
    "Seconds until current Google auth token expiry (if known)",
    ["auth_mode"],
    registry=REGISTRY,
)

AUTH_STATUS = Gauge(
    "contestra_auth_status",
    "Auth status flag (1 for current status label, 0 otherwise)",
    ["status"],  # ok|warn|error
    registry=REGISTRY,
)

# Proxy
PROXY_MODE = Gauge(
    "contestra_proxy_mode",
    "Proxy mode (direct=0, backbone=1, rotating=2, unknown=-1)",
    [],
    registry=REGISTRY,
)

PROXY_RTT_MS = Gauge(
    "contestra_proxy_rtt_ms",
    "Proxy probe RTT in milliseconds",
    ["service", "probe"],  # ipify|icanhazip|ifconfig ; first|second|secondary
    registry=REGISTRY,
)

# LLM
LLM_LATENCY_MS = Histogram(
    "contestra_llm_latency_ms",
    "LLM end-to-end request latency in milliseconds",
    ["vendor", "path", "proxied"],  # path: sdk|genai|direct ; proxied: true|false
    # buckets: 25ms .. 120s+
    buckets=(25, 50, 100, 200, 400, 800, 1600, 3000, 6000, 12000, 30000, 60000, 120000),
    registry=REGISTRY,
)

LLM_RATE_LIMITS = Counter(
    "contestra_llm_rate_limit_events_total",
    "Count of LLM 429 rate-limit events observed",
    ["vendor"],
    registry=REGISTRY,
)

# --- Update helpers ---

_STATUS_VALUES = {"ok": 0, "warn": 1, "error": 2}
_PROXY_VALUES = {"direct": 0, "backbone": 1, "rotating": 2, "unknown": -1}

def update_from_auth(payload: Dict[str, Any]) -> None:
    """
    payload: model of /health/auth response
    Expected keys: auth_mode, status, seconds_remaining
    """
    try:
        auth_mode = str(payload.get("auth_mode", "unknown"))
        status = str(payload.get("status", "warn"))
        seconds_remaining = payload.get("seconds_remaining")
        # Reset status flags to 0, then set the active one to 1
        for s in ("ok", "warn", "error"):
            AUTH_STATUS.labels(status=s).set(1.0 if s == status else 0.0)
        if seconds_remaining is not None:
            AUTH_SECONDS_REMAINING.labels(auth_mode=auth_mode).set(float(seconds_remaining))
    except Exception:
        # Never raise from metrics
        pass

def update_from_proxy(payload: Dict[str, Any]) -> None:
    """
    payload: model of /health/proxy response
    Expected keys: mode_guess, rtt_ms (map), primary_service, errors
    """
    try:
        mode = str(payload.get("mode_guess", "unknown"))
        mode_val = _PROXY_VALUES.get(mode, -1)
        PROXY_MODE.set(float(mode_val))
        
        # RTT metrics
        rtt_ms = payload.get("rtt_ms") or {}
        primary_service = str(payload.get("primary_service", "ipify"))
        secondary_service = str(payload.get("secondary_service", "icanhazip"))
        
        if rtt_ms.get("first") is not None:
            PROXY_RTT_MS.labels(service=primary_service, probe="first").set(float(rtt_ms["first"]))
        if rtt_ms.get("second") is not None:
            PROXY_RTT_MS.labels(service=primary_service, probe="second").set(float(rtt_ms["second"]))
        if rtt_ms.get("secondary") is not None:
            PROXY_RTT_MS.labels(service=secondary_service, probe="secondary").set(float(rtt_ms["secondary"]))
    except Exception:
        pass

def observe_llm(payload: Dict[str, Any]) -> None:
    """
    payload: model of /health/llm response
    Expected keys: vendor, duration_ms, details.path, proxy_env_masked or proxy_mode_hint
    """
    try:
        vendor = str(payload.get("vendor", "unknown"))
        duration_ms = payload.get("duration_ms")
        details = payload.get("details") or {}
        path = str(details.get("path", "direct"))
        
        # Determine if proxied
        proxy_env = payload.get("proxy_env_masked") or {}
        proxied = "true" if any(proxy_env.get(k) for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY")) else "false"
        
        if duration_ms is not None:
            LLM_LATENCY_MS.labels(vendor=vendor, path=path, proxied=proxied).observe(float(duration_ms))
    except Exception:
        pass

def inc_rate_limit(vendor: str) -> None:
    """
    Call this when you catch a 429 rate limit from vendor.
    """
    try:
        LLM_RATE_LIMITS.labels(vendor=vendor).inc()
    except Exception:
        pass

# --- FastAPI route ---

if APIRouter is not None:
    metrics_router = APIRouter()
    
    @metrics_router.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        """
        Prometheus metrics endpoint.
        """
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
else:
    metrics_router = None  # type: ignore