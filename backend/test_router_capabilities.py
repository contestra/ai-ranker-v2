#!/usr/bin/env python3
"""
Comprehensive tests for router capability gating, circuit breaker, and pacing.
Tests the unified_llm_adapter router enhancements.
"""
import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import Dict, Any

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


async def test_openai_capability_gating():
    """Test 1: OpenAI reasoning parameter gating - GPT-4o vs GPT-5."""
    print("\n" + "="*60)
    print("TEST 1: OpenAI Capability Gating")
    print("="*60)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    router = UnifiedLLMAdapter()
    
    # Test GPT-4o - should drop reasoning parameters
    print("\n[GPT-4o Test]")
    caps_4o = router._capabilities_for("openai", "gpt-4o")
    assert caps_4o["supports_reasoning_effort"] is False
    assert caps_4o["supports_reasoning_summary"] is False
    print("✅ GPT-4o correctly marked as non-reasoning model")
    
    # Mock adapter response
    mock_response = MagicMock()
    mock_response.content = "Test response"
    mock_response.success = True
    mock_response.grounded_effective = False
    mock_response.metadata = {}
    mock_response.model_version = "gpt-4o"
    mock_response.model_fingerprint = None
    mock_response.usage = {}
    mock_response.latency_ms = 100
    mock_response.raw_response = None
    mock_response.vendor = "openai"
    mock_response.model = "gpt-4o"
    mock_response.citations = []
    
    with patch.object(router, '_openai_adapter', new=MagicMock()):
        router._openai_adapter.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}],
            grounded=False,
            meta={"reasoning_effort": "medium", "reasoning_summary": True}
        )
        
        response = await router.complete(request)
        
        # Check that reasoning parameters were dropped
        assert "reasoning_effort" not in request.meta
        assert "reasoning_summary" not in request.meta
        assert response.metadata.get("reasoning_hint_dropped") is True
        print("✅ Reasoning parameters dropped for GPT-4o")
    
    # Test GPT-5 - should keep reasoning parameters
    print("\n[GPT-5 Test]")
    caps_5 = router._capabilities_for("openai", "gpt-5-2025-08-07")
    assert caps_5["supports_reasoning_effort"] is True
    assert caps_5["supports_reasoning_summary"] is True
    print("✅ GPT-5 correctly marked as reasoning model")
    
    with patch.object(router, '_openai_adapter', new=MagicMock()):
        router._openai_adapter.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": "Test"}],
            grounded=False,
            meta={"reasoning_effort": "medium", "reasoning_summary": True}
        )
        
        response = await router.complete(request)
        
        # Check that reasoning parameters were kept
        assert request.meta.get("reasoning_effort") == "medium"
        assert request.meta.get("reasoning_summary") is True
        assert response.metadata.get("reasoning_hint_dropped") is False
        print("✅ Reasoning parameters preserved for GPT-5")
    
    return True


async def test_gemini_thinking_gating():
    """Test 2: Gemini/Vertex thinking parameter gating."""
    print("\n" + "="*60)
    print("TEST 2: Gemini/Vertex Thinking Gating")
    print("="*60)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    router = UnifiedLLMAdapter()
    
    # Test Gemini 2.5 Flash - thinking capable
    print("\n[Gemini 2.5 Flash Test]")
    caps_flash = router._capabilities_for("vertex", "publishers/google/models/gemini-2.5-flash")
    assert caps_flash["supports_thinking_budget"] is True
    assert caps_flash["include_thoughts_allowed"] is True
    print("✅ Gemini 2.5 Flash marked as thinking-capable")
    
    # Test older Gemini model - not thinking capable
    print("\n[Gemini 1.0 Pro Test]")
    caps_old = router._capabilities_for("vertex", "publishers/google/models/gemini-1.0-pro")
    assert caps_old["supports_thinking_budget"] is False
    assert caps_old["include_thoughts_allowed"] is False
    print("✅ Gemini 1.0 Pro marked as non-thinking model")
    
    # Mock response
    mock_response = MagicMock()
    mock_response.content = "Test response"
    mock_response.success = True
    mock_response.grounded_effective = False
    mock_response.metadata = {}
    mock_response.model_version = "gemini-1.0-pro"
    mock_response.model_fingerprint = None
    mock_response.usage = {}
    mock_response.latency_ms = 100
    mock_response.raw_response = None
    mock_response.vendor = "vertex"
    mock_response.model = "publishers/google/models/gemini-1.0-pro"
    mock_response.citations = []
    
    with patch.object(router, 'vertex_adapter') as mock_adapter:
        mock_adapter.complete = AsyncMock(return_value=mock_response)
        
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-1.0-pro",
            messages=[{"role": "user", "content": "Test"}],
            grounded=False,
            meta={"thinking_budget": 10, "include_thoughts": True}
        )
        
        # Mock model validation
        with patch('app.llm.unified_llm_adapter.validate_model', return_value=(True, "")):
            # Mock the allowed models check
            with patch.dict(os.environ, {"ALLOWED_VERTEX_MODELS": "publishers/google/models/gemini-1.0-pro"}):
                response = await router.complete(request)
        
        # Check that thinking parameters were dropped
        assert "thinking_budget" not in request.meta
        assert "include_thoughts" not in request.meta
        assert response.metadata.get("thinking_hint_dropped") is True
        print("✅ Thinking parameters dropped for non-thinking model")
    
    return True


