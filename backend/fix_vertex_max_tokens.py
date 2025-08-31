#!/usr/bin/env python3
"""
Fix for Vertex empty responses when hitting MAX_TOKENS limit.

The issue: Vertex returns empty content when max_tokens is too low,
unlike OpenAI which returns partial content.

Solution:
1. Use reasonable default max_tokens for Vertex (minimum 500)
2. Detect MAX_TOKENS finish reason and provide informative error
3. Add metadata about finish_reason for debugging
"""

def get_vertex_min_tokens(requested_tokens: int) -> int:
    """
    Ensure minimum tokens for Vertex to avoid empty responses.
    
    Vertex doesn't return partial content when hitting MAX_TOKENS,
    so we need a reasonable minimum to get any response at all.
    """
    VERTEX_MIN_TOKENS = 500  # Minimum for reasonable responses
    return max(requested_tokens or VERTEX_MIN_TOKENS, VERTEX_MIN_TOKENS)

# Example fix in vertex_adapter.py:
"""
# In _create_generation_config_step1:
def _create_generation_config_step1(self, req: LLMRequest) -> gm.GenerationConfig:
    # Ensure minimum tokens for Vertex (avoid empty responses)
    requested_tokens = getattr(req, "max_tokens", 6000)
    if not req.grounded:  # Only apply minimum for ungrounded
        max_tokens = max(requested_tokens, 500)  # Minimum 500 for ungrounded
    else:
        max_tokens = requested_tokens  # Grounded can use lower limits
    
    config_dict = {
        "temperature": getattr(req, "temperature", 0.7),
        "top_p": getattr(req, "top_p", 0.95),
        "max_output_tokens": max_tokens,
    }
    return gm.GenerationConfig(**config_dict)

# In _extract_text_from_candidates, add finish_reason detection:
def _extract_text_from_candidates(resp: Any) -> str:
    # Check for MAX_TOKENS finish reason
    if hasattr(resp, "candidates") and resp.candidates:
        candidate = resp.candidates[0]
        if hasattr(candidate, "finish_reason"):
            finish_reason = str(candidate.finish_reason)
            if "MAX_TOKENS" in finish_reason:
                # Log warning about MAX_TOKENS
                logger.warning(f"Vertex hit MAX_TOKENS limit, may return empty content")
                # Still try to extract any partial content
    
    # ... existing extraction logic
"""

# Alternative: Return error for MAX_TOKENS with empty content
"""
# In complete() method after extraction:
text = _extract_text_from_candidates(response)

# Check for MAX_TOKENS with empty response
if not text and hasattr(response, "candidates") and response.candidates:
    candidate = response.candidates[0]
    if hasattr(candidate, "finish_reason"):
        finish_reason = str(candidate.finish_reason)
        if "MAX_TOKENS" in finish_reason:
            raise ValueError(
                f"Vertex returned empty content due to MAX_TOKENS limit. "
                f"Consider increasing max_tokens (current: {req.max_tokens})"
            )

# Add finish_reason to metadata for debugging
if hasattr(response, "candidates") and response.candidates:
    candidate = response.candidates[0]
    if hasattr(candidate, "finish_reason"):
        metadata["finish_reason"] = str(candidate.finish_reason)
"""