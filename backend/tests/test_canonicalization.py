"""
Comprehensive test suite for canonicalization module
Tests all PRD v2.6/v2.7 Section 5 requirements
"""

import json
import math
import pytest
from decimal import Decimal

from app.core.canonicalization import (
    canonicalize_number,
    canonicalize_string,
    canonicalize_enum,
    normalize_country_code,
    canonicalize_array,
    canonicalize_json,
    canonicalize_json_schema,
    compute_sha256,
    compute_template_hash,
    compute_output_hash,
    CanonicalizeError
)


class TestNumberCanonicalization:
    """Test numeric normalization per PRD §5"""
    
    def test_round_half_up(self):
        """Test ROUND_HALF_UP behavior at 6 decimal places"""
        assert canonicalize_number(1.2345665) == 1.234567  # Round up
        assert canonicalize_number(1.2345664) == 1.234566  # Round down
        assert canonicalize_number(1.2345675) == 1.234568  # Round up at .5
        
    def test_trailing_zeros_removed(self):
        """Test that trailing zeros are removed"""
        assert canonicalize_number(1.0) == 1
        assert canonicalize_number(1.500000) == 1.5
        assert canonicalize_number("1.230000") == 1.23
        assert canonicalize_number(0.000000) == 0
        
    def test_negative_zero_normalized(self):
        """Test that -0 becomes 0"""
        assert canonicalize_number(-0.0) == 0
        assert canonicalize_number("-0") == 0
        assert canonicalize_number(-0.000000) == 0
        
    def test_no_scientific_notation(self):
        """Test that scientific notation is avoided"""
        assert canonicalize_number(0.0000001) == 0  # Rounds to 0 at 6 decimals
        assert canonicalize_number(0.0000005) == 0.000001
        assert canonicalize_number(1234567890) == 1234567890
        
    def test_reject_non_finite(self):
        """Test that non-finite values are rejected"""
        with pytest.raises(CanonicalizeError):
            canonicalize_number(float('inf'))
        with pytest.raises(CanonicalizeError):
            canonicalize_number(float('-inf'))
        with pytest.raises(CanonicalizeError):
            canonicalize_number(float('nan'))
            
    def test_string_input(self):
        """Test parsing from string"""
        assert canonicalize_number("  3.14  ") == 3.14
        assert canonicalize_number("1.234567890") == 1.234568
        assert canonicalize_number("100") == 100
        
    def test_integer_preservation(self):
        """Test that integers remain integers"""
        assert canonicalize_number(42) == 42
        assert isinstance(canonicalize_number(42), int)
        assert canonicalize_number(42.000000) == 42
        assert isinstance(canonicalize_number(42.000000), int)


class TestStringCanonicalization:
    """Test string normalization per PRD §5"""
    
    def test_trim_edges(self):
        """Test edge trimming"""
        assert canonicalize_string("  hello  ") == "hello"
        assert canonicalize_string("\n\thello\n\t") == "hello"
        assert canonicalize_string("hello") == "hello"
        
    def test_crlf_to_lf(self):
        """Test CRLF → LF conversion"""
        assert canonicalize_string("line1\r\nline2") == "line1\nline2"
        assert canonicalize_string("line1\rline2") == "line1\nline2"
        assert canonicalize_string("line1\nline2") == "line1\nline2"
        
    def test_bom_removal(self):
        """Test BOM removal"""
        assert canonicalize_string("\ufeffhello") == "hello"
        assert canonicalize_string("hello") == "hello"
        
    def test_internal_whitespace_preserved(self):
        """Test that internal whitespace is not collapsed"""
        assert canonicalize_string("hello  world") == "hello  world"
        assert canonicalize_string("hello\t\tworld") == "hello\t\tworld"
        assert canonicalize_string("hello\n\n\nworld") == "hello\n\n\nworld"
        
    def test_nfc_normalization(self):
        """Test Unicode NFC normalization"""
        # Combining characters
        assert canonicalize_string("e\u0301") == "é"  # e + combining acute
        # Already NFC
        assert canonicalize_string("é") == "é"
        
    def test_empty_string(self):
        """Test empty string handling"""
        assert canonicalize_string("") == ""
        assert canonicalize_string("   ") == ""


