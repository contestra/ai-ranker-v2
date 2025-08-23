"""
Canonicalization module for AI Ranker V2
Implements PRD v2.6/v2.7 Section 5 requirements for deterministic hashing
"""

import hashlib
import json
import math
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Union
from collections import OrderedDict


class CanonicalizeError(ValueError):
    """Raised when canonicalization fails"""
    pass


def _is_real_number(x: Any) -> bool:
    """
    Check if value is a number for canonicalization.
    Returns True for int/float/Decimal but NOT bool.
    """
    return isinstance(x, (int, float, Decimal)) and not isinstance(x, bool)


def canonicalize_number(value: Union[int, float, Decimal, str]) -> Union[int, float]:
    """
    Canonicalize numeric values per PRD §5:
    - ≤6 fractional digits
    - ROUND_HALF_UP rounding
    - Trim trailing zeros
    - No scientific notation
    - Reject non-finite values
    - Convert -0 to 0
    """
    try:
        # Convert to Decimal for precise handling
        if isinstance(value, str):
            # Remove any whitespace
            value = value.strip()
        
        d = Decimal(str(value))
        
        # Reject non-finite values
        if not d.is_finite():
            raise CanonicalizeError(f"Non-finite number not allowed: {value}")
        
        # Handle -0 case
        if d.is_zero():
            return 0
        
        # Round to 6 decimal places using ROUND_HALF_UP
        quantized = d.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        
        # Remove trailing zeros
        normalized = quantized.normalize()
        
        # Convert to appropriate Python type
        if normalized == normalized.to_integral_value():
            return int(normalized)
        else:
            # Ensure no scientific notation in string representation
            result = float(normalized)
            # Verify no scientific notation would be used
            str_result = str(result)
            if 'e' in str_result.lower():
                # Format without scientific notation
                return float(f"{result:.6f}".rstrip('0').rstrip('.'))
            return result
            
    except (InvalidOperation, ValueError) as e:
        raise CanonicalizeError(f"Invalid number: {value}") from e


def canonicalize_string(value: str, for_array: bool = False) -> str:
    """
    Canonicalize string values per PRD §5:
    - Trim edges (leading/trailing whitespace)
    - CRLF → LF
    - Drop BOM
    - No internal whitespace collapse
    - NFC normalization for consistency
    
    Args:
        value: String to canonicalize
        for_array: If True, strip trailing whitespace for array elements
    """
    if not isinstance(value, str):
        raise CanonicalizeError(f"Expected string, got {type(value)}")
    
    # Remove BOM if present
    if value.startswith('\ufeff'):
        value = value[1:]
    
    # CRLF → LF
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    
    # Trim edges only (preserve internal whitespace)
    value = value.strip()
    
    # For arrays, also strip trailing whitespace from lines
    if for_array:
        value = value.rstrip()
    
    # NFC normalization for Unicode consistency
    value = unicodedata.normalize('NFC', value)
    
    return value


def canonicalize_enum(value: str, enum_type: str) -> str:
    """
    Canonicalize enum values per PRD §5:
    - Lower-case providers
    - Preserve model ID casing
    """
    if enum_type == 'provider':
        return value.lower()
    elif enum_type == 'model':
        # Preserve original casing for model IDs
        return value
    else:
        # Default: preserve casing
        return value


def normalize_country_code(code: str) -> str:
    """
    Normalize country codes per PRD §5:
    - UK → GB
    - Handle CC-SS format (country-subdivision)
    """
    code = code.upper().strip()
    
    # UK → GB normalization
    if code == 'UK':
        return 'GB'
    
    # Handle country-subdivision format
    if '-' in code:
        parts = code.split('-', 1)
        country = parts[0]
        if country == 'UK':
            country = 'GB'
        return f"{country}-{parts[1]}"
    
    return code


