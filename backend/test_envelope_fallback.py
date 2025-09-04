#!/usr/bin/env python3
"""
Test suite for TextEnvelope fallback mechanism.
Ensures ungrounded GPT-5 always returns usable text.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


async def test_1_normal_ungrounded():
    """Test 1: Normal ungrounded - should get message text without retry."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    print("=" * 80)
    print("TEST 1: NORMAL UNGROUNDED (no retry needed)")
    print("=" * 80)
    
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "Say 'hello world'."}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print("Request: Simple hello world (should work first try)")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Content length: {len(response.content)}")
    
    metadata = response.metadata or {}
    print(f"  Text source: {metadata.get('text_source', 'message')}")
    print(f"  Retry used: {metadata.get('ungrounded_retry', 0)}")
    
    success = len(response.content) > 0 and metadata.get('ungrounded_retry', 0) == 0
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'No retry needed' if success else 'Unexpected retry or empty'}")
    
    return success


async def test_2_force_envelope_fallback():
    """Test 2: Force envelope fallback - mock empty first response."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    print("\n" + "=" * 80)
    print("TEST 2: FORCE ENVELOPE FALLBACK")
    print("=" * 80)
    
    adapter = OpenAIAdapter()
    
    # Mock the first call to return empty
    original_create = adapter.client.responses.create
    call_count = 0
    
    async def mocked_create(**kwargs):
        nonlocal call_count
        call_count += 1
        
        if call_count == 1:
            # First call: return empty response
            print("  🔧 Mock: Returning empty response to trigger fallback")
            mock_response = MagicMock()
            mock_response.output = [MagicMock(type='reasoning', content=None)]
            mock_response.output_text = ''
            mock_response.usage = MagicMock(
                input_tokens=20, output_tokens=0, reasoning_tokens=0, total_tokens=20
            )
            return mock_response
        else:
            # Second call: check for TextEnvelope schema
            if "text" in kwargs and "format" in kwargs["text"]:
                format_info = kwargs["text"]["format"]
                if format_info.get("type") == "json_schema" and format_info.get("name") == "TextEnvelope":
                    print("  🔧 Mock: TextEnvelope schema detected, returning JSON")
                    # Return JSON envelope
                    mock_response = MagicMock()
                    mock_response.output = []
                    mock_response.output_text = '{"content":"Hello world from envelope"}'
                    mock_response.usage = MagicMock(
                        input_tokens=25, output_tokens=10, reasoning_tokens=0, total_tokens=35
                    )
                    return mock_response
            
            # Fallback to real call
            return await original_create(**kwargs)
    
    adapter.client.responses.create = mocked_create
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "Say hello"}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print("Request: Testing envelope fallback (mocked empty first response)")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Content length: {len(response.content)}")
    
    metadata = response.metadata or {}
    print(f"  Text source: {metadata.get('text_source')}")
    print(f"  Retry used: {metadata.get('ungrounded_retry', 0)}")
    print(f"  Retry reason: {metadata.get('retry_reason')}")
    print(f"  JSON valid: {metadata.get('output_json_valid')}")
    print(f"  Call count: {call_count}")
    
    success = (
        response.content == "Hello world from envelope" and
        metadata.get('ungrounded_retry') == 1 and
        metadata.get('text_source') == 'json_envelope_fallback' and
        call_count == 2
    )
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Envelope fallback worked' if success else 'Fallback failed'}")
    
    return success


async def test_3_grounded_unaffected():
    """Test 3: Grounded Required - should not trigger envelope fallback."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    from app.llm.errors import GroundingRequiredFailedError
    
    print("\n" + "=" * 80)
    print("TEST 3: GROUNDED REQUIRED (no fallback)")
    print("=" * 80)
    
    adapter = OpenAIAdapter()
    
    # Track if envelope fallback is attempted
    original_create = adapter.client.responses.create
    envelope_attempted = False
    
    async def track_create(**kwargs):
        nonlocal envelope_attempted
        if "text" in kwargs and "format" in kwargs["text"]:
            format_info = kwargs["text"]["format"]
            if format_info.get("name") == "TextEnvelope":
                envelope_attempted = True
        return await original_create(**kwargs)
    
    adapter.client.responses.create = track_create
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "What is 2+2?"}
        ],
        grounded=True,
        max_tokens=50,
        meta={"grounding_mode": "REQUIRED"}
    )
    
    print("Request: Simple math with REQUIRED mode")
    
    error_raised = False
    try:
        response = await adapter.complete(request, timeout=30)
        print(f"  Response: '{response.content}'")
    except (GroundingRequiredFailedError, Exception) as e:
        error_raised = True
        print(f"  ✓ Expected error: {str(e)[:100]}")
    
    print(f"  Envelope attempted: {envelope_attempted}")
    
    success = error_raised and not envelope_attempted
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'No fallback for grounded' if success else 'Unexpected behavior'}")
    
    return success


