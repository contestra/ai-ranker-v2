#!/usr/bin/env python3
"""Test OpenAI REQUIRED enforcement with citations."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment for tests
os.environ["OPENAI_PROVOKER_ENABLED"] = "true"
os.environ["OPENAI_GROUNDED_TWO_STEP"] = "false"
os.environ["OPENAI_GROUNDED_MAX_EVIDENCE"] = "5"


async def test_required_passes_with_tools_and_citations():
    """Test: REQUIRED passes when both tool calls and citations present."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock response with searches AND citations
    response = MagicMock()
    
    # Create search results
    result1 = MagicMock()
    result1.url = "https://example.com/article"
    result1.title = "Test Article"
    result1.annotation = None
    
    search_item = MagicMock()
    search_item.type = "web_search_call"
    search_item.search_results = [result1]
    
    response.output = [search_item]
    response.output_text = "Here is the answer based on search"
    response.usage = MagicMock(
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=25,
        total_tokens=175
    )
    
    async def mock_negotiate(payload, timeout):
        return response, "web_search"
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": "Search for news"}],
            grounded=True,
            max_tokens=1000,
            meta={"grounding_mode": "REQUIRED"}
        )
        
        result = await adapter.complete(request)
        
        # Should pass with content and citations
        assert result.success
        assert result.content == "Here is the answer based on search"
        assert len(result.citations) == 1
        assert result.metadata["tool_call_count"] == 1
        assert "fail_closed_reason" not in result.metadata
        
        print("✅ Test 1 passed: REQUIRED passes with tools and citations")


async def test_required_fails_no_citations():
    """Test: REQUIRED fails when tools present but no citations extracted."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    from app.llm.errors import GroundingRequiredFailedError
    
    adapter = OpenAIAdapter()
    
    # Mock response with search call but NO results
    response = MagicMock()
    
    search_item = MagicMock()
    search_item.type = "web_search_call"
    search_item.search_results = []  # Empty results!
    
    response.output = [search_item]
    response.output_text = "I searched but found nothing"
    response.usage = MagicMock(
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=25,
        total_tokens=175
    )
    
    async def mock_negotiate(payload, timeout):
        return response, "web_search"
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": "Search for news"}],
            grounded=True,
            max_tokens=1000,
            meta={"grounding_mode": "REQUIRED"}
        )
        
        try:
            await adapter.complete(request)
            assert False, "Should have raised GroundingRequiredFailedError"
        except GroundingRequiredFailedError as e:
            assert "no citations extracted" in str(e)
            print("✅ Test 2 passed: REQUIRED fails when no citations despite tool calls")


async def test_required_fails_no_tools():
    """Test: REQUIRED fails when no tool calls made."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    from app.llm.errors import GroundingRequiredFailedError
    
    adapter = OpenAIAdapter()
    
    # Mock response with NO tool calls
    response = MagicMock()
    response.output = [MagicMock(type="reasoning")]  # No searches
    response.output_text = "Here's my answer without searching"
    response.usage = MagicMock(
        input_tokens=100,
        output_tokens=50,
        reasoning_tokens=25,
        total_tokens=175
    )
    
    async def mock_negotiate(payload, timeout):
        return response, "web_search"
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": "Tell me something"}],
            grounded=True,
            max_tokens=1000,
            meta={"grounding_mode": "REQUIRED"}
        )
        
        try:
            await adapter.complete(request)
            assert False, "Should have raised GroundingRequiredFailedError"
        except GroundingRequiredFailedError as e:
            assert "no tool calls made" in str(e)
            print("✅ Test 3 passed: REQUIRED fails when no tool calls")


async def test_two_step_required_with_citations():
    """Test: Two-step synthesis preserves citations for REQUIRED mode."""
    # Enable two-step
    os.environ["OPENAI_GROUNDED_TWO_STEP"] = "true"
    
    # Reimport to pick up env change
    import importlib
    import app.llm.adapters.openai_adapter
    importlib.reload(app.llm.adapters.openai_adapter)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock Step-A with citations but no text
    step_a_response = MagicMock()
    
    result1 = MagicMock()
    result1.url = "https://trusted.org/article"
    result1.title = "Trusted Source"
    result1.annotation = None
    
    search_item = MagicMock()
    search_item.type = "web_search_call"
    search_item.search_results = [result1]
    
    step_a_response.output = [search_item]
    step_a_response.output_text = ""  # Empty initially
    
    # Mock Step-B synthesis
    step_b_response = MagicMock()
    step_b_response.output = []
    step_b_response.output_text = "Synthesized answer from evidence"
    step_b_response.usage = MagicMock(
        input_tokens=200,
        output_tokens=100,
        reasoning_tokens=0,
        total_tokens=300
    )
    
    negotiate_calls = 0
    async def mock_negotiate(payload, timeout):
        nonlocal negotiate_calls
        negotiate_calls += 1
        return step_a_response, "web_search"
    
    async def mock_create(**kwargs):
        return step_b_response
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        with patch.object(adapter.client.responses, 'create', mock_create):
            request = LLMRequest(
                vendor="openai",
                model="gpt-5-2025-08-07",
                messages=[{"role": "user", "content": "Search and tell me"}],
                grounded=True,
                max_tokens=1000,
                meta={"grounding_mode": "REQUIRED"}
            )
            
            result = await adapter.complete(request)
            
            # Should pass - tool calls from Step-A, citations preserved
            assert result.success
            assert result.content == "Synthesized answer from evidence"
            assert len(result.citations) == 1
            assert result.citations[0]["source_type"] == "evidence_list"
            assert result.metadata["synthesis_step_used"] == True
            assert result.metadata["tool_call_count"] == 1
            
            print("✅ Test 4 passed: Two-step preserves citations for REQUIRED")