def _format_number_for_sorting(value) -> str:
    """
    Format a number for sorting per PRD normalization rules.
    Returns the canonical string representation.
    """
    try:
        d = Decimal(str(value))
        # Round to 6 decimal places using ROUND_HALF_UP
        q = d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        # Handle -0 -> 0
        if q == 0:
            q = Decimal(0)
        # Format without scientific notation
        s = format(q, "f").rstrip("0").rstrip(".")
        return s or "0"
    except (InvalidOperation, ValueError):
        raise CanonicalizeError(f"Invalid number for sorting: {value}")


def _scalar_sort_key(v):
    """
    Generate a sort key for scalar values per PRD.
    JSON type precedence: null < boolean < number < string
    Returns (type_rank, canonical_string)
    """
    if v is None:
        return (0, "null")
    elif isinstance(v, bool):
        # Must check bool before number as bool is a subclass of int in Python
        return (1, "true" if v else "false")
    elif _is_real_number(v):
        return (2, _format_number_for_sorting(v))
    elif isinstance(v, str):
        return (3, v)
    else:
        raise CanonicalizeError(f"Non-scalar in scalar array: {type(v)}")


def _canonical_dump_str(v) -> str:
    """
    Generate a canonical string representation of a value.
    Uses our numeric normalization to avoid scientific notation.
    This is used for sorting and deduplication keys.
    """
    if v is None:
        return "null"
    elif isinstance(v, bool):
        # Must check bool before number as bool is a subclass of int
        return "true" if v else "false"
    elif _is_real_number(v):
        return _format_number_for_sorting(v)  # No scientific notation
    elif isinstance(v, str):
        return json.dumps(v, ensure_ascii=False, separators=(',', ':'))
    elif isinstance(v, list):
        return "[" + ",".join(_canonical_dump_str(x) for x in v) + "]"
    elif isinstance(v, dict):
        return "{" + ",".join(
            f"{json.dumps(k, ensure_ascii=False, separators=(',', ':'))}:{_canonical_dump_str(v2)}"
            for k, v2 in sorted(v.items(), key=lambda kv: kv[0])
        ) + "}"
    else:
        raise CanonicalizeError(f"Unsupported type in canonical dump: {type(v)}")


def _sort_and_dedupe_scalar_array(arr: List[Any]) -> List[Any]:
    """
    Sort and deduplicate a scalar array using canonical JSON representation.
    Numbers are normalized per PRD rules before comparison.
    """
    out = []
    seen = set()
    
    # Pre-compute keys to avoid redundant calls
    items_with_keys = [(v, _scalar_sort_key(v)) for v in arr]
    
    # Sort by the canonical key
    items_with_keys.sort(key=lambda x: x[1])
    
    for v, k in items_with_keys:
        if k in seen:
            continue
        seen.add(k)
        
        # Emit the canonicalized value
        if k[0] == 2:  # number type
            # Apply our standard number canonicalization
            out.append(canonicalize_number(v))
        else:
            out.append(v)
    
    return out


