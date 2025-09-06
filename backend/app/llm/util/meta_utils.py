"""Meta utilities for consistent metadata handling across adapters."""
from typing import Any, Dict


def get_meta(request) -> Dict[str, Any]:
    """Return a dict for caller-supplied metadata, regardless of whether the field is named
    'metadata' or 'meta'. Never returns None."""
    md = getattr(request, "metadata", None)
    if isinstance(md, dict) and md:
        return md
    m = getattr(request, "meta", None)
    if isinstance(m, dict) and m:
        return m
    return {}


def ensure_meta_aliases(request) -> None:
    """Make 'metadata' and 'meta' interchangeable for downstream code."""
    md = getattr(request, "metadata", None)
    m = getattr(request, "meta", None)
    md = md if isinstance(md, dict) else ({} if md is None else {})
    m = m if isinstance(m, dict) else ({} if m is None else {})
    # Prefer whichever is non-empty, otherwise empty dict.
    combined = md if md else (m if m else {})
    try:
        setattr(request, "metadata", combined)
    except Exception:
        pass
    try:
        setattr(request, "meta", combined)
    except Exception:
        pass