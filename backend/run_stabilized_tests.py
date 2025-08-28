#!/usr/bin/env python3
"""
Stabilized Test Runner for AI Ranker V2
Implements ChatGPT's recommendations for stable test execution
"""
import os
import sys
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# Load test environment settings
def load_test_env():
    """Load settings from .env.test"""
    env_file = Path(__file__).parent / ".env.test"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value
    print(f"✓ Loaded test environment from {env_file}")


def categorize_tests(test_matrix: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Categorize tests by priority order:
    1. Ungrounded tests (lowest token usage)
    2. Grounded without proxy
    3. OpenAI proxy tests
    4. Vertex proxy tests (should be skipped)
    """
    categories = {
        "ungrounded": [],
        "grounded_no_proxy": [],
        "openai_proxy": [],
        "vertex_proxy": []
    }
    
    for test in test_matrix:
        vendor = test.get("vendor", "")
        grounded = test.get("grounded", False)
        vantage_policy = str(test.get("vantage_policy", "ALS_ONLY"))
        
        is_proxy = vantage_policy in ("PROXY_ONLY", "ALS_PLUS_PROXY")
        
        if not grounded:
            categories["ungrounded"].append(test)
        elif vendor == "vertex" and is_proxy:
            categories["vertex_proxy"].append(test)
        elif vendor == "openai" and is_proxy:
            categories["openai_proxy"].append(test)
        else:
            categories["grounded_no_proxy"].append(test)
    
    return categories


async def run_single_test(test_config: Dict, test_index: int, total_tests: int) -> Dict:
    """
    Run a single test with proper configuration
    Returns result with token usage and timing
    """
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    print(f"\n[{test_index}/{total_tests}] Running test: {json.dumps(test_config, indent=2)}")
    
    # Override Vertex proxy tests to use ALS_ONLY
    if test_config.get("vendor") == "vertex" and test_config.get("vantage_policy") in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
        print("  ⚠️ Overriding Vertex proxy to ALS_ONLY (circuit breaker policy)")
        test_config["vantage_policy"] = "ALS_ONLY"
    
    # Create request
    request = LLMRequest(
        vendor=test_config.get("vendor", "openai"),
        model=test_config.get("model", "gpt-5"),
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": test_config.get("prompt", "What is 2+2?")}
        ],
        grounded=test_config.get("grounded", False),
        max_tokens=test_config.get("max_tokens", 1400),  # Use reduced default
        vantage_policy=test_config.get("vantage_policy", "ALS_ONLY"),
        template_id=test_config.get("template_id", "test-template"),
        run_id=f"test-{test_index}-{int(time.time())}"
    )
    
    # Run the request
    adapter = UnifiedLLMAdapter()
    start_time = time.time()
    
    try:
        response = await adapter.complete(request)
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        result = {
            "test_index": test_index,
            "config": test_config,
            "success": bool(response.content),
            "error": response.error if hasattr(response, "error") else None,
            "usage": response.usage,
            "latency_ms": elapsed_ms,
            "grounded_effective": response.grounded_effective,
            "timestamp": datetime.now().isoformat()
        }
        
        # Log token usage
        total_tokens = response.usage.get("total_tokens", 0) if response.usage else 0
        print(f"  ✓ Success: {total_tokens} tokens, {elapsed_ms}ms")
        
        # If we used >20k tokens, add extra sleep
        if total_tokens > 20000:
            sleep_time = 30  # Sleep for 30 seconds
            print(f"  ⚠️ High token usage ({total_tokens}), sleeping {sleep_time}s...")
            await asyncio.sleep(sleep_time)
        
        return result
        
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        print(f"  ✗ Failed: {error_msg}")
        
        return {
            "test_index": test_index,
            "config": test_config,
            "success": False,
            "error": error_msg,
            "usage": {},
            "latency_ms": elapsed_ms,
            "grounded_effective": False,
            "timestamp": datetime.now().isoformat()
        }


async def run_test_suite(test_matrix: List[Dict]) -> List[Dict]:
    """
    Run the full test suite with proper ordering and pacing
    """
    print("\n" + "="*60)
    print("AI Ranker V2 - Stabilized Test Suite")
    print("="*60)
    
    # Categorize tests
    categories = categorize_tests(test_matrix)
    
    # Build ordered test list
    ordered_tests = []
    ordered_tests.extend(categories["ungrounded"])
    ordered_tests.extend(categories["grounded_no_proxy"]) 
    ordered_tests.extend(categories["openai_proxy"])
    # Skip vertex proxy tests
    
    print(f"\nTest Distribution:")
    print(f"  - Ungrounded: {len(categories['ungrounded'])}")
    print(f"  - Grounded (no proxy): {len(categories['grounded_no_proxy'])}")
    print(f"  - OpenAI proxy: {len(categories['openai_proxy'])}")
    print(f"  - Vertex proxy: {len(categories['vertex_proxy'])} (SKIPPED)")
    print(f"  - Total to run: {len(ordered_tests)}")
    
    # Run tests sequentially with pacing
    results = []
    for i, test in enumerate(ordered_tests, 1):
        result = await run_single_test(test, i, len(ordered_tests))
        results.append(result)
        
        # Add delay between tests (3 seconds minimum)
        if i < len(ordered_tests):
            await asyncio.sleep(3)
    
    return results


def generate_report(results: List[Dict]) -> None:
    """Generate test report"""
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"\n✓ Successful: {len(successful)}/{len(results)}")
    print(f"✗ Failed: {len(failed)}/{len(results)}")
    
    if failed:
        print("\nFailed Tests:")
        for r in failed:
            config = r["config"]
            print(f"  - Test {r['test_index']}: {config['vendor']}/{config.get('model', 'unknown')}")
            print(f"    Error: {r['error'][:100]}...")
    
    # Token usage statistics
    total_tokens = sum(r.get("usage", {}).get("total_tokens", 0) for r in results)
    avg_tokens = total_tokens // len(results) if results else 0
    
    print(f"\nToken Usage:")
    print(f"  - Total: {total_tokens:,}")
    print(f"  - Average: {avg_tokens:,}")
    
    # Save results to file
    output_file = Path(__file__).parent / f"test_results_{int(time.time())}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ Full results saved to: {output_file}")


def main():
    """Main entry point"""
    # Load test environment
    load_test_env()
    
    # Example test matrix - replace with your actual tests
    test_matrix = [
        # Ungrounded tests (run first)
        {"vendor": "openai", "model": "gpt-5", "grounded": False, "vantage_policy": "ALS_ONLY"},
        {"vendor": "vertex", "model": "gemini-2.0-flash-exp", "grounded": False, "vantage_policy": "ALS_ONLY"},
        
        # Grounded without proxy (run second)
        {"vendor": "openai", "model": "gpt-5", "grounded": True, "vantage_policy": "ALS_ONLY"},
        {"vendor": "vertex", "model": "gemini-2.0-flash-exp", "grounded": True, "vantage_policy": "ALS_ONLY"},
        
        # OpenAI with proxy (run last)
        {"vendor": "openai", "model": "gpt-5", "grounded": True, "vantage_policy": "ALS_PLUS_PROXY"},
        
        # Vertex proxy tests (will be converted to ALS_ONLY)
        {"vendor": "vertex", "model": "gemini-2.0-flash-exp", "grounded": True, "vantage_policy": "PROXY_ONLY"},
    ]
    
    # Run the test suite
    results = asyncio.run(run_test_suite(test_matrix))
    
    # Generate report
    generate_report(results)
    
    # Exit with appropriate code
    failed_count = len([r for r in results if not r["success"]])
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()