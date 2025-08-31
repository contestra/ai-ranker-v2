#!/usr/bin/env python3
"""
Test Vertex true domain extraction from citations
"""

import asyncio
import json
import sys
from datetime import datetime

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from tests.util.als_ambient_utils import extract_tld_counts, format_tld_summary

async def test_true_domains():
    """Test extraction of true source domains from Vertex citations"""
    
    print("\n" + "="*80)
    print("VERTEX TRUE DOMAIN EXTRACTION TEST")
    print("="*80)
    
    adapter = UnifiedLLMAdapter()
    
    # Test with different ALS contexts to see if we get local domains
    test_configs = [
        ("BASELINE", None),
        ("CH", ALSContext(country_code="CH", locale="de-CH", als_block="")),
        ("DE", ALSContext(country_code="DE", locale="de-DE", als_block="")),
    ]
    
    # Use a query likely to return diverse sources
    PROMPT = "Find recent scientific publications about renewable energy research. Include European and international sources."
    
    for als_name, als_context in test_configs:
        print(f"\n[Testing ALS: {als_name}]")
        
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[{"role": "user", "content": PROMPT}],
            grounded=True,
            meta={"grounding_mode": "AUTO"},
            als_context=als_context,
            max_tokens=400
        )
        
        try:
            response = await adapter.complete(request)
            metadata = response.metadata if hasattr(response, 'metadata') else {}
            
            # Get citations
            citations = metadata.get('citations', [])
            
            print(f"  Total citations: {len(citations)}")
            
            # Analyze citations
            redirect_count = 0
            true_url_count = 0
            domains_found = []
            
            for i, cit in enumerate(citations[:5], 1):  # First 5 for detail
                print(f"\n  Citation {i}:")
                
                # Check URL type
                url = cit.get('url', '')
                is_redirect = cit.get('is_redirect', False) or 'vertexaisearch.cloud.google.com' in url
                
                if is_redirect:
                    redirect_count += 1
                    print(f"    URL: [REDIRECT] {url[:60]}...")
                else:
                    true_url_count += 1
                    print(f"    URL: [TRUE] {url[:60]}...")
                
                # Check source domain
                if 'source_domain' in cit:
                    print(f"    Source domain: {cit['source_domain']}")
                    domains_found.append(cit['source_domain'])
                elif 'title' in cit:
                    print(f"    Title: {cit['title']} (no source_domain)")
                
            # Summary statistics
            print(f"\n  Summary:")
            print(f"    Redirects: {redirect_count}/{len(citations)}")
            print(f"    True URLs: {true_url_count}/{len(citations)}")
            print(f"    Domains extracted: {len([c for c in citations if 'source_domain' in c])}/{len(citations)}")
            
            # TLD analysis using the enhanced utility
            tld_counts = extract_tld_counts(citations)
            print(f"    TLD distribution: {format_tld_summary(tld_counts)}")
            
            # Check for local domains
            if als_name == "CH" and '.ch' in tld_counts:
                print(f"    ✅ Found .ch domains: {tld_counts['.ch']}")
            elif als_name == "DE" and '.de' in tld_counts:
                print(f"    ✅ Found .de domains: {tld_counts['.de']}")
            
        except Exception as e:
            print(f"  Error: {str(e)[:100]}")
    
    # Analysis
    print("\n" + "="*80)
    print("DOMAIN EXTRACTION ANALYSIS")
    print("="*80)
    
    print("\nExpected improvements:")
    print("1. Non-redirect URLs extracted when available")
    print("2. Source domains extracted from multiple sources:")
    print("   - True URLs (not redirects)")
    print("   - Title field (when it's a domain)")
    print("   - Nested metadata (web.domain, source.host)")
    print("3. ALS utility uses source_domain for accurate TLD counting")
    print("4. Local domains (.ch, .de) visible in ALS contexts")

if __name__ == "__main__":
    asyncio.run(test_true_domains())