async def test_provoker_disabled():
    """Test: Provoker is skipped when disabled by flag."""
    os.environ["OPENAI_PROVOKER_ENABLED"] = "false"
    os.environ["OPENAI_GROUNDED_TWO_STEP"] = "false"
    
    # Reimport
    import importlib
    import app.llm.adapters.openai_adapter
    importlib.reload(app.llm.adapters.openai_adapter)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock empty response
    empty_response = MagicMock()
    
    result1 = MagicMock()
    result1.url = "https://example.com/test"
    result1.title = "Test"
    result1.annotation = None
    
    search_item = MagicMock()
    search_item.type = "web_search_call"
    search_item.search_results = [result1]
    
    empty_response.output = [search_item]
    empty_response.output_text = ""  # Empty
    empty_response.usage = MagicMock(
        input_tokens=100,
        output_tokens=0,
        reasoning_tokens=50,
        total_tokens=150
    )
    
    call_count = 0
    async def mock_negotiate(payload, timeout):
        nonlocal call_count
        call_count += 1
        # Should NOT have provoker text since disabled
        for msg in payload["input"]:
            assert "As of today" not in str(msg), "Provoker should not be added when disabled"
        return empty_response, "web_search"
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": "Search"}],
            grounded=True,
            max_tokens=1000,
            meta={"grounding_mode": "AUTO"}  # Not REQUIRED
        )
        
        result = await adapter.complete(request)
        
        # Should complete but with empty content
        assert result.success
        assert result.content == ""
        assert call_count == 1  # Only one call, no provoker retry
        assert result.metadata["provoker_retry_used"] == False
        assert result.metadata["synthesis_step_used"] == False
        
        print("✅ Test 5 passed: Provoker disabled by flag")


async def test_evidence_cap():
    """Test: Evidence list respects OPENAI_GROUNDED_MAX_EVIDENCE cap."""
    os.environ["OPENAI_PROVOKER_ENABLED"] = "true"
    os.environ["OPENAI_GROUNDED_TWO_STEP"] = "true"
    os.environ["OPENAI_GROUNDED_MAX_EVIDENCE"] = "3"  # Cap at 3
    
    # Reimport
    import importlib
    import app.llm.adapters.openai_adapter
    importlib.reload(app.llm.adapters.openai_adapter)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock response with many search results
    step_a_response = MagicMock()
    
    # Create 10 results
    results = []
    for i in range(10):
        r = MagicMock()
        r.url = f"https://example.com/article{i}"
        r.title = f"Article {i}"
        r.annotation = None
        results.append(r)
    
    search_item = MagicMock()
    search_item.type = "web_search_call"
    search_item.search_results = results
    
    step_a_response.output = [search_item]
    step_a_response.output_text = ""
    
    # Mock synthesis
    step_b_response = MagicMock()
    step_b_response.output = []
    step_b_response.output_text = "Synthesized"
    step_b_response.usage = MagicMock(
        input_tokens=200,
        output_tokens=50,
        reasoning_tokens=0,
        total_tokens=250
    )
    
    async def mock_negotiate(payload, timeout):
        return step_a_response, "web_search"
    
    evidence_count = 0
    async def mock_create(**kwargs):
        nonlocal evidence_count
        # Count evidence items in the input
        input_str = str(kwargs["input"])
        for i in range(10):
            if f"Article {i}" in input_str:
                evidence_count += 1
        return step_b_response
    
    with patch.object(adapter, '_call_with_tool_negotiation', mock_negotiate):
        with patch.object(adapter.client.responses, 'create', mock_create):
            request = LLMRequest(
                vendor="openai",
                model="gpt-5-2025-08-07",
                messages=[{"role": "user", "content": "Search"}],
                grounded=True,
                max_tokens=1000
            )
            
            result = await adapter.complete(request)
            
            # Should only use 3 for evidence (capped)
            assert result.success
            assert evidence_count == 3  # Only 3 in evidence despite 10 results
            assert result.metadata["synthesis_evidence_count"] == 3
            # But all 10 should be extracted initially
            assert len(result.citations) == 3  # Only evidence ones preserved in two-step
            
            print("✅ Test 6 passed: Evidence capped at OPENAI_GROUNDED_MAX_EVIDENCE")


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("OPENAI REQUIRED ENFORCEMENT TESTS")
    print("="*80 + "\n")
    
    await test_required_passes_with_tools_and_citations()
    await test_required_fails_no_citations()
    await test_required_fails_no_tools()
    await test_two_step_required_with_citations()
    await test_provoker_disabled()
    await test_evidence_cap()
    
    print("\n" + "="*80)
    print("All REQUIRED enforcement tests passed!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())