#!/usr/bin/env python3
"""
Integration test for router capabilities.
Tests the complete flow with real adapters.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

# Disable rate limiter for testing
os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_router_with_real_adapter():
    """Test router with real OpenAI adapter."""
    print("\n" + "="*60)
    print("ROUTER INTEGRATION TEST")
    print("="*60)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    router = UnifiedLLMAdapter()
    
    # Test 1: GPT-4o without reasoning (should work)
    print("\n[Test 1: GPT-4o without reasoning]")
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        grounded=False,
        max_tokens=50
    )
    
    try:
        response = await router.complete(request)
        print(f"✅ Success: {response.success}")
        print(f"Response: {response.content[:100]}")
        print(f"Metadata: {response.metadata}")
        assert response.success is True
        assert "reasoning_hint_dropped" in response.metadata
        assert "circuit_breaker_status" in response.metadata
        print("✅ Metadata fields present")
    except Exception as e:
        print(f"❌ Error: {str(e)[:200]}")
        return False
    
    # Test 2: GPT-4o with reasoning parameters (should drop them)
    print("\n[Test 2: GPT-4o with reasoning - should drop]")
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is 3+3?"}],
        grounded=False,
        max_tokens=50,
        meta={"reasoning_effort": "high"}
    )
    
    try:
        response2 = await router.complete(request2)
        print(f"✅ Success: {response2.success}")
        
        # Check that reasoning was dropped
        assert response2.metadata.get("reasoning_hint_dropped") is True
        print("✅ Reasoning parameters correctly dropped")
        
        # Verify request meta was cleaned
        assert "reasoning_effort" not in request2.meta
        print("✅ Request meta cleaned")
    except Exception as e:
        print(f"❌ Error: {str(e)[:200]}")
        return False
    
    # Test 3: Check capability matrix
    print("\n[Test 3: Capability matrix]")
    
    # GPT-4o should not support reasoning
    caps_4o = router._capabilities_for("openai", "gpt-4o")
    assert caps_4o["supports_reasoning_effort"] is False
    print("✅ GPT-4o: no reasoning support")
    
    # GPT-5 should support reasoning
    caps_5 = router._capabilities_for("openai", "gpt-5-2025-08-07")
    assert caps_5["supports_reasoning_effort"] is True
    print("✅ GPT-5: reasoning support")
    
    # Gemini 2.5 should support thinking
    caps_gemini = router._capabilities_for("vertex", "publishers/google/models/gemini-2.5-flash")
    assert caps_gemini["supports_thinking_budget"] is True
    print("✅ Gemini 2.5: thinking support")
    
    print("\n" + "="*60)
    print("✅ ALL INTEGRATION TESTS PASSED")
    print("="*60)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_router_with_real_adapter())
    sys.exit(0 if success else 1)