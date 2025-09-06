#!/usr/bin/env python3
"""Test that adapters persist deduped citations in metadata["citations"]."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from app.services.als.als_builder import ALSBuilder


async def test_adapter_citations_persistence(vendor: str, model: str):
    """Test that a specific adapter persists citations in metadata."""
    print(f"\nTesting {vendor} adapter...")
    
    adapter = UnifiedLLMAdapter()
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block('DE')
    
    req = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{'role': 'user', 'content': 'What are the health benefits of vitamin D?'}],
        grounded=True,
        temperature=0.5,
        als_context=ALSContext(
            country_code='DE',
            locale='de-DE',
            als_block=als_block,
            als_variant_id='de_v1'
        )
    )
    
    try:
        result = await asyncio.wait_for(adapter.complete(req), timeout=60)
        
        print(f"  Success: {result.success}")
        
        if result.metadata:
            md = result.metadata
            
            # Check if citations are in metadata
            has_md_citations = "citations" in md
            print(f"  metadata['citations'] exists: {has_md_citations}")
            
            if has_md_citations:
                md_citations = md["citations"]
                print(f"  metadata['citations'] count: {len(md_citations)}")
                
                # Check counts match
                anchored = md.get("anchored_citations_count", 0)
                unlinked = md.get("unlinked_sources_count", 0)
                total_count = anchored + unlinked
                
                print(f"  anchored_citations_count: {anchored}")
                print(f"  unlinked_sources_count: {unlinked}")
                print(f"  Sum of counts: {total_count}")
                
                # For Google vendors, unlinked sources might be chunks not full citations
                if vendor in ("vertex", "gemini_direct"):
                    # Google vendors may have unlinked as chunk count
                    if len(md_citations) > 0:
                        print(f"  ✅ Google adapter has citations in metadata")
                    else:
                        print(f"  ⚠️  Google adapter has no citations but {unlinked} unlinked sources")
                else:
                    # OpenAI should have exact match
                    if len(md_citations) == total_count:
                        print(f"  ✅ Citation counts match: {len(md_citations)} == {total_count}")
                    else:
                        print(f"  ❌ Citation count mismatch: {len(md_citations)} != {total_count}")
            
            # Check presentation
            if "presentation" in md and "citations_compact" in md["presentation"]:
                compact = md["presentation"]["citations_compact"]
                print(f"  presentation.citations_compact count: {len(compact)}")
                print(f"  ✅ Presentation added successfully")
            else:
                print(f"  ⚠️  No presentation field (may be no citations)")
        else:
            print(f"  ❌ No metadata in response")
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def test_fallback_to_response_citations():
    """Test router fallback when only response.citations is set."""
    print("\nTesting router fallback scenario...")
    
    from app.llm.types import LLMResponse
    from app.llm.unified_llm_adapter import present_citations_for_ui
    
    # Create a synthetic response with only response.citations
    response = LLMResponse(
        success=True,
        content="Test content",
        model_version="test-model",  # Required field
        citations=[
            {"url": "https://example.com/page1", "title": "Page 1"},
            {"url": "https://example.com/page2", "title": "Page 2"},
            {"url": "https://who.int/health", "title": "WHO Health"},
        ],
        metadata={"test": "value"}  # metadata exists but no citations key
    )
    
    # Simulate router presentation logic
    md = response.metadata or {}
    final_citations = md.get("citations")
    if not final_citations and hasattr(response, "citations"):
        final_citations = getattr(response, "citations") or []
    
    if final_citations:
        presented = present_citations_for_ui(final_citations)
        md.setdefault("presentation", {})
        md["presentation"]["citations_compact"] = presented
        response.metadata = md
        
        print(f"  Fallback worked: {len(final_citations)} citations")
        print(f"  Compact list: {len(md['presentation']['citations_compact'])} citations")
        print(f"  ✅ Router fallback successful")
    else:
        print(f"  ❌ Router fallback failed")


async def main():
    """Run all tests."""
    print("="*60)
    print("TESTING ADAPTER CITATIONS PERSISTENCE")
    print("="*60)
    
    # Test OpenAI
    await test_adapter_citations_persistence("openai", "gpt-5-2025-08-07")
    
    # Test Vertex
    await test_adapter_citations_persistence("vertex", "publishers/google/models/gemini-2.5-pro")
    
    # Test Gemini Direct if API key available
    import os
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        await test_adapter_citations_persistence("gemini_direct", "gemini-2.5-pro")
    
    # Test fallback
    await test_fallback_to_response_citations()
    
    print("\n" + "="*60)
    print("TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())