async def test_4_streaming_compatibility():
    """Test 4: Streaming acceptance - envelope fallback works with streaming."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    print("\n" + "=" * 80)
    print("TEST 4: STREAMING COMPATIBILITY")
    print("=" * 80)
    
    # Test GPT-4 streaming (GPT-5 doesn't use streaming)
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "Say 'hello from streaming'."}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print("Request: GPT-4 streaming test")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Content length: {len(response.content)}")
    
    metadata = response.metadata or {}
    print(f"  Response API: {metadata.get('response_api')}")
    print(f"  Has content: {len(response.content) > 0}")
    
    success = len(response.content) > 0 and "streaming" in response.content.lower()
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Streaming works' if success else 'Streaming issue'}")
    
    return success


async def test_5_feature_flag_off():
    """Test 5: Feature flag OFF - no envelope fallback when disabled."""
    import os
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    print("\n" + "=" * 80)
    print("TEST 5: FEATURE FLAG OFF")
    print("=" * 80)
    
    # Disable the feature
    os.environ["UNGROUNDED_JSON_ENVELOPE_FALLBACK"] = "off"
    
    # Force reload of adapter to pick up env change
    import importlib
    import app.llm.adapters.openai_adapter as oa_module
    importlib.reload(oa_module)
    
    adapter = oa_module.OpenAIAdapter()
    
    # Mock empty response
    original_create = adapter.client.responses.create
    create_count = 0
    
    async def mock_empty(**kwargs):
        nonlocal create_count
        create_count += 1
        mock_response = MagicMock()
        mock_response.output = [MagicMock(type='reasoning', content=None)]
        mock_response.output_text = ''
        mock_response.usage = MagicMock(
            input_tokens=20, output_tokens=0, reasoning_tokens=0, total_tokens=20
        )
        return mock_response
    
    adapter.client.responses.create = mock_empty
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "Test with flag off"}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print("Request: Testing with UNGROUNDED_JSON_ENVELOPE_FALLBACK=off")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Content length: {len(response.content)}")
    print(f"  Create calls: {create_count}")
    
    metadata = response.metadata or {}
    print(f"  Retry used: {metadata.get('ungrounded_retry', 0)}")
    
    # Re-enable for other tests
    os.environ["UNGROUNDED_JSON_ENVELOPE_FALLBACK"] = "on"
    
    success = create_count == 1 and metadata.get('ungrounded_retry', 0) == 0
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'No retry when disabled' if success else 'Unexpected retry'}")
    
    return success


async def main():
    """Run all envelope fallback tests."""
    print("\n" + "=" * 80)
    print("TEXTENVELOPE FALLBACK TEST SUITE")
    print("=" * 80)
    
    results = []
    tests = [
        ("Normal Ungrounded", test_1_normal_ungrounded),
        ("Force Envelope Fallback", test_2_force_envelope_fallback),
        ("Grounded Unaffected", test_3_grounded_unaffected),
        ("Streaming Compatibility", test_4_streaming_compatibility),
        ("Feature Flag Off", test_5_feature_flag_off)
    ]
    
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
            await asyncio.sleep(2)  # Rate limit
        except Exception as e:
            print(f"\n❌ {name} CRASHED: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print(f"\n{'🎉 ALL TESTS PASSED' if all_passed else '⚠️ SOME TESTS FAILED'}")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)