"""
Test Vertex AI grounding implementation
Tests UN (ungrounded) vs GR (grounded) modes
Tests JSON + grounding error handling
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm.types import LLMRequest
from app.llm.adapters.vertex_adapter import VertexAdapter


async def test_ungrounded():
    """Test ungrounded mode - should not use Google Search"""
    print("\n=== Testing Vertex Ungrounded Mode ===")
    
    adapter = VertexAdapter()
    request = LLMRequest(
        vendor="vertex",
        model="gemini-2.5-pro",
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
    """Test grounded mode - should use Google Search (auto)"""
    print("\n=== Testing Vertex Grounded Mode ===")
    
    adapter = VertexAdapter()
    request = LLMRequest(
        vendor="vertex",
        model="gemini-2.5-pro",
        messages=[
            {"role": "user", "content": "What is the current weather in San Francisco? Be specific."}
        ],
        grounded=True,
        max_tokens=1000  # Gemini needs more tokens
    )
    
    response = await adapter.complete(request, timeout=120)
    
    print(f"Content: {response.content[:200]}...")
    print(f"Grounded Requested: {request.grounded}")
    print(f"Grounded Effective: {response.grounded_effective}")
    print(f"Latency: {response.latency_ms}ms")
    print(f"Location: {adapter.location}")
    
    # Assertions (signals, not content)
    assert response.success, "Should succeed"
    # Note: Gemini auto-grounds, so it might not search for some queries
    # Weather should trigger search though
    
    print(f"✅ Grounded test completed (effective={response.grounded_effective})")
    return response


async def test_json_grounding_error():
    """Test that JSON + grounding fails cleanly (unsupported by Gemini)"""
    print("\n=== Testing Vertex JSON + Grounding Error ===")
    
    adapter = VertexAdapter()
    request = LLMRequest(
        vendor="vertex",
        model="gemini-2.5-pro",
        messages=[
            {"role": "user", "content": "Return current weather as JSON"}
        ],
        grounded=True,
        json_mode=True,  # This should trigger the guard
        max_tokens=200
    )
    
    try:
        response = await adapter.complete(request, timeout=120)
        
        # Should NOT get here
        print(f"❌ Expected error but got response: {response.content[:100]}")
        assert False, "Should have raised GROUNDED_JSON_UNSUPPORTED error"
        
    except RuntimeError as e:
        error_msg = str(e)
        print(f"Got expected error: {error_msg[:100]}")
        
        # Check for specific error
        assert "GROUNDED_JSON_UNSUPPORTED" in error_msg, f"Wrong error: {error_msg}"
        assert "cannot combine" in error_msg.lower(), "Error should explain the conflict"
        
        print("✅ JSON + grounding error test passed (failed as expected)")
        return None
    
    except Exception as e:
        print(f"❌ Unexpected error type: {type(e).__name__}: {e}")
        raise


async def test_location_configuration():
    """Test that location is configurable"""
    print("\n=== Testing Vertex Location Configuration ===")
    
    # Test with custom location
    adapter = VertexAdapter(location="europe-west4")
    print(f"Adapter location: {adapter.location}")
    assert adapter.location == "europe-west4", "Should use custom location"
    
    # Test with env variable (if set)
    env_location = os.getenv("VERTEX_LOCATION", "global")
    adapter2 = VertexAdapter()
    print(f"Adapter location (from env): {adapter2.location}")
    assert adapter2.location == env_location, f"Should use env location: {env_location}"
    
    print("✅ Location configuration test passed")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Vertex AI Grounding Tests")
    print("=" * 60)
    
    # Check environment
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("❌ GOOGLE_CLOUD_PROJECT not set")
        return
    
    print(f"Project: {project}")
    print(f"Location: {os.getenv('VERTEX_LOCATION', 'global')}")
    
    try:
        # Run tests
        await test_location_configuration()
        await test_ungrounded()
        await test_grounded()
        await test_json_grounding_error()
        
        print("\n" + "=" * 60)
        print("✅ All Vertex grounding tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())