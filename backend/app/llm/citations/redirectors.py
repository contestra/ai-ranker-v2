# citations/redirectors.py
from __future__ import annotations
from urllib.parse import urlparse, parse_qs, unquote

REDIRECTOR_HOSTS = {
    # Vertex grounding redirector
    "vertexaisearch.cloud.google.com": {
        "path_contains": ["/grounding-api-redirect/"],
        "end_site_query_keys": ["url", "target", "u", "dest", "destination"],
        "notes": "Vertex grounding redirect. Prefer sibling fields web.uri/reference.url; else decode query params."
    },
    # Common generic redirectors you might see via search
    "www.google.com": {
        "path_contains": ["/url", "/imgres"],
        "end_site_query_keys": ["q", "url"],
    },
    "news.google.com": {"path_contains": ["/rss/articles/"], "end_site_query_keys": ["url"]},
    "t.co": {"path_contains": [], "end_site_query_keys": ["url"]},  # fallback only; prefer HEAD if allowed
}

def is_redirector(host: str) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith(f".{h}") for h in REDIRECTOR_HOSTS)

def try_extract_target_from_query(url: str) -> str | None:
    p = urlparse(url)
    host = (p.netloc or "").lower()
    cfg = next((REDIRECTOR_HOSTS[h] for h in REDIRECTOR_HOSTS if host == h or host.endswith(f".{h}")), None)
    if not cfg:
        return None
    q = parse_qs(p.query or "")
    for key in cfg.get("end_site_query_keys", []):
        if key in q and q[key]:
            candidate = unquote(q[key][0])
            cp = urlparse(candidate)
            if cp.scheme in ("http", "https") and cp.netloc and not is_redirector(cp.netloc):
                return candidate
    return None

def path_looks_like_redirect(url: str) -> bool:
    p = urlparse(url)
    host = (p.netloc or "").lower()
    cfg = next((REDIRECTOR_HOSTS[h] for h in REDIRECTOR_HOSTS if host == h or host.endswith(f".{h}")), None)
    if not cfg:
        return False
    return any(seg in (p.path or "") for seg in cfg.get("path_contains", []))