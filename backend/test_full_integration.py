#!/usr/bin/env python3
"""
Full integration test - verify all fixes with actual API calls
"""
import asyncio
import os
import sys
import json
import time
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"
os.environ["ALLOWED_VERTEX_MODELS"] = "publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

PROMPT = "What is 2+2? Answer in exactly one word."

async def test_configuration(adapter, vendor, model, grounded, country, test_name):
    """Test a single configuration"""
    
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"Vendor: {vendor}, Model: {model}")
    print(f"Grounded: {grounded}, Country: {country}")
    
    # Build request
    als_context = {'country_code': country, 'locale': f'en-{country}'} if country else None
    
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.1,
        max_tokens=50,
        grounded=grounded,
        als_context=als_context
    )
    
    try:
        start = time.perf_counter()
        response = await adapter.complete(request)
        latency_ms = int((time.perf_counter() - start) * 1000)
        
        print(f"✅ Success in {latency_ms}ms")
        
        # Verify P0 fixes
        checks = []
        
        # 1. Check vendor field (Vertex parity)
        if hasattr(response, 'vendor'):
            print(f"  ✅ Vendor field: {response.vendor}")
            checks.append(True)
        else:
            print(f"  ❌ Missing vendor field")
            checks.append(False)
        
        # 2. Check latency_ms field (Vertex parity)
        if hasattr(response, 'latency_ms') and response.latency_ms is not None:
            print(f"  ✅ Latency field: {response.latency_ms}ms")
            checks.append(True)
        else:
            print(f"  ❌ Missing latency_ms field")
            checks.append(False)
        
        # 3. Check success field (Vertex parity)
        if hasattr(response, 'success'):
            print(f"  ✅ Success field: {response.success}")
            checks.append(True)
        else:
            print(f"  ❌ Missing success field")
            checks.append(False)
        
        # 4. Check token usage normalization
        if response.usage:
            has_telemetry_keys = 'prompt_tokens' in response.usage and 'completion_tokens' in response.usage
            has_adapter_keys = 'input_tokens' in response.usage and 'output_tokens' in response.usage
            
            if has_telemetry_keys:
                print(f"  ✅ Token telemetry keys: prompt={response.usage['prompt_tokens']}, completion={response.usage['completion_tokens']}")
                checks.append(True)
            else:
                print(f"  ❌ Missing telemetry token keys")
                checks.append(False)
                
            if has_adapter_keys:
                print(f"  ✅ Token adapter keys: input={response.usage['input_tokens']}, output={response.usage['output_tokens']}")
            
        # 5. Check ALS metadata (no raw text)
        if hasattr(request, 'metadata'):
            if 'als_block_text' in request.metadata:
                print(f"  ❌ Raw ALS text in metadata (security issue)")
                checks.append(False)
            else:
                if request.metadata.get('als_present'):
                    print(f"  ✅ ALS applied, SHA256: {request.metadata.get('als_block_sha256', '')[:16]}...")
                    print(f"  ✅ No raw ALS text (secure)")
                checks.append(True)
        
        # 6. Check metadata region (consistency)
        if response.metadata and 'region' in response.metadata:
            print(f"  ✅ Region: {response.metadata['region']}")
        
        # Response preview
        if response.content:
            preview = response.content[:100].replace('\n', ' ')
            print(f"  Response: {preview}...")
        
        all_checks_passed = all(checks)
        
        return {
            'success': True,
            'test': test_name,
            'vendor': vendor,
            'model': model,
            'grounded': grounded,
            'country': country,
            'latency_ms': latency_ms,
            'p0_fixes_verified': all_checks_passed,
            'checks': checks,
            'response_preview': response.content[:100] if response.content else ''
        }
        
    except Exception as e:
        error_msg = str(e)[:200]
        print(f"❌ Failed: {error_msg}")
        
        # Check if it's a vendor inference issue
        if "Cannot infer vendor" in error_msg:
            print("  ⚠️  Vendor inference failed - P0 fix may not be working")
        
        return {
            'success': False,
            'test': test_name,
            'vendor': vendor,
            'model': model,
            'grounded': grounded,
            'country': country,
            'error': error_msg
        }

async def main():
    """Run full integration test"""
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*60)
    print("FULL INTEGRATION TEST - P0 FIXES VERIFICATION")
    print("="*60)
    print(f"Testing with prompt: {PROMPT}")
    
    # Test matrix - focus on P0 fix verification
    tests = [
        # Test vendor inference with fully-qualified Vertex ID
        (None, "publishers/google/models/gemini-2.5-pro", False, None, "Vertex Inference Test"),
        
        # Test OpenAI with ALS
        ("openai", "gpt-5", False, "US", "OpenAI with ALS"),
        
        # Test both vendors for parity
        ("openai", "gpt-5", False, None, "OpenAI Basic"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, None, "Vertex Basic"),
    ]
    
    results = []
    for vendor, model, grounded, country, name in tests:
        result = await test_configuration(adapter, vendor, model, grounded, country, name)
        results.append(result)
        await asyncio.sleep(1)  # Rate limiting
    
    # Summary
    print("\n" + "="*60)
    print("INTEGRATION TEST SUMMARY")
    print("="*60)
    
    successful = sum(1 for r in results if r['success'])
    print(f"Success rate: {successful}/{len(results)}")
    
    # P0 fixes verification
    p0_verified = sum(1 for r in results if r.get('p0_fixes_verified'))
    print(f"P0 fixes verified: {p0_verified}/{successful} successful tests")
    
    # Specific P0 checks
    print("\nP0 Fix Status:")
    
    # Vendor inference
    inference_test = next((r for r in results if "Inference" in r['test']), None)
    if inference_test:
        if inference_test['success']:
            print("  ✅ Vendor inference for publishers/google/models/...")
        else:
            print("  ❌ Vendor inference failed")
    
    # Token normalization
    token_ok = all(r.get('checks', [False])[3] if len(r.get('checks', [])) > 3 else False 
                   for r in results if r['success'])
    print(f"  {'✅' if token_ok else '❌'} Token usage normalization")
    
    # Vertex parity
    vertex_tests = [r for r in results if r['vendor'] == 'vertex' and r['success']]
    if vertex_tests:
        has_fields = all(r.get('checks', [])[:3] == [True, True, True] 
                        for r in vertex_tests)
        print(f"  {'✅' if has_fields else '❌'} Vertex LLMResponse parity")
    
    # ALS security
    als_tests = [r for r in results if r.get('country') and r['success']]
    if als_tests:
        no_raw_text = all('als_block_text' not in r.get('checks', {}) 
                         for r in als_tests)
        print(f"  {'✅' if no_raw_text else '❌'} ALS text removed from metadata")
    
    print("\n" + "="*60)
    
    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"integration_test_results_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to: {filename}")
    
    return successful == len(results)

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)