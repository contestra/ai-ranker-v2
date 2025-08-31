#!/usr/bin/env python3
"""
Cache structure updates for OpenAI adapter
This file contains the new cache implementation to replace the tri-state cache
"""

# New cache methods to add to OpenAIAdapter class:

def _get_cached_tool_support(self, model: str) -> Optional[dict]:
    """Get cached tool support info with TTL handling for unsupported entries"""
    logger.debug(f"[CACHE_GET] Looking up tool support for model: {model}")
    
    if model not in self._tool_support_cache:
        return None
        
    cache_entry = self._tool_support_cache[model]
    cached_at = cache_entry.get("cached_at", 0)
    
    # Check TTL for any unsupported variants
    has_unsupported = any(v == "unsupported" for k, v in cache_entry.items() 
                          if k in ["web_search", "web_search_preview"])
    
    if has_unsupported:
        import time
        elapsed = time.time() - cached_at
        if elapsed > self._cache_ttl_seconds:
            # TTL expired, remove from cache to allow retry
            del self._tool_support_cache[model]
            logger.debug(f"[CACHE_TTL] Expired cache for {model} after {elapsed:.0f}s")
            return None
    
    return cache_entry

def _get_preferred_variant(self, model: str) -> Optional[str]:
    """Get the preferred (last known good) variant for a model"""
    cache_entry = self._get_cached_tool_support(model)
    if cache_entry:
        # Return preferred if set, else first supported variant
        if cache_entry.get("preferred"):
            return cache_entry["preferred"]
        
        # Find first supported variant
        for variant in ["web_search", "web_search_preview"]:
            if cache_entry.get(variant) == "supported":
                return variant
    
    return None

def _set_tool_support(self, model: str, variant: str, status: str):
    """Set tool support status for a specific model+variant"""
    import time
    
    if model not in self._tool_support_cache:
        self._tool_support_cache[model] = {"cached_at": time.time()}
    
    cache_entry = self._tool_support_cache[model]
    cache_entry[variant] = status
    cache_entry["cached_at"] = time.time()
    
    # Update preferred if this variant is supported
    if status == "supported":
        cache_entry["preferred"] = variant
    
    logger.info(f"[CACHE_SET] Model {model}, variant {variant}: {status}")
    logger.debug(f"[CACHE_SET] Cache entry: {cache_entry}")

def _mark_both_variants_unsupported(self, model: str):
    """Mark both variants as unsupported when we know neither works"""
    import time
    
    self._tool_support_cache[model] = {
        "web_search": "unsupported",
        "web_search_preview": "unsupported",
        "preferred": None,
        "cached_at": time.time()
    }
    
    logger.info(f"[CACHE_SET] Model {model}: both variants unsupported")


# Changes needed in the complete() method:

# Replace this:
#   cached_tool_type = self._get_cached_tool_type(model_name)
# With:
#   cache_entry = self._get_cached_tool_support(model_name)
#   both_unsupported = (cache_entry and 
#                      cache_entry.get("web_search") == "unsupported" and 
#                      cache_entry.get("web_search_preview") == "unsupported")

# Replace this:
#   if cached_tool_type == "unsupported":
# With:
#   if both_unsupported:

# Replace this:
#   tool_type = _choose_web_search_tool_type(cached_tool_type)
# With:
#   preferred = self._get_preferred_variant(model_name)
#   tool_type = _choose_web_search_tool_type(preferred)

# Replace calls to _set_cached_tool_type with:
#   self._set_tool_support(model_name, tool_type, "supported")  # When it works
#   self._set_tool_support(model_name, tool_type, "unsupported")  # When it fails
#   self._mark_both_variants_unsupported(model_name)  # When both fail