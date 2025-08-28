#!/usr/bin/env python3
"""
HARD TEST SUITE for AI Ranker V2 Stability Fixes
Tests all edge cases, failure modes, and stress scenarios
"""
import os
import sys
import asyncio
import json
import time
import random
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Load test environment
def setup_test_env():
    """Setup aggressive test environment"""
    # Override with aggressive settings for testing
    os.environ["OPENAI_TPM_LIMIT"] = "24000"  # Lower limit for testing
    os.environ["OPENAI_MAX_OUTPUT_TOKENS_CAP"] = "2000"
    os.environ["OPENAI_DEFAULT_MAX_OUTPUT_TOKENS"] = "1400"
    os.environ["OPENAI_MAX_CONCURRENCY"] = "1"  # Force sequential
    os.environ["LLM_TIMEOUT_UN"] = "90"
    os.environ["LLM_TIMEOUT_GR"] = "240"
    
    # Load .env.test if exists
    env_file = Path(__file__).parent / ".env.test"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key not in os.environ:  # Don't override our test settings
                        os.environ[key] = value


class HardTester:
    """Aggressive test runner"""
    
    def __init__(self):
        self.results = []
        self.start_time = time.time()
        
    async def test_adaptive_multiplier_learning(self):
        """Test that adaptive multiplier learns from actual usage"""
        print("\n" + "="*60)
        print("TEST: Adaptive Multiplier Learning")
        print("="*60)
        
        from app.llm.adapters.openai_adapter import _RL
        from app.llm.unified_llm_adapter import UnifiedLLMAdapter
        from app.llm.types import LLMRequest
        
        adapter = UnifiedLLMAdapter()
        
        # Get initial multiplier
        initial_multiplier = _RL.get_grounded_multiplier()
        print(f"Initial multiplier: {initial_multiplier:.2f}")
        
        # Run several grounded requests to train the multiplier
        test_prompts = [
            "Search for the latest news about AI and summarize in 50 words",
            "What are the current stock prices for AAPL, GOOGL, and MSFT?",
            "Find information about quantum computing breakthroughs in 2024",
        ]
        
        for i, prompt in enumerate(test_prompts):
            print(f"\n[{i+1}/{len(test_prompts)}] Testing with grounded request...")
            
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                grounded=True,
                max_tokens=1000,
                vantage_policy="ALS_ONLY",
                template_id="test-adaptive",
                run_id=f"adaptive-{i}-{int(time.time())}"
            )
            
            try:
                response = await adapter.complete(request)
                usage = response.usage or {}
                total_tokens = usage.get("total_tokens", 0)
                
                # Check new multiplier
                new_multiplier = _RL.get_grounded_multiplier()
                print(f"  Response tokens: {total_tokens}")
                print(f"  Updated multiplier: {new_multiplier:.2f}")
                
                # Give rate limiter time to update
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"  Error: {e}")
        
        final_multiplier = _RL.get_grounded_multiplier()
        print(f"\n✓ Multiplier adapted from {initial_multiplier:.2f} to {final_multiplier:.2f}")
        
        return {
            "test": "adaptive_multiplier",
            "success": final_multiplier != initial_multiplier,
            "initial": initial_multiplier,
            "final": final_multiplier
        }
    
    async def test_circuit_breaker_triggers(self):
        """Test circuit breaker with simulated proxy failures"""
        print("\n" + "="*60)
        print("TEST: Circuit Breaker Triggering")
        print("="*60)
        
        from app.llm.adapters.proxy_circuit_breaker import get_circuit_breaker
        
        breaker = get_circuit_breaker()
        
        # Simulate proxy failures for OpenAI
        print("\nSimulating 3 proxy failures for OpenAI...")
        for i in range(3):
            breaker.record_failure("openai", "Connection error: proxy tunnel failed")
            print(f"  Failure {i+1} recorded")
        
        # Check if circuit opened
        should_proxy, policy = breaker.should_use_proxy("openai", "PROXY_ONLY")
        print(f"\nCircuit state after 3 failures:")
        print(f"  Should proxy: {should_proxy}")
        print(f"  Adjusted policy: {policy}")
        
        assert policy == "ALS_ONLY", "Circuit should have opened and downgraded to ALS_ONLY"
        
        # Test Vertex always downgrades
        print("\nTesting Vertex proxy policy...")
        should_proxy_vertex, policy_vertex = breaker.should_use_proxy("vertex", "PROXY_ONLY")
        print(f"  Vertex PROXY_ONLY → {policy_vertex}")
        
        assert policy_vertex == "ALS_ONLY", "Vertex should always downgrade proxy policies"
        
        return {
            "test": "circuit_breaker",
            "success": True,
            "openai_triggered": policy == "ALS_ONLY",
            "vertex_bypassed": policy_vertex == "ALS_ONLY"
        }
    
    async def test_rate_limit_with_burst(self):
        """Test rate limiting with burst of requests"""
        print("\n" + "="*60)
        print("TEST: Rate Limiting with Burst")
        print("="*60)
        
        from app.llm.unified_llm_adapter import UnifiedLLMAdapter
        from app.llm.types import LLMRequest
        
        adapter = UnifiedLLMAdapter()
        
        # Create burst of small requests
        burst_size = 5
        print(f"\nSending burst of {burst_size} requests...")
        
        tasks = []
        for i in range(burst_size):
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[
                    {"role": "user", "content": f"Count to {i+1}"}
                ],
                grounded=False,
                max_tokens=50,  # Very small to avoid hitting TPM
                vantage_policy="ALS_ONLY",
                template_id="test-burst",
                run_id=f"burst-{i}-{int(time.time())}"
            )
            
            # Launch concurrently to test rate limiting
            tasks.append(self._timed_request(adapter, request, f"Burst-{i}"))
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        successes = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        errors = [r for r in results if isinstance(r, Exception) or (isinstance(r, dict) and not r.get("success"))]
        
        print(f"\nBurst results:")
        print(f"  Successful: {successes}/{burst_size}")
        print(f"  Errors: {len(errors)}")
        
        for err in errors:
            if isinstance(err, Exception):
                print(f"    - {type(err).__name__}: {str(err)[:100]}")
            elif isinstance(err, dict):
                print(f"    - Failed: {err.get('error', 'Unknown')[:100]}")
        
        return {
            "test": "rate_limit_burst",
            "success": successes > 0,  # At least some should succeed
            "completed": successes,
            "total": burst_size,
            "errors": len(errors)
        }
    
    async def test_grounding_token_explosion(self):
        """Test grounding with prompts that could explode token usage"""
        print("\n" + "="*60)
        print("TEST: Grounding Token Explosion Prevention")
        print("="*60)
        
        from app.llm.unified_llm_adapter import UnifiedLLMAdapter
        from app.llm.types import LLMRequest
        
        adapter = UnifiedLLMAdapter()
        
        # Prompt that could trigger many searches
        evil_prompt = (
            "Search for information about the following topics and provide detailed summaries: "
            "1. Latest AI developments, 2. Quantum computing, 3. Climate change, "
            "4. Space exploration, 5. Medical breakthroughs, 6. Economic trends, "
            "7. Political updates, 8. Technology news, 9. Scientific discoveries, "
            "10. Future predictions. Be very thorough."
        )
        
        print("\nSending prompt designed to trigger many searches...")
        print(f"Prompt length: {len(evil_prompt)} chars")
        
        request = LLMRequest(
            vendor="openai", 
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": evil_prompt}
            ],
            grounded=True,
            max_tokens=2000,  # Will be capped by settings
            vantage_policy="ALS_ONLY",
            template_id="test-explosion",
            run_id=f"explosion-{int(time.time())}"
        )
        
        start = time.time()
        try:
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            usage = response.usage or {}
            total_tokens = usage.get("total_tokens", 0)
            
            print(f"\n✓ Completed in {elapsed:.1f}s")
            print(f"  Total tokens: {total_tokens:,}")
            print(f"  Grounded effective: {response.grounded_effective}")
            
            # Check if token usage was controlled
            assert total_tokens < 10000, f"Token explosion! Used {total_tokens} tokens"
            
            return {
                "test": "grounding_explosion",
                "success": True,
                "tokens_used": total_tokens,
                "elapsed_seconds": elapsed
            }
            
        except Exception as e:
            elapsed = time.time() - start
            print(f"\n✗ Failed after {elapsed:.1f}s: {e}")
            return {
                "test": "grounding_explosion", 
                "success": False,
                "error": str(e),
                "elapsed_seconds": elapsed
            }
    
    async def test_window_edge_jitter(self):
        """Test that jitter prevents thundering herd at window edges"""
        print("\n" + "="*60)
        print("TEST: Window Edge Jitter")
        print("="*60)
        
        from app.llm.adapters.openai_adapter import _RL
        
        # Monitor sleep times when hitting TPM limit
        print("\nForcing TPM limit to test jitter...")
        
        # Temporarily set very low limit
        original_limit = _RL._tpm_limit
        _RL._tpm_limit = 100  # Very low to force sleeping
        
        sleep_times = []
        
        # Override asyncio.sleep to capture sleep times
        original_sleep = asyncio.sleep
        async def monitored_sleep(duration):
            if duration > 1:  # Only capture window-edge sleeps
                sleep_times.append(duration)
                print(f"  Window-edge sleep: {duration:.3f}s")
            await original_sleep(min(duration, 0.1))  # Speed up test
        
        asyncio.sleep = monitored_sleep
        
        try:
            # Trigger multiple window-edge waits
            for i in range(3):
                await _RL.await_tpm(150)  # Over limit, forces sleep
                await asyncio.sleep(0.01)  # Small delay
        finally:
            # Restore
            asyncio.sleep = original_sleep
            _RL._tpm_limit = original_limit
        
        # Check for jitter variation
        if len(sleep_times) >= 2:
            variation = max(sleep_times) - min(sleep_times)
            print(f"\n✓ Sleep time variation: {variation:.3f}s")
            print(f"  Min: {min(sleep_times):.3f}s, Max: {max(sleep_times):.3f}s")
        
        return {
            "test": "window_jitter",
            "success": len(sleep_times) > 0,
            "sleep_count": len(sleep_times),
            "variation": max(sleep_times) - min(sleep_times) if len(sleep_times) >= 2 else 0
        }
    
    async def test_proxy_mode_selection(self):
        """Test proxy mode selection based on token size"""
        print("\n" + "="*60)
        print("TEST: Proxy Mode Selection")
        print("="*60)
        
        from app.llm.adapters.openai_adapter import _proxy_connection_mode
        
        # Mock request class
        class MockRequest:
            def __init__(self, max_tokens, meta=None):
                self.max_tokens = max_tokens
                self.meta = meta or {}
        
        # Test default modes
        short_req = MockRequest(max_tokens=500)
        long_req = MockRequest(max_tokens=3000)
        
        short_mode = _proxy_connection_mode(short_req)
        long_mode = _proxy_connection_mode(long_req)
        
        print(f"Short request (500 tokens): {short_mode}")
        print(f"Long request (3000 tokens): {long_mode}")
        
        assert short_mode == "rotating", "Short requests should use rotating"
        assert long_mode == "backbone", "Long requests should use backbone"
        
        # Test override
        override_req = MockRequest(max_tokens=3000, meta={"proxy_connection": "rotating"})
        override_mode = _proxy_connection_mode(override_req)
        print(f"Override (3000 tokens, forced rotating): {override_mode}")
        
        assert override_mode == "rotating", "Meta should override default"
        
        return {
            "test": "proxy_mode",
            "success": True,
            "short_mode": short_mode,
            "long_mode": long_mode
        }
    
    async def test_error_recovery(self):
        """Test error recovery and retry logic"""
        print("\n" + "="*60)
        print("TEST: Error Recovery")
        print("="*60)
        
        from app.llm.unified_llm_adapter import UnifiedLLMAdapter
        from app.llm.types import LLMRequest
        
        adapter = UnifiedLLMAdapter()
        
        # Test with invalid model to trigger error
        print("\nTesting with invalid configuration...")
        
        request = LLMRequest(
            vendor="openai",
            model="invalid-model-xyz",  # Should trigger error
            messages=[
                {"role": "user", "content": "test"}
            ],
            grounded=False,
            max_tokens=10,
            vantage_policy="ALS_ONLY",
            template_id="test-error",
            run_id=f"error-{int(time.time())}"
        )
        
        try:
            response = await adapter.complete(request)
            
            # Check if error was handled gracefully
            if response.error:
                print(f"✓ Error handled gracefully: {response.error[:100]}")
                return {
                    "test": "error_recovery",
                    "success": True,
                    "error_handled": True,
                    "error_message": response.error
                }
            else:
                print("✗ No error returned for invalid model")
                return {
                    "test": "error_recovery",
                    "success": False,
                    "error_handled": False
                }
                
        except Exception as e:
            print(f"✓ Exception caught: {type(e).__name__}: {str(e)[:100]}")
            return {
                "test": "error_recovery",
                "success": True,
                "exception_caught": True,
                "exception": str(e)
            }
    
    async def _timed_request(self, adapter, request, label):
        """Helper to time a request"""
        start = time.time()
        try:
            response = await adapter.complete(request)
            elapsed = time.time() - start
            return {
                "label": label,
                "success": bool(response.content),
                "elapsed": elapsed,
                "tokens": response.usage.get("total_tokens", 0) if response.usage else 0
            }
        except Exception as e:
            elapsed = time.time() - start
            return {
                "label": label,
                "success": False,
                "elapsed": elapsed,
                "error": str(e)
            }
    
    async def run_all_tests(self):
        """Run all hard tests"""
        print("\n" + "="*60)
        print("🔥 HARD TEST SUITE FOR AI RANKER V2")
        print("="*60)
        print("Testing all edge cases and failure modes...\n")
        
        tests = [
            self.test_adaptive_multiplier_learning,
            self.test_circuit_breaker_triggers,
            self.test_window_edge_jitter,
            self.test_proxy_mode_selection,
            self.test_rate_limit_with_burst,
            self.test_grounding_token_explosion,
            self.test_error_recovery,
        ]
        
        for test_func in tests:
            try:
                result = await test_func()
                self.results.append(result)
                await asyncio.sleep(2)  # Pause between tests
            except Exception as e:
                print(f"\n❌ Test {test_func.__name__} crashed: {e}")
                self.results.append({
                    "test": test_func.__name__,
                    "success": False,
                    "crashed": True,
                    "error": str(e)
                })
        
        self.print_summary()
        return self.results
    
    def print_summary(self):
        """Print test summary"""
        elapsed = time.time() - self.start_time
        
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in self.results if r.get("success"))
        failed = len(self.results) - passed
        
        print(f"\n✅ Passed: {passed}/{len(self.results)}")
        print(f"❌ Failed: {failed}/{len(self.results)}")
        print(f"⏱️  Duration: {elapsed:.1f}s")
        
        if failed > 0:
            print("\nFailed tests:")
            for r in self.results:
                if not r.get("success"):
                    print(f"  - {r.get('test', 'unknown')}: {r.get('error', 'failed')[:100]}")
        
        # Save detailed results
        output_file = Path(__file__).parent / f"hard_test_results_{int(time.time())}.json"
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\n📁 Detailed results saved to: {output_file}")
        
        return passed == len(self.results)


async def main():
    """Main entry point"""
    setup_test_env()
    
    tester = HardTester()
    results = await tester.run_all_tests()
    
    # Exit with appropriate code
    all_passed = all(r.get("success") for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(130)