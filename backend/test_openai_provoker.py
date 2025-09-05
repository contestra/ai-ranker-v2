#!/usr/bin/env python3
"""Test OpenAI provoker retry and two-step fallback."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment for tests
os.environ["OPENAI_GROUNDED_TWO_STEP"] = "false"  # Default off


async def test_provoker_fixes_empty():
    """Test: Grounded searches but empty → provoker fixes it."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock responses
    empty_response = MagicMock()
    empty_response.output = [
        MagicMock(type="reasoning"),
        MagicMock(type="web_search_call"),
        MagicMock(type="web_search_call"),
        MagicMock(type="web_search_call"),
    ]
    empty_response.output_text = ""  # Empty
    empty_response.usage = MagicMock(
        input_tokens=100,
        output_tokens=0,
        reasoning_tokens=50,
        total_tokens=150
    )
    
    fixed_response = MagicMock()
    fixed_response.output = [
        MagicMock(type="reasoning"),
        MagicMock(type="web_search_call"),
    ]
    fixed_response.output_text = "Based on my search, here is the answer with sources..."
    fixed_response.usage = MagicMock(
        input_tokens=200,
        output_tokens=100,
        reasoning_tokens=50,
        total_tokens=350
    )
    
    # Mock the API calls
    call_count = 0
    async def mock_negotiate(payload, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call returns empty
            return empty_response, "web_search"
        else:
            # Provoker call returns content
            # Verify provoker was added
            assert any("As of today" in str(msg) for msg in payload["input"]), "Provoker not added"
            return fixed_response, "web_search"
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": "What's the news?"}],
            grounded=True,
            max_tokens=1000
        )
        
        response = await adapter.complete(request)
        
        # Verify results
        assert response.success
        assert response.content == "Based on my search, here is the answer with sources..."
        assert response.metadata["provoker_retry_used"] == True
        assert response.metadata.get("synthesis_step_used") != True
        assert call_count == 2, f"Expected 2 calls (original + provoker), got {call_count}"
        
        print("✅ Test 1 passed: Provoker retry fixes empty grounded response")


async def test_two_step_synthesis():
    """Test: Grounded searches, empty after provoker → 2-step succeeds (flag ON)."""
    # Enable two-step
    os.environ["OPENAI_GROUNDED_TWO_STEP"] = "true"
    
    # Reimport to pick up the env change
    import importlib
    import app.llm.adapters.openai_adapter
    importlib.reload(app.llm.adapters.openai_adapter)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock responses
    empty_response = MagicMock()
    empty_response.output = [
        MagicMock(type="reasoning"),
        MagicMock(type="web_search_call"),
        MagicMock(type="web_search_call"),
    ]
    empty_response.output_text = ""  # Still empty after provoker
    empty_response.usage = MagicMock(
        input_tokens=100,
        output_tokens=0,
        reasoning_tokens=50,
        total_tokens=150
    )
    
    synthesis_response = MagicMock()
    synthesis_response.output = []
    synthesis_response.output_text = "Synthesized answer based on the evidence provided..."
    synthesis_response.usage = MagicMock(
        input_tokens=300,
        output_tokens=150,
        reasoning_tokens=0,
        total_tokens=450
    )
    
    # Track calls
    negotiate_calls = 0
    async def mock_negotiate(payload, timeout):
        nonlocal negotiate_calls
        negotiate_calls += 1
        return empty_response, "web_search"
    
    create_calls = 0
    original_create = None
    async def mock_create(**kwargs):
        nonlocal create_calls
        create_calls += 1
        # Synthesis call should have no tools
        assert kwargs["tools"] == [], "Synthesis should have no tools"
        assert any("Synthesize a final answer" in str(msg) for msg in kwargs["input"]), "Synthesis instruction missing"
        return synthesis_response
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        with patch.object(adapter.client.responses, 'create', mock_create):
            # Mock citations extraction
            with patch.object(adapter, '_extract_citations', return_value=([
                {"title": "Source 1", "url": "https://example.com/1"},
                {"title": "Source 2", "url": "https://example.com/2"}
            ], 0, 2)):
                request = LLMRequest(
                    vendor="openai",
                    model="gpt-5-2025-08-07",
                    messages=[{"role": "user", "content": "What's the news?"}],
                    grounded=True,
                    max_tokens=1000
                )
                
                response = await adapter.complete(request)
                
                # Verify results
                assert response.success
                assert response.content == "Synthesized answer based on the evidence provided..."
                assert response.metadata["provoker_retry_used"] == True
                assert response.metadata["synthesis_step_used"] == True
                assert response.metadata["synthesis_tool_count"] == 2  # From empty_response
                assert response.metadata["synthesis_evidence_count"] > 0
                assert negotiate_calls == 2, f"Expected 2 negotiate calls, got {negotiate_calls}"
                assert create_calls == 1, f"Expected 1 synthesis create call, got {create_calls}"
                
                print("✅ Test 2 passed: Two-step synthesis works when flag is ON")


async def test_two_step_disabled():
    """Test: Two-step is NOT attempted when flag is OFF."""
    # Disable two-step
    os.environ["OPENAI_GROUNDED_TWO_STEP"] = "false"
    
    # Reimport to pick up the env change
    import importlib
    import app.llm.adapters.openai_adapter
    importlib.reload(app.llm.adapters.openai_adapter)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock empty responses
    empty_response = MagicMock()
    empty_response.output = [
        MagicMock(type="reasoning"),
        MagicMock(type="web_search_call"),
    ]
    empty_response.output_text = ""
    empty_response.usage = MagicMock(
        input_tokens=100,
        output_tokens=0,
        reasoning_tokens=50,
        total_tokens=150
    )
    
    negotiate_calls = 0
    async def mock_negotiate(payload, timeout):
        nonlocal negotiate_calls
        negotiate_calls += 1
        return empty_response, "web_search"
    
    create_calls = 0
    async def mock_create(**kwargs):
        nonlocal create_calls
        create_calls += 1
        raise AssertionError("Synthesis should not be attempted when flag is OFF")
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        with patch.object(adapter.client.responses, 'create', mock_create):
            request = LLMRequest(
                vendor="openai",
                model="gpt-5-2025-08-07",
                messages=[{"role": "user", "content": "What's the news?"}],
                grounded=True,
                max_tokens=1000
            )
            
            response = await adapter.complete(request)
            
            # Verify results - should have empty content
            assert response.success
            assert response.content == ""
            assert response.metadata["provoker_retry_used"] == True
            assert response.metadata.get("synthesis_step_used") != True
            assert negotiate_calls == 2, f"Expected 2 negotiate calls (original + provoker), got {negotiate_calls}"
            assert create_calls == 0, f"Expected 0 synthesis calls, got {create_calls}"
            
            print("✅ Test 3 passed: Two-step synthesis NOT attempted when flag is OFF")


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("OPENAI PROVOKER & TWO-STEP TESTS")
    print("="*80 + "\n")
    
    await test_provoker_fixes_empty()
    await test_two_step_synthesis()
    await test_two_step_disabled()
    
    print("\n" + "="*80)
    print("All tests passed!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())