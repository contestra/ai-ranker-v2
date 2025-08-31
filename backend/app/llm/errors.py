"""
Custom exceptions for LLM adapter layer
"""

class GroundingNotSupportedError(RuntimeError):
    """Raised when REQUIRED grounding is requested but the provider/model can't support web_search."""
    pass

class GroundingRequiredFailedError(RuntimeError):
    """Raised when REQUIRED mode had no grounding evidence."""
    pass