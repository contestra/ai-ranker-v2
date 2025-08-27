# health_auth_endpoint.py
"""
FastAPI health endpoint to report Google auth mode (WIF vs ADC vs SA)
and token expiry status. Drop-in: import router and include in your app.
"""
from __future__ import annotations

import os
import datetime as dt
from typing import Optional, Literal

from fastapi import APIRouter
from pydantic import BaseModel

# Google auth
import google.auth
from google.auth.transport.requests import Request

# Types for classification
try:
    from google.auth import impersonated_credentials  # type: ignore
except Exception:  # pragma: no cover
    impersonated_credentials = None  # type: ignore

try:
    from google.auth import external_account  # type: ignore
except Exception:  # pragma: no cover
    external_account = None  # type: ignore

try:
    from google.auth import compute_engine  # type: ignore
except Exception:  # pragma: no cover
    compute_engine = None  # type: ignore

try:
    from google.oauth2 import service_account, credentials as user_credentials  # type: ignore
except Exception:  # pragma: no cover
    service_account, user_credentials = None, None  # type: ignore


router = APIRouter()


class AuthHealth(BaseModel):
    status: Literal["ok", "warn", "error"]
    auth_mode: str
    principal: Optional[str] = None
    project: Optional[str] = None
    quota_project: Optional[str] = None
    expiry: Optional[str] = None
    seconds_remaining: Optional[int] = None
    warn_threshold_hours: int
    details: dict = {}
    error: Optional[str] = None


def _classify_mode(creds) -> str:
    """Best-effort classification of auth mode."""
    try:
        if impersonated_credentials and isinstance(creds, impersonated_credentials.Credentials):
            # Often used with WIF → SA impersonation
            return "WIF-ImpersonatedSA"
        if external_account and isinstance(creds, external_account.Credentials):
            return "WIF-ExternalAccount"
        if service_account and isinstance(creds, service_account.Credentials):
            return "ServiceAccountKey"
        if compute_engine and isinstance(creds, compute_engine.Credentials):
            return "ComputeMetadata"
        if user_credentials and isinstance(creds, user_credentials.Credentials):
            return "ADC-User"
    except Exception:
        pass
    return creds.__class__.__name__


def _principal_hint(creds) -> Optional[str]:
    for attr in ("service_account_email", "_service_account_email", "target_principal", "subject"):
        v = getattr(creds, attr, None)
        if v:
            return str(v)
    # Some credential wrappers carry underlying creds
    inner = getattr(creds, "_source_credentials", None) or getattr(creds, "_credentials", None)
    if inner is not None and inner is not creds:
        return _principal_hint(inner)
    return None


@router.get("/health/auth", response_model=AuthHealth)
def health_auth() -> AuthHealth:
    warn_hours = int(os.getenv("AUTH_EXPIRY_WARN_HOURS", "24"))
    warn_delta = dt.timedelta(hours=warn_hours)

    details = {}
    try:
        # Ask for broad scope so refresh yields an access token with expiry
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        creds, project = google.auth.default(scopes=scopes)
        details["creds_type"] = creds.__class__.__name__
        details["scopes"] = scopes

        # Refresh to populate expiry if needed
        req = Request()
        if not getattr(creds, "valid", False) or getattr(creds, "expiry", None) is None:
            try:
                creds.refresh(req)
            except Exception as e:
                # Keep going; we'll return error status below
                details["refresh_error"] = repr(e)

        expiry = getattr(creds, "expiry", None)
        seconds_remaining: Optional[int] = None
        status: Literal["ok", "warn", "error"] = "ok"

        if expiry is not None:
            now = dt.datetime.now(dt.timezone.utc)
            seconds_remaining = int((expiry - now).total_seconds())
            if seconds_remaining <= 0:
                status = "error"
            elif expiry - now < warn_delta:
                status = "warn"
            else:
                status = "ok"
            expiry_iso = expiry.astimezone(dt.timezone.utc).isoformat()
        else:
            # No expiry available after refresh → warn; some metadata creds behave like this
            expiry_iso = None
            status = "warn"

        auth_mode = _classify_mode(creds)
        principal = _principal_hint(creds)

        quota_project = getattr(creds, "quota_project_id", None)

        # Also peek common env hints
        env_hints = {
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT"),
            "VERTEX_LOCATION": os.getenv("VERTEX_LOCATION"),
        }
        details["env_hints"] = {k: ("<set>" if v else None) for k, v in env_hints.items()}

        result = AuthHealth(
            status=status,
            auth_mode=auth_mode,
            principal=principal,
            project=project,
            quota_project=quota_project,
            expiry=expiry_iso,
            seconds_remaining=seconds_remaining,
            warn_threshold_hours=warn_hours,
            details=details,
            error=None if status != "error" else details.get("refresh_error"),
        )
        
        # Update Prometheus metrics
        try:
            from app.prometheus_metrics import update_from_auth
            update_from_auth(result.dict())
        except Exception:
            pass  # Don't fail health check if metrics unavailable
            
        return result

    except Exception as e:
        result = AuthHealth(
            status="error",
            auth_mode="unknown",
            principal=None,
            project=None,
            quota_project=None,
            expiry=None,
            seconds_remaining=None,
            warn_threshold_hours=warn_hours,
            details=details,
            error=repr(e),
        )
        
        # Update Prometheus metrics for error case
        try:
            from app.prometheus_metrics import update_from_auth
            update_from_auth(result.dict())
        except Exception:
            pass
            
        return result