#!/usr/bin/env python3
"""
Comprehensive Vertex/Gemini ALS tests with three modes:
- UNGROUNDED
- GROUNDED (AUTO/Preferred)
- GROUNDED (REQUIRED)
"""

import os
import sys
import asyncio
import pytest
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.services.als.als_builder import ALSBuilder

MODEL = "publishers/google/models/gemini-2.5-pro"
ALS_COUNTRY = "DE"
ALS_LOCALE = "de-DE"
PROMPT = "List three public emergency numbers and the common mains plug letters used in the country."
TIMEOUT_S = 90

def _require_vertex_env():
    """Check for required Vertex environment variables"""
    missing = []
    if not os.getenv("VERTEX_PROJECT"):
        missing.append("VERTEX_PROJECT")
    if not os.getenv("VERTEX_LOCATION"):
        missing.append("VERTEX_LOCATION")
    if missing:
        raise RuntimeError(f"Missing required env: {', '.join(missing)}")

async def _run(adapter: UnifiedLLMAdapter, request: LLMRequest):
    """Run request with timeout"""
    return await asyncio.wait_for(adapter.complete(request), timeout=TIMEOUT_S)

def _build_als_context(country_code: str, locale: str) -> ALSContext:
    """Build proper ALS context with block"""
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block(country_code)
    return ALSContext(
        country_code=country_code,
        locale=locale,
        als_block=als_block,
        als_variant_id=f"{country_code.lower()}_v1"
    )

@pytest.mark.asyncio
async def test_vertex_ungrounded_with_als():
    """Test UNGROUNDED mode with ALS"""
    _require_vertex_env()
    adapter = UnifiedLLMAdapter()
    
    als_context = _build_als_context(ALS_COUNTRY, ALS_LOCALE)
    
    req = LLMRequest(
        vendor="vertex",
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        grounded=False,  # UNGROUNDED
        temperature=1.0,
        als_context=als_context,
    )
    
    print("=" * 80)
    print(f"TEST: VERTEX UNGROUNDED with ALS={ALS_COUNTRY} ({MODEL})")
    print("=" * 80)
    print(f"Prompt: {PROMPT}")
    print(f"ALS Country: {ALS_COUNTRY}")
    print(f"ALS Locale: {ALS_LOCALE}")
    print("-" * 80)
    
    res = await _run(adapter, req)
    assert res.success, f"Run failed: {res.error}"
    
    md = res.metadata or {}
    
    # ALS must be applied
    assert md.get("als_present", False) is True, "ALS not applied (als_present=False)"
    assert md.get("als_country") == ALS_COUNTRY, f"ALS country mismatch: {md.get('als_country')}"
    
    # Check for variant if available
    if "als_variant_id" in md:
        print(f"✅ ALS variant: {md['als_variant_id']}")
    
    # Ungrounded → no tool calls
    tool_calls = md.get("tool_calls", 0)
    assert tool_calls == 0, f"Ungrounded mode should have 0 tool calls, got {tool_calls}"
    assert md.get("grounded_effective", False) is False
    assert not res.citations, "Ungrounded run should not return web citations"
    
    # Print response preview
    content = res.content or ""
    print(f"\n📝 Response preview (first 200 chars):")
    print(content[:200] + ("..." if len(content) > 200 else ""))
    
    print(f"\n💰 Tokens: {res.usage}")
    print("✅ Ungrounded + ALS passed; no tools used.")

@pytest.mark.asyncio
async def test_vertex_grounded_auto_with_als():
    """Test GROUNDED (AUTO/Preferred) mode with ALS"""
    _require_vertex_env()
    adapter = UnifiedLLMAdapter()
    
    als_context = _build_als_context(ALS_COUNTRY, ALS_LOCALE)
    
    req = LLMRequest(
        vendor="vertex",
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        grounded=True,   # Grounded (AUTO/Preferred)
        temperature=1.0,
        als_context=als_context,
        meta={"grounding_mode": "PREFERRED"}
    )
    
    print("\n" + "=" * 80)
    print(f"TEST: VERTEX GROUNDED (AUTO/PREFERRED) with ALS={ALS_COUNTRY} ({MODEL})")
    print("=" * 80)
    print(f"Prompt: {PROMPT}")
    print(f"ALS Country: {ALS_COUNTRY}")
    print(f"ALS Locale: {ALS_LOCALE}")
    print("-" * 80)
    
    res = await _run(adapter, req)
    assert res.success, f"Run failed: {res.error}"
    
    md = res.metadata or {}
    
    # ALS must be applied
    assert md.get("als_present", False) is True, "ALS not applied"
    assert md.get("als_country") == ALS_COUNTRY
    
    # AUTO mode: tool_call_count may be 0 (model's choice)
    tool_calls = md.get("tool_calls", 0)
    grounded_effective = md.get("grounded_effective", False)
    
    print(f"\n📊 Grounding stats:")
    print(f"  - Tool calls: {tool_calls}")
    print(f"  - Grounded effective: {grounded_effective}")
    print(f"  - Citations: {len(res.citations) if res.citations else 0}")
    
    # If citations present, show first few
    if res.citations:
        print(f"\n📚 Sample citations (first 3):")
        for i, citation in enumerate(res.citations[:3], 1):
            url = citation.get('url', 'N/A')
            title = citation.get('title', 'N/A')
            print(f"  [{i}] {title}")
            print(f"      {url}")
    
    # Print response preview
    content = res.content or ""
    print(f"\n📝 Response preview (first 200 chars):")
    print(content[:200] + ("..." if len(content) > 200 else ""))
    
    print(f"\n💰 Tokens: {res.usage}")
    print("✅ Grounded (AUTO) completed successfully.")

