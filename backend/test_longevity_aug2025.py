#!/usr/bin/env python3
"""
Comprehensive test of OpenAI models with different configurations.
Tests: US/DE, grounded/ungrounded, with/without ALS
"""

import os
import sys
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env
from dotenv import load_dotenv
load_dotenv('/home/leedr/ai-ranker-v2/backend/.env')

# Configure models
os.environ['ALLOWED_OPENAI_MODELS'] = 'gpt-5-2025-08-07,gpt-4o'

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test prompt
LONGEVITY_PROMPT = "What was the most interesting longevity and healthspan extension news during August 2025?"

# Test configurations
TEST_CONFIGS = [
    # Model, Country, Grounded, ALS
    ("gpt-5-2025-08-07", "US", True, False),
    ("gpt-5-2025-08-07", "US", False, False),
    ("gpt-5-2025-08-07", "DE", True, False),
    ("gpt-5-2025-08-07", "DE", False, False),
    ("gpt-5-2025-08-07", "US", True, True),
    ("gpt-5-2025-08-07", "US", False, True),
    ("gpt-4o", "US", True, False),
    ("gpt-4o", "US", False, False),
    ("gpt-4o", "DE", True, False),
    ("gpt-4o", "DE", False, False),
    ("gpt-4o", "US", True, True),
    ("gpt-4o", "US", False, True),
]

async def test_configuration(
    model: str,
    country: str,
    grounded: bool,
    with_als: bool
) -> Dict[str, Any]:
    """Test a single configuration"""
    
    adapter = UnifiedLLMAdapter()
    
    # Build request
    metadata = {
        "country": country,
        "grounding_mode": "AUTO"
    }
    
    if with_als:
        metadata["als_present"] = True
        metadata["als_country"] = country
        metadata["als_locale"] = f"{country.lower()}_US" if country == "US" else f"{country.lower()}_DE"
        metadata["als_template_id"] = "test-template"
        metadata["als_variant_id"] = "variant-1"
    
    request = LLMRequest(
        messages=[{"role": "user", "content": LONGEVITY_PROMPT}],
        model=model,
        vendor="openai",
        grounded=grounded,
        max_tokens=200,
        meta=metadata
    )
    
    # Add metadata for ALS if needed
    if with_als:
        request.metadata = metadata
    
    result = {
        "model": model,
        "country": country,
        "grounded": grounded,
        "als": with_als,
        "success": False,
        "error": None,
        "metrics": {}
    }
    
    try:
        response = await adapter.complete(request)
        result["success"] = True
        
        # Extract metrics
        meta = response.metadata or {}
        result["metrics"] = {
            "grounded_effective": meta.get("grounded_effective", False),
            "tool_type": meta.get("chosen_web_tool_type"),
            "tool_requested": meta.get("response_api_tool_type") is not None,
            "tool_used": meta.get("grounding_detected", False),
            "anchored_citations": meta.get("anchored_citations_count", 0),
            "unlinked_citations": meta.get("unlinked_citations_count", 0),
            "als_mirrored": meta.get("als_mirrored_by_router", False),
            "temperature_overridden": meta.get("temperature_overridden", False),
            "response_length": len(response.content) if response.content else 0
        }
        
        # Sample response start
        if response.content:
            result["response_sample"] = response.content[:100] + "..."
        
    except Exception as e:
        result["error"] = str(e)[:200]
        
    return result

