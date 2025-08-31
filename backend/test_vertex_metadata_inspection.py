#!/usr/bin/env python3
"""
Inspect Vertex grounding metadata to find actual source URLs
"""

import asyncio
import json
import sys
from pprint import pprint

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

async def inspect_metadata():
    """Inspect what Vertex returns in grounding metadata"""
    
    print("\n" + "="*80)
    print("VERTEX GROUNDING METADATA INSPECTION")
    print("="*80)
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        model="publishers/google/models/gemini-2.5-pro",
        messages=[{
            "role": "user", 
            "content": "What are the latest findings on NAD+ supplements? Include research sources."
        }],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        als_context=ALSContext(country_code="CH", locale="de-CH", als_block=""),
        max_tokens=300
    )
    
    try:
        # Get raw response to inspect structure
        response = await adapter.complete(request)
        
        print("\n[RESPONSE METADATA]")
        print("-" * 40)
        
        if hasattr(response, 'metadata'):
            metadata = response.metadata
            
            # Print full metadata structure
            print("\nFull metadata keys:")
            for key in sorted(metadata.keys()):
                print(f"  - {key}: {type(metadata[key]).__name__}")
            
            # Inspect citations in detail
            if 'citations' in metadata:
                print(f"\nCitations count: {len(metadata['citations'])}")
                
                if metadata['citations']:
                    print("\nFirst citation structure:")
                    first = metadata['citations'][0]
                    pprint(first, width=100)
                    
                    # Check if title contains domain info
                    if 'title' in first and first['title']:
                        print(f"\nTitle analysis:")
                        print(f"  Raw title: {first['title']}")
                        # Try to extract domain from title if present
                        import re
                        domain_match = re.search(r'(?:www\.)?([a-zA-Z0-9-]+\.[a-z]{2,})', first['title'])
                        if domain_match:
                            print(f"  Extracted domain: {domain_match.group(1)}")
                    
                    print("\nAll citation URLs and titles:")
                    for i, cit in enumerate(metadata['citations'][:5], 1):
                        print(f"\n  Citation {i}:")
                        print(f"    URL: {cit.get('url', 'N/A')[:80]}...")
                        print(f"    Title: {cit.get('title', 'N/A')}")
                        if cit.get('snippet'):
                            print(f"    Snippet: {cit.get('snippet', '')[:100]}...")
            
            # Check for audit info
            if 'citations_audit' in metadata:
                print("\n[CITATIONS AUDIT]")
                audit = metadata['citations_audit']
                print(f"  Candidates: {audit.get('candidates', 0)}")
                print(f"  Keys found: {audit.get('grounding_metadata_keys', [])}")
                if audit.get('example'):
                    print(f"  Example structure:")
                    pprint(audit['example'], width=100)
        
        # Also check raw response structure if available
        print("\n[RAW RESPONSE INSPECTION]")
        print("-" * 40)
        
        # Try to access the underlying Vertex response
        if hasattr(response, '_raw_response'):
            raw = response._raw_response
            print(f"Raw response type: {type(raw)}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    return response

if __name__ == "__main__":
    asyncio.run(inspect_metadata())