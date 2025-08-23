"""
Operations endpoints for system health and validation
"""

import os
import sys
from typing import Dict, List, Any
from fastapi import APIRouter
from openai import AsyncOpenAI
import httpx

router = APIRouter(prefix="/ops", tags=["operations"])


@router.get("/openai-preflight")
async def openai_preflight() -> Dict[str, Any]:
    """
    Validate OpenAI API configuration and connectivity.
    Uses Responses API with minimal token test to match the adapter.
    
    Returns:
        ready: bool - Whether OpenAI API is ready
        errors: List[str] - Any configuration or connectivity errors
        model_allowlist: List[str] - Allowed models from configuration
        probe_tokens: int - Number of tokens used for probe
    """
    allow = [m.strip() for m in os.getenv("OPENAI_MODELS_ALLOWLIST", "gpt-5").split(",") if m.strip()]
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return {"ready": False, "errors": ["OPENAI_API_KEY missing"], "model_allowlist": allow}
    
    connect_s = float(os.getenv("OPENAI_CONNECT_TIMEOUT_MS", "2000")) / 1000.0
    read_s = float(os.getenv("OPENAI_READ_TIMEOUT_MS", "60000")) / 1000.0
    probe_tokens = max(16, int(os.getenv("OPENAI_PREFLIGHT_TOKENS", "16")))  # Clamp to min 16
    
    client = AsyncOpenAI(
        api_key=api_key,
        timeout=httpx.Timeout(
            connect=connect_s,
            read=read_s,
            write=read_s,
            pool=read_s
        )
    )
    
    try:
        # Use RESPONSES API with clamped token probe
        _ = await client.responses.create(
            model=allow[0],
            input="ping",
            max_output_tokens=probe_tokens
        )
        return {"ready": True, "errors": [], "model_allowlist": allow, "probe_tokens": probe_tokens}
    except Exception as e:
        return {"ready": False, "errors": [f"{type(e).__name__}: {e}"], "model_allowlist": allow, "probe_tokens": probe_tokens}


@router.get("/runtime-info")
async def runtime_info() -> Dict[str, Any]:
    """Show runtime information about Python and packages"""
    import openai
    from openai import AsyncOpenAI
    
    return {
        "python": sys.version,
        "sys_executable": sys.executable,
        "openai_version": getattr(openai, "__version__", "?"),
        "openai_path": getattr(openai, "__file__", "?"),
        "has_responses": hasattr(AsyncOpenAI(api_key="sk-test"), "responses"),
        "env": {
            "OPENAI_API_KEY_present": bool(os.getenv("OPENAI_API_KEY")),
            "OPENAI_MODELS_ALLOWLIST": os.getenv("OPENAI_MODELS_ALLOWLIST"),
        },
    }


@router.get("/vertex-preflight")
def vertex_preflight():
    proj = os.getenv("GOOGLE_CLOUD_PROJECT")
    loc = (os.getenv("VERTEX_LOCATION") or os.getenv("GOOGLE_CLOUD_REGION") or "").strip().lower() or None
    try:
        from google.auth import default
        from google.auth.transport.requests import Request

        creds, detected_project = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        ident = getattr(creds, "service_account_email", "user-ADC")
        return {
            "ready": True,
            "errors": [],
            "project": proj or detected_project,
            "location": loc,
            "credential_type": type(creds).__name__,
            "principal": ident,
        }
    except Exception as e:
        return {"ready": False, "errors": [str(e)], "project": proj, "location": loc}


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Basic health check endpoint"""
    return {"status": "healthy"}