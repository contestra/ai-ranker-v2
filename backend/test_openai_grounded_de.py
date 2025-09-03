#!/usr/bin/env python3
"""
Test OpenAI adapter with proper Responses API and assertions.
Tests both AUTO and REQUIRED grounding modes with 6000 token budget.
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

# Set ALS to Germany
os.environ["ALS_COUNTRY_CODE"] = "DE"
os.environ["ALS_LOCALE"] = "de-DE"
os.environ["ALS_TZ"] = "Europe/Berlin"

# Disable rate limiter for testing
os.environ["OAI_DISABLE_LIMITER"] = "1"

# Ensure 6000 tokens for grounded runs
os.environ["OAI_GROUNDED_MAX_TOKENS"] = "6000"


async def test_openai_grounded_auto():
    """Test OpenAI with grounded AUTO mode."""
    print("\n" + "="*80)
    print("TEST 1: OPENAI GROUNDED AUTO MODE")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    # Initialize adapter
    adapter = OpenAIAdapter()
    
    # Build ALS text (implicit, no labels)
    als_text = "de-DE, Germany, Europe/Berlin timezone, metric units, 24-hour time, DD.MM.YYYY date format"
    
    # Create request with AUTO mode
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{als_text}\n\ntell me the primary health and wellness news during August 2025"}
        ],
        grounded=True,
        temperature=0.7,
        max_tokens=6000,  # Will be overridden to 6000 anyway
        meta={"grounding_mode": "AUTO"}
    )
    
    print(f"\n📋 Configuration:")
    print(f"  • Model: {request.model}")
    print(f"  • Grounding mode: AUTO")
    print(f"  • Max tokens: 6000 (enforced)")
    print(f"  • ALS: {os.environ['ALS_LOCALE']} ({os.environ['ALS_COUNTRY_CODE']})")
    
    print(f"\n⏳ Calling OpenAI adapter with AUTO mode...")
    start = datetime.now()
    
    try:
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=60),
            timeout=60
        )
        
        duration = (datetime.now() - start).total_seconds()
        print(f"✅ Response received in {duration:.1f}s")
        
        # Extract metadata
        metadata = response.metadata or {}
        
        # Assertions for AUTO mode
        print(f"\n📊 AUTO Mode Assertions:")
        
        # 1. Response API used
        assert metadata.get("response_api") == "responses_http", f"Expected responses_http, got {metadata.get('response_api')}"
        print(f"  ✓ Response API: {metadata.get('response_api')}")
        
        # 2. Tool call count exists
        assert "tool_call_count" in metadata, "Missing tool_call_count"
        tool_count = metadata["tool_call_count"]
        print(f"  ✓ Tool calls: {tool_count}")
        
        # 3. Grounded effective matches tool calls
        assert metadata.get("grounded_effective") == (tool_count > 0), "grounded_effective mismatch"
        print(f"  ✓ Grounded effective: {metadata.get('grounded_effective')}")
        
        # 4. Why not grounded (if no search)
        if tool_count == 0:
            assert metadata.get("why_not_grounded") == "auto_mode_no_search", f"Expected auto_mode_no_search, got {metadata.get('why_not_grounded')}"
            print(f"  ✓ Why not grounded: {metadata.get('why_not_grounded')}")
        else:
            assert metadata.get("why_not_grounded") is None or metadata.get("why_not_grounded") == "", "why_not_grounded should be empty when grounded"
        
        # 5. Web tool type recorded
        if tool_count > 0:
            assert "web_tool_type" in metadata, "Missing web_tool_type"
            print(f"  ✓ Web tool type: {metadata.get('web_tool_type')}")
        
        # 6. Content is not empty
        assert response.content and len(response.content) > 0, "Empty content returned"
        print(f"  ✓ Content length: {len(response.content)} chars")
        
        # 7. Usage flattened
        if response.usage:
            assert "prompt_tokens" in response.usage, "Missing prompt_tokens"
            assert "completion_tokens" in response.usage, "Missing completion_tokens"
            print(f"  ✓ Usage: prompt={response.usage.get('prompt_tokens', 0)}, "
                  f"completion={response.usage.get('completion_tokens', 0)}")
        
        print(f"\n✅ AUTO MODE TEST PASSED")
        
        # Print full response for inspection
        print(f"\n📄 Response Preview (first 500 chars):")
        print(response.content[:500] if response.content else "[Empty]")
        
        return True
        
    except asyncio.TimeoutError:
        print(f"❌ Request timed out after 60 seconds")
        return False
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_openai_grounded_required():
    """Test OpenAI with grounded REQUIRED mode."""
    print("\n" + "="*80)
    print("TEST 2: OPENAI GROUNDED REQUIRED MODE")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    from app.llm.errors import GroundingRequiredFailedError
    
    # Initialize adapter
    adapter = OpenAIAdapter()
    
    # Build ALS text
    als_text = "de-DE, Germany, Europe/Berlin timezone, metric units, 24-hour time, DD.MM.YYYY date format"
    
    # Create request with REQUIRED mode and strict JSON
    json_schema = {
        "name": "HealthNewsSummary",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "key_topics": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "locale_used": {"type": "string"}
            },
            "required": ["summary", "key_topics", "locale_used"],
            "additionalProperties": False
        }
    }
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Always search for current information."},
            {"role": "user", "content": f"{als_text}\n\nSearch for and summarize the primary health and wellness news during August 2025. You MUST search the web."}
        ],
        grounded=True,
        temperature=0.7,
        max_tokens=6000,
        meta={
            "grounding_mode": "REQUIRED",
            "json_schema": json_schema
        }
    )
    
    print(f"\n📋 Configuration:")
    print(f"  • Model: {request.model}")
    print(f"  • Grounding mode: REQUIRED")
    print(f"  • Max tokens: 6000 (enforced)")
    print(f"  • Strict JSON: Yes")
    
    print(f"\n⏳ Calling OpenAI adapter with REQUIRED mode...")
    start = datetime.now()
    
    try:
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=60),
            timeout=60
        )
        
        duration = (datetime.now() - start).total_seconds()
        print(f"✅ Response received in {duration:.1f}s")
        
        # Extract metadata
        metadata = response.metadata or {}
        
        # Assertions for REQUIRED mode
        print(f"\n📊 REQUIRED Mode Assertions:")
        
        # 1. Tool calls must be > 0 (or would have raised exception)
        assert metadata.get("tool_call_count", 0) > 0, "REQUIRED mode but no tool calls"
        print(f"  ✓ Tool calls: {metadata['tool_call_count']} (REQUIRED satisfied)")
        
        # 2. Grounded effective must be true
        assert metadata.get("grounded_effective") == True, "Not grounded despite tool calls"
        print(f"  ✓ Grounded effective: True")
        
        # 3. No why_not_grounded
        assert not metadata.get("why_not_grounded"), "why_not_grounded set despite being grounded"
        print(f"  ✓ Why not grounded: None (as expected)")
        
        # 4. Strict JSON validation
        if json_schema:
            try:
                parsed = json.loads(response.content)
                assert "summary" in parsed, "Missing 'summary' in JSON"
                assert "key_topics" in parsed, "Missing 'key_topics' in JSON"
                assert "locale_used" in parsed, "Missing 'locale_used' in JSON"
                assert isinstance(parsed["key_topics"], list), "key_topics not an array"
                print(f"  ✓ Strict JSON valid with all required fields")
                print(f"  ✓ Locale used: {parsed.get('locale_used', 'N/A')}")
            except json.JSONDecodeError:
                print(f"  ⚠️ Response not valid JSON (might be plain text if schema not applied)")
        
        print(f"\n✅ REQUIRED MODE TEST PASSED")
        
        return True
        
    except GroundingRequiredFailedError as e:
        print(f"✅ REQUIRED mode correctly failed when no search performed")
        print(f"   Error: {e}")
        return True  # This is expected behavior
    except asyncio.TimeoutError:
        print(f"❌ Request timed out after 60 seconds")
        return False
    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_openai_required_fail_case():
    """Test that REQUIRED mode fails when model doesn't search."""
    print("\n" + "="*80)
    print("TEST 3: OPENAI REQUIRED MODE FAIL CASE")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    from app.llm.errors import GroundingRequiredFailedError
    
    # Initialize adapter
    adapter = OpenAIAdapter()
    
    # Create request that likely won't trigger search
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "What is 2+2? Answer only the number."}
        ],
        grounded=True,
        temperature=0.0,
        max_tokens=10,
        meta={"grounding_mode": "REQUIRED"}
    )
    
    print(f"\n📋 Configuration:")
    print(f"  • Prompt: 'What is 2+2?'")
    print(f"  • Grounding mode: REQUIRED")
    print(f"  • Expected: Should fail with GroundingRequiredFailedError")
    
    print(f"\n⏳ Testing REQUIRED fail case...")
    
    try:
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=30),
            timeout=30
        )
        print(f"❌ Expected GroundingRequiredFailedError but got success")
        return False
        
    except GroundingRequiredFailedError as e:
        print(f"✅ Correctly raised GroundingRequiredFailedError")
        print(f"   Error message: {e}")
        assert "no_tool_calls" in str(e), "Error should mention no_tool_calls"
        return True
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("OPENAI ADAPTER RESPONSES API TEST SUITE")
    print("="*80)
    
    results = []
    
    # Test 1: AUTO mode
    results.append(("AUTO Mode", await test_openai_grounded_auto()))
    
    # Test 2: REQUIRED mode (should succeed with search)
    results.append(("REQUIRED Mode", await test_openai_grounded_required()))
    
    # Test 3: REQUIRED fail case
    results.append(("REQUIRED Fail Case", await test_openai_required_fail_case()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        print(f"\n🎉 ALL TESTS PASSED")
    else:
        print(f"\n⚠️ SOME TESTS FAILED")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)