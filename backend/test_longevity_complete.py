#!/usr/bin/env python3
"""
Complete longevity test with FULL response capture
"""
import asyncio
import os
import sys
import json
import time
from datetime import datetime
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

# The prompt to test
PROMPT = "List the 10 most trusted longevity supplement brands"

async def run_single_test(adapter, vendor, model, grounded, vantage_policy, country, test_name):
    """Run a single test and capture FULL response"""
    
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.3,
        max_tokens=500,
        grounded=grounded,
        vantage_policy=vantage_policy,
        meta={"country": country} if country else None
    )
    
    result = {
        "test_name": test_name,
        "vendor": vendor,
        "model": model,
        "grounded": grounded,
        "vantage_policy": vantage_policy,
        "country": country or "none",
        "prompt": PROMPT
    }
    
    try:
        start = time.perf_counter()
        response = await adapter.complete(request)
        latency_ms = int((time.perf_counter() - start) * 1000)
        
        result["success"] = True
        result["latency_ms"] = latency_ms
        result["full_response"] = response.content  # FULL response
        result["usage"] = response.usage
        result["metadata"] = response.metadata
        result["grounded_effective"] = response.metadata.get('grounded_effective', False)
        result["web_grounded"] = response.metadata.get('web_grounded', False)
        result["tool_call_count"] = response.metadata.get('tool_call_count', 0)
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["full_response"] = ""
    
    return result

async def main():
    adapter = UnifiedLLMAdapter()
    all_results = []
    
    # Test configurations
    tests = [
        # OpenAI tests
        ("openai", "gpt-5", False, "NONE", None, "Test 1: OpenAI Ungrounded - No ALS"),
        ("openai", "gpt-5", True, "NONE", None, "Test 2: OpenAI Grounded - No ALS"),
        ("openai", "gpt-5", False, "ALS", "US", "Test 3: OpenAI Ungrounded - ALS US"),
        ("openai", "gpt-5", True, "ALS", "US", "Test 4: OpenAI Grounded - ALS US"),
        ("openai", "gpt-5", False, "ALS", "DE", "Test 5: OpenAI Ungrounded - ALS DE"),
        ("openai", "gpt-5", True, "ALS", "DE", "Test 6: OpenAI Grounded - ALS DE"),
        
        # Vertex tests
        ("vertex", "gemini-2.0-flash-exp", False, "NONE", None, "Test 7: Vertex Ungrounded - No ALS"),
        ("vertex", "gemini-2.0-flash-exp", True, "NONE", None, "Test 8: Vertex Grounded - No ALS"),
        ("vertex", "gemini-2.0-flash-exp", False, "ALS", "US", "Test 9: Vertex Ungrounded - ALS US"),
        ("vertex", "gemini-2.0-flash-exp", True, "ALS", "US", "Test 10: Vertex Grounded - ALS US"),
        ("vertex", "gemini-2.0-flash-exp", False, "ALS", "DE", "Test 11: Vertex Ungrounded - ALS DE"),
        ("vertex", "gemini-2.0-flash-exp", True, "ALS", "DE", "Test 12: Vertex Grounded - ALS DE"),
    ]
    
    print(f"Running {len(tests)} tests...")
    for vendor, model, grounded, policy, country, name in tests:
        print(f"\n{name}...")
        result = await run_single_test(adapter, vendor, model, grounded, policy, country, name)
        all_results.append(result)
        
        # Print brief status
        if result["success"]:
            print(f"  ✅ Success in {result['latency_ms']}ms")
            print(f"  Response length: {len(result['full_response'])} chars")
            if result.get('grounded_effective'):
                print(f"  Grounding: ACTIVE")
        else:
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
        
        # Small delay to avoid rate limits
        await asyncio.sleep(1)
    
    # Save results
    filename = f"longevity_complete_{int(time.time())}.json"
    with open(filename, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "prompt": PROMPT,
            "tests": all_results
        }, f, indent=2, default=str)
    
    print(f"\n✅ Results saved to {filename}")
    return all_results

if __name__ == "__main__":
    asyncio.run(main())