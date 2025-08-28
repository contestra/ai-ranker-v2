"""
Centralized model configuration for LLM adapters.
Only these models are allowed in production.
"""

# OpenAI models - Responses API only
OPENAI_ALLOWED_MODELS = {
    "gpt-5",  # Current name in use
    "gpt-5-chat-latest"  # Canonical name per spec
}

# Default OpenAI model
OPENAI_DEFAULT_MODEL = "gpt-5-chat-latest"

# Vertex/Gemini models - Only 2.5-pro via Vertex
VERTEX_ALLOWED_MODELS = {
    "publishers/google/models/gemini-2.5-pro"
}

# Default Vertex model
VERTEX_DEFAULT_MODEL = "publishers/google/models/gemini-2.5-pro"

# Model validation messages
MODEL_NOT_ALLOWED_MESSAGES = {
    "vertex": "Only publishers/google/models/gemini-2.5-pro is supported in this release.",
    "openai": "Only gpt-5 and gpt-5-chat-latest are supported via Responses API."
}

def validate_model(vendor: str, model: str) -> tuple[bool, str]:
    """
    Validate if a model is allowed for a vendor.
    Returns (is_valid, error_message)
    """
    if vendor == "openai":
        if model in OPENAI_ALLOWED_MODELS:
            return True, ""
        return False, MODEL_NOT_ALLOWED_MESSAGES["openai"]
    
    elif vendor == "vertex":
        if model in VERTEX_ALLOWED_MODELS:
            return True, ""
        return False, MODEL_NOT_ALLOWED_MESSAGES["vertex"]
    
    return False, f"Unknown vendor: {vendor}"

def normalize_model(vendor: str, model: str = None) -> str:
    """
    Normalize or default the model for a vendor.
    """
    if vendor == "openai":
        if not model:
            return OPENAI_DEFAULT_MODEL
        # Map gpt-5 to canonical name
        if model == "gpt-5":
            return "gpt-5-chat-latest"
        return model
    
    elif vendor == "vertex":
        # Always force the canonical Vertex model
        return VERTEX_DEFAULT_MODEL
    
    return model