#!/usr/bin/env python3
"""
Systematic debug test suite for UNGROUNDED Responses API.
Tests various payload configurations to identify what makes the model return text.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
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


async def test_1_baseline_with_hints():
    """Test 1: Baseline UNGROUNDED with all format hints."""
    print("\n" + "="*80)
    print("TEST 1: BASELINE UNGROUNDED WITH ALL HINTS")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    # Patch adapter to add format hints
    adapter = OpenAIAdapter()
    original_build = adapter._build_ungrounded_responses_payload
    
    def patched_build(request, system_content, user_content, json_schema=None):
        payload, tokens = original_build(request, system_content, user_content, json_schema)
        # Add format hints that SDK might accept
        payload["text"] = {
            "format": {
                "type": "text"
            }
        }
        return payload, tokens
    
    adapter._build_ungrounded_responses_payload = patched_build
    
    # Create request with ALS
    als_text = "en-US, United States, America/New_York timezone"
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": f"{als_text}\n\nSay 'hello world'."}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print(f"📋 Configuration:")
    print(f"  • Payload hints: text.format.type='text'")
    print(f"  • ALS included: Yes")
    print(f"  • System prompt: Yes")
    
    response = await adapter.complete(request, timeout=30)
    metadata = response.metadata or {}
    
    # Analyze response
    print(f"\n📊 Results:")
    print(f"  • response_api: {metadata.get('response_api')}")
    print(f"  • tool_call_count: {metadata.get('tool_call_count')}")
    print(f"  • grounded_effective: {metadata.get('grounded_effective')}")
    print(f"  • why_not_grounded: {metadata.get('why_not_grounded')}")
    print(f"  • text_source: {metadata.get('text_source', 'not_set')}")
    print(f"  • Content length: {len(response.content)} chars")
    print(f"  • Content: '{response.content[:100]}...'" if response.content else "  • Content: EMPTY")
    
    success = len(response.content) > 0
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Got text' if success else 'No text returned'}")
    
    return success, metadata


async def test_2_negative_control():
    """Test 2: Negative control without format hints."""
    print("\n" + "="*80)
    print("TEST 2: NEGATIVE CONTROL (NO FORMAT HINTS)")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Create same request, no patches (no format hints)
    als_text = "en-US, United States, America/New_York timezone"
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": f"{als_text}\n\nSay 'hello world'."}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print(f"📋 Configuration:")
    print(f"  • Payload hints: NONE")
    print(f"  • ALS included: Yes")
    print(f"  • System prompt: Yes")
    
    response = await adapter.complete(request, timeout=30)
    metadata = response.metadata or {}
    
    # Analyze response
    print(f"\n📊 Results:")
    print(f"  • text_source: {metadata.get('text_source', 'not_set')}")
    print(f"  • Content length: {len(response.content)} chars")
    print(f"  • Content: '{response.content[:100]}...'" if response.content else "  • Content: EMPTY")
    
    success = len(response.content) == 0  # Expect failure
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Empty as expected' if success else 'Got unexpected text'}")
    
    return success, metadata


async def test_3_extraction_paths():
    """Test 3: Verify extraction discipline."""
    print("\n" + "="*80)
    print("TEST 3: EXTRACTION DISCIPLINE")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Patch to log extraction
    extraction_log = []
    original_complete = adapter.complete
    
    async def patched_complete(request, timeout=60):
        response = await original_complete(request, timeout)
        
        # Log what text_source was used
        metadata = response.metadata or {}
        extraction_log.append({
            "grounded": request.grounded,
            "text_source": metadata.get("text_source", "not_set"),
            "has_content": len(response.content) > 0
        })
        
        return response
    
    adapter.complete = patched_complete
    
    # Test ungrounded
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "Say 'test'."}],
        grounded=False,
        max_tokens=50
    )
    
    # Test grounded
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        grounded=True,
        max_tokens=50,
        meta={"grounding_mode": "AUTO"}
    )
    
    print(f"📋 Testing extraction paths...")
    
    response1 = await adapter.complete(request1, timeout=30)
    response2 = await adapter.complete(request2, timeout=30)
    
    print(f"\n📊 Extraction Log:")
    for entry in extraction_log:
        mode = "GROUNDED" if entry["grounded"] else "UNGROUNDED"
        print(f"  • {mode}: text_source={entry['text_source']}, has_content={entry['has_content']}")
    
    # Verify no grounded uses reasoning_fallback
    grounded_entries = [e for e in extraction_log if e["grounded"]]
    bad_fallback = any(e["text_source"] == "reasoning_fallback" for e in grounded_entries)
    
    success = not bad_fallback
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'No grounded fallback' if success else 'Grounded used reasoning fallback!'}")
    
    return success, extraction_log


async def test_4_token_clamp():
    """Test 4: Token floor clamp verification."""
    print("\n" + "="*80)
    print("TEST 4: TOKEN FLOOR CLAMP")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    results = []
    
    # Test ungrounded with low tokens
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "Hi"}],
        grounded=False,
        max_tokens=10  # Below minimum
    )
    
    # Test grounded with low tokens
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "Hi"}],
        grounded=True,
        max_tokens=10,  # Below minimum
        meta={"grounding_mode": "AUTO"}
    )
    
    print(f"📋 Testing with max_tokens=10 (below 16 minimum)...")
    
    response1 = await adapter.complete(request1, timeout=30)
    response2 = await adapter.complete(request2, timeout=30)
    
    meta1 = response1.metadata or {}
    meta2 = response2.metadata or {}
    
    eff1 = meta1.get("effective_max_output_tokens", 0)
    eff2 = meta2.get("effective_max_output_tokens", 0)
    
    print(f"\n📊 Results:")
    print(f"  • UNGROUNDED: requested=10, effective={eff1}")
    print(f"  • GROUNDED: requested=10, effective={eff2}")
    
    # Both should be clamped to at least 16
    success = eff1 >= 16 and eff2 >= 16
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Both clamped to >=16' if success else 'Clamping failed'}")
    
    return success, {"ungrounded": eff1, "grounded": eff2}


async def test_5_strict_json():
    """Test 5: UNGROUNDED with strict JSON schema."""
    print("\n" + "="*80)
    print("TEST 5: UNGROUNDED WITH STRICT JSON")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    json_schema = {
        "name": "SimpleResponse",
        "schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "timestamp": {"type": "string"}
            },
            "required": ["message", "timestamp"],
            "additionalProperties": False
        }
    }
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a JSON response generator."},
            {"role": "user", "content": "Generate a simple JSON with message='hello' and current timestamp."}
        ],
        grounded=False,
        max_tokens=200,
        meta={"json_schema": json_schema}
    )
    
    print(f"📋 Configuration:")
    print(f"  • Schema: SimpleResponse")
    print(f"  • Required fields: message, timestamp")
    
    response = await adapter.complete(request, timeout=30)
    metadata = response.metadata or {}
    
    # Try to parse JSON
    valid_json = False
    parsed = None
    try:
        if response.content:
            parsed = json.loads(response.content)
            valid_json = "message" in parsed and "timestamp" in parsed
    except:
        pass
    
    print(f"\n📊 Results:")
    print(f"  • tool_call_count: {metadata.get('tool_call_count')}")
    print(f"  • Content length: {len(response.content)} chars")
    print(f"  • Valid JSON: {valid_json}")
    if parsed:
        print(f"  • Parsed: {parsed}")
    
    success = valid_json
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: {'Valid JSON returned' if success else 'Invalid/no JSON'}")
    
    return success, metadata


async def main():
    """Run all systematic tests."""
    print("\n" + "="*80)
    print("SYSTEMATIC DEBUG TEST SUITE")
    print("="*80)
    
    results = []
    
    # Run tests with delays to avoid rate limits
    tests = [
        ("Test 1: Baseline with hints", test_1_baseline_with_hints),
        ("Test 2: Negative control", test_2_negative_control),
        ("Test 3: Extraction discipline", test_3_extraction_paths),
        ("Test 4: Token clamp", test_4_token_clamp),
        ("Test 5: Strict JSON", test_5_strict_json)
    ]
    
    for name, test_func in tests:
        try:
            success, data = await test_func()
            results.append((name, success))
            await asyncio.sleep(3)  # Rate limit protection
        except Exception as e:
            print(f"\n❌ {name} CRASHED: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print(f"\n{'🎉 ALL TESTS PASSED' if all_passed else '⚠️ SOME TESTS FAILED'}")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)