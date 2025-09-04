#!/usr/bin/env python3
"""
Test OpenAI adapter UNGROUNDED mode using Responses API.
Verifies that ungrounded calls now use Responses SDK with proper telemetry.
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

# Set ALS for testing
os.environ["ALS_COUNTRY_CODE"] = "US"
os.environ["ALS_LOCALE"] = "en-US"
os.environ["ALS_TZ"] = "America/New_York"

# Disable rate limiter for testing
os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_ungrounded_plain_text():
    """Test ungrounded mode with plain text response."""
    print("\n" + "="*80)
    print("TEST 1: UNGROUNDED MODE - PLAIN TEXT")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    # Initialize adapter
    adapter = OpenAIAdapter()
    
    # Build ALS text
    als_text = "en-US, United States, America/New_York timezone, imperial units, 12-hour time, MM/DD/YYYY date format"
    
    # Create ungrounded request (no grounded=True)
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{als_text}\n\nWhat is the capital of France? Answer in one word."}
        ],
        grounded=False,  # UNGROUNDED
        temperature=0.0,
        max_tokens=50
    )
    
    print(f"\n📋 Configuration:")
    print(f"  • Model: {request.model}")
    print(f"  • Grounded: FALSE (ungrounded mode)")
    print(f"  • Max tokens: {request.max_tokens}")
    print(f"  • ALS: {os.environ['ALS_LOCALE']}")
    
    print(f"\n⏳ Calling OpenAI adapter in ungrounded mode...")
    start = datetime.now()
    
    try:
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=30),
            timeout=30
        )
        
        duration = (datetime.now() - start).total_seconds()
        print(f"✅ Response received in {duration:.1f}s")
        
        # Extract metadata
        metadata = response.metadata or {}
        
        # Assertions for UNGROUNDED mode
        print(f"\n📊 Ungrounded Mode Assertions:")
        
        # 1. Response API should be responses_sdk
        assert metadata.get("response_api") == "responses_sdk", f"Expected responses_sdk, got {metadata.get('response_api')}"
        print(f"  ✓ Response API: {metadata.get('response_api')}")
        
        # 2. Tool call count should be 0
        assert metadata.get("tool_call_count") == 0, f"Expected 0 tool calls, got {metadata.get('tool_call_count')}"
        print(f"  ✓ Tool calls: 0 (ungrounded)")
        
        # 3. Grounded effective should be false
        assert metadata.get("grounded_effective") == False, "Expected grounded_effective=false"
        print(f"  ✓ Grounded effective: False")
        
        # 4. Why not grounded should be "ungrounded_mode"
        assert metadata.get("why_not_grounded") == "ungrounded_mode", f"Expected ungrounded_mode, got {metadata.get('why_not_grounded')}"
        print(f"  ✓ Why not grounded: ungrounded_mode")
        
        # 5. Effective max tokens check
        eff = metadata.get("effective_max_output_tokens")
        assert eff is not None, "Adapter must record effective_max_output_tokens after clamp"
        assert isinstance(eff, int), f"effective_max_output_tokens should be int, got {type(eff)}"
        assert eff >= 16, f"Responses requires >=16, got {eff}"
        print(f"  ✓ Effective max tokens: {eff} (>= 16)")
        
        # 6. Content should exist
        assert response.content and len(response.content) > 0, "Empty content returned"
        print(f"  ✓ Content: '{response.content}'")
        
        # 6. Usage should be present
        if response.usage:
            assert "prompt_tokens" in response.usage, "Missing prompt_tokens"
            assert "completion_tokens" in response.usage, "Missing completion_tokens"
            print(f"  ✓ Usage: prompt={response.usage.get('prompt_tokens', 0)}, "
                  f"completion={response.usage.get('completion_tokens', 0)}")
        
        print(f"\n✅ UNGROUNDED PLAIN TEXT TEST PASSED")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ungrounded_strict_json():
    """Test ungrounded mode with strict JSON schema."""
    print("\n" + "="*80)
    print("TEST 2: UNGROUNDED MODE - STRICT JSON")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    # Initialize adapter
    adapter = OpenAIAdapter()
    
    # Build ALS text
    als_text = "en-US, United States, America/New_York timezone, imperial units, 12-hour time, MM/DD/YYYY date format"
    
    # Define strict JSON schema
    json_schema = {
        "name": "CapitalResponse",
        "schema": {
            "type": "object",
            "properties": {
                "country": {"type": "string"},
                "capital": {"type": "string"},
                "locale_acknowledged": {"type": "string"}
            },
            "required": ["country", "capital", "locale_acknowledged"],
            "additionalProperties": False
        }
    }
    
    # Create ungrounded request with JSON schema
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Always respond in valid JSON."},
            {"role": "user", "content": f"{als_text}\n\nWhat is the capital of France? Include the locale you acknowledged."}
        ],
        grounded=False,  # UNGROUNDED
        temperature=0.0,
        max_tokens=200,
        meta={"json_schema": json_schema}
    )
    
    print(f"\n📋 Configuration:")
    print(f"  • Model: {request.model}")
    print(f"  • Grounded: FALSE (ungrounded mode)")
    print(f"  • Max tokens: {request.max_tokens}")
    print(f"  • Strict JSON: Yes")
    print(f"  • Schema: CapitalResponse")
    
    print(f"\n⏳ Calling OpenAI adapter with strict JSON...")
    start = datetime.now()
    
    try:
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=30),
            timeout=30
        )
        
        duration = (datetime.now() - start).total_seconds()
        print(f"✅ Response received in {duration:.1f}s")
        
        # Extract metadata
        metadata = response.metadata or {}
        
        # Assertions
        print(f"\n📊 Strict JSON Assertions:")
        
        # 1. Response API should be responses_sdk
        assert metadata.get("response_api") == "responses_sdk", f"Expected responses_sdk, got {metadata.get('response_api')}"
        print(f"  ✓ Response API: {metadata.get('response_api')}")
        
        # 2. Ungrounded telemetry
        assert metadata.get("tool_call_count") == 0, "Should have 0 tool calls"
        assert metadata.get("grounded_effective") == False, "Should not be grounded"
        assert metadata.get("why_not_grounded") == "ungrounded_mode", "Should be ungrounded_mode"
        print(f"  ✓ Ungrounded telemetry correct")
        
        # 3. Effective max tokens check  
        eff = metadata.get("effective_max_output_tokens")
        assert eff is not None, "Adapter must record effective_max_output_tokens"
        assert isinstance(eff, int), f"effective_max_output_tokens should be int, got {type(eff)}"
        assert eff >= 16, f"Responses requires >=16, got {eff}"
        print(f"  ✓ Effective max tokens: {eff}")
        
        # 4. Valid JSON response
        try:
            parsed = json.loads(response.content)
            assert "country" in parsed, "Missing 'country' field"
            assert "capital" in parsed, "Missing 'capital' field"
            assert "locale_acknowledged" in parsed, "Missing 'locale_acknowledged' field"
            print(f"  ✓ Valid JSON with all required fields")
            print(f"  ✓ Country: {parsed['country']}")
            print(f"  ✓ Capital: {parsed['capital']}")
            print(f"  ✓ Locale: {parsed['locale_acknowledged']}")
            
            # Check JSON validity flag in metadata
            assert metadata.get("json_valid") == True, "JSON should be marked as valid"
            print(f"  ✓ JSON validity tracked in metadata")
            
        except json.JSONDecodeError as e:
            print(f"  ❌ Invalid JSON: {e}")
            print(f"  Response: {response.content}")
            return False
        
        print(f"\n✅ UNGROUNDED STRICT JSON TEST PASSED")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_token_clamping():
    """Test that tokens < 16 are clamped to 16."""
    print("\n" + "="*80)
    print("TEST 3: TOKEN CLAMPING (<16 -> 16)")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Test with explicit max_tokens=10 (should be clamped to 16)
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "Say 'hi'"}
        ],
        grounded=False,
        temperature=0.0,
        max_tokens=10  # Below minimum!
    )
    
    print(f"\n📋 Testing with max_tokens=10 (below minimum)...")
    
    response = await adapter.complete(request, timeout=30)
    md = response.metadata or {}
    
    # A) Clamping assertion for explicit max_tokens=10
    eff = md.get("effective_max_output_tokens")
    assert eff is not None, "Adapter must record effective_max_output_tokens after clamp"
    assert isinstance(eff, int)
    assert eff == 16, f"Expected clamp to 16 for Responses, got {eff}"
    print(f"  ✓ Clamped to minimum: {eff} (was 10)")
    
    # C) Verify Responses SDK used
    assert md.get("response_api") == "responses_sdk", "Ungrounded runs must use Responses SDK"
    print(f"  ✓ Response API: {md.get('response_api')}")
    
    # D) Usage sanity check
    usage = response.usage or {}
    for k in ["prompt_tokens", "completion_tokens"]:
        if k in usage:
            assert isinstance(usage[k], int), f"{k} should be an int, got {type(usage[k])}"
    print(f"  ✓ Usage types correct")
    
    print("\n✅ TOKEN CLAMPING TEST PASSED")
    return True


async def test_ungrounded_vs_grounded_telemetry():
    """Compare telemetry between ungrounded and grounded modes."""
    print("\n" + "="*80)
    print("TEST 4: TELEMETRY COMPARISON - UNGROUNDED VS GROUNDED")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    als_text = "en-US, United States, America/New_York timezone"
    
    # Test ungrounded
    print("\n📊 Testing UNGROUNDED mode...")
    request_ungrounded = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": f"{als_text}\n\nWhat is 2+2?"}
        ],
        grounded=False,
        temperature=0.0,
        max_tokens=10
    )
    
    response_ungrounded = await adapter.complete(request_ungrounded, timeout=30)
    meta_ungrounded = response_ungrounded.metadata or {}
    
    print(f"  Response API: {meta_ungrounded.get('response_api')}")
    print(f"  Tool calls: {meta_ungrounded.get('tool_call_count')}")
    print(f"  Grounded effective: {meta_ungrounded.get('grounded_effective')}")
    print(f"  Why not grounded: {meta_ungrounded.get('why_not_grounded')}")
    
    # Test grounded AUTO (likely won't search for simple math)
    print("\n📊 Testing GROUNDED AUTO mode (simple question)...")
    request_grounded = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": f"{als_text}\n\nWhat is 2+2?"}
        ],
        grounded=True,
        temperature=0.0,
        max_tokens=10,
        meta={"grounding_mode": "AUTO"}
    )
    
    response_grounded = await adapter.complete(request_grounded, timeout=30)
    meta_grounded = response_grounded.metadata or {}
    
    print(f"  Response API: {meta_grounded.get('response_api')}")
    print(f"  Tool calls: {meta_grounded.get('tool_call_count')}")
    print(f"  Grounded effective: {meta_grounded.get('grounded_effective')}")
    print(f"  Why not grounded: {meta_grounded.get('why_not_grounded')}")
    
    # Verify differences
    print("\n📊 Telemetry Comparison:")
    print(f"  Ungrounded why_not: '{meta_ungrounded.get('why_not_grounded')}'")
    print(f"  Grounded why_not: '{meta_grounded.get('why_not_grounded')}'")
    
    assert meta_ungrounded.get('why_not_grounded') == "ungrounded_mode", "Ungrounded should say ungrounded_mode"
    assert meta_grounded.get('why_not_grounded') in ["auto_mode_no_search", "no_tool_calls"], "Grounded should have different reason"
    
    print("\n✅ TELEMETRY COMPARISON TEST PASSED")
    
    return True


async def main():
    """Run all ungrounded tests."""
    print("\n" + "="*80)
    print("OPENAI UNGROUNDED RESPONSES API TEST SUITE")
    print("="*80)
    print("Testing that ungrounded calls now use Responses SDK")
    
    results = []
    
    # Test 1: Plain text ungrounded
    results.append(("Ungrounded Plain Text", await test_ungrounded_plain_text()))
    
    # Add delay to avoid rate limit
    await asyncio.sleep(2)
    
    # Test 2: Strict JSON ungrounded
    results.append(("Ungrounded Strict JSON", await test_ungrounded_strict_json()))
    
    # Add delay
    await asyncio.sleep(2)
    
    # Test 3: Token clamping
    results.append(("Token Clamping", await test_token_clamping()))
    
    # Add delay
    await asyncio.sleep(2)
    
    # Test 4: Telemetry comparison
    results.append(("Telemetry Comparison", await test_ungrounded_vs_grounded_telemetry()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        print(f"\n🎉 ALL TESTS PASSED - Ungrounded now uses Responses API!")
    else:
        print(f"\n⚠️ SOME TESTS FAILED")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)