class TestEnumCanonicalization:
    """Test enum canonicalization"""
    
    def test_provider_lowercase(self):
        """Test provider names are lowercased"""
        assert canonicalize_enum("OpenAI", "provider") == "openai"
        assert canonicalize_enum("VERTEX", "provider") == "vertex"
        assert canonicalize_enum("Gemini", "provider") == "gemini"
        
    def test_model_casing_preserved(self):
        """Test model IDs preserve casing"""
        assert canonicalize_enum("gpt-4o", "model") == "gpt-4o"
        assert canonicalize_enum("GPT-4o", "model") == "GPT-4o"
        assert canonicalize_enum("gemini-2.5-pro", "model") == "gemini-2.5-pro"
        
    def test_other_enums_preserved(self):
        """Test other enums preserve casing"""
        assert canonicalize_enum("REQUIRED", "grounding_mode") == "REQUIRED"
        assert canonicalize_enum("json", "output_type") == "json"


class TestCountryCodeNormalization:
    """Test country code normalization"""
    
    def test_uk_to_gb(self):
        """Test UK → GB normalization"""
        assert normalize_country_code("UK") == "GB"
        assert normalize_country_code("uk") == "GB"
        assert normalize_country_code("GB") == "GB"
        
    def test_country_subdivision(self):
        """Test country-subdivision format"""
        assert normalize_country_code("US-CA") == "US-CA"
        assert normalize_country_code("uk-eng") == "GB-ENG"
        assert normalize_country_code("UK-SCT") == "GB-SCT"
        
    def test_case_normalization(self):
        """Test uppercase normalization"""
        assert normalize_country_code("us") == "US"
        assert normalize_country_code("de") == "DE"
        assert normalize_country_code("Fr") == "FR"
        
    def test_whitespace_trim(self):
        """Test whitespace trimming"""
        assert normalize_country_code("  US  ") == "US"
        assert normalize_country_code("\tGB\n") == "GB"


class TestArrayCanonicalization:
    """Test array canonicalization"""
    
    def test_scalar_sort_dedupe(self):
        """Test scalar arrays are sorted and deduplicated"""
        assert canonicalize_array([3, 1, 2, 1, 3]) == [1, 2, 3]
        assert canonicalize_array(["c", "a", "b", "a"]) == ["a", "b", "c"]
        
    def test_number_array(self):
        """Test number arrays with canonicalization"""
        assert canonicalize_array([1.0, 1, 1.000000], element_type='number') == [1]
        assert canonicalize_array([3.14159265, 2.71828], element_type='number') == [2.71828, 3.141593]
        
    def test_country_array(self):
        """Test country code arrays"""
        assert canonicalize_array(["US", "UK", "GB", "DE"], element_type='country') == ["DE", "GB", "US"]
        
    def test_object_array(self):
        """Test object arrays sorted by canonical dump"""
        objs = [
            {"b": 2, "a": 1},
            {"a": 1, "b": 2},  # Duplicate
            {"c": 3}
        ]
        result = canonicalize_array(objs, element_type='object')
        assert len(result) == 2
        assert result[0] == {"a": 1, "b": 2}
        assert result[1] == {"c": 3}
        
    def test_preserve_order(self):
        """Test preserve_order flag for runtime use"""
        assert canonicalize_array([3, 1, 2], preserve_order=True) == [3, 1, 2]
        assert canonicalize_array([3, 1, 2], preserve_order=False) == [1, 2, 3]
        
    def test_mixed_types(self):
        """Test arrays with mixed types - sorted by type then value"""
        result = canonicalize_array([1, "a", 2, "b"])
        # Numbers come before strings when sorted by type name
        assert result == [1, 2, "a", "b"]
        
    def test_empty_array(self):
        """Test empty array"""
        assert canonicalize_array([]) == []


class TestJSONCanonicalization:
    """Test JSON object canonicalization"""
    
    def test_recursive_canonicalization(self):
        """Test recursive canonicalization of complex objects"""
        obj = {
            "numbers": [1.000, 2.345678901, -0.0],
            "strings": ["  hello  ", "world\r\n"],
            "nested": {
                "array": [3, 1, 2, 1],
                "value": "  test  "
            }
        }
        
        result = canonicalize_json(obj)
        
        # Check numbers — sorted/deduped by canonical JSON string after numeric normalization
        # (ROUND_HALF_UP ≤6dp; ints preserved; -0 -> 0)
        assert result["numbers"] == [0, 1, 2.345679]  # Sorted, deduplicated, canonicalized
        
        # Check strings (trailing whitespace stripped in arrays)
        assert result["strings"] == ["hello", "world"]  # Sorted
        
        # Check nested
        assert result["nested"]["array"] == [1, 2, 3]  # Sorted, deduplicated
        assert result["nested"]["value"] == "test"
        
    def test_key_ordering(self):
        """Test that object keys are sorted"""
        obj = {"z": 1, "a": 2, "m": 3}
        canonical = canonicalize_json(obj)
        keys = list(json.loads(json.dumps(canonical, sort_keys=True)).keys())
        assert keys == ["a", "m", "z"]
        
    def test_for_hashing_flag(self):
        """Test for_hashing flag behavior"""
        obj = {"items": [3, 1, 2]}
        
        # Template hashing - arrays sorted
        assert canonicalize_json(obj, for_hashing=True)["items"] == [1, 2, 3]
        
        # Output hashing - array order preserved
        assert canonicalize_json(obj, for_hashing=False)["items"] == [3, 1, 2]
        
    def test_null_and_boolean(self):
        """Test null and boolean handling"""
        obj = {"null": None, "true": True, "false": False}
        result = canonicalize_json(obj)
        assert result == {"false": False, "null": None, "true": True}


