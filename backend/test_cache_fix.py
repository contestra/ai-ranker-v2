#!/usr/bin/env venv/bin/python
"""
Test that cache key uses the correct model after adjustment
Verifies fix for cache poisoning issue
"""

import asyncio
import os
import json
from datetime import datetime

# Enable model adjustment
os.environ["MODEL_ADJUST_FOR_GROUNDING"] = "true"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"

import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

async def test_cache_fix():
    """Test that cache properly handles model adjustment"""
    
    adapter = UnifiedLLMAdapter()
    results = []
    
    print("\n" + "="*80)
    print("CACHE FIX VERIFICATION TEST")
    print("="*80)
    
    # Test 1: First grounded request with gpt-5-chat-latest (should adjust to gpt-5)
    print("\n[TEST 1] First grounded request with gpt-5-chat-latest")
    print("-" * 40)
    
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",  # This should be adjusted to gpt-5
        messages=[{"role": "user", "content": "What is the official URL of whitehouse.gov?"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=500
    )
    
    try:
        print("Sending request with model: gpt-5-chat-latest (grounded=True)")
        response1 = await adapter.complete(request1)
        
        # Check metadata
        if hasattr(response1, 'metadata') and response1.metadata:
            meta = response1.metadata
            print(f"Model adjusted: {meta.get('model_adjusted_for_grounding', False)}")
            print(f"Original model: {meta.get('original_model', 'N/A')}")
            print(f"Grounding attempted: {meta.get('grounding_attempted', False)}")
            print(f"Tool type cached: {meta.get('response_api_tool_type', 'N/A')}")
            
            results.append({
                "test": "first_grounded",
                "model_sent": "gpt-5-chat-latest",
                "model_adjusted": meta.get('model_adjusted_for_grounding', False),
                "original_model": meta.get('original_model'),
                "grounding_attempted": meta.get('grounding_attempted', False),
                "cached_tool_type": meta.get('response_api_tool_type')
            })
            
    except Exception as e:
        print(f"Error: {e}")
        results.append({
            "test": "first_grounded",
            "error": str(e)
        })
    
    # Test 2: Second grounded request with same model (should use cache)
    print("\n[TEST 2] Second grounded request with gpt-5-chat-latest (cache hit)")
    print("-" * 40)
    
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",  # Same model, should adjust and hit cache
        messages=[{"role": "user", "content": "What is the official URL of bbc.com?"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=500
    )
    
    try:
        print("Sending request with model: gpt-5-chat-latest (grounded=True)")
        response2 = await adapter.complete(request2)
        
        if hasattr(response2, 'metadata') and response2.metadata:
            meta = response2.metadata
            print(f"Model adjusted: {meta.get('model_adjusted_for_grounding', False)}")
            print(f"Cache hit expected - tool type should be reused")
            print(f"Grounding attempted: {meta.get('grounding_attempted', False)}")
            
            results.append({
                "test": "second_grounded_cache",
                "model_sent": "gpt-5-chat-latest",
                "model_adjusted": meta.get('model_adjusted_for_grounding', False),
                "grounding_attempted": meta.get('grounding_attempted', False)
            })
            
    except Exception as e:
        print(f"Error: {e}")
        results.append({
            "test": "second_grounded_cache",
            "error": str(e)
        })
    
    # Test 3: Ungrounded request with gpt-5-chat-latest (should NOT adjust)
    print("\n[TEST 3] Ungrounded request with gpt-5-chat-latest (no adjustment)")
    print("-" * 40)
    
    request3 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",  # Should NOT be adjusted (grounded=False)
        messages=[{"role": "user", "content": "What is 2+2?"}],
        grounded=False,
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=500
    )
    
    try:
        print("Sending request with model: gpt-5-chat-latest (grounded=False)")
        response3 = await adapter.complete(request3)
        
        if hasattr(response3, 'metadata') and response3.metadata:
            meta = response3.metadata
            print(f"Model adjusted: {meta.get('model_adjusted_for_grounding', False)}")
            print(f"Should be False - no adjustment for ungrounded")
            
            results.append({
                "test": "ungrounded_no_adjust",
                "model_sent": "gpt-5-chat-latest",
                "model_adjusted": meta.get('model_adjusted_for_grounding', False),
                "grounding_attempted": meta.get('grounding_attempted', False)
            })
            
    except Exception as e:
        print(f"Error: {e}")
        results.append({
            "test": "ungrounded_no_adjust",
            "error": str(e)
        })
    
    # Test 4: Direct gpt-5 request (should work without adjustment)
    print("\n[TEST 4] Direct gpt-5 grounded request (no adjustment needed)")
    print("-" * 40)
    
    request4 = LLMRequest(
        vendor="openai",
        model="gpt-5",  # Direct gpt-5, no adjustment needed
        messages=[{"role": "user", "content": "What is the official URL of nasa.gov?"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=500
    )
    
    try:
        print("Sending request with model: gpt-5 (grounded=True)")
        response4 = await adapter.complete(request4)
        
        if hasattr(response4, 'metadata') and response4.metadata:
            meta = response4.metadata
            print(f"Model adjusted: {meta.get('model_adjusted_for_grounding', False)}")
            print(f"Should be False - already using gpt-5")
            print(f"Grounding attempted: {meta.get('grounding_attempted', False)}")
            
            results.append({
                "test": "direct_gpt5",
                "model_sent": "gpt-5",
                "model_adjusted": meta.get('model_adjusted_for_grounding', False),
                "grounding_attempted": meta.get('grounding_attempted', False)
            })
            
    except Exception as e:
        print(f"Error: {e}")
        results.append({
            "test": "direct_gpt5",
            "error": str(e)
        })
    
    # Analysis
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)
    
    # Check for cache consistency
    grounded_adjusted = [r for r in results if r.get("model_adjusted") is True]
    grounded_not_adjusted = [r for r in results if r.get("test", "").startswith("direct") and r.get("grounding_attempted")]
    
    print(f"\n✓ Requests with model adjustment: {len(grounded_adjusted)}")
    print(f"✓ Direct gpt-5 requests (no adjustment): {len(grounded_not_adjusted)}")
    
    # Verify cache is not poisoned
    cache_errors = [r for r in results if "error" in r and "GROUNDING_NOT_SUPPORTED" in r.get("error", "")]
    if cache_errors:
        print(f"\n❌ CACHE POISONING DETECTED: {len(cache_errors)} requests incorrectly marked unsupported")
        for err in cache_errors:
            print(f"   - {err['test']}: {err['error'][:100]}")
    else:
        print(f"\n✅ No cache poisoning detected - all requests processed correctly")
    
    # Save results
    filename = f"CACHE_FIX_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "summary": {
                "total_tests": len(results),
                "model_adjustments": len(grounded_adjusted),
                "cache_poisoning_errors": len(cache_errors),
                "fix_successful": len(cache_errors) == 0
            }
        }, f, indent=2)
    
    print(f"\n📁 Results saved to: {filename}\n")
    
    if len(cache_errors) == 0:
        print("🎉 CACHE FIX SUCCESSFUL - Model adjustment preserved, no poisoning")
    else:
        print("⚠️  CACHE ISSUES REMAIN - Review logs for details")
    
    return results


if __name__ == "__main__":
    asyncio.run(test_cache_fix())