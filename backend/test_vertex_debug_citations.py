#!/usr/bin/env python3
"""
Debug what's in Vertex citations
"""

import asyncio
import json
import sys

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

async def debug_citations():
    """Debug citation structure"""
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        model="publishers/google/models/gemini-2.5-pro",
        messages=[{"role": "user", "content": "What are recent findings on magnesium supplements?"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        als_context=ALSContext(country_code="CH", locale="de-CH", als_block=""),
        max_tokens=300
    )
    
    try:
        response = await adapter.complete(request)
        metadata = response.metadata if hasattr(response, 'metadata') else {}
        
        citations = metadata.get('citations', [])
        
        print(f"\nTotal citations: {len(citations)}")
        print("\nFirst 3 citations structure:")
        for i, cit in enumerate(citations[:3], 1):
            print(f"\nCitation {i}:")
            for key, value in cit.items():
                if key == 'url':
                    print(f"  {key}: {str(value)[:60]}...")
                else:
                    print(f"  {key}: {value}")
        
        # Check if source_domain is being set
        domains_found = sum(1 for c in citations if 'source_domain' in c)
        print(f"\nCitations with source_domain field: {domains_found}/{len(citations)}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_citations())