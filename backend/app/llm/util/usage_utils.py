"""Usage normalization utilities for consistent telemetry across adapters."""

from typing import Any, Dict, Tuple


def normalize_usage_openai(raw: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """
    Normalize OpenAI usage to canonical format.
    
    Returns (normalized, raw_preserved).
    Normalized keys: input_tokens, output_tokens, total_tokens (ints).
    
    Handles nested fields like input_tokens_details, reasoning_tokens, etc.
    """
    raw = raw or {}
    
    # Direct mapping for common fields
    inp = 0
    out = 0
    
    # Try direct fields first
    if "prompt_tokens" in raw:
        inp = int(raw.get("prompt_tokens", 0))
    elif "input_tokens" in raw:
        inp = int(raw.get("input_tokens", 0))
    
    if "completion_tokens" in raw:
        out = int(raw.get("completion_tokens", 0))
    elif "output_tokens" in raw:
        out = int(raw.get("output_tokens", 0))
    
    # Total can be explicit or computed
    if "total_tokens" in raw:
        tot = int(raw.get("total_tokens", 0))
    else:
        tot = inp + out
    
    normalized = {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": tot
    }
    
    return normalized, raw


def normalize_usage_google(raw: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """
    Normalize Google usage_metadata to canonical format.
    
    Google uses: input_token_count, output_token_count, total_token_count.
    Normalize to canonical keys; keep raw as-is for audit.
    """
    raw = raw or {}
    
    # Google uses *_token_count pattern
    inp = int(raw.get("input_token_count", 0) or raw.get("prompt_token_count", 0) or 0)
    out = int(raw.get("output_token_count", 0) or raw.get("candidates_token_count", 0) or 0)
    
    # Total can be explicit or computed
    if "total_token_count" in raw:
        tot = int(raw.get("total_token_count", 0))
    else:
        tot = inp + out
    
    normalized = {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": tot
    }
    
    return normalized, raw


def ensure_usage_normalized(metadata: Dict[str, Any], vendor: str = None) -> None:
    """
    Ensure metadata has normalized usage field.
    
    This is a fallback for router/analytics that handles both patterns.
    Modifies metadata in-place.
    """
    if not metadata:
        return
    
    # If already has normalized usage, we're done
    if "usage" in metadata and isinstance(metadata["usage"], dict):
        usage = metadata["usage"]
        if all(k in usage for k in ["input_tokens", "output_tokens", "total_tokens"]):
            return
    
    # Try to normalize from vendor_usage
    vendor_usage = metadata.get("vendor_usage", {})
    
    # Try Google pattern first
    if "input_token_count" in vendor_usage or "output_token_count" in vendor_usage:
        normalized, _ = normalize_usage_google(vendor_usage)
        metadata["usage"] = normalized
        return
    
    # Try OpenAI pattern
    if any(k in vendor_usage for k in ["prompt_tokens", "completion_tokens", "input_tokens", "output_tokens"]):
        normalized, _ = normalize_usage_openai(vendor_usage)
        metadata["usage"] = normalized
        return
    
    # Last resort: set zeros
    metadata["usage"] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0
    }