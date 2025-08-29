#!/usr/bin/env python3
"""
Comprehensive test of ALS with both models, grounded/ungrounded, US/DE
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
os.environ["ALLOWED_VERTEX_MODELS"] = "publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

# Test prompt
PROMPT = "List the 10 most trusted longevity supplement brands"

async def run_test(adapter, vendor, model, grounded, country, test_name):
    """Run a single test configuration"""
    
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"Vendor: {vendor}, Model: {model}")
    print(f"Grounded: {grounded}, Country: {country}")
    
    # Build request with ALS context
    als_context = {'country_code': country, 'locale': f'en-{country}'} if country else None
    
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.3 if vendor == "openai" else 0.7,
        max_tokens=500,
        grounded=grounded,
        als_context=als_context
    )
    
    try:
        start = time.perf_counter()
        response = await adapter.complete(request)
        latency_ms = int((time.perf_counter() - start) * 1000)
        
        print(f"✅ Success in {latency_ms}ms")
        
        # Check ALS application
        if als_context:
            if hasattr(request, 'als_applied') and request.als_applied:
                print(f"✅ ALS applied: {country}")
                if hasattr(request, 'metadata'):
                    print(f"   SHA256: {request.metadata.get('als_block_sha256', '')[:16]}...")
                    print(f"   Length: {request.metadata.get('als_nfc_length', 'unknown')} chars")
            else:
                print(f"❌ ALS NOT applied")
        
        # Check grounding
        if hasattr(response, 'metadata') and response.metadata:
            meta = response.metadata
            print(f"Grounded effective: {meta.get('grounded_effective', False)}")
            print(f"Tool calls: {meta.get('tool_call_count', 0)}")
            print(f"Response API: {meta.get('response_api', 'unknown')}")
            
            # Store metadata for analysis
            result_meta = {
                'grounded_effective': meta.get('grounded_effective', False),
                'tool_call_count': meta.get('tool_call_count', 0),
                'response_api': meta.get('response_api'),
                'provider_api_version': meta.get('provider_api_version'),
                'region': meta.get('region')
            }
        else:
            result_meta = {}
        
        # Extract first 3 brands from response
        if response.content:
            lines = response.content.split('\n')
            brands = []
            for line in lines:
                if line.strip() and any(c.isdigit() for c in line[:3]):
                    # Clean and extract brand name
                    brand = line.strip()
                    for i, char in enumerate(brand):
                        if char.isdigit() or char in '.):':
                            continue
                        else:
                            brand = brand[i:].strip()
                            break
                    if brand and len(brand) < 100:
                        # Remove common prefixes
                        brand = brand.lstrip('*- ')
                        # Extract just the brand name (before descriptions)
                        if ' - ' in brand:
                            brand = brand.split(' - ')[0]
                        if ' – ' in brand:
                            brand = brand.split(' – ')[0]
                        if ':' in brand:
                            brand = brand.split(':')[0]
                        brands.append(brand.strip())
                        if len(brands) >= 3:
                            break
            
            if brands:
                print(f"Top 3 brands: {', '.join(brands)}")
        
        return {
            'success': True,
            'test': test_name,
            'vendor': vendor,
            'model': model,
            'grounded': grounded,
            'country': country,
            'latency_ms': latency_ms,
            'als_applied': hasattr(request, 'als_applied') and request.als_applied,
            'als_sha256': request.metadata.get('als_block_sha256', '')[:16] if hasattr(request, 'metadata') else '',
            'brands': brands if 'brands' in locals() else [],
            'metadata': result_meta,
            'content_preview': response.content[:200] if response.content else ''
        }
        
    except Exception as e:
        print(f"❌ Failed: {str(e)[:100]}")
        return {
            'success': False,
            'test': test_name,
            'vendor': vendor,
            'model': model,
            'grounded': grounded,
            'country': country,
            'error': str(e)[:200]
        }

async def main():
    """Run comprehensive test matrix"""
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*70)
    print("COMPREHENSIVE ALS TEST MATRIX")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Prompt: {PROMPT}")
    
    # Define test matrix
    tests = [
        # OpenAI tests
        ("openai", "gpt-5", False, "US", "OpenAI Ungrounded US"),
        ("openai", "gpt-5", False, "DE", "OpenAI Ungrounded DE"),
        ("openai", "gpt-5", True, "US", "OpenAI Grounded US"),
        ("openai", "gpt-5", True, "DE", "OpenAI Grounded DE"),
        
        # Vertex tests
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "US", "Vertex Ungrounded US"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "DE", "Vertex Ungrounded DE"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "US", "Vertex Grounded US"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "DE", "Vertex Grounded DE"),
    ]
    
    results = []
    for vendor, model, grounded, country, name in tests:
        result = await run_test(adapter, vendor, model, grounded, country, name)
        results.append(result)
        await asyncio.sleep(2)  # Rate limiting
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    successful = sum(1 for r in results if r['success'])
    print(f"Success rate: {successful}/{len(results)}")
    
    # ALS effectiveness
    als_tests = [r for r in results if r.get('country') and r['success']]
    if als_tests:
        als_applied = sum(1 for r in als_tests if r.get('als_applied'))
        print(f"ALS applied: {als_applied}/{len(als_tests)}")
    
    # Grounding effectiveness
    grounded_tests = [r for r in results if r.get('grounded') and r['success']]
    if grounded_tests:
        grounded_effective = sum(1 for r in grounded_tests if r.get('metadata', {}).get('grounded_effective'))
        print(f"Grounding effective: {grounded_effective}/{len(grounded_tests)}")
    
    # Brand consistency
    print("\nTop brands by frequency:")
    brand_counts = {}
    for r in results:
        if r['success'] and 'brands' in r:
            for brand in r['brands']:
                brand_counts[brand] = brand_counts.get(brand, 0) + 1
    
    for brand, count in sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {brand}: {count}/{len(results)} appearances")
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"als_test_results_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed results saved to: {filename}")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(main())