async def run_all_tests() -> List[Dict[str, Any]]:
    """Run all test configurations"""
    
    print("=" * 60)
    print("COMPREHENSIVE LONGEVITY TEST")
    print("=" * 60)
    print(f"Prompt: {LONGEVITY_PROMPT}")
    print(f"Configurations: {len(TEST_CONFIGS)}")
    print("-" * 60)
    
    results = []
    
    for i, (model, country, grounded, with_als) in enumerate(TEST_CONFIGS, 1):
        config_str = f"{model}/{country}/{'grounded' if grounded else 'ungrounded'}/{'ALS' if with_als else 'no-ALS'}"
        print(f"\n[{i}/{len(TEST_CONFIGS)}] Testing: {config_str}")
        
        result = await test_configuration(model, country, grounded, with_als)
        results.append(result)
        
        # Print immediate result
        if result["success"]:
            metrics = result["metrics"]
            print(f"  ✅ Success")
            if grounded:
                print(f"    Tool: {metrics.get('tool_type', 'none')}")
                print(f"    Tool used: {metrics.get('tool_used', False)}")
                print(f"    Citations: {metrics.get('anchored_citations', 0)} anchored, {metrics.get('unlinked_citations', 0)} unlinked")
            if with_als:
                print(f"    ALS mirrored: {metrics.get('als_mirrored', False)}")
        else:
            print(f"  ❌ Error: {result['error']}")
        
        # Small delay between requests
        await asyncio.sleep(0.5)
    
    return results

def analyze_results(results: List[Dict[str, Any]]):
    """Analyze and summarize test results"""
    
    print("\n" + "=" * 60)
    print("RESULTS ANALYSIS")
    print("=" * 60)
    
    # Success rate
    successful = sum(1 for r in results if r["success"])
    print(f"\nSuccess Rate: {successful}/{len(results)} ({100*successful/len(results):.1f}%)")
    
    # By model
    for model in ["gpt-5-2025-08-07", "gpt-4o"]:
        model_results = [r for r in results if r["model"] == model]
        model_success = sum(1 for r in model_results if r["success"])
        print(f"\n{model}:")
        print(f"  Success: {model_success}/{len(model_results)}")
        
        # Grounding effectiveness
        grounded_results = [r for r in model_results if r["grounded"] and r["success"]]
        if grounded_results:
            tools_used = sum(1 for r in grounded_results if r["metrics"].get("tool_used", False))
            print(f"  Grounding: {tools_used}/{len(grounded_results)} invoked tools")
            
            citations = [r["metrics"].get("anchored_citations", 0) for r in grounded_results]
            if citations:
                print(f"  Citations: avg {sum(citations)/len(citations):.1f} anchored per request")
    
    # Country differences
    for country in ["US", "DE"]:
        country_results = [r for r in results if r["country"] == country and r["success"]]
        if country_results:
            tools_used = sum(1 for r in country_results if r["grounded"] and r["metrics"].get("tool_used", False))
            grounded_count = sum(1 for r in country_results if r["grounded"])
            print(f"\n{country} Region:")
            print(f"  Success: {len(country_results)}/{len([r for r in results if r['country'] == country])}")
            if grounded_count > 0:
                print(f"  Tool usage: {tools_used}/{grounded_count} grounded requests")
    
    # ALS impact
    als_results = [r for r in results if r["als"] and r["success"]]
    if als_results:
        mirrored = sum(1 for r in als_results if r["metrics"].get("als_mirrored", False))
        print(f"\nALS:")
        print(f"  Mirrored by router: {mirrored}/{len(als_results)}")
    
    # Issues found
    print("\n" + "-" * 60)
    print("ISSUES DETECTED:")
    
    issues = []
    
    # Check for grounding failures
    grounding_failures = [r for r in results if r["grounded"] and r["success"] and not r["metrics"].get("tool_used", False)]
    if grounding_failures:
        issues.append(f"Grounding not invoked in {len(grounding_failures)} cases despite being requested")
    
    # Check for errors
    errors = [r for r in results if not r["success"]]
    if errors:
        unique_errors = set(r["error"] for r in errors)
        for error in unique_errors:
            count = sum(1 for r in errors if r["error"] == error)
            issues.append(f"Error ({count}x): {error[:100]}")
    
    if issues:
        for issue in issues:
            print(f"  • {issue}")
    else:
        print("  None - all tests passed successfully!")

async def main():
    print("\n🔬 COMPREHENSIVE MODEL TEST SUITE")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Run tests
    results = await run_all_tests()
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"longevity_test_results_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "prompt": LONGEVITY_PROMPT,
            "results": results
        }, f, indent=2)
    
    print(f"\n📁 Results saved to: {filename}")
    
    # Analyze
    analyze_results(results)
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())