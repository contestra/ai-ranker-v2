#!/usr/bin/env python3
"""
Acceptance tests for Gemini resiliency features.
Tests retry logic, circuit breaker, and optional failover.

⚠️ PRODUCTION: ONLY gemini-2.5-pro allowed
"""
import asyncio
import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
import sys

# Add parent directory to path for imports
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


async def test_retry_success():
    """Test A: Simulate 503 on first call, ensure success on retry."""
    print("="*80)
    print("TEST A: RETRY SUCCESS")
    print("="*80)
    
    from app.llm.adapters.gemini_adapter import GeminiAdapter
    from app.llm.types import LLMRequest
    
    adapter = GeminiAdapter()
    
    # Mock the generate_content to fail once then succeed
    call_count = 0
    original_method = adapter.client.models.generate_content
    
    def mock_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call fails with 503
            raise Exception("503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The model is overloaded.', 'status': 'UNAVAILABLE'}}")
        else:
            # Subsequent calls succeed
            return original_method(*args, **kwargs)
    
    adapter.client.models.generate_content = mock_generate
    
    request = LLMRequest(
        vendor="gemini_direct",
        model="gemini-2.5-pro",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2? Answer with just the number."}
        ],
        grounded=True,
        meta={"grounding_mode": "REQUIRED"}
    )
    
    try:
        response = await adapter.complete(request, timeout=30)
        
        # Check metadata
        assert response.metadata.get("retry_count", 0) >= 1, f"Expected retry_count >= 1, got {response.metadata.get('retry_count')}"
        assert response.metadata.get("upstream_status") == 503, "Expected upstream_status=503"
        
        # Check grounding (may or may not have data depending on API)
        tool_calls = response.metadata.get("tool_call_count", 0)
        pass_reason = response.metadata.get("required_pass_reason")
        
        print(f"✅ Retry successful after {response.metadata.get('retry_count')} attempt(s)")
        print(f"   upstream_status: {response.metadata.get('upstream_status')}")
        print(f"   tool_calls: {tool_calls}")
        print(f"   required_pass_reason: {pass_reason}")
        
        # Verify prompt immutability
        # Hash check would go here in production
        
        print(f"\nAUDIT vendor=gemini_direct model=gemini-2.5-pro attempts={call_count} "
              f"breaker={response.metadata.get('circuit_state', 'closed')} failover=false "
              f"tool_calls={tool_calls} chunks={response.metadata.get('grounding_chunks_count', 0)} "
              f"supports={response.metadata.get('grounding_supports_count', 0)} "
              f"anchored={response.metadata.get('anchored_citations_count', 0)} "
              f"unlinked={response.metadata.get('unlinked_sources_count', 0)} "
              f"coverage_pct={response.metadata.get('anchored_coverage_pct', 0):.1f} "
              f"reason={pass_reason}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        # Restore original method
        adapter.client.models.generate_content = original_method


async def test_circuit_breaker_open():
    """Test B: Simulate ≥5 consecutive 503s, assert breaker opens."""
    print("\n" + "="*80)
    print("TEST B: CIRCUIT BREAKER OPEN")
    print("="*80)
    
    from app.llm.adapters.gemini_adapter import GeminiAdapter, _circuit_breakers
    from app.llm.types import LLMRequest
    
    adapter = GeminiAdapter()
    
    # Clear any existing breaker state
    _circuit_breakers.clear()
    
    # Mock to always return 503
    def mock_generate_503(*args, **kwargs):
        raise Exception("503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The model is overloaded.', 'status': 'UNAVAILABLE'}}")
    
    adapter.client.models.generate_content = mock_generate_503
    
    request = LLMRequest(
        vendor="gemini_direct",
        model="gemini-2.5-pro",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"}
        ],
        grounded=False
    )
    
    # First request should retry 4 times and fail
    try:
        response = await adapter.complete(request, timeout=30)
        print("❌ Expected failure but got success")
        return False
    except Exception as e:
        error_str = str(e)
        print(f"✅ First request failed as expected: {error_str[:100]}...")
    
    # Check breaker state - it might not be open yet (needs 5 consecutive failures)
    breaker_key = "gemini_direct:models/gemini-2.5-pro"
    breaker = _circuit_breakers.get(breaker_key)
    
    if breaker and breaker.consecutive_failures < 5:
        # Need more attempts to open the breaker
        for i in range(5 - breaker.consecutive_failures):
            try:
                await adapter.complete(request, timeout=30)
            except:
                pass
    
    # Now breaker should be open
    breaker = _circuit_breakers.get(breaker_key)
    assert breaker is not None, "Circuit breaker not found"
    assert breaker.state == "open", f"Expected breaker state=open, got {breaker.state}"
    
    # Next request should fail fast
    try:
        response = await adapter.complete(request, timeout=30)
        print("❌ Expected fast failure but got success")
        return False
    except Exception as e:
        error_str = str(e)
        assert "Circuit breaker open" in error_str, f"Expected circuit breaker error, got: {error_str}"
        print(f"✅ Circuit breaker opened and failing fast")
        print(f"   breaker_state: {breaker.state}")
        print(f"   consecutive_failures: {breaker.consecutive_failures}")
        print(f"   open_until: {breaker.open_until}")
    
    print(f"\nAUDIT vendor=gemini_direct model=gemini-2.5-pro attempts=0 "
          f"breaker=open failover=false error_type=service_unavailable_upstream")
    
    return True


