#!/usr/bin/env python3
"""
Unit tests for OpenAI adapter capability probe cache behavior
Tests that:
1. First grounded call on unsupported model → cache set to False, Required raises
2. Second grounded call → tools not attached, Preferred returns ungrounded
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["ALLOW_PREVIEW_COMPAT"] = "false"
os.environ["OPENAI_READ_TIMEOUT_MS"] = "120000"
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.types import LLMRequest

async def test_cache_behavior():
    """Test that capability probe cache works correctly"""
    
    print("="*60)
    print("Testing OpenAI Capability Probe Cache Behavior")
    print("="*60)
    
    # Create a fresh adapter instance
    adapter = OpenAIAdapter()
    model_name = "gpt-5-chat-latest"  # Known unsupported model
    
    # Check initial cache state
    print(f"\n1. Initial cache state:")
    print(f"   Cache for {model_name}: {adapter._web_search_support.get(model_name, 'Not cached')}")
    assert adapter._web_search_support.get(model_name) is None, "Cache should start empty"
    print("   ✅ Cache starts empty")
    
    # Test 1: First Required call should probe and fail
    print(f"\n2. First grounded call (REQUIRED mode):")
    request1 = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[{'role': 'user', 'content': 'Test'}],
        grounded=True,
        temperature=0.7,
        max_tokens=100
    )
    request1.meta = {'grounding_mode': 'REQUIRED'}
    
    try:
        await adapter.complete(request1)
        print("   ❌ ERROR: Should have raised GROUNDING_NOT_SUPPORTED")
        assert False, "Required mode should have failed"
    except RuntimeError as e:
        if "GROUNDING_NOT_SUPPORTED" in str(e):
            print(f"   ✅ Correctly raised: {str(e)[:80]}...")
            # Check cache was set
            cache_value = adapter._web_search_support.get(model_name)
            print(f"   Cache after probe: {cache_value}")
            assert cache_value is False, "Cache should be set to False after probe"
            print("   ✅ Cache set to False")
        else:
            print(f"   ❌ Wrong error: {e}")
            assert False, f"Expected GROUNDING_NOT_SUPPORTED, got {e}"
    
    # Test 2: Second Preferred call should use cache, not probe again
    print(f"\n3. Second grounded call (PREFERRED mode):")
    request2 = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[{'role': 'user', 'content': 'What is 2+2?'}],
        grounded=True,
        temperature=0.7,
        max_tokens=100
    )
    request2.meta = {'grounding_mode': 'AUTO'}
    
    # Track if probe was called (it shouldn't be)
    original_probe = adapter.client.responses.create
    probe_called = False
    
    async def mock_create(*args, **kwargs):
        nonlocal probe_called
        # Check if this is a probe call (very small max_output_tokens)
        if kwargs.get('max_output_tokens') == 16 and kwargs.get('input') == 'capability probe':
            probe_called = True
            print("   ⚠️ Probe was called (shouldn't happen on second call)")
        return await original_probe(*args, **kwargs)
    
    # Temporarily replace the create method
    adapter.client.responses.create = mock_create
    
    try:
        response = await adapter.complete(request2)
        
        # Check response characteristics
        print(f"   Response success: {response.success}")
        print(f"   Content length: {len(response.content) if response.content else 0}")
        print(f"   Grounded effective: {response.grounded_effective}")
        print(f"   Why not grounded: {response.metadata.get('why_not_grounded', 'N/A')}")
        
        # Verify expectations
        assert response.success, "Preferred mode should succeed"
        assert not response.grounded_effective, "Should not be grounded"
        assert response.metadata.get('why_not_grounded') == "web_search unsupported for model"
        assert not probe_called, "Probe should not be called on second request (cache hit)"
        
        print("   ✅ Used cache (no probe)")
        print("   ✅ Returned ungrounded content with correct metadata")
        
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        assert False, f"Preferred mode should succeed, got {e}"
    finally:
        # Restore original method
        adapter.client.responses.create = original_probe
    
    # Test 3: Verify Required still fails on subsequent calls
    print(f"\n4. Third grounded call (REQUIRED mode again):")
    request3 = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[{'role': 'user', 'content': 'Test again'}],
        grounded=True,
        temperature=0.7,
        max_tokens=100
    )
    request3.meta = {'grounding_mode': 'REQUIRED'}
    
    try:
        await adapter.complete(request3)
        print("   ❌ ERROR: Should have raised GROUNDING_NOT_SUPPORTED")
        assert False, "Required mode should still fail"
    except RuntimeError as e:
        if "GROUNDING_NOT_SUPPORTED" in str(e):
            print("   ✅ Still correctly fails for Required mode")
        else:
            print(f"   ❌ Wrong error: {e}")
            assert False, f"Expected GROUNDING_NOT_SUPPORTED, got {e}"
    
    print("\n" + "="*60)
    print("✅ All cache behavior tests passed!")
    print("="*60)
    print("\nSummary:")
    print("1. Cache starts empty ✅")
    print("2. First call probes and caches result ✅")
    print("3. Subsequent calls use cache (no re-probe) ✅")
    print("4. Required mode consistently fails ✅")
    print("5. Preferred mode proceeds ungrounded ✅")

if __name__ == "__main__":
    asyncio.run(test_cache_behavior())