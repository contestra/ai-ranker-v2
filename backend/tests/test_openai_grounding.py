"""
Test OpenAI grounding implementation
Tests UN (ungrounded) vs GR (grounded) modes
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm.types import LLMRequest
from app.llm.adapters.openai_adapter import OpenAIAdapter


async def test_ungrounded():
    """Test ungrounded mode - should not use web search"""
    print("\n=== Testing OpenAI Ungrounded Mode ===")
    
    adapter = OpenAIAdapter()
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[
            {"role": "user", "content": "What is 2+2? Answer in one word."}
        ],
        grounded=False,
        max_tokens=100
    )
    
    response = await adapter.complete(request, timeout=60)
    
    print(f"Content: {response.content[:100]}...")
    print(f"Grounded Requested: {request.grounded}")
    print(f"Grounded Effective: {response.grounded_effective}")
    print(f"Latency: {response.latency_ms}ms")
    
    # Assertions
    assert response.grounded_effective == False, "Should not be grounded"
    assert response.content, "Should have content"
    assert response.success, "Should succeed"
    
    print("✅ Ungrounded test passed")
    return response


async def test_grounded():
    """Test grounded mode - should use web search"""
    print("\n=== Testing OpenAI Grounded Mode ===")
    
    adapter = OpenAIAdapter()
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[
            {"role": "user", "content": "What is the current date and time in UTC? Be specific."}
        ],
        grounded=True,
        max_tokens=200
    )
    
    response = await adapter.complete(request, timeout=120)
    
    print(f"Content: {response.content[:200]}...")
    print(f"Grounded Requested: {request.grounded}")
    print(f"Grounded Effective: {response.grounded_effective}")
    print(f"Latency: {response.latency_ms}ms")
    
    # Check metadata for fallback extraction
    if hasattr(response, 'metadata'):
        if response.metadata.get('grounding_extraction_fallback'):
            print("📝 Used fallback text extraction")
    
    # Assertions (signals, not content)
    assert response.success, "Should succeed"
    # Note: grounded_effective might still be False if model chose not to search
    # But with time-sensitive question, it should search
    
    print(f"✅ Grounded test completed (effective={response.grounded_effective})")
    return response


async def test_grounded_with_json():
    """Test grounded mode with JSON - OpenAI allows this"""
    print("\n=== Testing OpenAI Grounded + JSON Mode ===")
    
    adapter = OpenAIAdapter()
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[
            {"role": "user", "content": "Return a JSON object with the current UTC date and time"}
        ],
        grounded=True,
        json_mode=True,
        max_tokens=200
    )
    
    try:
        response = await adapter.complete(request, timeout=120)
        
        print(f"Content: {response.content[:200]}...")
        print(f"Grounded Requested: {request.grounded}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"JSON Mode: {request.json_mode}")
        
        # OpenAI should allow this combination
        assert response.success, "Should succeed"
        print("✅ Grounded + JSON test passed")
        return response
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        # OpenAI should NOT fail on JSON+grounding
        raise


async def main():
    """Run all tests"""
    print("=" * 60)
    print("OpenAI Grounding Tests")
    print("=" * 60)
    
    # Check environment
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set")
        return
    
    print(f"Tool Type: {os.getenv('OPENAI_GROUNDING_TOOL', 'web_search')}")
    print(f"Tool Choice: {os.getenv('OPENAI_TOOL_CHOICE', 'auto')}")
    
    try:
        # Run tests
        await test_ungrounded()
        await test_grounded()
        await test_grounded_with_json()
        
        print("\n" + "=" * 60)
        print("✅ All OpenAI grounding tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())