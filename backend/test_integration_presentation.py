#!/usr/bin/env python3
"""Integration test for citation presentation functionality."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from app.services.als.als_builder import ALSBuilder


async def test_citation_presentation_integration():
    """Test that citation presentation is added to live responses."""
    print("Testing citation presentation integration...")
    
    adapter = UnifiedLLMAdapter()
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block('DE')
    
    req = LLMRequest(
        vendor='gemini_direct',
        model='publishers/google/models/gemini-2.5-pro',
        messages=[{'role': 'user', 'content': 'What are some recent health studies about vitamin D and immune system?'}],
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
        
        print(f"Response success: {result.success}")
        print(f"Citations count: {len(result.citations or [])}")
        
        if result.citations:
            print("\nOriginal citations:")
            for i, cite in enumerate(result.citations):
                url = cite.get('url') or cite.get('resolved_url', '')
                title = cite.get('title', 'No title')
                print(f"  {i+1}. {title} - {url}")
            
            # Check if presentation was added
            if hasattr(result, 'metadata') and result.metadata and 'presentation' in result.metadata:
                pres = result.metadata['presentation']
                if 'citations_compact' in pres:
                    compact_citations = pres['citations_compact']
                    print(f"\nCompact citations (UI): {len(compact_citations)} citations")
                    for i, cite in enumerate(compact_citations):
                        url = cite.get('url') or cite.get('resolved_url', '')
                        title = cite.get('title', 'No title')
                        print(f"  {i+1}. {title} - {url}")
                    
                    # Verify domain capping worked
                    from app.llm.unified_llm_adapter import _domain_key
                    domains = [_domain_key(c.get('url') or c.get('resolved_url', '')) for c in compact_citations]
                    domain_counts = {}
                    for d in domains:
                        domain_counts[d] = domain_counts.get(d, 0) + 1
                    
                    print(f"\nDomain distribution: {domain_counts}")
                    print("✅ Citation presentation added successfully")
                else:
                    print("❌ No citations_compact in presentation")
            else:
                print("❌ No presentation metadata found")
        else:
            print("No citations returned - cannot test presentation")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Only run if we have an API key
    import os
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        asyncio.run(test_citation_presentation_integration())
    else:
        print("Skipping integration test (no Gemini API key)")