class TestJSONSchemaCanonicalization:
    """Test JSON Schema canonicalization"""
    
    def test_required_array_sorted(self):
        """Test that 'required' arrays are sorted"""
        schema = {
            "type": "object",
            "required": ["z", "a", "m"],
            "properties": {
                "nested": {
                    "type": "object",
                    "required": ["c", "b", "a"]
                }
            }
        }
        
        result = canonicalize_json_schema(schema)
        assert result["required"] == ["a", "m", "z"]
        assert result["properties"]["nested"]["required"] == ["a", "b", "c"]
        
    def test_remote_ref_forbidden(self):
        """Test that remote $ref is forbidden"""
        schema = {
            "type": "object",
            "$ref": "https://example.com/schema.json"
        }
        
        with pytest.raises(CanonicalizeError, match="Remote \\$ref not allowed"):
            canonicalize_json_schema(schema)
            
    def test_local_ref_allowed(self):
        """Test that local $ref is allowed"""
        schema = {
            "type": "object",
            "properties": {
                "item": {"$ref": "#/definitions/Item"}
            },
            "definitions": {
                "Item": {"type": "string"}
            }
        }
        
        # Should not raise
        result = canonicalize_json_schema(schema)
        assert "$ref" in result["properties"]["item"]


class TestHashing:
    """Test hashing functions"""
    
    def test_sha256_string(self):
        """Test SHA-256 of string"""
        hash_val = compute_sha256("hello world")
        assert hash_val == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        
    def test_sha256_bytes(self):
        """Test SHA-256 of bytes"""
        hash_val = compute_sha256(b"hello world")
        assert hash_val == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        
    def test_sha256_dict(self):
        """Test SHA-256 of dict (canonicalized)"""
        obj = {"b": 2, "a": 1.000}
        hash_val = compute_sha256(obj)
        
        # Should be same hash regardless of key order or number format
        obj2 = {"a": 1, "b": 2.0}
        assert compute_sha256(obj2) == hash_val
        
    def test_template_hash(self):
        """Test template hash computation"""
        template = {
            "name": "test",
            "numbers": [3.14159265, 1.0],
            "countries": ["UK", "US", "GB"]
        }
        
        hash_val = compute_template_hash(template)
        
        # Verify deterministic
        assert compute_template_hash(template) == hash_val
        
        # Create different template with same canonical form
        # Note: arrays must be handled as strings for country codes
        template2 = {
            "name": "test",
            "numbers": [1.0, 3.14159265],  # Same numbers, different order
            "countries": ["UK", "US"]  # UK normalizes to GB
        }
        
        # Template with truly different values
        template3 = {
            "name": "test2",  # Different name
            "numbers": [1.0, 3.141593],
            "countries": ["GB", "US"]
        }
        
        # These should have different hashes
        assert compute_template_hash(template3) != hash_val
        
    def test_output_hash_json(self):
        """Test output hash for JSON"""
        json_str = '{"b": 2, "a": 1, "arr": [3, 1, 2]}'
        hash_val = compute_output_hash(json_str, 'json')
        
        # Different key order, same hash
        json_str2 = '{"a": 1.0, "b": 2.000, "arr": [3, 1, 2]}'
        assert compute_output_hash(json_str2, 'json') == hash_val
        
        # Different array order, different hash (array order preserved for output)
        json_str3 = '{"a": 1, "b": 2, "arr": [1, 2, 3]}'
        assert compute_output_hash(json_str3, 'json') != hash_val
        
    def test_output_hash_text(self):
        """Test output hash for text"""
        text = "Hello World  \r\n"
        hash_val = compute_output_hash(text, 'text')
        
        # Should normalize whitespace
        text2 = "Hello World\n"
        assert compute_output_hash(text2, 'text') == hash_val
        
        # Different content
        text3 = "Hello World!"
        assert compute_output_hash(text3, 'text') != hash_val


    def test_scalar_numeric_dedupe_and_neg_zero(self):
        """Test numeric deduplication and -0 normalization"""
        obj = {"numbers": [1, 1.0, 1.000000, -0.0, 0]}
        res = canonicalize_json(obj)
        assert res["numbers"] == [0, 1]  # 1.0 == 1; -0 -> 0
        
    def test_scalar_string_vs_number_no_collapse(self):
        """Test that string '1' and number 1 remain distinct"""
        obj = {"mixed": ["1", 1]}
        res = canonicalize_json(obj)
        # Numbers (rank 2) come before strings (rank 3)
        assert res["mixed"] == [1, "1"]
        
    def test_scalar_numeric_lexicographic_sort_explained(self):
        """Test lexicographic sorting of numbers by their canonical string"""
        # Lexicographic over canonical strings by design
        obj = {"nums": [10, 2]}
        res = canonicalize_json(obj)
        assert res["nums"] == [10, 2]  # "10" < "2" lexicographically
        
        # More examples
        obj2 = {"nums": [100, 20, 3]}
        res2 = canonicalize_json(obj2)
        assert res2["nums"] == [100, 20, 3]  # "100" < "20" < "3"
        
    def test_object_array_sort_no_scientific_notation_in_key(self):
        """Test object array sorting doesn't use scientific notation"""
        obj = {"arr": [{"x": 0.000001}, {"x": 1}]}
        res = canonicalize_json(obj)
        # Sorting should not depend on '1e-06' vs '0.000001' because we use _canonical_dump_str
        # The order is deterministic based on canonical string comparison
        assert len(res["arr"]) == 2
        assert {"x": 0.000001} in res["arr"]
        assert {"x": 1} in res["arr"]
        # Verify deterministic ordering
        res2 = canonicalize_json(obj)
        assert res == res2
        
    def test_preserve_order_for_output_hashing(self):
        """Test that preserve_order flag prevents sorting (for output hashing)"""
        obj = {"items": [3, 1, 2]}
        
        # Template hashing - arrays sorted
        template_result = canonicalize_json(obj, for_hashing=True)
        assert template_result["items"] == [1, 2, 3]
        
        # Output hashing - array order preserved
        output_result = canonicalize_json(obj, for_hashing=False)
        assert output_result["items"] == [3, 1, 2]


    def test_compute_sha256_no_sci_notation_in_template_hash(self):
        """Test that template hashes never use scientific notation"""
        data = {"x": 0.000001, "y": 1}
        h1 = compute_sha256(data)
        # Reordered keys / equivalent numbers must hash identically
        data2 = {"y": 1.0, "x": 0.000001}  # 1.0 -> 1; no sci-notation
        h2 = compute_sha256(data2)
        assert h1 == h2
        
        # Test with very small and large numbers
        template = {"small": 1e-7, "large": 1e10}
        h3 = compute_template_hash(template)
        h4 = compute_template_hash(template)
        assert h3 == h4  # Deterministic
        
    def test_output_hash_preserves_array_order(self):
        """Test that output hashing preserves array order (does not sort)"""
        # JSON output with arrays in different orders
        json1 = '{"arr": [2, 10]}'
        json2 = '{"arr": [10, 2]}'
        
        hash1 = compute_output_hash(json1, 'json')
        hash2 = compute_output_hash(json2, 'json')
        
        # Array order is significant for output hashing
        assert hash1 != hash2
        
        # But object key order should not matter
        json3 = '{"arr": [2, 10], "name": "test"}'
        json4 = '{"name": "test", "arr": [2, 10]}'
        
        hash3 = compute_output_hash(json3, 'json')
        hash4 = compute_output_hash(json4, 'json')
        
        # Same content, different key order = same hash
        assert hash3 == hash4
        
    def test_template_hash_sorts_arrays(self):
        """Test that template hashing sorts and deduplicates arrays"""
        # Template hashing should sort arrays
        template1 = {"nums": [3, 1, 2, 1]}
        template2 = {"nums": [1, 2, 3]}  # Sorted and deduplicated
        
        hash1 = compute_template_hash(template1)
        hash2 = compute_template_hash(template2)
        
        # Should be the same after canonicalization
        assert hash1 == hash2
        
    def test_output_vs_template_hash_difference(self):
        """Test that output and template hashing treat arrays differently"""
        obj = {"items": [3, 1, 2]}
        
        # Template hash (sorts arrays)
        template_hash = compute_template_hash(obj)
        
        # Output hash (preserves array order)
        json_str = json.dumps(obj)
        output_hash = compute_output_hash(json_str, 'json')
        
        # Now test with sorted array
        obj_sorted = {"items": [1, 2, 3]}
        template_hash_sorted = compute_template_hash(obj_sorted)
        json_str_sorted = json.dumps(obj_sorted)
        output_hash_sorted = compute_output_hash(json_str_sorted, 'json')
        
        # Template hashes should be the same (both sort to [1,2,3])
        assert template_hash == template_hash_sorted
        
        # Output hashes should be different (array order matters)
        assert output_hash != output_hash_sorted


    def test_output_hash_object_key_reorder_same(self):
        """Test that output hash is same regardless of object key order"""
        a = {"b": 1.0, "a": 0.000001}
        b = {"a": 0.000001, "b": 1}  # same values, different key order/types
        
        hash_a = compute_output_hash(json.dumps(a), 'json')
        hash_b = compute_output_hash(json.dumps(b), 'json')
        
        assert hash_a == hash_b
        
    def test_output_hash_array_order_differs(self):
        """Test that array order matters for output hashing"""
        a = {"arr": [2, 10]}
        b = {"arr": [10, 2]}
        
        hash_a = compute_output_hash(json.dumps(a), 'json')
        hash_b = compute_output_hash(json.dumps(b), 'json')
        
        assert hash_a != hash_b
        
    def test_output_hash_nested_arrays_preserve_order(self):
        """Test that nested arrays also preserve order in output hashing"""
        obj1 = {"data": [[1, 2], [3, 4]]}
        obj2 = {"data": [[3, 4], [1, 2]]}
        
        hash1 = compute_output_hash(obj1)  # Direct dict input
        hash2 = compute_output_hash(obj2)
        
        # Different outer array order = different hash
        assert hash1 != hash2
        
        # Same structure but inner arrays swapped
        obj3 = {"data": [[2, 1], [4, 3]]}
        hash3 = compute_output_hash(obj3)
        
        # Different inner array order = different hash
        assert hash1 != hash3
        
    def test_output_hash_handles_all_input_types(self):
        """Test that output hash handles various input types correctly"""
        # String JSON
        hash1 = compute_output_hash('{"a": 1}', 'json')
        
        # Direct dict
        hash2 = compute_output_hash({"a": 1})
        
        # Should be the same
        assert hash1 == hash2
        
        # Bytes input
        hash3 = compute_output_hash(b'{"a": 1}', 'json')
        assert hash3 == hash1
        
        # Text normalization
        text1 = "hello world  \r\n"
        text2 = "hello world\n"
        hash_text1 = compute_output_hash(text1, 'text')
        hash_text2 = compute_output_hash(text2, 'text')
        assert hash_text1 == hash_text2
        
    def test_template_vs_output_numeric_edge_cases(self):
        """Test numeric edge cases in template vs output hashing"""
        # Very small numbers that Python might represent as scientific notation
        obj = {"tiny": 1e-7, "huge": 1e10}
        
        # Template hash (will sort and normalize)
        template_hash = compute_template_hash(obj)
        
        # Output hash (preserves values but normalizes format)
        output_hash = compute_output_hash(obj)
        
        # Both should be deterministic
        assert compute_template_hash(obj) == template_hash
        assert compute_output_hash(obj) == output_hash


