#!/usr/bin/env python3
"""
Comprehensive tests for refactored OpenAI adapter.
Tests the lean implementation focusing on shape conversion, policy enforcement, and telemetry.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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

os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_ungrounded_happy_path():
    """Test 1: Ungrounded happy path - Model returns content normally."""
    print("\n" + "="*60)
    print("TEST 1: Ungrounded Happy Path")
    print("="*60)
    
    from app.llm.adapters.openai_adapter_refactored import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock successful response with content
    mock_response = MagicMock()
    mock_response.output = [
        MagicMock(
            type='message',
            content=[MagicMock(text='Paris is the capital of France.')]
        )
    ]
    mock_response.output_text = 'Paris is the capital of France.'
    mock_response.usage = MagicMock(
        input_tokens=10,
        output_tokens=8,
        reasoning_tokens=0,
        total_tokens=18
    )
    
    with patch.object(adapter.client.responses, 'create', new=AsyncMock(return_value=mock_response)):
        request = LLMRequest(
            vendor="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "What is the capital of France?"}],
            grounded=False,
            max_tokens=100
        )
        
        response = await adapter.complete(request, timeout=30)
        
        assert response.content == "Paris is the capital of France."
        assert response.success is True
        assert response.grounded_effective is False
        assert response.metadata["tool_call_count"] == 0
        assert response.metadata["fallback_used"] is False
        print("✅ Ungrounded happy path works correctly")
        return True


async def test_ungrounded_empty_quirk():
    """Test 2: GPT-5 empty text quirk - TextEnvelope fallback kicks in."""
    print("\n" + "="*60)
    print("TEST 2: GPT-5 Empty Text Quirk (TextEnvelope Fallback)")
    print("="*60)
    
    from app.llm.adapters.openai_adapter_refactored import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # First call returns empty
    empty_response = MagicMock()
    empty_response.output = []
    empty_response.output_text = ""
    empty_response.usage = MagicMock(
        input_tokens=10,
        output_tokens=0,
        reasoning_tokens=5,
        total_tokens=15
    )
    
    # Fallback call returns JSON envelope
    envelope_response = MagicMock()
    envelope_response.output_text = json.dumps({"content": "Fallback content from envelope"})
    envelope_response.usage = MagicMock(
        input_tokens=15,
        output_tokens=8,
        reasoning_tokens=0,
        total_tokens=23
    )
    
    call_count = 0
    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call - empty response
            assert "tools" in kwargs
            assert kwargs["tools"] == []
            return empty_response
        else:
            # Second call - TextEnvelope
            assert "text" in kwargs
            assert kwargs["text"]["format"]["type"] == "json_schema"
            assert kwargs["text"]["format"]["name"] == "TextEnvelope"
            return envelope_response
    
    with patch.object(adapter.client.responses, 'create', new=AsyncMock(side_effect=mock_create)):
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": "Test prompt"}],
            grounded=False,
            max_tokens=100
        )
        
        response = await adapter.complete(request, timeout=30)
        
        assert response.content == "Fallback content from envelope"
        assert response.success is True
        assert response.metadata["fallback_used"] is True
        assert response.metadata["text_source"] == "text_envelope"
        assert call_count == 2, f"Expected 2 API calls, got {call_count}"
        print("✅ TextEnvelope fallback works for empty responses")
        return True


async def test_grounded_required_pass():
    """Test 3: REQUIRED grounding mode - Passes when tool calls present."""
    print("\n" + "="*60)
    print("TEST 3: Grounded REQUIRED Mode - Pass Case")
    print("="*60)
    
    from app.llm.adapters.openai_adapter_refactored import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Mock response with web search tool calls
    mock_response = MagicMock()
    mock_response.output = [
        MagicMock(type='web_search_call'),
        MagicMock(
            type='message',
            content=[MagicMock(text='According to search results...')]
        )
    ]
    mock_response.output_text = 'According to search results...'
    mock_response.usage = MagicMock(
        input_tokens=20,
        output_tokens=15,
        reasoning_tokens=0,
        total_tokens=35
    )
    
    with patch.object(adapter.client.responses, 'create', new=AsyncMock(return_value=mock_response)):
        request = LLMRequest(
            vendor="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "What is the weather today?"}],
            grounded=True,
            max_tokens=200,
            meta={"grounding_mode": "REQUIRED"}
        )
        
        response = await adapter.complete(request, timeout=30)
        
        assert response.content == "According to search results..."
        assert response.success is True
        assert response.grounded_effective is True
        assert response.metadata["tool_call_count"] == 1
        assert response.metadata["grounded_evidence_present"] is True
        print("✅ REQUIRED grounding passes with tool calls")
        return True


async def test_grounded_required_fail():
    """Test 4: REQUIRED grounding mode - Fails when no tool calls."""
    print("\n" + "="*60)
    print("TEST 4: Grounded REQUIRED Mode - Fail Case")
    print("="*60)
    
    from app.llm.adapters.openai_adapter_refactored import OpenAIAdapter
    from app.llm.types import LLMRequest
    from app.llm.errors import GroundingRequiredFailedError
    
    adapter = OpenAIAdapter()
    
    # Mock response without tool calls
    mock_response = MagicMock()
    mock_response.output = [
        MagicMock(
            type='message',
            content=[MagicMock(text='I cannot search for that.')]
        )
    ]
    mock_response.output_text = 'I cannot search for that.'
    mock_response.usage = MagicMock(
        input_tokens=20,
        output_tokens=10,
        reasoning_tokens=0,
        total_tokens=30
    )
    
    with patch.object(adapter.client.responses, 'create', new=AsyncMock(return_value=mock_response)):
        request = LLMRequest(
            vendor="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            grounded=True,
            max_tokens=200,
            meta={"grounding_mode": "REQUIRED"}
        )
        
        try:
            await adapter.complete(request, timeout=30)
            print("❌ Should have raised GroundingRequiredFailedError")
            return False
        except GroundingRequiredFailedError as e:
            assert "no tool calls made" in str(e)
            print("✅ REQUIRED grounding correctly fails without tool calls")
            return True


async def test_rate_limit_sdk_handling():
    """Test 5: SDK handles rate limits transparently."""
    print("\n" + "="*60)
    print("TEST 5: SDK Rate Limit Handling")
    print("="*60)
    
    from app.llm.adapters.openai_adapter_refactored import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    # This test verifies our adapter doesn't implement custom retry logic
    # The SDK should handle retries based on max_retries parameter
    
    # Check that the adapter uses SDK configuration
    adapter = OpenAIAdapter()
    
    # Verify max_retries is set (SDK handles retries)
    assert adapter.client.max_retries == int(os.environ.get("OPENAI_MAX_RETRIES", "5"))
    
    # Verify timeout is set (SDK handles timeouts)  
    assert adapter.client.timeout == int(os.environ.get("OPENAI_TIMEOUT_SECONDS", "60"))
    
    # Mock a successful response (SDK would handle any retries internally)
    mock_response = MagicMock()
    mock_response.output = [
        MagicMock(
            type='message',
            content=[MagicMock(text='SDK handles retries')]
        )
    ]
    mock_response.output_text = 'SDK handles retries'
    mock_response.usage = MagicMock(
        input_tokens=10,
        output_tokens=5,
        reasoning_tokens=0,
        total_tokens=15
    )
    
    with patch.object(adapter.client.responses, 'create', new=AsyncMock(return_value=mock_response)):
        request = LLMRequest(
            vendor="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}],
            grounded=False,
            max_tokens=50
        )
        
        response = await adapter.complete(request, timeout=30)
        
        assert response.content == "SDK handles retries"
        assert response.success is True
        
        # Verify adapter doesn't have custom retry logic
        assert not hasattr(adapter, '_retry_with_backoff')
        assert not hasattr(adapter, 'rate_limiter')
        assert not hasattr(adapter, 'circuit_breaker')
        
        print(f"✅ SDK configuration verified (retries={adapter.client.max_retries}, timeout={adapter.client.timeout})")
        return True


async def test_tool_negotiation():
    """Test 6: Tool type negotiation for grounded requests."""
    print("\n" + "="*60)
    print("TEST 6: Tool Type Negotiation")
    print("="*60)
    
    from app.llm.adapters.openai_adapter_refactored import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    call_count = 0
    mock_response = MagicMock()
    mock_response.output = [
        MagicMock(type='web_search_preview_call'),
        MagicMock(
            type='message',
            content=[MagicMock(text='Search results...')]
        )
    ]
    mock_response.output_text = 'Search results...'
    mock_response.usage = MagicMock(
        input_tokens=20,
        output_tokens=10,
        reasoning_tokens=0,
        total_tokens=30
    )
    
    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call with web_search fails
            assert kwargs["tools"] == [{"type": "web_search"}]
            raise Exception("Tool type web_search is unsupported")
        else:
            # Second call with web_search_preview succeeds
            assert kwargs["tools"] == [{"type": "web_search_preview"}]
            return mock_response
    
    with patch.object(adapter.client.responses, 'create', new=AsyncMock(side_effect=mock_create)):
        request = LLMRequest(
            vendor="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Current news?"}],
            grounded=True,
            max_tokens=200
        )
        
        response = await adapter.complete(request, timeout=30)
        
        assert response.content == "Search results..."
        assert response.metadata["web_tool_type"] == "web_search_preview"
        assert call_count == 2
        print("✅ Tool negotiation works correctly")
        return True


async def test_banned_patterns():
    """Test 7: Check for banned patterns in refactored code."""
    print("\n" + "="*60)
    print("TEST 7: Banned Patterns Check")
    print("="*60)
    
    # Read the refactored adapter
    refactored_path = Path("/home/leedr/ai-ranker-v2/backend/app/llm/adapters/openai_adapter_refactored.py")
    with open(refactored_path, 'r') as f:
        code = f.read()
    
    banned_patterns = [
        "httpx",
        "aiohttp",
        "CircuitBreaker",
        "RateLimiter",
        "BackoffManager",
        "HealthCheck",
        "health_check",
        "_health_check",
        "stream=True",
        "async for chunk",
        "iter_lines",
        "SSE",
        "chat.completions",
        "ChatCompletion",
        "_call_chat_api",
        "_call_with_streaming"
    ]
    
    found_banned = []
    for pattern in banned_patterns:
        if pattern.lower() in code.lower():
            found_banned.append(pattern)
    
    if found_banned:
        print(f"❌ Found banned patterns: {found_banned}")
        return False
    else:
        print("✅ No banned patterns found in refactored adapter")
        return True


async def run_all_tests():
    """Run all comprehensive tests."""
    print("\n" + "="*60)
    print("RUNNING COMPREHENSIVE ADAPTER TESTS")
    print("="*60)
    
    tests = [
        ("Ungrounded Happy Path", test_ungrounded_happy_path),
        ("GPT-5 Empty Quirk", test_ungrounded_empty_quirk),
        ("Grounded REQUIRED Pass", test_grounded_required_pass),
        ("Grounded REQUIRED Fail", test_grounded_required_fail),
        ("SDK Rate Limit Handling", test_rate_limit_sdk_handling),
        ("Tool Negotiation", test_tool_negotiation),
        ("Banned Patterns", test_banned_patterns)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} failed with error: {str(e)}")
            results.append((name, False))
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
        if not success:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️ SOME TESTS FAILED")
    print("="*60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)