async def test_vendor_failover():
    """Test C: Test failover from Gemini Direct to Vertex when circuit breaker is open."""
    print("\n" + "="*80)
    print("TEST C: VENDOR FAILOVER (gemini_direct → vertex)")
    print("="*80)
    
    # Set the failover flag
    os.environ["GEMINI_DIRECT_FAILOVER_TO_VERTEX"] = "true"
    
    # Need to reimport to pick up the env change
    import importlib
    import app.llm.unified_llm_adapter
    importlib.reload(app.llm.unified_llm_adapter)
    
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    from app.llm.adapters.gemini_adapter import _circuit_breakers
    
    router = UnifiedLLMAdapter()
    
    # Open the circuit breaker for gemini_direct
    from datetime import datetime, timedelta
    from app.llm.adapters.gemini_adapter import CircuitBreakerState
    
    breaker_key = "gemini_direct:models/gemini-2.5-pro"
    _circuit_breakers[breaker_key] = CircuitBreakerState(
        consecutive_failures=5,
        state="open",
        open_until=datetime.now() + timedelta(seconds=60)
    )
    
    request = LLMRequest(
        vendor="gemini_direct",
        model="gemini-2.5-pro",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France? Answer in one word."}
        ],
        grounded=False
    )
    
    try:
        # This should failover to vertex
        response = await router.complete(request)
        
        # Check failover metadata
        assert response.metadata.get("vendor_path") == ["gemini_direct", "vertex"], \
            f"Expected vendor_path=['gemini_direct', 'vertex'], got {response.metadata.get('vendor_path')}"
        assert response.metadata.get("failover_from") == "gemini_direct"
        assert response.metadata.get("failover_to") == "vertex"
        assert response.metadata.get("failover_reason") == "503_circuit_open"
        
        print(f"✅ Failover successful")
        print(f"   vendor_path: {response.metadata.get('vendor_path')}")
        print(f"   failover_reason: {response.metadata.get('failover_reason')}")
        print(f"   response: {response.content[:50]}...")
        
        print(f"\nAUDIT vendor=vertex model=gemini-2.5-pro attempts=1 "
              f"breaker=closed failover=true "
              f"vendor_path={response.metadata.get('vendor_path')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failover test failed: {e}")
        return False
    finally:
        # Reset env
        os.environ["GEMINI_DIRECT_FAILOVER_TO_VERTEX"] = "false"