@pytest.mark.asyncio
async def test_vertex_grounded_required_with_als():
    """Test GROUNDED (REQUIRED) mode with ALS"""
    _require_vertex_env()
    adapter = UnifiedLLMAdapter()
    
    als_context = _build_als_context(ALS_COUNTRY, ALS_LOCALE)
    
    req = LLMRequest(
        vendor="vertex",
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        grounded=True,   # Grounded (REQUIRED)
        temperature=1.0,
        als_context=als_context,
        meta={"grounding_mode": "REQUIRED"}
    )
    
    print("\n" + "=" * 80)
    print(f"TEST: VERTEX GROUNDED (REQUIRED) with ALS={ALS_COUNTRY} ({MODEL})")
    print("=" * 80)
    print(f"Prompt: {PROMPT}")
    print(f"ALS Country: {ALS_COUNTRY}")
    print(f"ALS Locale: {ALS_LOCALE}")
    print("-" * 80)
    
    try:
        res = await _run(adapter, req)
    except Exception as e:
        # Router should fail-closed if no evidence
        msg = str(e).lower()
        if ("required" in msg and "ground" in msg) or ("no search" in msg) or ("no evidence" in msg):
            print(f"\n⚠️ REQUIRED mode fail-closed (expected): {e}")
            print("✅ REQUIRED correctly failed closed when no grounding evidence.")
            return
        else:
            raise AssertionError(f"Unexpected error in REQUIRED mode: {e}")
    
    # If we reach here, adapter returned success
    assert res.success, f"Run failed: {res.error}"
    
    md = res.metadata or {}
    
    # ALS must be applied
    assert md.get("als_present", False) is True, "ALS not applied"
    assert md.get("als_country") == ALS_COUNTRY
    
    # REQUIRED mode must have evidence
    tool_calls = md.get("tool_calls", 0)
    grounded_effective = md.get("grounded_effective", False)
    
    assert tool_calls >= 1, f"REQUIRED: expected at least 1 tool call, got {tool_calls}"
    assert grounded_effective is True, "REQUIRED: grounded_effective must be True"
    assert res.citations and len(res.citations) > 0, "REQUIRED: citations must be present"
    
    print(f"\n📊 Grounding stats (REQUIRED mode):")
    print(f"  - Tool calls: {tool_calls}")
    print(f"  - Grounded effective: {grounded_effective}")
    print(f"  - Citations: {len(res.citations)}")
    
    # Show first few citations
    print(f"\n📚 Sample citations (first 3):")
    for i, citation in enumerate(res.citations[:3], 1):
        url = citation.get('url', 'N/A')
        title = citation.get('title', 'N/A')
        print(f"  [{i}] {title}")
        print(f"      {url}")
    
    # Print response preview
    content = res.content or ""
    print(f"\n📝 Response preview (first 200 chars):")
    print(content[:200] + ("..." if len(content) > 200 else ""))
    
    print(f"\n💰 Tokens: {res.usage}")
    print("✅ REQUIRED succeeded with evidence (tool calls + citations).")

async def main():
    """Run all tests sequentially"""
    print("\n🚀 Starting Vertex/Gemini ALS comprehensive tests\n")
    
    try:
        _require_vertex_env()
    except RuntimeError as e:
        print(f"❌ {e}")
        print("Please set required environment variables:")
        print("  export VERTEX_PROJECT=your-project-id")
        print("  export VERTEX_LOCATION=us-central1")
        return
    
    # Run tests
    try:
        await test_vertex_ungrounded_with_als()
    except Exception as e:
        print(f"❌ Ungrounded test failed: {e}")
    
    try:
        await test_vertex_grounded_auto_with_als()
    except Exception as e:
        print(f"❌ Grounded AUTO test failed: {e}")
    
    try:
        await test_vertex_grounded_required_with_als()
    except Exception as e:
        print(f"❌ Grounded REQUIRED test failed: {e}")
    
    print("\n✅ All Vertex/Gemini ALS tests completed!\n")

if __name__ == "__main__":
    # Can run directly or via pytest
    asyncio.run(main())