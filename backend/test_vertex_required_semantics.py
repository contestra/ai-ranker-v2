#!/usr/bin/env python3
"""
Test Vertex/Gemini Required mode semantics enforced at adapter layer.
SDK only supports AUTO/ANY, so Required is implemented via post-hoc validation.
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
PROMPT = (
    "As of today, list 3 official sources and summarize the public emergency numbers "
    "and common mains plug letters for the country. Include source URLs."
)
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
async def test_vertex_grounded_required_enforced_by_adapter():
    """
    Required mode for Gemini is enforced by our adapter post-hoc:
      - If grounding metadata/citations exist => pass
      - Else => adapter must fail-closed with a clear error
    """
    _require_vertex_env()
    adapter = UnifiedLLMAdapter()
    
    als_context = _build_als_context(ALS_COUNTRY, ALS_LOCALE)

    # IMPORTANT: We request "Required" via meta/grounding_mode, but the SDK only supports AUTO/ANY.
    # The adapter attaches GoogleSearch and validates evidence after the call.
    req = LLMRequest(
        vendor="vertex",
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        grounded=True,
        temperature=1.0,
        als_context=als_context,
        meta={"grounding_mode": "REQUIRED"}  # consumed by our router/adapter
    )

    print("=" * 80)
    print(f"TEST: VERTEX GROUNDED (REQUIRED semantics via adapter) ALS={ALS_COUNTRY} ({MODEL})")
    print("=" * 80)
    print(f"Prompt: {PROMPT}")
    print(f"Model: {MODEL}")
    print(f"ALS Country: {ALS_COUNTRY}")
    print(f"ALS Locale: {ALS_LOCALE}")
    print(f"Grounding Mode: REQUIRED (enforced post-hoc)")
    print("-" * 80)

    try:
        res = await _run(adapter, req)
    except Exception as e:
        # Adapter should fail-closed with a message that clearly indicates REQUIRED with no evidence.
        msg = str(e).lower()
        if (("required" in msg and "ground" in msg) or 
            ("no search" in msg) or 
            ("no evidence" in msg) or
            ("grounding required" in msg)):
            print(f"\n⚠️ Adapter FAILED-CLOSED (expected behavior):")
            print(f"   Error: {e}")
            print("\n✅ Adapter correctly FAILED-CLOSED for REQUIRED with no grounding evidence.")
            return
        else:
            # Unexpected error - re-raise for visibility
            print(f"\n❌ Unexpected error (not a proper fail-closed):")
            print(f"   Error: {e}")
            raise AssertionError(f"Unexpected error: {e}")

    # If no exception, we must have evidence.
    assert res.success, f"Run failed unexpectedly: {res.error}"
    
    md = res.metadata or {}

    # Evidence checks: at least one tool signal + at least one citation.
    # Our adapter normalizes tool/citation signals; names may vary by SDK surface.
    tool_calls = md.get("tool_calls", md.get("tool_call_count", 0))
    tool_calls = int(tool_calls) if tool_calls is not None else 0
    
    grounded_effective = bool(md.get("grounded_effective", False))
    citations = res.citations or []
    
    # Print actual values for debugging
    print(f"\n📊 Grounding Evidence:")
    print(f"  - Tool calls: {tool_calls}")
    print(f"  - Grounded effective: {grounded_effective}")
    print(f"  - Citations count: {len(citations)}")
    print(f"  - ALS applied: {md.get('als_present', False)}")
    print(f"  - ALS country: {md.get('als_country', 'N/A')}")
    
    # Show sample citations if present
    if citations:
        print(f"\n📚 Sample citations (first 3):")
        for i, citation in enumerate(citations[:3], 1):
            url = citation.get('url', 'N/A')
            title = citation.get('title', 'N/A')
            print(f"  [{i}] {title}")
            print(f"      URL: {url}")
    
    # Response preview
    content = res.content or ""
    if content:
        print(f"\n📝 Response preview (first 300 chars):")
        print("  " + content[:300].replace("\n", "\n  ") + ("..." if len(content) > 300 else ""))
    
    # Token usage
    if res.usage:
        print(f"\n💰 Token usage: {res.usage}")
    
    # Perform assertions
    try:
        assert tool_calls >= 1, f"REQUIRED: expected >=1 tool call (GoogleSearch signal), got {tool_calls}"
        assert grounded_effective is True, f"REQUIRED: grounded_effective must be True, got {grounded_effective}"
        assert len(citations) > 0, f"REQUIRED: expected >=1 citation, got {len(citations)}"
        
        print(f"\n✅ Adapter PASSED with evidence (tool_calls={tool_calls}, citations={len(citations)}).")
        print("   REQUIRED mode semantics correctly enforced at adapter layer.")
        
    except AssertionError as e:
        print(f"\n❌ Evidence validation failed: {e}")
        print("   REQUIRED mode should have evidence or fail-closed earlier.")
        raise

async def main():
    """Run the test with proper environment setup"""
    print("\n🚀 Testing Vertex/Gemini REQUIRED mode semantics enforcement\n")
    
    try:
        _require_vertex_env()
    except RuntimeError as e:
        print(f"❌ {e}")
        print("\nPlease set required environment variables:")
        print("  export VERTEX_PROJECT=your-project-id")
        print("  export VERTEX_LOCATION=us-central1")
        return 1
    
    try:
        await test_vertex_grounded_required_enforced_by_adapter()
        print("\n✅ Test completed successfully!\n")
        return 0
    except Exception as e:
        print(f"\n❌ Test failed: {e}\n")
        return 1

if __name__ == "__main__":
    # Can run directly or via pytest
    exit_code = asyncio.run(main())
    exit(exit_code)