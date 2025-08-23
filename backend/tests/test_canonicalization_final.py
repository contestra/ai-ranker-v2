"""
Final verification tests for canonicalization per PRD v2.7
These tests ensure all edge cases and requirements are met
"""

import json
import math
import pytest

from app.core.canonicalization import (
    canonicalize_json, compute_sha256, compute_output_hash, 
    _canonical_dump_str, CanonicalizeError
)


def test_numbers_no_scientific_notation_edge_cases():
    """Test that canonical dump never uses scientific notation"""
    # Thresholds around rounding, tiny values, huge ints
    cases = [
        (1e-7, "0"),
        (1e-6, "0.000001"),
        (10000000000.0, "10000000000"),
        (-0.0000004, "0"),
        (1.2345655, "1.234566"),  # half-away-from-zero
    ]
    dump = "{" + ",".join(f'"x":{_canonical_dump_str(v)}' for v, _ in cases) + "}"
    assert "e" not in dump.lower()  # no sci-notation anywhere in canonical dump
    for v, expected in cases:
        s = _canonical_dump_str(v)
        assert s == expected, f"Failed for {v}: got {s}, expected {expected}"


def test_object_array_sort_and_dedupe_canonical_dump():
    """Test object arrays are sorted/deduped by canonical dump"""
    # These are NOT equivalent - different values for a and b
    arr1 = [{"a": 1.0, "b": 0.000001}, {"b": 1, "a": 1e-6}]
    obj1 = {"arr": arr1}
    canon1 = canonicalize_json(obj1, for_hashing=True)
    # Should have 2 objects with normalized numbers
    assert len(canon1["arr"]) == 2
    
    # Test actual deduplication with identical objects
    arr2 = [{"a": 1.0, "b": 2}, {"b": 2.0, "a": 1}]  # Same object, different order
    obj2 = {"arr": arr2}
    canon2 = canonicalize_json(obj2, for_hashing=True)
    # Should dedupe to single object
    assert len(canon2["arr"]) == 1
    assert canon2["arr"][0] == {"a": 1, "b": 2}


def test_output_hash_preserves_array_order_recursively():
    """Test that output hashing preserves nested array order"""
    a = {"x": [[1, 2], [3, 4]]}
    b = {"x": [[3, 4], [1, 2]]}
    ha = compute_output_hash(json.dumps(a))
    hb = compute_output_hash(json.dumps(b))
    assert ha != hb  # order matters for arrays (recursively)
    
    # Also test deeper nesting
    c = {"y": [[[1]], [[2]]]}
    d = {"y": [[[2]], [[1]]]}
    hc = compute_output_hash(json.dumps(c))
    hd = compute_output_hash(json.dumps(d))
    assert hc != hd


def test_output_hash_object_key_reorder_same_and_numeric_eq():
    """Test output hash is same for reordered keys and equivalent numbers"""
    a = {"b": 1.0, "a": 0.000001}
    b = {"a": 1e-6, "b": 1}
    assert compute_output_hash(json.dumps(a)) == compute_output_hash(json.dumps(b))
    
    # Also test nested objects
    c = {"outer": {"inner": {"z": 1, "a": 2}}}
    d = {"outer": {"inner": {"a": 2.0, "z": 1.000}}}
    assert compute_output_hash(json.dumps(c)) == compute_output_hash(json.dumps(d))


def test_compute_sha256_template_hash_stable_re_key_order_and_numbers():
    """Test template hash is stable regardless of key order and number format"""
    a = {"b": 1.0, "a": 0.000001}
    b = {"a": 1e-6, "b": 1}
    assert compute_sha256(a) == compute_sha256(b)
    
    # Test with arrays that should be sorted
    c = {"nums": [3, 1, 2], "vals": [1.0, 1.000000]}
    d = {"vals": [1], "nums": [1, 2, 3]}  # Sorted and deduped
    assert compute_sha256(c) == compute_sha256(d)


def test_reject_non_finite_numbers_in_template():
    """Test that non-finite numbers are rejected"""
    bad_values = [
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": float("-inf")},
        {"nested": {"val": float("nan")}},
        {"arr": [1, 2, float("inf")]},
    ]
    
    for bad in bad_values:
        with pytest.raises(CanonicalizeError):
            canonicalize_json(bad, for_hashing=True)


def test_lexicographic_numeric_sort():
    """Test that numbers sort lexicographically by their canonical string"""
    # Numbers that would sort differently numerically vs lexicographically
    obj = {"nums": [10, 2, 100, 20, 3]}
    canon = canonicalize_json(obj, for_hashing=True)
    # Lexicographic sort: "10" < "100" < "2" < "20" < "3"
    assert canon["nums"] == [10, 100, 2, 20, 3]


