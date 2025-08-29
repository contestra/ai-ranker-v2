#!/usr/bin/env python3
"""
Test Vertex with ALS and all P0 fixes
"""
import asyncio
import os
import sys
import json
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_vertex_complete():
    """Test Vertex with all fixes"""
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*60)
    print("VERTEX COMPLETE TEST WITH P0 FIXES")
    print("="*60)
    
    # Test configurations
    tests = [
        # Basic Vertex test
        {
            "name": "Vertex Basic",
            "vendor": "vertex",
            "model": "publishers/google/models/gemini-2.5-pro",
            "als": None,
            "grounded": False
        },
        # Vertex with ALS
        {
            "name": "Vertex with US ALS",
            "vendor": "vertex",
            "model": "publishers/google/models/gemini-2.5-pro",
            "als": {"country_code": "US", "locale": "en-US"},
            "grounded": False
        },
        # Vertex with vendor inference
        {
            "name": "Vertex Inference Test",
            "vendor": None,  # Should infer from model
            "model": "publishers/google/models/gemini-2.5-pro",
            "als": None,
            "grounded": False
        },
        # Vertex JSON mode
        {
            "name": "Vertex JSON Mode",
            "vendor": "vertex",
            "model": "publishers/google/models/gemini-2.5-pro",
            "als": None,
            "grounded": False,
            "json_mode": True
        }
    ]
    
    results = []
    
    for test in tests:
        print(f"\n{'='*60}")
        print(f"TEST: {test['name']}")
        print(f"Model: {test['model']}")
        if test.get('als'):
            print(f"ALS: {test['als']['country_code']}")
        
        request = LLMRequest(
            vendor=test.get("vendor"),
            model=test["model"],
            messages=[{"role": "user", "content": "What is 2+2? Answer with just the number."}],
            temperature=0.1,
            max_tokens=50,
            grounded=test.get("grounded", False),
            als_context=test.get("als"),
            json_mode=test.get("json_mode", False)
        )
        
        try:
            response = await adapter.complete(request)
            
            print(f"✅ Success!")
            
            # Check P0 fixes
            checks = []
            
            # 1. Vendor field
            if hasattr(response, 'vendor') and response.vendor == "vertex":
                print(f"  ✅ Vendor: {response.vendor}")
                checks.append(True)
            else:
                print(f"  ❌ Vendor field missing or wrong")
                checks.append(False)
            
            # 2. Latency field
            if hasattr(response, 'latency_ms') and response.latency_ms is not None:
                print(f"  ✅ Latency: {response.latency_ms}ms")
                checks.append(True)
            else:
                print(f"  ❌ Latency field missing")
                checks.append(False)
            
            # 3. Success field
            if hasattr(response, 'success'):
                print(f"  ✅ Success: {response.success}")
                checks.append(True)
            else:
                print(f"  ❌ Success field missing")
                checks.append(False)
            
            # 4. Token usage normalization
            if response.usage:
                has_both = ('prompt_tokens' in response.usage and 
                           'input_tokens' in response.usage)
                if has_both:
                    print(f"  ✅ Token keys: both conventions present")
                    print(f"     prompt={response.usage['prompt_tokens']}, input={response.usage['input_tokens']}")
                    checks.append(True)
                else:
                    print(f"  ❌ Token normalization incomplete")
                    checks.append(False)
            
            # 5. Region consistency
            if response.metadata and 'region' in response.metadata:
                if response.metadata['region'] == "europe-west4":
                    print(f"  ✅ Region: {response.metadata['region']} (consistent)")
                    checks.append(True)
                else:
                    print(f"  ⚠️  Region: {response.metadata['region']} (expected europe-west4)")
                    checks.append(False)
            
            # 6. ALS check
            if test.get('als'):
                if hasattr(request, 'metadata') and request.metadata.get('als_present'):
                    print(f"  ✅ ALS applied: SHA256={request.metadata.get('als_block_sha256', '')[:16]}...")
                    if 'als_block_text' in request.metadata:
                        print(f"  ❌ Raw ALS text present (security issue)")
                        checks.append(False)
                    else:
                        print(f"  ✅ No raw ALS text (secure)")
                        checks.append(True)
            
            # Response content
            if response.content:
                print(f"  Response: {response.content[:100]}")
            
            result = {
                "test": test["name"],
                "success": True,
                "p0_checks": all(checks),
                "checks": checks,
                "response": response.content[:100] if response.content else None
            }
            results.append(result)
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            results.append({
                "test": test["name"],
                "success": False,
                "error": str(e)[:200]
            })
        
        await asyncio.sleep(1)  # Rate limiting
    
    # Summary
    print("\n" + "="*60)
    print("VERTEX TEST SUMMARY")
    print("="*60)
    
    successful = sum(1 for r in results if r['success'])
    print(f"Success rate: {successful}/{len(results)}")
    
    p0_verified = sum(1 for r in results if r.get('p0_checks'))
    print(f"P0 fixes verified: {p0_verified}/{successful}")
    
    print("\nIndividual test results:")
    for r in results:
        status = "✅" if r['success'] else "❌"
        p0_status = "✅" if r.get('p0_checks') else "⚠️" if r['success'] else ""
        print(f"  {status} {r['test']} {p0_status}")
    
    return successful == len(results)

if __name__ == "__main__":
    success = asyncio.run(test_vertex_complete())
    sys.exit(0 if success else 1)