def canonicalize_array(
    arr: List[Any], 
    element_type: str = 'auto',
    preserve_order: bool = False
) -> List[Any]:
    """
    Canonicalize arrays per PRD §5:
    - Sort and deduplicate scalar arrays by canonical JSON representation
    - Sort object arrays by canonical dump
    - Apply element-specific canonicalization
    
    Args:
        arr: Array to canonicalize
        element_type: Type hint for elements ('string', 'number', 'country', 'object', 'auto')
        preserve_order: If True, maintain original order (for runtime, not template hashing)
    """
    if not isinstance(arr, list):
        raise CanonicalizeError(f"Expected list, got {type(arr)}")
    
    # First, canonicalize each element
    canonicalized = []
    
    for item in arr:
        if element_type == 'auto':
            # Auto-detect type - check bool before number since bool is subclass of int
            if isinstance(item, bool):
                canon_item = item  # Booleans pass through unchanged
            elif _is_real_number(item):
                canon_item = canonicalize_number(item)
            elif isinstance(item, str):
                canon_item = canonicalize_string(item, for_array=True)
            elif isinstance(item, dict):
                canon_item = canonicalize_json(item)
            elif isinstance(item, list):
                canon_item = canonicalize_array(item)
            else:
                canon_item = item
        elif element_type == 'number':
            canon_item = canonicalize_number(item)
        elif element_type == 'string':
            canon_item = canonicalize_string(item, for_array=True)
        elif element_type == 'country':
            canon_item = normalize_country_code(item)
        elif element_type == 'object':
            canon_item = canonicalize_json(item)
        else:
            canon_item = item
        
        canonicalized.append(canon_item)
    
    if preserve_order:
        return canonicalized
    
    # Sort and deduplicate based on type
    if element_type == 'object' or (element_type == 'auto' and canonicalized and isinstance(canonicalized[0], dict)):
        # For objects, sort/dedupe by canonical dump (no sci-notation, stable across Python)
        seen = set()
        unique = []
        for item in canonicalized:
            key = _canonical_dump_str(item)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        # Sort by canonical dump
        unique.sort(key=_canonical_dump_str)
        return unique
    else:
        # For scalars, use the canonical sort and dedupe
        return _sort_and_dedupe_scalar_array(canonicalized)


def canonicalize_json(obj: Any, for_hashing: bool = True) -> Any:
    """
    Recursively canonicalize a JSON object per PRD §5.
    
    Args:
        obj: JSON-serializable object
        for_hashing: If True, apply template canonicalization (sort arrays).
                    If False, preserve array order (for output hashing).
    """
    if obj is None:
        return None
    elif isinstance(obj, bool):
        return obj  # Booleans pass through unchanged
    elif _is_real_number(obj):
        return canonicalize_number(obj)
    elif isinstance(obj, str):
        return canonicalize_string(obj)
    elif isinstance(obj, list):
        if for_hashing:
            # Template hashing: sort and deduplicate arrays
            return canonicalize_array(
                [canonicalize_json(item, for_hashing) for item in obj],
                preserve_order=False
            )
        else:
            # Output hashing: preserve array order, just canonicalize elements
            return [canonicalize_json(item, for_hashing) for item in obj]
    elif isinstance(obj, dict):
        # Always sort keys deterministically for both template and output hashing
        items = sorted(obj.items(), key=lambda kv: kv[0])
        result = OrderedDict(
            (k, canonicalize_json(v, for_hashing)) for k, v in items
        )
        return dict(result)
    else:
        raise CanonicalizeError(f"Non-JSON-serializable type: {type(obj)}")


