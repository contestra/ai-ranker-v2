#!/usr/bin/env python3
"""
Test ALS functionality with proper context
Following the improved test matrix recommendations
"""
import asyncio
import os
import sys
import json
import time
from datetime import datetime
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

# The prompt to test
PROMPT = "List the 10 most trusted longevity supplement brands"

async def run_test_with_als(adapter, vendor, model, grounded, country, test_name):
    """Run a single test with proper ALS context"""
    
    # Build ALS context properly
    als_context = None
    if country and country != "none":
        # Create a simple ALS context - the adapter will build the actual block
        als_context = {
            'country_code': country,
            'locale': f"en-{country}"
        }
    
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.3 if vendor == "openai" else 0.7,  # Follow spec recommendations
        max_tokens=500,
        grounded=grounded,
        als_context=als_context  # Pass ALS context properly
    )
    
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"Vendor: {vendor}, Model: {model}")
    print(f"Grounded: {grounded}, Country: {country}")
    print(f"ALS Context: {'Yes' if als_context else 'No'}")
    
    try:
        start = time.perf_counter()
        response = await adapter.complete(request)
        latency_ms = int((time.perf_counter() - start) * 1000)
        
        print(f"✅ Success in {latency_ms}ms")
        
        # Check if ALS was actually applied
        if als_context and response.content:
            # Look for regional indicators in response
            regional_indicators = {
                'US': ['FDA', 'NSF', 'USP', 'GMP', 'U.S.', 'United States'],
                'DE': ['EU', 'European', 'Germany', 'Deutschland', 'CE', 'EFSA'],
                'UK': ['MHRA', 'UK', 'British', 'United Kingdom']
            }
            
            found_indicators = []
            for indicator in regional_indicators.get(country, []):
                if indicator.lower() in response.content.lower():
                    found_indicators.append(indicator)
            
            if found_indicators:
                print(f"🎯 Regional indicators found: {', '.join(found_indicators)}")
            else:
                print(f"⚠️ No regional indicators found for {country}")
        
        # Extract first 3 brands
        lines = response.content.split('\n')
        brands = []
        for line in lines:
            if line.strip() and (line[0].isdigit() or line.startswith('*') or line.startswith('-')):
                # Extract brand name
                brand_line = line.strip('1234567890.*- ')
                if brand_line and len(brand_line) < 100:
                    brands.append(brand_line.split('–')[0].split(':')[0].strip(' *'))
                    if len(brands) >= 3:
                        break
        
        if brands:
            print(f"Top 3 brands: {', '.join(brands)}")
        
        # Check metadata
        meta = response.metadata
        print(f"Grounded effective: {meta.get('grounded_effective', False)}")
        
        return {
            "success": True,
            "latency_ms": latency_ms,
            "grounded_effective": meta.get('grounded_effective', False),
            "brands": brands,
            "regional_indicators": found_indicators if als_context else []
        }
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        return {"success": False, "error": str(e)}

async def main():
    """Run the improved test matrix"""
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*70)
    print("IMPROVED TEST MATRIX - ALS VERIFICATION")
    print("="*70)
    
    # Test matrix as recommended:
    # Lane A: OpenAI Ungrounded (AUTO, expect fallbacks)
    # Lane B: OpenAI Grounded REQUIRED (expect some failures)
    # Lane C: Vertex Grounded REQUIRED (expect 20-50s)
    # Lane D: Vertex Ungrounded (no tools)
    
    tests = [
        # OpenAI Lane A: Ungrounded with ALS
        ("openai", "gpt-5", False, None, "OpenAI Ungrounded - No ALS"),
        ("openai", "gpt-5", False, "US", "OpenAI Ungrounded - ALS US"),
        ("openai", "gpt-5", False, "DE", "OpenAI Ungrounded - ALS DE"),
        
        # OpenAI Lane B: Grounded (will fallback)
        ("openai", "gpt-5", True, None, "OpenAI Grounded - No ALS"),
        ("openai", "gpt-5", True, "US", "OpenAI Grounded - ALS US"),
        
        # Vertex Lane C: Grounded (should work)
        ("vertex", "gemini-2.5-pro", True, None, "Vertex Grounded - No ALS"),
        ("vertex", "gemini-2.5-pro", True, "US", "Vertex Grounded - ALS US"),
        
        # Vertex Lane D: Ungrounded
        ("vertex", "gemini-2.5-pro", False, None, "Vertex Ungrounded - No ALS"),
        ("vertex", "gemini-2.5-pro", False, "US", "Vertex Ungrounded - ALS US"),
    ]
    
    results = []
    for vendor, model, grounded, country, name in tests:
        result = await run_test_with_als(adapter, vendor, model, grounded, country, name)
        results.append({
            "test": name,
            "vendor": vendor,
            "country": country,
            **result
        })
        await asyncio.sleep(2)  # Rate limit protection
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    successful = sum(1 for r in results if r['success'])
    print(f"Success rate: {successful}/{len(results)}")
    
    # Check ALS effectiveness
    als_tests = [r for r in results if r.get('country') and r['success']]
    if als_tests:
        als_effective = sum(1 for r in als_tests if r.get('regional_indicators'))
        print(f"ALS effectiveness: {als_effective}/{len(als_tests)} showed regional signals")
    
    # Save results
    with open(f"als_test_results_{int(time.time())}.json", 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n✅ Test complete")

if __name__ == "__main__":
    asyncio.run(main())