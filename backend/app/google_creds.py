import os
import google.auth

def _friendly_type(creds) -> str:
    mod = creds.__class__.__module__
    name = creds.__class__.__name__
    if "service_account" in mod:
        return "ServiceAccountCredentials"
    if "external_account" in mod:
        return "ExternalAccountCredentials"
    if "impersonated_credentials" in mod:
        return "ImpersonatedCredentials"
    return name  # e.g., "Credentials" for ADC

def creds_info():
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    creds, project = google.auth.default(scopes=scopes)
    info = {
        "credential_type": _friendly_type(creds),
        "principal": getattr(creds, "service_account_email", None),
        "project": project,
        "quota_project": getattr(creds, "quota_project_id", None),
    }
    return info

def enforce_wif_if_required(info: dict):
    if os.getenv("ENFORCE_VERTEX_WIF", "false").lower() == "true":
        # Health check for WIF file presence (defense in depth)
        wif_path = "/etc/gcloud/wif-credentials.json"
        if not os.path.exists(wif_path):
            raise RuntimeError(f"WIF enforced but {wif_path} not found. Check WIF_CREDENTIALS_JSON secret.")
        # Only allow WIF-ish credentials in prod
        if info["credential_type"] not in {"ExternalAccountCredentials", "ImpersonatedCredentials"}:
            raise RuntimeError(
                f"WIF required but got {info['credential_type']} (principal={info['principal']})"
            )