#!/usr/bin/env python3
"""
GPT-5 Acceptance Tests
Tests that GPT-5 ungrounded now works with proper payload shaping.
"""
import asyncio
import json
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


async def test_1_ungrounded_hello_world():
    """Test 1: Ungrounded Hello World - expect non-empty message or valid fallback."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    print("=" * 80)
    print("TEST 1: UNGROUNDED HELLO WORLD")
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
    
    print("Request: Simple hello world (ungrounded)")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Content length: {len(response.content)}")
    
    metadata = response.metadata or {}
    print(f"  Text source: {metadata.get('text_source', 'message')}")
    print(f"  Retry used: {metadata.get('ungrounded_retry', 0)}")
    print(f"  Response API: {metadata.get('response_api')}")
    
    success = len(response.content) > 0
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Got text output' if success else 'Empty response'}")
    
    return success


async def test_2_ungrounded_strict_json():
    """Test 2: Ungrounded strict JSON - expect valid JSON in output_text."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    print("\n" + "=" * 80)
    print("TEST 2: UNGROUNDED STRICT JSON")
    print("=" * 80)
    
    adapter = OpenAIAdapter()
    
    # Minimal JSON schema
    json_schema = {
        "name": "SimpleOutput",
        "schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"}
            },
            "required": ["message"],
            "additionalProperties": False
        }
    }
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "Generate JSON with message='hello'"}
        ],
        grounded=False,
        max_tokens=100,
        meta={"json_schema": json_schema}
    )
    
    print("Request: JSON generation with strict schema (ungrounded)")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Content length: {len(response.content)}")
    
    # Try to parse JSON
    valid_json = False
    parsed = None
    try:
        if response.content:
            parsed = json.loads(response.content)
            valid_json = "message" in parsed
    except:
        pass
    
    metadata = response.metadata or {}
    print(f"  Valid JSON: {valid_json}")
    if parsed:
        print(f"  Parsed: {parsed}")
    print(f"  Text source: {metadata.get('text_source', 'message')}")
    print(f"  Retry used: {metadata.get('ungrounded_retry', 0)}")
    
    success = valid_json
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Valid JSON output' if success else 'Invalid/no JSON'}")
    
    return success


async def test_3_grounded_required():
    """Test 3: Grounded Required - must still fail-closed if no tool call is made."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    from app.llm.errors import GroundingRequiredFailedError
    
    print("\n" + "=" * 80)
    print("TEST 3: GROUNDED REQUIRED MODE")
    print("=" * 80)
    
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "What is 2+2? Do not search the web."}
        ],
        grounded=True,
        max_tokens=50,
        meta={"grounding_mode": "REQUIRED"}
    )
    
    print("Request: Simple math with REQUIRED mode (should fail)")
    
    error_raised = False
    try:
        response = await adapter.complete(request, timeout=30)
        print(f"  Response content: '{response.content}'")
    except GroundingRequiredFailedError as e:
        error_raised = True
        print(f"  ✓ Expected error raised: {str(e)[:100]}")
    except Exception as e:
        # API limitation: tool_choice != auto not supported
        if "tool choices" in str(e).lower() or "not supported" in str(e).lower():
            error_raised = True
            print(f"  ✓ API limitation (tool_choice must be auto): {str(e)[:100]}")
        else:
            print(f"  ✗ Unexpected error: {str(e)[:200]}")
    
    success = error_raised
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Failed closed as expected' if success else 'Did not fail'}")
    
    return success


async def test_4_gpt4_regression():
    """Test 4: GPT-4 regression check - ungrounded still works normally."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    print("\n" + "=" * 80)
    print("TEST 4: GPT-4 UNGROUNDED REGRESSION")
    print("=" * 80)
    
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "Say 'hello from GPT-4'."}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print("Request: GPT-4 ungrounded (should work normally)")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Content length: {len(response.content)}")
    
    metadata = response.metadata or {}
    print(f"  Response API: {metadata.get('response_api')}")
    print(f"  Model: {response.model}")
    
    success = len(response.content) > 0 and "gpt-4" in response.content.lower()
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'GPT-4 works' if success else 'GPT-4 broken'}")
    
    return success


async def main():
    """Run all acceptance tests."""
    print("\n" + "=" * 80)
    print("GPT-5 UNGROUNDED ACCEPTANCE TEST SUITE")
    print("=" * 80)
    
    results = []
    tests = [
        ("Ungrounded Hello World", test_1_ungrounded_hello_world),
        ("Ungrounded Strict JSON", test_2_ungrounded_strict_json),
        ("Grounded Required Mode", test_3_grounded_required),
        ("GPT-4 Regression Check", test_4_gpt4_regression)
    ]
    
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
            await asyncio.sleep(3)  # Rate limit
        except Exception as e:
            print(f"\n❌ {name} CRASHED: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("ACCEPTANCE TEST SUMMARY")
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