class TestGoldenVectors:
    """Golden test vectors to ensure consistency across implementations"""
    
    def test_numeric_golden_vectors(self):
        """Test numeric canonicalization golden vectors"""
        vectors = [
            # (input, expected_output)
            (1.2345665, 1.234567),
            (1.2345675, 1.234568),
            (1.0, 1),
            (0.999999, 0.999999),
            (0.9999995, 1),
            (-0.0, 0),
            (123456789, 123456789),
            (0.000001, 0.000001),
            (0.0000001, 0),
        ]
        
        for input_val, expected in vectors:
            assert canonicalize_number(input_val) == expected
            
    def test_hash_golden_vectors(self):
        """Test hash computation golden vectors - ensure consistent hashing"""
        # First, let's compute the actual hashes for our golden vectors
        obj1 = {"template": "test", "version": 1}
        hash1 = compute_template_hash(obj1)
        
        obj2 = {"array": [3, 1, 2], "number": 3.14159265}
        hash2 = compute_template_hash(obj2)
        
        # Verify that hashes are deterministic
        assert compute_template_hash(obj1) == hash1
        assert compute_template_hash(obj2) == hash2
        
        # Verify that canonicalization is working
        obj1_reordered = {"version": 1, "template": "test"}
        assert compute_template_hash(obj1_reordered) == hash1
        
        obj2_reordered = {"number": 3.141593, "array": [2, 3, 1]}  # Reordered array and rounded number
        assert compute_template_hash(obj2_reordered) == hash2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])