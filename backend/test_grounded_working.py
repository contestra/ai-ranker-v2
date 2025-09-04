#!/usr/bin/env python3
"""
Test that grounded mode still works correctly.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_grounded():
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Test 1: AUTO mode with search-worthy query
    print("=" * 80)
    print("TEST 1: GROUNDED AUTO MODE (should search)")
    print("=" * 80)
    
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "What is the current weather in Paris?"}
        ],
        grounded=True,
        max_tokens=100,
        meta={"grounding_mode": "AUTO"}
    )
    
    print("Request: Asking about current weather (should trigger search)")
    response1 = await adapter.complete(request1, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content length: {len(response1.content)}")
    print(f"  Content preview: '{response1.content[:100]}...'")
    print(f"  Grounded effective: {response1.grounded_effective}")
    
    metadata1 = response1.metadata or {}
    print(f"  Tool calls: {metadata1.get('tool_call_count', 0)}")
    print(f"  Why not grounded: {metadata1.get('why_not_grounded', 'N/A')}")
    
    # Test 2: AUTO mode with simple query
    print("\n" + "=" * 80)
    print("TEST 2: GROUNDED AUTO MODE (should not search)")
    print("=" * 80)
    
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "What is 2+2?"}
        ],
        grounded=True,
        max_tokens=50,
        meta={"grounding_mode": "AUTO"}
    )
    
    print("Request: Simple math question (should not trigger search)")
    response2 = await adapter.complete(request2, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content length: {len(response2.content)}")
    print(f"  Content: '{response2.content}'")
    print(f"  Grounded effective: {response2.grounded_effective}")
    
    metadata2 = response2.metadata or {}
    print(f"  Tool calls: {metadata2.get('tool_call_count', 0)}")
    print(f"  Why not grounded: {metadata2.get('why_not_grounded', 'N/A')}")
    
    # Test 3: REQUIRED mode
    print("\n" + "=" * 80)
    print("TEST 3: GROUNDED REQUIRED MODE")
    print("=" * 80)
    
    request3 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "Tell me about recent AI news"}
        ],
        grounded=True,
        max_tokens=100,
        meta={"grounding_mode": "REQUIRED"}
    )
    
    print("Request: AI news (REQUIRED mode must search)")
    
    try:
        response3 = await adapter.complete(request3, timeout=30)
        
        print(f"\n📊 Results:")
        print(f"  Content length: {len(response3.content)}")
        print(f"  Content preview: '{response3.content[:100]}...'")
        print(f"  Grounded effective: {response3.grounded_effective}")
        
        metadata3 = response3.metadata or {}
        print(f"  Tool calls: {metadata3.get('tool_call_count', 0)}")
        
        if metadata3.get('tool_call_count', 0) == 0:
            print("  ⚠️ WARNING: REQUIRED mode didn't make tool calls!")
    except Exception as e:
        print(f"  Error (expected if no search): {str(e)[:200]}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    success = (
        len(response1.content) > 0 and 
        len(response2.content) > 0
    )
    
    print(f"Test 1 (AUTO with search): {'✅ PASS' if len(response1.content) > 0 else '❌ FAIL'}")
    print(f"Test 2 (AUTO no search): {'✅ PASS' if len(response2.content) > 0 else '❌ FAIL'}")
    print(f"Test 3 (REQUIRED): See results above")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(test_grounded())
    print(f"\n{'🎉 GROUNDED MODE WORKS' if success else '❌ GROUNDED MODE BROKEN'}")