"""
RFC-6902 JSON Patch generation for template conflicts
"""

from typing import Any, Dict, List
import jsonpatch


def generate_rfc6902_diff(source: Dict[str, Any], target: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate RFC-6902 JSON Patch diff between two objects.
    
    Args:
        source: Original object
        target: New object to compare against
        
    Returns:
        List of RFC-6902 patch operations
        
    Example:
        >>> source = {"model": "gpt-4", "temp": 0.7}
        >>> target = {"model": "gpt-4", "temp": 0.8}
        >>> generate_rfc6902_diff(source, target)
        [{"op": "replace", "path": "/temp", "value": 0.8}]
    """
    patch = jsonpatch.make_patch(source, target)
    return list(patch)