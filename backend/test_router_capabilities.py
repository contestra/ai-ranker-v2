#!/usr/bin/env python3
"""
Test router capabilities for Gemini-2.5-Pro thinking defaults.
Tests that router properly applies defaults and honors explicit values.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set required environment variables
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["LLM_TIMEOUT_GR"] = "120"
os.environ["GEMINI_PRO_THINKING_BUDGET"] = "256"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_UNGROUNDED"] = "768"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_GROUNDED"] = "1536"


async def test_defaults_applied_ungrounded():
    """Test that router applies thinking defaults for Gemini-2.5-Pro when unspecified."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest, LLMResponse
    
    adapter = UnifiedLLMAdapter()
    
    # Mock the vertex adapter
    mock_response = LLMResponse(
        content="Test response",
        success=True,
        vendor="vertex",
        model="gemini-2.5-pro",
        metadata={}
    )
    
    with patch.object(adapter, 'vertex_adapter') as mock_vertex:
        mock_vertex.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="vertex",
            model="gemini-2.5-pro",
            messages=[{"role": "user", "content": "Hello"}],
            grounded=False
            # Note: no max_tokens or thinking_budget specified
        )
        
        await adapter.complete(request)
        
        # Verify the request was modified with defaults
        assert request.max_tokens == 768, f"Expected max_tokens=768, got {request.max_tokens}"
        assert request.metadata.get("thinking_budget_tokens") == 256, \
            f"Expected thinking_budget_tokens=256, got {request.metadata.get('thinking_budget_tokens')}"
        
        print("✅ Test 1 passed: Defaults applied for ungrounded Gemini-2.5-Pro")


async def test_explicit_values_win():
    """Test that explicit values override router defaults."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest, LLMResponse
    
    adapter = UnifiedLLMAdapter()
    
    mock_response = LLMResponse(
        content="Test response",
        success=True,
        vendor="vertex",
        model="gemini-2.5-pro",
        metadata={}
    )
    
    with patch.object(adapter, 'vertex_adapter') as mock_vertex:
        mock_vertex.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="vertex",
            model="gemini-2.5-pro",
            messages=[{"role": "user", "content": "Hello"}],
            grounded=False,
            max_tokens=512,  # Explicit value
            meta={"thinking_budget": 128}  # Explicit value
        )
        
        await adapter.complete(request)
        
        # Verify explicit values are preserved
        assert request.max_tokens == 512, f"Expected max_tokens=512, got {request.max_tokens}"
        assert request.metadata.get("thinking_budget_tokens") == 128, \
            f"Expected thinking_budget_tokens=128, got {request.metadata.get('thinking_budget_tokens')}"
        
        print("✅ Test 2 passed: Explicit values override defaults")


async def test_non_pro_model_no_defaults():
    """Test that non-Pro models don't get thinking defaults."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest, LLMResponse
    
    adapter = UnifiedLLMAdapter()
    
    mock_response = LLMResponse(
        content="Test response",
        success=True,
        vendor="vertex",
        model="gemini-2.0-flash",
        metadata={}
    )
    
    with patch.object(adapter, 'vertex_adapter') as mock_vertex:
        mock_vertex.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="vertex",
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "Hello"}],
            grounded=False
            # Note: no max_tokens or thinking_budget specified
        )
        
        await adapter.complete(request)
        
        # Verify no defaults applied for non-Pro model
        assert request.max_tokens is None or request.max_tokens == 1024, \
            f"Expected no special max_tokens for flash, got {request.max_tokens}"
        assert request.metadata.get("thinking_budget_tokens") is None, \
            f"Expected no thinking_budget_tokens for flash, got {request.metadata.get('thinking_budget_tokens')}"
        
        print("✅ Test 3 passed: Non-Pro model gets no thinking defaults")


async def test_grounded_defaults():
    """Test that grounded requests get higher max_tokens default."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest, LLMResponse
    
    adapter = UnifiedLLMAdapter()
    
    mock_response = LLMResponse(
        content="Test response",
        success=True,
        vendor="vertex",
        model="gemini-2.5-pro",
        metadata={}
    )
    
    with patch.object(adapter, 'vertex_adapter') as mock_vertex:
        mock_vertex.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="vertex",
            model="gemini-2.5-pro",
            messages=[{"role": "user", "content": "Search for health news"}],
            grounded=True
            # Note: no max_tokens specified
        )
        
        await adapter.complete(request)
        
        # Verify grounded default applied
        assert request.max_tokens == 1536, f"Expected max_tokens=1536 for grounded, got {request.max_tokens}"
        assert request.metadata.get("thinking_budget_tokens") == 256, \
            f"Expected thinking_budget_tokens=256, got {request.metadata.get('thinking_budget_tokens')}"
        
        print("✅ Test 4 passed: Grounded requests get higher max_tokens default")


async def test_capability_gating():
    """Test that thinking budget is only set when capability is supported."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest, LLMResponse
    
    adapter = UnifiedLLMAdapter()
    
    # Test with OpenAI (doesn't support thinking_budget)
    mock_response = LLMResponse(
        content="Test response",
        success=True,
        vendor="openai",
        model="gpt-4o",
        metadata={}
    )
    
    with patch.object(adapter, 'openai_adapter') as mock_openai:
        mock_openai.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            grounded=False
        )
        
        await adapter.complete(request)
        
        # Verify no thinking_budget for OpenAI
        assert request.metadata.get("thinking_budget_tokens") is None, \
            f"OpenAI shouldn't get thinking_budget_tokens, got {request.metadata.get('thinking_budget_tokens')}"
        
        print("✅ Test 5 passed: Capability gating prevents thinking_budget for unsupported models")


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("ROUTER CAPABILITY TESTS")
    print("="*80 + "\n")
    
    tests = [
        test_defaults_applied_ungrounded,
        test_explicit_values_win,
        test_non_pro_model_no_defaults,
        test_grounded_defaults,
        test_capability_gating
    ]
    
    for test in tests:
        try:
            await test()
        except AssertionError as e:
            print(f"❌ Test failed: {test.__name__}")
            print(f"   Error: {e}")
        except Exception as e:
            print(f"❌ Test error in {test.__name__}: {e}")
    
    print("\n" + "="*80)
    print("All router capability tests completed!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())