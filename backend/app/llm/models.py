"""
Centralized model configuration for LLM adapters.
Only these models are allowed in production.
"""

# OpenAI models - Responses API only
OPENAI_ALLOWED_MODELS = {
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4-turbo-2024-04-09",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",  # Primary GPT-5 model (reasoning)
    "gpt-5-mini",  # Smaller GPT-5 variant
    "gpt-5-nano",  # Smallest GPT-5 variant
    "gpt-5-chat-latest",  # Non-reasoning chat variant
    "gpt-5-2025-08-07"  # Specific GPT-5 version
}

# Default OpenAI model
OPENAI_DEFAULT_MODEL = "gpt-5"  # Use reasoning model as default

# Vertex/Gemini models - Default allowed models via Vertex
# Can be overridden via ALLOWED_VERTEX_MODELS env var
VERTEX_ALLOWED_MODELS = {
    "publishers/google/models/gemini-2.5-pro",
    "publishers/google/models/gemini-2.0-flash"
}

# Default Vertex model  
# Note: For Gemini Direct, this will be normalized to "gemini-2.5-pro"
VERTEX_DEFAULT_MODEL = "publishers/google/models/gemini-2.5-pro"

# Model validation messages
MODEL_NOT_ALLOWED_MESSAGES = {
    "vertex": "Only gemini-2.5-pro and gemini-2.0-flash are supported by default. Configure via ALLOWED_VERTEX_MODELS env var.",
    "openai": "Model not supported via Responses API. Check OPENAI_ALLOWED_MODELS."
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
    
    elif vendor == "vertex" or vendor == "gemini_direct":
        # Gemini Direct uses same models as Vertex
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
        # No remapping - use model as specified
        return model
    
    elif vendor == "vertex" or vendor == "gemini_direct":
        # Always force the canonical Vertex model
        return VERTEX_DEFAULT_MODEL
    
    return model