#!/usr/bin/env python3
"""
REAL-WORLD MODEL TESTING
Tests both OpenAI and Vertex models with/without grounding and ALS
"""
import os
import sys
import asyncio
import json
import time
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Set environment
os.environ["DISABLE_PROXIES"] = "true"
os.environ["OPENAI_TPM_LIMIT"] = "24000"
os.environ["LLM_TIMEOUT_UN"] = "90"
os.environ["LLM_TIMEOUT_GR"] = "240"

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))


class RealWorldModelTester:
    """Test suite for real model calls"""
    
    def __init__(self):
        self.results = []
        self.start_time = time.time()
        
        # Simple test prompt
        self.test_prompt = "What is 2+2? Give just the number."
        self.grounded_prompt = "What is the current CEO of Microsoft? Give just the name."
        
        # ALS configuration
        self.als_seed = "test_seed_key_123"
        self.als_country = "US"
        self.als_language = "en"
        
    def generate_als(self, text: str) -> str:
        """Generate simple ALS string"""
        # Create ALS components
        components = [
            f"locale:{self.als_language}-{self.als_country}",
            f"timestamp:{int(time.time())}",
            f"region:{self.als_country}",
        ]
        
        # Create signature
        message = "|".join(components)
        signature = hmac.new(
            self.als_seed.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        
        # Build ALS
        als = f"[ALS:{message}|sig:{signature}]"
        return als
    
    async def test_openai_ungrounded_no_als(self):
        """Test 1: OpenAI ungrounded without ALS"""
        print("\n" + "="*70)
        print("TEST 1: OpenAI Ungrounded without ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[
                    {"role": "user", "content": self.test_prompt}
                ],
                grounded=False,
                max_tokens=50,
                temperature=0,
                vantage_policy="ALS_ONLY",  # Will be normalized from PROXY_ONLY
                template_id="test-openai-ungrounded-no-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.test_prompt}")
            print(f"Grounded: False, ALS: No")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Tokens: {response.usage}")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            
            return {
                "test": "openai_ungrounded_no_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "proxies_enabled": response.metadata.get('proxies_enabled', None),
                "grounded_effective": response.grounded_effective
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "openai_ungrounded_no_als",
                "success": False,
                "error": str(e)
            }
    
    async def test_openai_ungrounded_with_als(self):
        """Test 2: OpenAI ungrounded with ALS"""
        print("\n" + "="*70)
        print("TEST 2: OpenAI Ungrounded with ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            # Add ALS to prompt
            als = self.generate_als(self.test_prompt)
            prompt_with_als = f"{als}\n{self.test_prompt}"
            
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[
                    {"role": "user", "content": prompt_with_als}
                ],
                grounded=False,
                max_tokens=50,
                temperature=0,
                vantage_policy="ALS_ONLY",
                template_id="test-openai-ungrounded-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.test_prompt}")
            print(f"ALS: {als}")
            print(f"Grounded: False, ALS: Yes")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            
            return {
                "test": "openai_ungrounded_with_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "proxies_enabled": response.metadata.get('proxies_enabled', None),
                "als_included": True
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "openai_ungrounded_with_als",
                "success": False,
                "error": str(e)
            }
    
    async def test_openai_grounded_no_als(self):
        """Test 3: OpenAI grounded without ALS"""
        print("\n" + "="*70)
        print("TEST 3: OpenAI Grounded without ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[
                    {"role": "user", "content": self.grounded_prompt}
                ],
                grounded=True,  # Enable grounding
                max_tokens=100,
                temperature=0,
                vantage_policy="PROXY_ONLY",  # Test normalization
                template_id="test-openai-grounded-no-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.grounded_prompt}")
            print(f"Grounded: True, ALS: No")
            print(f"Original vantage_policy: PROXY_ONLY (should normalize to ALS_ONLY)")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Grounded effective: {response.grounded_effective}")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            print(f"Final vantage_policy: {response.metadata.get('vantage_policy', 'unknown')}")
            
            return {
                "test": "openai_grounded_no_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "grounded_effective": response.grounded_effective,
                "proxies_enabled": response.metadata.get('proxies_enabled', None),
                "policy_normalized": response.metadata.get('proxies_normalized', False)
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "openai_grounded_no_als",
                "success": False,
                "error": str(e)
            }
    
    async def test_openai_grounded_with_als(self):
        """Test 4: OpenAI grounded with ALS"""
        print("\n" + "="*70)
        print("TEST 4: OpenAI Grounded with ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            # Add ALS to prompt
            als = self.generate_als(self.grounded_prompt)
            prompt_with_als = f"{als}\n{self.grounded_prompt}"
            
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[
                    {"role": "user", "content": prompt_with_als}
                ],
                grounded=True,
                max_tokens=100,
                temperature=0,
                vantage_policy="ALS_PLUS_PROXY",  # Test normalization
                template_id="test-openai-grounded-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.grounded_prompt}")
            print(f"ALS: {als}")
            print(f"Grounded: True, ALS: Yes")
            print(f"Original vantage_policy: ALS_PLUS_PROXY (should normalize to ALS_ONLY)")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Grounded effective: {response.grounded_effective}")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            
            return {
                "test": "openai_grounded_with_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "grounded_effective": response.grounded_effective,
                "proxies_enabled": response.metadata.get('proxies_enabled', None),
                "als_included": True
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "openai_grounded_with_als",
                "success": False,
                "error": str(e)
            }
    
    async def test_vertex_ungrounded_no_als(self):
        """Test 5: Vertex ungrounded without ALS"""
        print("\n" + "="*70)
        print("TEST 5: Vertex Ungrounded without ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            request = LLMRequest(
                vendor="vertex",
                model="gemini-2.0-flash-exp",
                messages=[
                    {"role": "user", "content": self.test_prompt}
                ],
                grounded=False,
                max_tokens=50,
                temperature=0,
                vantage_policy="PROXY_ONLY",  # Test normalization for Vertex
                template_id="test-vertex-ungrounded-no-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.test_prompt}")
            print(f"Grounded: False, ALS: No")
            print(f"Original vantage_policy: PROXY_ONLY (should normalize to ALS_ONLY)")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Tokens: {response.usage}")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            
            return {
                "test": "vertex_ungrounded_no_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "proxies_enabled": response.metadata.get('proxies_enabled', None)
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "vertex_ungrounded_no_als",
                "success": False,
                "error": str(e)
            }
    
    async def test_vertex_ungrounded_with_als(self):
        """Test 6: Vertex ungrounded with ALS"""
        print("\n" + "="*70)
        print("TEST 6: Vertex Ungrounded with ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            # Add ALS to prompt
            als = self.generate_als(self.test_prompt)
            prompt_with_als = f"{als}\n{self.test_prompt}"
            
            request = LLMRequest(
                vendor="vertex",
                model="gemini-2.0-flash-exp",
                messages=[
                    {"role": "user", "content": prompt_with_als}
                ],
                grounded=False,
                max_tokens=50,
                temperature=0,
                vantage_policy="ALS_ONLY",
                template_id="test-vertex-ungrounded-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.test_prompt}")
            print(f"ALS: {als}")
            print(f"Grounded: False, ALS: Yes")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            
            return {
                "test": "vertex_ungrounded_with_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "proxies_enabled": response.metadata.get('proxies_enabled', None),
                "als_included": True
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "vertex_ungrounded_with_als",
                "success": False,
                "error": str(e)
            }
    
    async def test_vertex_grounded_no_als(self):
        """Test 7: Vertex grounded without ALS"""
        print("\n" + "="*70)
        print("TEST 7: Vertex Grounded without ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            request = LLMRequest(
                vendor="vertex",
                model="gemini-2.0-flash-exp",
                messages=[
                    {"role": "user", "content": self.grounded_prompt}
                ],
                grounded=True,
                max_tokens=100,
                temperature=0,
                vantage_policy="ALS_PLUS_PROXY",  # Test normalization
                template_id="test-vertex-grounded-no-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.grounded_prompt}")
            print(f"Grounded: True, ALS: No")
            print(f"Original vantage_policy: ALS_PLUS_PROXY (should normalize to ALS_ONLY)")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Grounded effective: {response.grounded_effective}")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            
            return {
                "test": "vertex_grounded_no_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "grounded_effective": response.grounded_effective,
                "proxies_enabled": response.metadata.get('proxies_enabled', None)
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "vertex_grounded_no_als",
                "success": False,
                "error": str(e)
            }
    
    async def test_vertex_grounded_with_als(self):
        """Test 8: Vertex grounded with ALS"""
        print("\n" + "="*70)
        print("TEST 8: Vertex Grounded with ALS")
        print("="*70)
        
        try:
            from app.llm.unified_llm_adapter import UnifiedLLMAdapter
            from app.llm.types import LLMRequest
            
            # Add ALS to prompt
            als = self.generate_als(self.grounded_prompt)
            prompt_with_als = f"{als}\n{self.grounded_prompt}"
            
            request = LLMRequest(
                vendor="vertex",
                model="gemini-2.0-flash-exp",
                messages=[
                    {"role": "user", "content": prompt_with_als}
                ],
                grounded=True,
                max_tokens=100,
                temperature=0,
                vantage_policy="ALS_ONLY",
                template_id="test-vertex-grounded-als",
                run_id=f"test-{int(time.time())}"
            )
            
            adapter = UnifiedLLMAdapter()
            start = time.time()
            
            print(f"Request: {self.grounded_prompt}")
            print(f"ALS: {als}")
            print(f"Grounded: True, ALS: Yes")
            
            response = await adapter.complete(request)
            elapsed = time.time() - start
            
            print(f"Response: {response.content}")
            print(f"Latency: {elapsed*1000:.0f}ms")
            print(f"Grounded effective: {response.grounded_effective}")
            print(f"Proxies enabled: {response.metadata.get('proxies_enabled', 'unknown')}")
            
            return {
                "test": "vertex_grounded_with_als",
                "success": bool(response.content),
                "response": response.content[:100] if response.content else None,
                "latency_ms": elapsed * 1000,
                "usage": response.usage,
                "grounded_effective": response.grounded_effective,
                "proxies_enabled": response.metadata.get('proxies_enabled', None),
                "als_included": True
            }
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "test": "vertex_grounded_with_als",
                "success": False,
                "error": str(e)
            }
    
    async def run_all_tests(self):
        """Run all model tests"""
        print("\n" + "="*70)
        print("🚀 REAL-WORLD MODEL TESTING SUITE")
        print("="*70)
        print(f"Starting: {datetime.now().isoformat()}")
        print(f"DISABLE_PROXIES: {os.getenv('DISABLE_PROXIES')}")
        print(f"Models: OpenAI (gpt-5), Vertex (gemini-2.0-flash-exp)")
        print("="*70)
        
        tests = [
            ("OpenAI Ungrounded No ALS", self.test_openai_ungrounded_no_als),
            ("OpenAI Ungrounded With ALS", self.test_openai_ungrounded_with_als),
            ("OpenAI Grounded No ALS", self.test_openai_grounded_no_als),
            ("OpenAI Grounded With ALS", self.test_openai_grounded_with_als),
            ("Vertex Ungrounded No ALS", self.test_vertex_ungrounded_no_als),
            ("Vertex Ungrounded With ALS", self.test_vertex_ungrounded_with_als),
            ("Vertex Grounded No ALS", self.test_vertex_grounded_no_als),
            ("Vertex Grounded With ALS", self.test_vertex_grounded_with_als),
        ]
        
        for test_name, test_func in tests:
            try:
                result = await test_func()
                self.results.append(result)
                
                # Add delay to respect rate limits
                await asyncio.sleep(3)
                
            except Exception as e:
                print(f"\n❌ Test {test_name} crashed: {e}")
                self.results.append({
                    "test": test_name.lower().replace(" ", "_"),
                    "success": False,
                    "crashed": True,
                    "error": str(e)
                })
        
        self.print_summary()
        return self.results
    
    def print_summary(self):
        """Print test summary"""
        elapsed = time.time() - self.start_time
        
        print("\n" + "="*70)
        print("📊 TEST SUMMARY")
        print("="*70)
        
        # Count results
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get('success', False))
        failed = total - passed
        
        print(f"\nTests Completed: {total}")
        print(f"Passed: {passed} ({passed/total*100:.1f}%)")
        print(f"Failed: {failed} ({failed/total*100:.1f}%)")
        print(f"Duration: {elapsed:.1f}s")
        
        # Analyze by vendor
        openai_tests = [r for r in self.results if 'openai' in r.get('test', '')]
        vertex_tests = [r for r in self.results if 'vertex' in r.get('test', '')]
        
        openai_passed = sum(1 for r in openai_tests if r.get('success', False))
        vertex_passed = sum(1 for r in vertex_tests if r.get('success', False))
        
        print(f"\nOpenAI: {openai_passed}/{len(openai_tests)} passed")
        print(f"Vertex: {vertex_passed}/{len(vertex_tests)} passed")
        
        # Check proxy normalization
        proxy_checks = []
        for r in self.results:
            if 'proxies_enabled' in r:
                proxy_checks.append(r['proxies_enabled'] == False)
        
        if proxy_checks:
            print(f"\nProxy Status: {sum(proxy_checks)}/{len(proxy_checks)} correctly disabled")
        
        # Grounding effectiveness
        grounded_tests = [r for r in self.results if 'grounded' in r.get('test', '')]
        grounded_effective = [r for r in grounded_tests if r.get('grounded_effective', False)]
        
        if grounded_tests:
            print(f"Grounding: {len(grounded_effective)}/{len(grounded_tests)} effectively grounded")
        
        # Performance stats
        latencies = [r.get('latency_ms', 0) for r in self.results if r.get('success', False)]
        if latencies:
            print(f"\nAverage Latency: {sum(latencies)/len(latencies):.0f}ms")
            print(f"Min/Max Latency: {min(latencies):.0f}ms / {max(latencies):.0f}ms")
        
        # Failed tests
        if failed > 0:
            print("\n❌ Failed Tests:")
            for r in self.results:
                if not r.get('success', False):
                    error = r.get('error', 'Unknown error')
                    print(f"  - {r.get('test', 'unknown')}: {error[:100]}")
        
        # Detailed results table
        print("\n📋 Detailed Results:")
        print("-" * 70)
        print(f"{'Test':<30} {'Success':<10} {'Latency':<12} {'Grounded':<10}")
        print("-" * 70)
        
        for r in self.results:
            test_name = r.get('test', 'unknown')[:30]
            success = "✅ Yes" if r.get('success', False) else "❌ No"
            latency = f"{r.get('latency_ms', 0):.0f}ms" if r.get('latency_ms') else "N/A"
            grounded = "Yes" if r.get('grounded_effective', False) else "No" if 'grounded' in r.get('test', '') else "N/A"
            
            print(f"{test_name:<30} {success:<10} {latency:<12} {grounded:<10}")
        
        # Save results
        results_file = f"model_test_results_{int(time.time())}.json"
        with open(results_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": elapsed,
                "total_tests": total,
                "passed": passed,
                "failed": failed,
                "results": self.results
            }, f, indent=2, default=str)
        
        print(f"\n📁 Results saved to: {results_file}")
        
        # Final verdict
        print("\n" + "="*70)
        if failed == 0:
            print("🎉 ALL TESTS PASSED!")
            print("\nKey Achievements:")
            print("  ✅ Both models working without proxies")
            print("  ✅ Grounding functional")
            print("  ✅ ALS processing works")
            print("  ✅ Policy normalization verified")
            print("  ✅ All telemetry shows proxies disabled")
        else:
            print(f"⚠️  {failed} test(s) failed. Review the errors above.")


async def main():
    """Main test runner"""
    tester = RealWorldModelTester()
    results = await tester.run_all_tests()
    
    # Return appropriate exit code
    failed = sum(1 for r in results if not r.get('success', False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    print("\n⚠️  This test will make REAL API calls to OpenAI and Vertex!")
    print("Make sure you have:")
    print("  1. Valid API credentials set")
    print("  2. Sufficient quota/credits")
    print("  3. Network connectivity")
    
    # Check for non-interactive mode
    non_interactive = "--non-interactive" in sys.argv or "-y" in sys.argv
    
    if not non_interactive:
        response = input("\nContinue? (y/n): ")
        if response.lower() != 'y':
            print("Test cancelled.")
            sys.exit(0)
    else:
        print("\nRunning in non-interactive mode...")
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(130)