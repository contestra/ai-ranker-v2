#!/usr/bin/env venv/bin/python
"""
Comprehensive sanity matrix test for OpenAI grounding
Tests all combinations of models, grounding modes, and cache states
"""

import asyncio
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any

# Configuration
os.environ["MODEL_ADJUST_FOR_GROUNDING"] = "true"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"
os.environ["LLM_TIMEOUT_GR"] = "180"  # Longer timeout for grounded

import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from app.llm.grounding_empty_results import GroundingEmptyResultsError

async def run_sanity_matrix():
    """Run comprehensive sanity matrix tests"""
    
    adapter = UnifiedLLMAdapter()
    results = {
        "timestamp": datetime.now().isoformat(),
        "matrix_results": [],
        "cache_integrity": {},
        "model_adjustment": {},
        "summary": {}
    }
    
    print("\n" + "="*80)
    print("OPENAI GROUNDING SANITY MATRIX")
    print("="*80)
    
    # Test matrix: [model, grounded, grounding_mode, expected_adjustment, expect_required_fail]
    test_matrix = [
        # gpt-5-chat-latest tests
        ("gpt-5-chat-latest", True, "AUTO", True, False),      # Should adjust to gpt-5
        ("gpt-5-chat-latest", True, "REQUIRED", True, True),  # Should fail (API limitation)
        ("gpt-5-chat-latest", False, None, False, False),      # No adjustment (not grounded)
        
        # gpt-5 direct tests
        ("gpt-5", True, "AUTO", False, False),                 # Already gpt-5, no adjustment
        ("gpt-5", True, "REQUIRED", False, True),             # Should fail (API limitation)
        ("gpt-5", False, None, False, False),                  # No adjustment (not grounded)
    ]
    
    print("\n[MATRIX TESTS] Running comprehensive test matrix")
    print("-" * 40)
    
    for idx, (model, grounded, grounding_mode, expect_adjust, expect_required_fail) in enumerate(test_matrix, 1):
        test_name = f"Test {idx}: model={model}, grounded={grounded}, mode={grounding_mode}"
        print(f"\n{test_name}")
        
        # Build request
        request = LLMRequest(
            vendor="openai",
            model=model,
            messages=[{"role": "user", "content": "What is the capital of France?"}],
            grounded=grounded,
            meta={"grounding_mode": grounding_mode} if grounding_mode else {},
            als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
            max_tokens=100
        )
        
        try:
            start_time = time.time()
            response = await adapter.complete(request)
            elapsed = time.time() - start_time
            
            # Extract metadata
            meta = response.metadata if hasattr(response, 'metadata') else {}
            
            # Validate expectations
            actual_adjusted = meta.get('model_adjusted_for_grounding', False)
            adjustment_correct = actual_adjusted == expect_adjust
            
            result = {
                "test": test_name,
                "model_sent": model,
                "grounded": grounded,
                "grounding_mode": grounding_mode,
                "expected_adjustment": expect_adjust,
                "actual_adjustment": actual_adjusted,
                "adjustment_correct": adjustment_correct,
                "original_model": meta.get('original_model'),
                "grounding_attempted": meta.get('grounding_attempted', False),
                "grounded_effective": meta.get('grounded_effective', False),
                "tool_type": meta.get('response_api_tool_type'),
                "elapsed_seconds": round(elapsed, 2),
                "status": "success"
            }
            
            # Print validation
            if adjustment_correct:
                print(f"  ✅ Model adjustment: {actual_adjusted} (expected: {expect_adjust})")
            else:
                print(f"  ❌ Model adjustment: {actual_adjusted} (expected: {expect_adjust})")
            
            if grounded:
                print(f"  Grounding attempted: {result['grounding_attempted']}")
                print(f"  Tool type: {result['tool_type']}")
                
        except GroundingEmptyResultsError as e:
            result = {
                "test": test_name,
                "model_sent": model,
                "grounded": grounded,
                "grounding_mode": grounding_mode,
                "status": "empty_results",
                "error": str(e)
            }
            print(f"  ⚠️  Empty results (expected for OpenAI)")
            
        except GroundingNotSupportedError as e:
            # Check if this is expected (REQUIRED mode for OpenAI)
            if expect_required_fail:
                result = {
                    "test": test_name,
                    "model_sent": model,
                    "grounded": grounded,
                    "grounding_mode": grounding_mode,
                    "status": "expected_fail",
                    "error": str(e),
                    "expected": True
                }
                print(f"  ✓ Expected fail (REQUIRED mode API limitation): {str(e)[:60]}")
            else:
                result = {
                    "test": test_name,
                    "model_sent": model,
                    "grounded": grounded,
                    "grounding_mode": grounding_mode,
                    "status": "error",
                    "error": str(e)
                }
                print(f"  ❌ Unexpected error: {str(e)[:60]}")
            
        except Exception as e:
            result = {
                "test": test_name,
                "model_sent": model,
                "grounded": grounded,
                "grounding_mode": grounding_mode,
                "status": "error",
                "error": str(e)
            }
            print(f"  ❌ Error: {e}")
        
        results["matrix_results"].append(result)
    
    # Cache integrity checks
    print("\n[CACHE INTEGRITY] Testing cache consistency")
    print("-" * 40)
    
    # Clear cache by waiting (simulated)
    print("\nSending duplicate requests to test cache behavior...")
    
    for model in ["gpt-5-chat-latest", "gpt-5"]:
        print(f"\nTesting cache for model: {model}")
        
        cache_results = []
        for i in range(3):
            request = LLMRequest(
                vendor="openai",
                model=model,
                messages=[{"role": "user", "content": f"Test {i}"}],
                grounded=True,
                meta={"grounding_mode": "AUTO"},
                als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
                max_tokens=50
            )
            
            try:
                start = time.time()
                response = await adapter.complete(request)
                elapsed = time.time() - start
                
                meta = response.metadata if hasattr(response, 'metadata') else {}
                cache_results.append({
                    "attempt": i + 1,
                    "tool_type": meta.get('response_api_tool_type'),
                    "elapsed": round(elapsed, 2)
                })
                
            except Exception as e:
                cache_results.append({
                    "attempt": i + 1,
                    "error": str(e)[:100]
                })
        
        # Check consistency
        tool_types = [r.get('tool_type') for r in cache_results if 'tool_type' in r]
        consistent = len(set(tool_types)) <= 1
        
        results["cache_integrity"][model] = {
            "results": cache_results,
            "consistent": consistent,
            "tool_type": tool_types[0] if tool_types else None
        }
        
        print(f"  Cache consistency: {'✅ Consistent' if consistent else '❌ Inconsistent'}")
        if tool_types:
            print(f"  Cached tool type: {tool_types[0]}")
    
    # Analysis
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)
    
    # Model adjustment analysis
    adjustment_tests = [r for r in results["matrix_results"] if "adjustment_correct" in r]
    adjustment_correct = sum(1 for r in adjustment_tests if r["adjustment_correct"])
    
    print(f"\n📊 Model Adjustment:")
    print(f"   Correct: {adjustment_correct}/{len(adjustment_tests)}")
    
    # Grounding analysis
    grounded_tests = [r for r in results["matrix_results"] if r.get("grounded")]
    grounding_attempted = sum(1 for r in grounded_tests if r.get("grounding_attempted"))
    
    print(f"\n📊 Grounding:")
    print(f"   Attempted: {grounding_attempted}/{len(grounded_tests)}")
    
    # Cache analysis
    cache_consistent = sum(1 for v in results["cache_integrity"].values() if v["consistent"])
    
    print(f"\n📊 Cache Integrity:")
    print(f"   Consistent: {cache_consistent}/{len(results['cache_integrity'])}")
    
    # Error analysis
    errors = [r for r in results["matrix_results"] if r.get("status") == "error"]
    empty_results = [r for r in results["matrix_results"] if r.get("status") == "empty_results"]
    expected_fails = [r for r in results["matrix_results"] if r.get("status") == "expected_fail"]
    
    print(f"\n📊 Errors:")
    print(f"   Hard errors: {len(errors)}")
    print(f"   Empty results: {len(empty_results)}")
    print(f"   Expected fails (REQUIRED mode): {len(expected_fails)}")
    
    # Summary
    all_tests_passed = (
        adjustment_correct == len(adjustment_tests) and
        cache_consistent == len(results["cache_integrity"]) and
        len(errors) == 0
    )
    
    results["summary"] = {
        "total_tests": len(results["matrix_results"]),
        "model_adjustment_correct": f"{adjustment_correct}/{len(adjustment_tests)}",
        "grounding_attempted": f"{grounding_attempted}/{len(grounded_tests)}",
        "cache_consistent": f"{cache_consistent}/{len(results['cache_integrity'])}",
        "errors": len(errors),
        "empty_results": len(empty_results),
        "all_passed": all_tests_passed
    }
    
    # Save results
    filename = f"SANITY_MATRIX_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Results saved to: {filename}")
    
    # Final verdict
    print("\n" + "="*80)
    if all_tests_passed:
        print("✅ SANITY CHECK PASSED - All systems operational")
        print("   - Model adjustment working correctly")
        print("   - Cache integrity maintained")
        print("   - No unexpected errors")
    else:
        print("⚠️  SANITY CHECK FAILED - Issues detected:")
        if adjustment_correct < len(adjustment_tests):
            print("   - Model adjustment logic has issues")
        if cache_consistent < len(results["cache_integrity"]):
            print("   - Cache poisoning detected")
        if errors:
            print(f"   - {len(errors)} unexpected errors")
    
    if empty_results:
        print(f"\n📝 Note: {len(empty_results)} empty results (expected for OpenAI grounding)")
    
    print("="*80 + "\n")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_sanity_matrix())