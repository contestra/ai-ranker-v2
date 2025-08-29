#!/usr/bin/env python3
"""
Final verification of all fixes - quick test
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def main():
    """Quick final verification"""
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*60)
    print("FINAL VERIFICATION - ALL FIXES")
    print("="*60)
    
    # Test 1: ALS Determinism
    print("\n1. ALS DETERMINISM TEST")
    sha_values = []
    for i in range(3):
        request = LLMRequest(
            vendor="openai",
            model="gpt-5",
            messages=[{"role": "user", "content": "Test"}],
            als_context={'country_code': 'US', 'locale': 'en-US'}
        )
        modified = adapter._apply_als(request)
        sha = modified.metadata.get('als_block_sha256', '')
        sha_values.append(sha)
        print(f"   Run {i+1}: SHA256={sha[:16]}...")
    
    if len(set(sha_values)) == 1:
        print("   ✅ ALS is deterministic")
    else:
        print("   ❌ ALS is NOT deterministic")
    
    # Test 2: Vendor Inference
    print("\n2. VENDOR INFERENCE TEST")
    test_models = [
        ("publishers/google/models/gemini-2.5-pro", "vertex"),
        ("gpt-5", "openai")
    ]
    for model, expected in test_models:
        vendor = adapter.get_vendor_for_model(model)
        if vendor == expected:
            print(f"   ✅ {model[:30]}... -> {vendor}")
        else:
            print(f"   ❌ {model[:30]}... -> {vendor} (expected {expected})")
    
    # Test 3: Quick API calls
    print("\n3. API CALL TEST")
    
    # OpenAI
    try:
        request = LLMRequest(
            vendor="openai",
            model="gpt-5",
            messages=[{"role": "user", "content": "Say 'hi'"}],
            max_tokens=10
        )
        response = await adapter.complete(request)
        
        checks = [
            ("vendor", hasattr(response, 'vendor')),
            ("latency_ms", hasattr(response, 'latency_ms')),
            ("success", hasattr(response, 'success')),
            ("tokens", response.usage and 'prompt_tokens' in response.usage)
        ]
        
        all_good = all(c[1] for c in checks)
        print(f"   OpenAI: {'✅' if all_good else '❌'} - {', '.join(c[0] for c in checks if c[1])}")
        
    except Exception as e:
        print(f"   OpenAI: ❌ {str(e)[:50]}")
    
    # Vertex
    try:
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[{"role": "user", "content": "Say 'hi'"}],
            max_tokens=10
        )
        response = await adapter.complete(request)
        
        checks = [
            ("vendor", hasattr(response, 'vendor')),
            ("latency_ms", hasattr(response, 'latency_ms')),
            ("success", hasattr(response, 'success')),
            ("tokens", response.usage and 'input_tokens' in response.usage)
        ]
        
        all_good = all(c[1] for c in checks)
        print(f"   Vertex: {'✅' if all_good else '❌'} - {', '.join(c[0] for c in checks if c[1])}")
        
    except Exception as e:
        print(f"   Vertex: ❌ {str(e)[:50]}")
    
    # Test 4: Security check
    print("\n4. SECURITY TEST")
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "Test"}],
        als_context={'country_code': 'US'}
    )
    modified = adapter._apply_als(request)
    
    if 'als_block_text' in modified.metadata:
        print("   ❌ Raw ALS text found in metadata (security issue)")
    else:
        print("   ✅ No raw ALS text in metadata (secure)")
    
    print("\n" + "="*60)
    print("FINAL VERIFICATION COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())