async def test_circuit_breaker():
    """Test 3: Circuit breaker open/half-open/close transitions."""
    print("\n" + "="*60)
    print("TEST 3: Circuit Breaker Transitions")
    print("="*60)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    # Set low threshold for testing
    os.environ["CB_FAILURE_THRESHOLD"] = "2"
    os.environ["CB_COOLDOWN_SECONDS"] = "2"
    
    router = UnifiedLLMAdapter()
    
    # Create a rate limit error
    rate_limit_error = Exception("Error code: 429 - Rate limit exceeded")
    rate_limit_error.response = MagicMock()
    rate_limit_error.response.status_code = 429
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Test"}],
        grounded=False
    )
    
    print("\n[Failure accumulation]")
    # First failure
    router._record_failure("openai", "gpt-4o", rate_limit_error)
    status1, _ = router._check_circuit_breaker("openai", "gpt-4o")
    assert status1 == "closed"
    print("✅ First failure: breaker still closed")
    
    # Second failure - should open
    router._record_failure("openai", "gpt-4o", rate_limit_error)
    status2, error2 = router._check_circuit_breaker("openai", "gpt-4o")
    assert status2 == "open"
    assert error2 is not None
    print("✅ Second failure: breaker opened")
    
    print("\n[Open state blocks requests]")
    # Try a request while open - should fail fast
    with patch.object(router, '_openai_adapter', new=MagicMock()):
        response = await router.complete(request)
        assert response.success is False
        assert "Circuit breaker open" in response.error
        assert response.metadata.get("circuit_breaker_status") == "open"
        print("✅ Request blocked while breaker open")
    
    print("\n[Half-open transition]")
    # Wait for cooldown
    await asyncio.sleep(2.5)
    
    status3, error3 = router._check_circuit_breaker("openai", "gpt-4o")
    assert status3 == "half-open"
    assert error3 is None
    print("✅ Breaker transitioned to half-open after cooldown")
    
    print("\n[Close on success]")
    # Successful call should close breaker
    router._record_success("openai", "gpt-4o")
    status4, _ = router._check_circuit_breaker("openai", "gpt-4o")
    assert status4 == "closed"
    print("✅ Breaker closed after successful call")
    
    # Check open counter
    assert router._cb_open_count == 1
    print(f"✅ Circuit breaker open count: {router._cb_open_count}")
    
    return True


async def test_router_pacing():
    """Test 4: Router pacing with Retry-After headers."""
    print("\n" + "="*60)
    print("TEST 4: Router Pacing with Retry-After")
    print("="*60)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    router = UnifiedLLMAdapter()
    
    # Create error with Retry-After header
    rate_error = Exception("Rate limit exceeded")
    rate_error.response = MagicMock()
    rate_error.response.headers = {"Retry-After": "5"}
    
    print("\n[Extract Retry-After]")
    retry_after = router._extract_retry_after("openai", rate_error)
    assert retry_after == 5
    print("✅ Extracted Retry-After: 5 seconds")
    
    print("\n[Update pacing]")
    router._update_pacing("openai", "gpt-4o", rate_error)
    
    # Check pacing immediately
    pace_error = router._check_pacing("openai", "gpt-4o")
    assert pace_error is not None
    assert "wait" in pace_error
    print(f"✅ Pacing active: {pace_error}")
    
    print("\n[Request blocked by pacing]")
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Test"}],
        grounded=False
    )
    
    with patch.object(router, '_openai_adapter', new=MagicMock()):
        response = await router.complete(request)
        assert response.success is False
        assert "Router pacing" in response.error
        assert response.metadata.get("router_pacing_delay") is True
        print("✅ Request blocked by pacing")
    
    # Wait and check pacing cleared
    print("\n[Pacing cleared after delay]")
    await asyncio.sleep(5.5)
    pace_error2 = router._check_pacing("openai", "gpt-4o")
    assert pace_error2 is None
    print("✅ Pacing cleared after delay")
    
    return True


