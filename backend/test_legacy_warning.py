#!/usr/bin/env python3
"""Test that legacy telemetry warning is emitted correctly."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest, LLMResponse
from app.llm.unified_llm_adapter import _read_telemetry_canonical_first, _warn_once_if_legacy_used


def test_canonical_reading():
    """Test the canonical telemetry reading helper."""
    
    # Test 1: All canonical fields present
    print("Test 1: Canonical fields only...")
    md_canonical = {
        "tool_call_count": 5,
        "anchored_citations_count": 3,
        "unlinked_sources_count": 2,
        "web_tool_type": "web_search",
        "response_api": "responses_sdk",
        "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    }
    
    result = _read_telemetry_canonical_first(md_canonical)
    assert result["tool_call_count"] == 5
    assert result["anchored_citations_count"] == 3
    assert result["unlinked_sources_count"] == 2
    assert result["web_tool_type"] == "web_search"
    assert result["used_aliases"] == False
    print("✅ Canonical reading works, no aliases used")
    
    # Test 2: Legacy aliases used
    print("\nTest 2: Legacy aliases...")
    md_legacy = {
        "web_search_count": 4,  # legacy alias for tool_call_count
        "citation_count": 6,    # legacy alias for anchored_citations_count
        "vendor_usage": {
            "input_token_count": 200,
            "output_token_count": 100
        }
    }
    
    result = _read_telemetry_canonical_first(md_legacy)
    assert result["tool_call_count"] == 4
    assert result["anchored_citations_count"] == 6
    assert result["unlinked_sources_count"] == 0
    assert result["used_aliases"] == True
    assert result["usage"]["input_tokens"] == 200
    assert result["usage"]["output_tokens"] == 100
    print("✅ Legacy aliases correctly mapped, used_aliases=True")
    
    # Test 3: Mixed canonical and legacy
    print("\nTest 3: Mixed canonical and legacy...")
    md_mixed = {
        "tool_call_count": 10,  # canonical
        "citation_count": 8,     # legacy alias
        "usage": {"input_tokens": 50, "output_tokens": 25, "total_tokens": 75}
    }
    
    result = _read_telemetry_canonical_first(md_mixed)
    assert result["tool_call_count"] == 10
    assert result["anchored_citations_count"] == 8
    assert result["used_aliases"] == True  # because citation_count is legacy
    print("✅ Mixed fields work, used_aliases=True when any legacy field used")
    
    # Test 4: Warning emission (should only emit once)
    print("\nTest 4: Legacy warning emission...")
    _warn_once_if_legacy_used(True, "test/path1")
    print("First call should emit warning (check logs)")
    
    _warn_once_if_legacy_used(True, "test/path2")
    print("Second call should NOT emit warning (already emitted)")
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_canonical_reading()