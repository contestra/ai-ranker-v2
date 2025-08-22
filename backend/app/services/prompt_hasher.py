"""
Prompt hashing utilities for integrity checking and deduplication.
Ensures prompts haven't been modified between creation and execution.
"""

import hashlib
import json
from typing import Optional, Iterable, List

def _normalize_prompt_text(s: Optional[str]) -> str:
    """Normalize prompt text for consistent hashing."""
    if not s:
        return ""
    s = s.strip().replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple spaces
    return " ".join(s.split())

def _normalize_countries(countries: Optional[Iterable[str]]) -> List[str]:
    """Normalize and sort country codes."""
    if not countries:
        return []
    out = []
    for c in countries:
        if not c:
            continue
        cc = str(c).strip().upper()
        # Handle special cases
        if cc in {"NONE", "BASE", "BASE MODEL", "NO LOCATION"}:
            cc = "NONE"  # Our frontend uses "NONE" for base model
        if cc == "UK":
            cc = "GB"
        out.append(cc)
    return sorted(set(out))

def _normalize_modes(modes: Optional[Iterable[str]]) -> List[str]:
    """Normalize grounding modes to canonical keys."""
    # Map various representations to canonical
    MAP = {
        "MODEL KNOWLEDGE ONLY": "none",
        "MODEL_ONLY": "none",
        "UNGROUNDED": "none",
        "NONE": "none",
        "GROUNDED (WEB SEARCH)": "web",
        "WEB": "web",
        "WEB_SEARCH": "web",
        "GROUNDED": "web",
    }
    out = []
    for m in modes or []:
        if not m:
            continue
        k = str(m).strip().upper()
        k = MAP.get(k, m.lower())  # Use mapping or lowercase original
        out.append(k)
    return sorted(set(out))

def calculate_bundle_hash(
    prompt_text: str,
    *,
    model_name: Optional[str] = None,
    countries: Optional[Iterable[str]] = None,
    grounding_modes: Optional[Iterable[str]] = None,
    prompt_type: Optional[str] = None,
) -> str:
    """
    Calculate hash for a template bundle (prompt + model + countries + modes).
    This represents the template's identity as a run configuration.
    
    NOTE: prompt_type is accepted for backward compatibility but NOT included
    in the hash since it doesn't affect the AI's output.
    
    Args:
        prompt_text: The prompt text
        model_name: The AI model name
        countries: List of country codes
        grounding_modes: List of grounding modes
        prompt_type: The prompt type (IGNORED - kept for compatibility)
        
    Returns:
        64-character hex string of SHA256 hash
    """
    canonical = {
        "prompt_text": _normalize_prompt_text(prompt_text),
        "countries": _normalize_countries(countries),
        "grounding_modes": _normalize_modes(grounding_modes),
        "model_name": (model_name or "").strip(),
        # prompt_type removed - it's just metadata, doesn't affect AI output
    }
    payload = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

# Keep the old function for backward compatibility but redirect to bundle hash
def calculate_prompt_hash(
    prompt_text: str,
    model_name: Optional[str] = None,
    countries: Optional[Iterable[str]] = None,
    grounding_modes: Optional[Iterable[str]] = None,
    prompt_type: Optional[str] = None,
) -> str:
    """
    Calculate SHA256 hash for template deduplication.
    Includes model, countries, and grounding modes for bundle-aware dedup.
    
    NOTE: prompt_type is accepted for backward compatibility but NOT included
    in the hash since it doesn't affect the AI's output.
    
    Args:
        prompt_text: The prompt text to hash
        model_name: Optional model name for bundle hashing
        countries: Optional country list for bundle hashing
        grounding_modes: Optional grounding modes for bundle hashing
        prompt_type: Optional prompt type (IGNORED - kept for compatibility)
        
    Returns:
        64-character hex string of SHA256 hash
    """
    # If additional params provided, use bundle hash
    if model_name or countries or grounding_modes:
        return calculate_bundle_hash(
            prompt_text,
            model_name=model_name,
            countries=countries,
            grounding_modes=grounding_modes,
            prompt_type=prompt_type  # Passed but ignored in hash calculation
        )
    
    # Legacy behavior for text-only hashing
    if not prompt_text:
        return hashlib.sha256(b'').hexdigest()
    
    # Normalize the prompt for consistent hashing
    normalized = prompt_text.strip()
    normalized = normalized.replace('\r\n', '\n')
    normalized = normalized.replace('\r', '\n')
    
    # Calculate hash
    hash_obj = hashlib.sha256(normalized.encode('utf-8'))
    return hash_obj.hexdigest()

def verify_prompt_integrity(
    original_hash: str, 
    current_prompt: str
) -> tuple[bool, Optional[str]]:
    """
    Verify that a prompt hasn't been modified.
    
    Args:
        original_hash: The stored hash of the original prompt
        current_prompt: The current prompt text to verify
        
    Returns:
        Tuple of (is_valid, current_hash)
        - is_valid: True if prompt matches original hash
        - current_hash: The hash of the current prompt
    """
    current_hash = calculate_prompt_hash(current_prompt)
    is_valid = (original_hash == current_hash)
    return is_valid, current_hash

def detect_prompt_modification(
    template_hash: Optional[str],
    execution_hash: Optional[str]
) -> dict:
    """
    Detect if a prompt was modified between template creation and execution.
    
    Args:
        template_hash: Hash stored when template was created
        execution_hash: Hash of prompt actually sent to model
        
    Returns:
        Dictionary with detection results
    """
    if not template_hash or not execution_hash:
        return {
            "modified": None,
            "reason": "Missing hash data",
            "template_hash": template_hash,
            "execution_hash": execution_hash
        }
    
    if template_hash == execution_hash:
        return {
            "modified": False,
            "reason": "Prompt unchanged",
            "template_hash": template_hash,
            "execution_hash": execution_hash
        }
    else:
        return {
            "modified": True,
            "reason": "Prompt was modified between creation and execution",
            "template_hash": template_hash,
            "execution_hash": execution_hash,
            "warning": "Integrity check failed - prompt may have been altered"
        }

def find_duplicate_prompts(prompts: list[dict]) -> dict:
    """
    Find duplicate prompts based on hash.
    
    Args:
        prompts: List of dicts with 'id' and 'prompt_text' keys
        
    Returns:
        Dictionary mapping hash to list of duplicate prompt IDs
    """
    hash_map = {}
    
    for prompt in prompts:
        prompt_id = prompt.get('id')
        prompt_text = prompt.get('prompt_text', '')
        prompt_hash = calculate_prompt_hash(prompt_text)
        
        if prompt_hash not in hash_map:
            hash_map[prompt_hash] = []
        hash_map[prompt_hash].append(prompt_id)
    
    # Filter to only show duplicates
    duplicates = {
        hash_val: ids 
        for hash_val, ids in hash_map.items() 
        if len(ids) > 1
    }
    
    return duplicates

# Export the normalize functions for use in other modules
__all__ = [
    'calculate_prompt_hash',
    'calculate_bundle_hash',
    'verify_prompt_integrity',
    'detect_prompt_modification',
    'find_duplicate_prompts',
    '_normalize_prompt_text',
    '_normalize_countries', 
    '_normalize_modes'
]