async def test_telemetry_fields():
    """Test 5: Verify telemetry includes new fields."""
    print("\n" + "="*60)
    print("TEST 5: Telemetry Field Verification")
    print("="*60)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    router = UnifiedLLMAdapter()
    
    # Mock response with all metadata
    mock_response = MagicMock()
    mock_response.content = "Test response"
    mock_response.success = True
    mock_response.grounded_effective = True
    mock_response.metadata = {
        "tool_call_count": 1,
        "response_api": "responses",
        "reasoning_hint_dropped": True,
        "thinking_hint_dropped": False,
        "circuit_breaker_status": "closed"
    }
    mock_response.model_version = "gpt-4o"
    mock_response.model_fingerprint = "fp_123"
    mock_response.usage = {"total_tokens": 100}
    mock_response.latency_ms = 150
    mock_response.raw_response = None
    mock_response.vendor = "openai"
    mock_response.model = "gpt-4o"
    mock_response.citations = []
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Test"}],
        grounded=True,
        meta={
            "reasoning_effort": "medium",
            "reasoning_summary": True,
            "grounding_mode": "AUTO"
        },
        template_id="test_template",
        run_id="test_run"
    )
    
    # Mock session and telemetry emit
    mock_session = MagicMock()
    
    with patch.object(router, '_openai_adapter', new=MagicMock()):
        router._openai_adapter.complete = AsyncMock(return_value=mock_response)
        
        with patch.object(router, '_emit_telemetry') as mock_emit:
            response = await router.complete(request, session=mock_session)
            
            # Verify _emit_telemetry was called
            mock_emit.assert_called_once()
            
            # Check response metadata has required fields
            assert "reasoning_hint_dropped" in response.metadata
            assert "circuit_breaker_status" in response.metadata
            print("✅ Response metadata includes new fields")
    
    # Test telemetry metadata construction
    print("\n[Telemetry metadata validation]")
    
    # Manually test metadata construction like in _emit_telemetry
    meta_json = {
        'reasoning_effort': request.meta.get('reasoning_effort'),
        'reasoning_summary_requested': request.meta.get('reasoning_summary', False),
        'reasoning_hint_dropped': response.metadata.get('reasoning_hint_dropped', False),
        'thinking_hint_dropped': response.metadata.get('thinking_hint_dropped', False),
        'circuit_breaker_status': response.metadata.get('circuit_breaker_status', 'closed'),
        'circuit_breaker_open_count': router._cb_open_count,
        'router_pacing_delay': response.metadata.get('router_pacing_delay', False)
    }
    
    assert meta_json['reasoning_effort'] == 'medium'
    assert meta_json['reasoning_summary_requested'] is True
    assert meta_json['reasoning_hint_dropped'] is True
    assert meta_json['thinking_hint_dropped'] is False
    assert meta_json['circuit_breaker_status'] == 'closed'
    print("✅ Telemetry metadata correctly constructed")
    
    return True


async def test_no_prompt_mutation():
    """Test 6: Verify user prompts are never mutated."""
    print("\n" + "="*60)
    print("TEST 6: No Prompt Mutation Verification")
    print("="*60)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    import copy
    
    router = UnifiedLLMAdapter()
    
    original_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"}
    ]
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=copy.deepcopy(original_messages),
        grounded=False,
        meta={"reasoning_effort": "high"}  # Will be dropped
    )
    
    # Store original content
    original_content = [msg["content"] for msg in request.messages]
    
    mock_response = MagicMock()
    mock_response.content = "4"
    mock_response.success = True
    mock_response.grounded_effective = False
    mock_response.metadata = {}
    mock_response.model_version = "gpt-4o"
    mock_response.model_fingerprint = None
    mock_response.usage = {}
    mock_response.latency_ms = 100
    mock_response.raw_response = None
    mock_response.vendor = "openai"
    mock_response.model = "gpt-4o"
    mock_response.citations = []
    
    with patch.object(router, '_openai_adapter', new=MagicMock()):
        router._openai_adapter.complete = AsyncMock(return_value=mock_response)
        
        response = await router.complete(request)
        
        # Verify messages content unchanged
        current_content = [msg["content"] for msg in request.messages]
        
        # Check each message
        for orig, curr in zip(original_content, current_content):
            assert orig == curr, f"Message content changed: {orig} != {curr}"
        
        print("✅ User messages unchanged")
        
        # Verify only parameters were dropped
        assert "reasoning_effort" not in request.meta
        print("✅ Only unsupported parameters dropped, not message content")
    
    return True


async def run_all_tests():
    """Run all router capability tests."""
    print("\n" + "="*60)
    print("ROUTER CAPABILITY TESTS")
    print("="*60)
    
    tests = [
        ("OpenAI Capability Gating", test_openai_capability_gating),
        ("Gemini Thinking Gating", test_gemini_thinking_gating),
        ("Circuit Breaker", test_circuit_breaker),
        ("Router Pacing", test_router_pacing),
        ("Telemetry Fields", test_telemetry_fields),
        ("No Prompt Mutation", test_no_prompt_mutation)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            print(f"\nRunning: {name}")
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} failed with error: {str(e)}")
            import traceback
            traceback.print_exc()
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
        print("🎉 ALL ROUTER TESTS PASSED!")
    else:
        print("⚠️ SOME TESTS FAILED")
    print("="*60)
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)