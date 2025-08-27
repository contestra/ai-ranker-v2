"""
ALS (Ambient Location Signals) Constants
MISSION-CRITICAL: DO NOT MODIFY WITHOUT EXPLICIT PERMISSION

This file contains the calibrated ALS system prompt that took weeks to perfect.
ANY modification, even a single character, will break the entire geographic testing system.
"""

# CRITICAL: This EXACT prompt is required for ALS to work correctly
# It has been carefully calibrated through extensive testing
# DO NOT MODIFY even one character
ALS_SYSTEM_PROMPT = """Answer the user's question directly and naturally.
You may use any ambient context provided only to infer locale and set defaults (language variants, units, currency, regulatory framing).
Do not mention, cite, or acknowledge the ambient context or any location inference.
Do not state or imply country/region/city names unless the user explicitly asks.
Do not preface with anything about training data or location. Produce the answer only."""

# Default system prompt for non-ALS runs
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

def get_system_prompt(use_als: bool = False) -> str:
    """
    Get the appropriate system prompt based on whether ALS is being used.
    
    Args:
        use_als: Whether this is an ALS-enabled run
        
    Returns:
        The exact system prompt to use (DO NOT MODIFY)
    """
    return ALS_SYSTEM_PROMPT if use_als else DEFAULT_SYSTEM_PROMPT

def validate_als_message_order(messages: list) -> bool:
    """
    Validate that messages are in the correct order for ALS.
    
    Critical order:
    1. System prompt (role: system)
    2. ALS context (role: user) 
    3. User's actual question (role: user)
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        
    Returns:
        True if order is correct for ALS
    """
    if len(messages) < 3:
        return False
        
    # Check system prompt is first
    if messages[0].get('role') != 'system':
        return False
        
    # Check ALS context is second user message
    if messages[1].get('role') != 'user':
        return False
        
    # Check actual question is third
    if messages[2].get('role') != 'user':
        return False
        
    # Verify system prompt content matches
    if messages[0].get('content') != ALS_SYSTEM_PROMPT:
        return False
        
    return True