def canonicalize_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Canonicalize JSON Schema per PRD §5:
    - Draft 2020-12 support
    - Resolve local $ref
    - Sort 'required' array
    - Forbid remote $ref
    - Minimize then hash
    """
    # Deep copy to avoid modifying original
    schema = json.loads(json.dumps(schema))
    
    # Check for forbidden remote $ref
    def check_refs(obj, path=""):
        if isinstance(obj, dict):
            if '$ref' in obj:
                ref = obj['$ref']
                if ref.startswith('http://') or ref.startswith('https://'):
                    raise CanonicalizeError(f"Remote $ref not allowed at {path}: {ref}")
                # TODO: Implement local $ref resolution
            for key, value in obj.items():
                check_refs(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_refs(item, f"{path}[{i}]")
    
    check_refs(schema)
    
    # Sort 'required' arrays
    def sort_required(obj):
        if isinstance(obj, dict):
            if 'required' in obj and isinstance(obj['required'], list):
                obj['required'] = sorted(obj['required'])
            for value in obj.values():
                sort_required(value)
        elif isinstance(obj, list):
            for item in obj:
                sort_required(item)
    
    sort_required(schema)
    
    # Canonicalize the entire schema
    return canonicalize_json(schema)


def compute_sha256(data: Union[str, bytes, Dict[str, Any], List[Any]]) -> str:
    """
    Compute SHA-256 hash of data for TEMPLATE hashing.
    Arrays are sorted/deduped as per canonicalization rules.
    
    Args:
        data: String, bytes, dict, or list
    
    Returns:
        Hex-encoded SHA-256 hash
    """
    if isinstance(data, dict):
        # Canonicalize and serialize using our canonical dump to avoid scientific notation
        canonical = canonicalize_json(data, for_hashing=True)  # Arrays sorted for templates
        payload = _canonical_dump_str(canonical)
    elif isinstance(data, list):
        # If a top-level list arrives, canonicalize it too
        canonical = canonicalize_array(data)
        payload = _canonical_dump_str(canonical)
    elif isinstance(data, str):
        payload = data
    elif isinstance(data, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(data)).hexdigest()
    else:
        # Fallback: dump any scalar via canonical dumper (bool/None/number/string)
        payload = _canonical_dump_str(data)
    
    data_bytes = payload.encode('utf-8')
    return hashlib.sha256(data_bytes).hexdigest()


def compute_template_hash(template_config: Dict[str, Any]) -> str:
    """
    Compute template_sha256 per PRD §5.
    
    Args:
        template_config: Template configuration dict
    
    Returns:
        SHA-256 hash of canonical template
    """
    canonical = canonicalize_json(template_config, for_hashing=True)
    return compute_sha256(canonical)




def _normalize_text_for_hash(s: str) -> str:
    """
    Normalize text for hashing per PRD §6.
    - CRLF → LF
    - Strip trailing whitespace from each line
    - NFC normalization
    """
    # CRLF → LF
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    # Strip trailing whitespace on each line
    s = '\n'.join(line.rstrip() for line in s.splitlines())
    # NFC normalize
    return unicodedata.normalize('NFC', s)


def compute_output_hash(output: Union[str, bytes, bytearray, dict, list, Any], 
                       output_type: Optional[str] = None) -> str:
    """
    Compute output hash per PRD §6.
    For JSON: normalize numbers, sort object keys, but PRESERVE array order recursively.
    For text: normalize whitespace and unicode.
    
    Args:
        output: Output data (string, bytes, dict, list, or any JSON-serializable type)
        output_type: 'json' or 'text' (auto-detected if None)
    
    Returns:
        SHA-256 hash of canonicalized output
    """
    # Fast-path: JSON objects/arrays passed directly
    if isinstance(output, (dict, list)):
        # Direct JSON object - canonicalize with array order preserved
        canonical = canonicalize_json(output, for_hashing=False)
        payload = _canonical_dump_str(canonical)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
    
    # Bytes → decode to string
    if isinstance(output, (bytes, bytearray, memoryview)):
        try:
            output = bytes(output).decode('utf-8')
        except UnicodeDecodeError:
            # If not valid UTF-8, hash the raw bytes
            return hashlib.sha256(bytes(output)).hexdigest()
    
    # Handle string input
    if isinstance(output, str):
        # Auto-detect type if not specified
        if output_type is None:
            # Try to parse as JSON
            try:
                json.loads(output)
                output_type = 'json'
            except (json.JSONDecodeError, ValueError):
                output_type = 'text'
        
        if output_type == 'json':
            try:
                obj = json.loads(output)
                # Canonicalize with array order preserved recursively
                canonical = canonicalize_json(obj, for_hashing=False)
                payload = _canonical_dump_str(canonical)
                return hashlib.sha256(payload.encode('utf-8')).hexdigest()
            except json.JSONDecodeError:
                # Fall back to text if JSON parsing fails
                output_type = 'text'
        
        if output_type == 'text':
            text = _normalize_text_for_hash(output)
            return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    # Fallback for other types (scalars): hash their canonical dump
    try:
        payload = _canonical_dump_str(output)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
    except Exception:
        # Last resort: convert to string and hash
        text = _normalize_text_for_hash(str(output))
        return hashlib.sha256(text.encode('utf-8')).hexdigest()