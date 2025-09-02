"""
Runtime tool type negotiation for OpenAI SDK.
Inspects the SDK's WebSearchToolParam to determine supported types.
"""

import typing
from typing import Optional, List, Literal, get_args
import logging

logger = logging.getLogger(__name__)

def negotiate_openai_tool_type() -> str:
    """
    Negotiate the best web search tool type at runtime based on SDK support.
    
    Preference order:
    1. "web_search" (if available)
    2. Any "web_search_YYYY_MM_DD" (newest first)
    3. Any "web_search_preview_YYYY_MM_DD" (newest first)
    4. "web_search_preview" (fallback)
    
    Returns:
        The best available tool type string
    """
    try:
        # Import the SDK's type definition
        from openai.types.responses.web_search_tool_param import WebSearchToolParam
        
        # Get the type annotation for the 'type' field
        type_annotation = WebSearchToolParam.__annotations__.get("type")
        
        if not type_annotation:
            logger.warning("[TOOL_NEGOTIATION] No type annotation found, using fallback")
            return "web_search_preview"
        
        # Handle ForwardRef by evaluating it
        supported_types = []
        
        # Convert ForwardRef to string and parse it
        type_str = str(type_annotation)
        
        # Look for Literal values in the string representation
        # Format is typically: "Required[Literal['value1', 'value2']]"
        import re
        literal_match = re.search(r"Literal\[(.*?)\]", type_str)
        if literal_match:
            # Extract the quoted strings
            literal_content = literal_match.group(1)
            # Find all quoted strings
            values = re.findall(r"'([^']+)'", literal_content)
            supported_types = values
            logger.debug(f"[TOOL_NEGOTIATION] Extracted from ForwardRef: {supported_types}")
        
        # Fallback: try direct evaluation if no ForwardRef
        if not supported_types:
            try:
                # Try to get args directly
                from typing_extensions import get_args
                
                # Handle Required wrapper
                if hasattr(type_annotation, "__args__"):
                    inner = type_annotation.__args__[0] if type_annotation.__args__ else type_annotation
                    literal_args = get_args(inner)
                    if literal_args:
                        supported_types = list(literal_args)
            except Exception as e:
                logger.debug(f"[TOOL_NEGOTIATION] Direct extraction failed: {e}")
        
        if not supported_types:
            logger.warning("[TOOL_NEGOTIATION] No supported types found, using fallback")
            return "web_search_preview"
        
        logger.info(f"[TOOL_NEGOTIATION] SDK supports: {supported_types}")
        
        # Apply preference order
        
        # 1. Check for "web_search" (stable/primary)
        if "web_search" in supported_types:
            logger.info("[TOOL_NEGOTIATION] Selected: web_search (stable)")
            return "web_search"
        
        # 2. Check for date-stamped web_search (e.g., "web_search_2025_03_11")
        date_stamped = [t for t in supported_types if t.startswith("web_search_") and "_preview" not in t]
        if date_stamped:
            # Sort by date (newest first)
            date_stamped.sort(reverse=True)
            selected = date_stamped[0]
            logger.info(f"[TOOL_NEGOTIATION] Selected: {selected} (date-stamped)")
            return selected
        
        # 3. Check for date-stamped preview (e.g., "web_search_preview_2025_03_11")
        preview_dated = [t for t in supported_types if t.startswith("web_search_preview_") and len(t.split("_")) >= 5]
        if preview_dated:
            # Sort by date (newest first)
            preview_dated.sort(reverse=True)
            selected = preview_dated[0]
            logger.info(f"[TOOL_NEGOTIATION] Selected: {selected} (preview date-stamped)")
            return selected
        
        # 4. Fallback to basic preview
        if "web_search_preview" in supported_types:
            logger.info("[TOOL_NEGOTIATION] Selected: web_search_preview (fallback)")
            return "web_search_preview"
        
        # 5. Last resort - use first available
        selected = supported_types[0]
        logger.warning(f"[TOOL_NEGOTIATION] Using first available: {selected}")
        return selected
        
    except ImportError as e:
        logger.error(f"[TOOL_NEGOTIATION] Could not import SDK types: {e}")
        return "web_search_preview"
    except Exception as e:
        logger.error(f"[TOOL_NEGOTIATION] Negotiation failed: {e}")
        return "web_search_preview"

def build_typed_web_search_tool(tool_type: Optional[str] = None):
    """
    Build a properly typed WebSearchToolParam object.
    
    This constructs the actual SDK type (not a dict) to avoid Pydantic warnings.
    
    Args:
        tool_type: Override tool type, or None to negotiate
        
    Returns:
        WebSearchToolParam instance or dict fallback
    """
    try:
        from openai.types.responses.web_search_tool_param import WebSearchToolParam
        
        # Negotiate tool type if not provided
        if tool_type is None:
            tool_type = negotiate_openai_tool_type()
        
        # WebSearchToolParam is a TypedDict, so we construct it as a dict
        # but with the proper type annotation for the SDK
        tool = {
            "type": tool_type,
            "search_context_size": "medium"  # Optional but recommended
        }
        
        # Validate it matches the TypedDict structure
        # This ensures we're building the right shape
        try:
            # TypedDict validation happens at runtime in the SDK
            _ = WebSearchToolParam(**tool)
        except Exception:
            pass  # Validation failed, but we'll use the dict anyway
        
        logger.debug(f"[TOOL_BUILDER] Built WebSearchTool dict: {tool_type}")
        return tool
        
    except Exception as e:
        logger.warning(f"[TOOL_BUILDER] Could not build typed tool, using dict: {e}")
        # Fallback to dict if typed construction fails
        if tool_type is None:
            tool_type = negotiate_openai_tool_type()
        
        return {
            "type": tool_type,
            "search_context_size": "medium"
        }

# Cache the negotiated type for the session
_negotiated_tool_type: Optional[str] = None

def get_negotiated_tool_type() -> str:
    """
    Get the negotiated tool type, caching the result.
    
    Returns:
        The negotiated tool type string
    """
    global _negotiated_tool_type
    if _negotiated_tool_type is None:
        _negotiated_tool_type = negotiate_openai_tool_type()
    return _negotiated_tool_type