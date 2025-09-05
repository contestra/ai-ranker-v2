"""
Contract for LLMRequest field usage - Meta vs Metadata

This module documents and enforces the contract between request.meta and request.metadata
to prevent accidental drift and confusion.

FIELD CONTRACT:
===============

request.meta (Dict[str, Any]) - USER CONFIGURATION & TUNING KNOBS
------------------------------------------------------------------
Purpose: User-provided configuration that affects HOW the model behaves
Ownership: Set by the API caller, read by adapters
Immutability: Should not be modified by router or adapters (except deletion of unsupported params)

Fields:
- grounding_mode: "AUTO" | "REQUIRED" - How strictly to enforce grounding
- json_schema: Dict - JSON schema for structured output
- reasoning_effort: str - OpenAI reasoning effort level ("minimal", "medium", "high")
- reasoning_summary: bool - Whether to include reasoning summary
- thinking_budget: int - Gemini thinking token budget (user-facing)
- include_thoughts: bool - Whether to include thinking process in output

request.metadata (Dict[str, Any]) - INTERNAL ROUTER STATE & COMPUTED VALUES
---------------------------------------------------------------------------
Purpose: Internal bookkeeping, computed values, and capabilities set by the router
Ownership: Set by the router, read by adapters and telemetry
Mutability: Router can add/modify fields during request processing

Fields:
- capabilities: Dict - Model capabilities computed by router
- original_model: str - Model name before any normalization
- thinking_budget_tokens: int - Actual token budget (computed from thinking_budget)
- router_pacing_delay: int - Milliseconds of pacing delay applied
- als_* fields: ALS-related metadata (als_present, als_country, etc.)
- model_adjusted_for_grounding: bool - Whether model was changed for grounding

USAGE PATTERNS:
===============

1. Adapter reading user config:
   grounding_mode = request.meta.get("grounding_mode", "AUTO") if request.meta else "AUTO"

2. Adapter reading capabilities:
   caps = request.metadata.get("capabilities", {}) if hasattr(request, 'metadata') else {}

3. Router setting internal state:
   request.metadata["thinking_budget_tokens"] = computed_value

4. Telemetry reading both:
   meta_json["reasoning_effort"] = request.meta.get("reasoning_effort")  # User config
   meta_json["capabilities"] = request.metadata.get("capabilities")  # Router computed
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


class RequestHelper:
    """Helper class for consistent access to request fields following the contract."""
    
    @staticmethod
    def get_user_config(request, field: str, default: Any = None) -> Any:
        """Get user configuration from request.meta.
        
        Args:
            request: LLMRequest object
            field: Field name to retrieve
            default: Default value if field not present
            
        Returns:
            Field value or default
        """
        if hasattr(request, 'meta') and request.meta:
            return request.meta.get(field, default)
        return default
    
    @staticmethod
    def get_capability(request, field: str, default: Any = None) -> Any:
        """Get capability from request.metadata.capabilities.
        
        Args:
            request: LLMRequest object  
            field: Capability field name
            default: Default value if not present
            
        Returns:
            Capability value or default
        """
        if hasattr(request, 'metadata') and request.metadata:
            caps = request.metadata.get('capabilities', {})
            return caps.get(field, default)
        return default
    
    @staticmethod
    def get_router_state(request, field: str, default: Any = None) -> Any:
        """Get router internal state from request.metadata.
        
        Args:
            request: LLMRequest object
            field: Metadata field name
            default: Default value if not present
            
        Returns:
            Metadata value or default
        """
        if hasattr(request, 'metadata') and request.metadata:
            return request.metadata.get(field, default)
        return default
    
    @staticmethod
    def set_router_state(request, field: str, value: Any):
        """Set router internal state in request.metadata.
        
        Args:
            request: LLMRequest object
            field: Metadata field name
            value: Value to set
        """
        if not hasattr(request, 'metadata'):
            request.metadata = {}
        request.metadata[field] = value
    
    @staticmethod
    def get_grounding_mode(request) -> str:
        """Get grounding mode from user config.
        
        Standard accessor for the commonly used grounding_mode field.
        """
        return RequestHelper.get_user_config(request, 'grounding_mode', 'AUTO')
    
    @staticmethod
    def get_json_schema(request) -> Optional[Dict]:
        """Get JSON schema from user config.
        
        Standard accessor for the commonly used json_schema field.
        """
        return RequestHelper.get_user_config(request, 'json_schema')
    
    @staticmethod
    def get_thinking_config(request) -> Dict[str, Any]:
        """Get all thinking-related configuration.
        
        Returns dict with thinking_budget, include_thoughts, etc.
        """
        return {
            'thinking_budget': RequestHelper.get_user_config(request, 'thinking_budget'),
            'thinking_budget_tokens': RequestHelper.get_router_state(request, 'thinking_budget_tokens'),
            'include_thoughts': RequestHelper.get_user_config(request, 'include_thoughts', False),
        }
    
    @staticmethod
    def get_reasoning_config(request) -> Dict[str, Any]:
        """Get all reasoning-related configuration (OpenAI).
        
        Returns dict with reasoning_effort, reasoning_summary, etc.
        """
        return {
            'reasoning_effort': RequestHelper.get_user_config(request, 'reasoning_effort', 'minimal'),
            'reasoning_summary': RequestHelper.get_user_config(request, 'reasoning_summary', False),
        }


# Convenience functions for the most common patterns
def get_grounding_mode(request) -> str:
    """Get grounding mode from request.meta."""
    return RequestHelper.get_grounding_mode(request)


def get_json_schema(request) -> Optional[Dict]:
    """Get JSON schema from request.meta."""
    return RequestHelper.get_json_schema(request)


def supports_thinking(request) -> bool:
    """Check if model supports thinking (from capabilities)."""
    return RequestHelper.get_capability(request, 'supports_thinking_budget', False)


def supports_reasoning(request) -> bool:
    """Check if model supports reasoning (from capabilities)."""  
    return RequestHelper.get_capability(request, 'supports_reasoning_effort', False)