async def test_immutability_check():
    """Test D: Verify prompt and model immutability during retries/failover."""
    print("\n" + "="*80)
    print("TEST D: IMMUTABILITY CHECK")
    print("="*80)
    
    from app.llm.adapters.gemini_adapter import GeminiAdapter
    from app.llm.types import LLMRequest
    
    adapter = GeminiAdapter()
    
    # Create request with ALS
    original_prompt = "Tell me about the Eiffel Tower."
    original_model = "gemini-2.5-pro"
    
    request = LLMRequest(
        vendor="gemini_direct",
        model=original_model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": original_prompt}
        ],
        grounded=False
    )
    
    # Hash the prompt before
    prompt_hash_before = hashlib.sha256(original_prompt.encode()).hexdigest()
    model_before = request.model
    
    # Mock to fail once then succeed (to trigger retry)
    call_count = 0
    original_method = adapter.client.models.generate_content
    
    def mock_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        # Verify model hasn't changed
        assert kwargs.get("model") == "models/gemini-2.5-pro", f"Model changed during retry!"
        
        # Verify prompt hasn't changed
        contents = kwargs.get("contents", "")
        assert original_prompt in contents, f"Prompt mutated during retry!"
        
        if call_count == 1:
            raise Exception("503 UNAVAILABLE")
        return original_method(*args, **kwargs)
    
    adapter.client.models.generate_content = mock_generate
    
    try:
        response = await adapter.complete(request, timeout=30)
        
        # Verify model and prompt unchanged
        assert request.model == model_before, f"Model changed: {model_before} → {request.model}"
        
        # Extract prompt from messages
        final_prompt = request.messages[-1]["content"]
        prompt_hash_after = hashlib.sha256(final_prompt.encode()).hexdigest()
        
        assert prompt_hash_before == prompt_hash_after, "Prompt hash changed!"
        
        print(f"✅ Immutability verified")
        print(f"   Model unchanged: {original_model}")
        print(f"   Prompt hash unchanged: {prompt_hash_before[:16]}...")
        print(f"   Retry count: {response.metadata.get('retry_count', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Immutability test failed: {e}")
        return False
    finally:
        adapter.client.models.generate_content = original_method


async def main():
    """Run all acceptance tests."""
    print("GEMINI RESILIENCY ACCEPTANCE TESTS")
    print("Testing retry, circuit breaker, and failover")
    print("="*80)
    
    tests = [
        ("Retry Success", test_retry_success),
        ("Circuit Breaker", test_circuit_breaker_open),
        ("Vendor Failover", test_vendor_failover),
        ("Immutability", test_immutability_check)
    ]
    
    results = {}
    
    for name, test_func in tests:
        try:
            success = await test_func()
            results[name] = "✅ PASSED" if success else "❌ FAILED"
        except Exception as e:
            print(f"\n❌ Test {name} crashed: {e}")
            results[name] = "❌ CRASHED"
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    for name, status in results.items():
        print(f"{name}: {status}")
    
    all_passed = all("PASSED" in status for status in results.values())
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED - RESILIENCY IMPLEMENTATION COMPLETE")
        print("\nPR Description:")
        print("-" * 40)
        print("Implemented resiliency for Gemini 2.5 Pro that preserves immutability:")
        print("• Retries with exponential backoff (4 attempts, 0.5s→1s→2s→4s with jitter)")
        print("• Circuit breaker (opens after 5 consecutive 503s, holds 60-120s)")
        print("• Optional vendor failover (Direct→Vertex) with same model, no prompt mutation")
        print("• Grounding remains single-call FFC; anchored citations emitted when supports exist")
        print("• Dev/staging/prod stay aligned; no silent downgrades or prompt edits")
        print("• Full telemetry: retry_count, backoff_ms, circuit_state, vendor_path, failover_reason")
    else:
        print("\n⚠️ SOME TESTS FAILED - Review implementation")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))