def test_string_number_type_separation():
    """Test that strings and numbers don't collapse together"""
    obj = {"mixed": ["1", 1, "2", 2.0, "0", 0]}
    canon = canonicalize_json(obj, for_hashing=True)
    # Numbers (type rank 2) come before strings (type rank 3)
    # Within each type, they're sorted by canonical string
    assert canon["mixed"] == [0, 1, 2, "0", "1", "2"]


def test_boolean_null_ordering():
    """Test type ordering: null < boolean < number < string"""
    obj = {"mixed": ["test", True, None, 1, False, "a", 0, None]}
    canon = canonicalize_json(obj, for_hashing=True)
    # After dedup and sort by type rank:
    # null (0), booleans (1), numbers (2), strings (3)
    assert canon["mixed"] == [None, False, True, 0, 1, "a", "test"]


def test_array_dedupe_preserves_first_occurrence_form():
    """Test that deduplication preserves the canonical form"""
    obj = {"nums": [1.0, 1, 1.000000, 2.5, 2.500000]}
    canon = canonicalize_json(obj, for_hashing=True)
    # Should dedupe to canonical forms
    assert canon["nums"] == [1, 2.5]  # 1 stays as int, 2.5 as float


def test_negative_zero_normalization():
    """Test that -0 is normalized to 0"""
    obj = {"nums": [-0.0, 0, 0.0, -0]}
    canon = canonicalize_json(obj, for_hashing=True)
    assert canon["nums"] == [0]  # All forms of zero dedupe to single 0
    
    # Verify in canonical dump
    assert _canonical_dump_str(-0.0) == "0"
    assert _canonical_dump_str(-0) == "0"


def test_unicode_nfc_normalization():
    """Test Unicode NFC normalization in strings"""
    # Combining characters vs precomposed
    obj = {"text": ["café", "cafe\u0301"]}  # é vs e + combining acute
    canon = canonicalize_json(obj, for_hashing=True)
    # Both should normalize to same NFC form and dedupe
    assert len(canon["text"]) == 1
    assert canon["text"][0] == "café"


def test_crlf_normalization():
    """Test CRLF to LF normalization"""
    obj = {"text": "line1\r\nline2\rline3\nline4"}
    canon = canonicalize_json(obj, for_hashing=True)
    assert canon["text"] == "line1\nline2\nline3\nline4"


def test_template_vs_output_array_behavior():
    """Test that template and output hashing treat arrays differently"""
    obj = {"items": [3, 1, 2]}
    
    # Template hashing (sorts arrays)
    template_canon = canonicalize_json(obj, for_hashing=True)
    assert template_canon["items"] == [1, 2, 3]
    
    # Output hashing (preserves array order)
    output_canon = canonicalize_json(obj, for_hashing=False)
    assert output_canon["items"] == [3, 1, 2]
    
    # Verify hashes are different
    template_hash = compute_sha256(obj)
    output_hash = compute_output_hash(obj)
    
    # Compare with sorted version
    sorted_obj = {"items": [1, 2, 3]}
    template_hash_sorted = compute_sha256(sorted_obj)
    output_hash_sorted = compute_output_hash(sorted_obj)
    
    assert template_hash == template_hash_sorted  # Templates normalize to same
    assert output_hash != output_hash_sorted  # Outputs preserve order


def test_bool_not_treated_as_number_in_scalars():
    """Test that booleans are not treated as numbers"""
    obj = {"vals": [0, False, 1, True]}
    # For template canonicalization, scalars are sorted by type rank then canonical string:
    # null < bool < number < string  => [False, True, 0, 1]
    canon = canonicalize_json(obj, for_hashing=True)
    assert canon["vals"] == [False, True, 0, 1]
    # Ensure no dedupe between 0 and False (different types)
    assert len(canon["vals"]) == 4


def test_mixed_types_string_vs_number_vs_bool():
    """Test mixed type handling with strings, numbers, and booleans"""
    obj = {"vals": ["1", 1, True, "true"]}
    canon = canonicalize_json(obj, for_hashing=True)
    # Order by type rank: bool(1)->True, number(2)->1, string(3)->"1","true"
    assert canon["vals"] == [True, 1, "1", "true"]
    
    # Test with more complex mix
    obj2 = {"vals": [0, "0", False, "false", 1, "1", True, "true"]}
    canon2 = canonicalize_json(obj2, for_hashing=True)
    # Booleans first, then numbers, then strings
    assert canon2["vals"] == [False, True, 0, 1, "0", "1", "false", "true"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])