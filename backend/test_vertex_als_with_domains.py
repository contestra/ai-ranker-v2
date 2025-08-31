#!/usr/bin/env python3
"""
Test Vertex ALS with proper domain extraction from titles
"""

import asyncio
import json
import sys
from datetime import datetime

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from tests.util.als_ambient_utils import extract_tld_counts, format_tld_summary

async def test_als_domains():
    """Test ALS effects with proper domain extraction"""
    
    print("\n" + "="*80)
    print("VERTEX ALS TEST WITH PROPER DOMAIN EXTRACTION")
    print("="*80)
    
    adapter = UnifiedLLMAdapter()
    results = {}
    
    # Test different ALS contexts
    test_configs = [
        ("BASELINE", None),
        ("CH", ALSContext(country_code="CH", locale="de-CH", als_block="")),
        ("DE", ALSContext(country_code="DE", locale="de-DE", als_block="")),
        ("US", ALSContext(country_code="US", locale="en-US", als_block=""))
    ]
    
    # Use a neutral prompt
    PROMPT = "Find recent peer-reviewed studies about vitamin D supplementation in adults. Include research sources."
    
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
            
            # Extract TLD counts - now handles source_domain
            tld_counts = extract_tld_counts(citations)
            
            # Print detailed results
            print(f"  Grounded: {metadata.get('grounded_effective', False)}")
            print(f"  Citations: {len(citations)}")
            print(f"  TLDs: {format_tld_summary(tld_counts)}")
            
            # Show actual domains from source_domain field
            actual_domains = []
            for c in citations[:5]:  # First 5
                if 'source_domain' in c:
                    actual_domains.append(c['source_domain'])
                elif 'title' in c:
                    actual_domains.append(c['title'])
            
            if actual_domains:
                print(f"  Sample domains: {', '.join(actual_domains)}")
            
            results[als_name] = {
                "grounded": metadata.get('grounded_effective', False),
                "citations": len(citations),
                "tld_counts": tld_counts,
                "sample_domains": actual_domains
            }
            
        except Exception as e:
            print(f"  Error: {str(e)[:100]}")
            results[als_name] = {"error": str(e)[:100]}
    
    # Analysis
    print("\n" + "="*80)
    print("ALS EFFECTS ANALYSIS WITH PROPER DOMAINS")
    print("="*80)
    
    if 'BASELINE' in results and 'CH' in results:
        baseline_tlds = results['BASELINE'].get('tld_counts', {})
        ch_tlds = results['CH'].get('tld_counts', {})
        
        print("\nTLD Distribution (with proper domains):")
        print(f"  BASELINE: {format_tld_summary(baseline_tlds)}")
        print(f"  CH:       {format_tld_summary(ch_tlds)}")
        
        # Check for increased .ch domains
        ch_increase = ch_tlds.get('.ch', 0) > baseline_tlds.get('.ch', 0)
        if ch_increase:
            print(f"\n✅ ALS EFFECT CONFIRMED: CH context increased .ch domains")
            print(f"   .ch: Baseline={baseline_tlds.get('.ch', 0)}, CH={ch_tlds.get('.ch', 0)}")
        else:
            print(f"\n⚠️ No clear increase in .ch domains")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"/home/leedr/ai-ranker-v2/backend/reports/VERTEX_ALS_DOMAINS_{timestamp}.json"
    
    with open(output_path, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "results": results,
            "analysis": {
                "domain_extraction": "Using source_domain from titles",
                "als_effects": any(
                    results.get(als, {}).get('tld_counts', {}).get(f'.{als.lower()}', 0) > 
                    results.get('BASELINE', {}).get('tld_counts', {}).get(f'.{als.lower()}', 0)
                    for als in ['CH', 'DE']
                )
            }
        }, f, indent=2)
    
    print(f"\n✓ Results saved: {output_path}")
    return results

if __name__ == "__main__":
    asyncio.run(test_als_domains())