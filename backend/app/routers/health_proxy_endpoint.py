# health_proxy_endpoint.py
"""
FastAPI endpoint: /health/proxy
- Echoes observed egress IP twice to detect rotation vs backbone vs direct.
- Cross-checks with a second service.
- Honors environment proxies (HTTPS_PROXY/HTTP_PROXY/ALL_PROXY) via httpx trust_env=True.
"""
from __future__ import annotations

import os
import time
import re
from typing import Optional, Literal, Dict, Any

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()

IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

PRIMARY_ENDPOINTS = {
    "ipify": "https://api.ipify.org",
    "icanhazip": "https://ipv4.icanhazip.com",
    "ifconfig": "https://ifconfig.me/ip",
}
SECONDARY_ENDPOINTS = {
    "ipify": "https://api.ipify.org",
    "icanhazip": "https://ipv4.icanhazip.com",
    "ifconfig": "https://ifconfig.me/ip",
}


def _mask(uri: Optional[str]) -> Optional[str]:
    if not uri:
        return None
    try:
        from urllib.parse import urlsplit
        p = urlsplit(uri)
        user = p.username or ""
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        return f"{p.scheme}://{user}:***@{host}{port}"
    except Exception:
        return "<masked>"


class ProxyHealth(BaseModel):
    status: Literal["ok", "warn", "error"]
    mode_guess: Literal["direct", "backbone", "rotating", "unknown"]
    primary_service: str
    first_ip: Optional[str]
    second_ip: Optional[str]
    match_stable: Optional[bool]
    secondary_service: str
    secondary_ip: Optional[str]
    proxy_env: Dict[str, Optional[str]]
    timeouts_ms: Dict[str, int]
    rtt_ms: Dict[str, Optional[int]]
    errors: Dict[str, Optional[str]]
    suggestion: Optional[str] = None


@router.get("/health/proxy", response_model=ProxyHealth)
def health_proxy(
    timeout_ms: int = Query(5000, ge=500, le=30000),
    sleep_ms: int = Query(800, ge=0, le=10000),
    primary: str = Query("ipify", regex="^(ipify|icanhazip|ifconfig)$"),
    secondary: str = Query("icanhazip", regex="^(ipify|icanhazip|ifconfig)$"),
) -> ProxyHealth:
    connect = read = timeout_ms / 1000.0
    client = httpx.Client(
        timeout=httpx.Timeout(connect=connect, read=read, write=read, pool=read),
        http2=False,  # safer through many HTTP proxies
        follow_redirects=True,
        trust_env=True,  # use env proxies if present
    )

    errors: Dict[str, Optional[str]] = {"first": None, "second": None, "secondary": None}
    rtt: Dict[str, Optional[int]] = {"first": None, "second": None, "secondary": None}

    def fetch(url: str, key: str) -> Optional[str]:
        t0 = time.perf_counter()
        try:
            resp = client.get(url)
            resp.raise_for_status()
            ip = resp.text.strip()
            rtt[key] = int((time.perf_counter() - t0) * 1000)
            return ip if IP_RE.match(ip) else None
        except Exception as e:
            errors[key] = repr(e)
            rtt[key] = int((time.perf_counter() - t0) * 1000)
            return None

    first_ip = fetch(PRIMARY_ENDPOINTS[primary], "first")
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    second_ip = fetch(PRIMARY_ENDPOINTS[primary], "second")
    secondary_ip = fetch(SECONDARY_ENDPOINTS[secondary], "secondary")

    match_stable = (first_ip is not None and first_ip == second_ip)
    proxy_env = {
        "HTTPS_PROXY": _mask(os.getenv("HTTPS_PROXY")),
        "HTTP_PROXY": _mask(os.getenv("HTTP_PROXY")),
        "ALL_PROXY": _mask(os.getenv("ALL_PROXY")),
        "NO_PROXY": os.getenv("NO_PROXY") or None,
    }

    # Mode guess logic
    env_has_proxy = any(os.getenv(k) for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"))
    if not first_ip and not second_ip and not secondary_ip:
        status = "error"
        mode = "unknown"
        suggestion = "No IP detected; check network/proxy reachability and NO_PROXY exclusions."
    else:
        if env_has_proxy:
            if first_ip and second_ip and first_ip != second_ip:
                mode = "rotating"
                status = "warn"
                suggestion = "IP rotated between calls; use backbone/static IP for long LLM runs."
            elif first_ip and second_ip and first_ip == second_ip:
                mode = "backbone"
                status = "ok"
                suggestion = None
            else:
                mode = "unknown"
                status = "warn"
                suggestion = "Partial IP readings; consider increasing timeout_ms or selecting a different service."
        else:
            mode = "direct"
            status = "ok"
            suggestion = None

    result = ProxyHealth(
        status=status, mode_guess=mode,
        primary_service=primary, first_ip=first_ip, second_ip=second_ip, match_stable=match_stable,
        secondary_service=secondary, secondary_ip=secondary_ip,
        proxy_env=proxy_env,
        timeouts_ms={"connect": int(timeout_ms), "read": int(timeout_ms)},
        rtt_ms=rtt,
        errors=errors,
        suggestion=suggestion,
    )
    
    # Update Prometheus metrics
    try:
        from app.prometheus_metrics import update_from_proxy
        update_from_proxy(result.dict())
    except Exception:
        pass  # Don't fail health check if metrics unavailable
        
    return result