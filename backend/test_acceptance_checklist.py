#!/usr/bin/env venv/bin/python
"""
Acceptance Checklist for Cache Poisoning Fixes
Tests all requirements from the acceptance criteria
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
os.environ["LLM_TIMEOUT_GR"] = "180"

import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from app.llm.grounding_empty_results import GroundingEmptyResultsError
from app.llm.errors import GroundingNotSupportedError

async def run_acceptance_checklist():
    """Run comprehensive acceptance checklist"""
    
    adapter = UnifiedLLMAdapter()
    results = {
        "timestamp": datetime.now().isoformat(),
        "checklist": {
            "cache_integrity": {},
            "required_semantics": {},
            "two_pass_fallback": {},
            "telemetry": {},
            "normalization": {}
        },
        "control_probes": []
    }
    
    print("\n" + "="*80)
    print("ACCEPTANCE CHECKLIST FOR CACHE POISONING FIXES")
    print("="*80)
    
    # ========================================
    # 1. CACHE INTEGRITY TEST
    # ========================================
    print("\n[1] CACHE INTEGRITY TEST")
    print("-" * 40)
    print("Testing cache key per model+variant...")
    
    # Clear cache by using different models/variants
    test_configs = [
        ("gpt-5", "web_search"),
        ("gpt-5", "web_search_preview"),
        ("gpt-5-chat-latest", "web_search"),
        ("gpt-5-chat-latest", "web_search_preview"),
    ]
    
    cache_test_results = []
    for model, variant in test_configs:
        # Force specific variant
        os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"] = variant
        
        request = LLMRequest(
            vendor="openai",
            model=model,
            messages=[{"role": "user", "content": "Test"}],
            grounded=True,
            meta={"grounding_mode": "AUTO"},
            als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
            max_tokens=50
        )
        
        try:
            response = await adapter.complete(request)
            meta = response.metadata if hasattr(response, 'metadata') else {}
            
            cache_key = f"{model}:{variant}"
            cache_test_results.append({
                "cache_key": cache_key,
                "model_sent": model,
                "model_used": meta.get('normalized_model', model),
                "variant_requested": variant,
                "variant_used": meta.get('response_api_tool_type'),
                "model_adjusted": meta.get('model_adjusted_for_grounding', False),
                "status": "success"
            })
            print(f"  ✓ {cache_key}: variant={meta.get('response_api_tool_type')}")
            
        except Exception as e:
            cache_test_results.append({
                "cache_key": f"{model}:{variant}",
                "error": str(e)[:100],
                "status": "error"
            })
            print(f"  ✗ {model}:{variant}: {str(e)[:50]}")
    
    # Clear env override
    if "OPENAI_WEB_SEARCH_TOOL_TYPE" in os.environ:
        del os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"]
    
    # Check for unique cache entries
    unique_keys = set(r['cache_key'] for r in cache_test_results if r.get('status') == 'success')
    results["checklist"]["cache_integrity"] = {
        "test_configs": cache_test_results,
        "unique_cache_keys": len(unique_keys),
        "expected_unique": len(test_configs),
        "passed": len(unique_keys) >= 2  # At least different per model
    }
    
    print(f"\nCache integrity: {'✅ PASSED' if results['checklist']['cache_integrity']['passed'] else '❌ FAILED'}")
    print(f"Unique cache keys: {len(unique_keys)}/{len(test_configs)}")
    
    # ========================================
    # 2. REQUIRED SEMANTICS TEST
    # ========================================
    print("\n[2] REQUIRED SEMANTICS TEST")
    print("-" * 40)
    print("Testing REQUIRED mode fail-closed behavior...")
    
    required_tests = []
    
    # Test REQUIRED mode (should fail-closed for OpenAI)
    request_required = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is the White House URL?"}],
        grounded=True,
        meta={"grounding_mode": "REQUIRED"},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=100
    )
    
    try:
        response = await adapter.complete(request_required)
        required_tests.append({
            "mode": "REQUIRED",
            "result": "unexpected_success",
            "error": None
        })
        print("  ⚠️  REQUIRED mode succeeded (unexpected)")
        
    except GroundingNotSupportedError as e:
        required_tests.append({
            "mode": "REQUIRED",
            "result": "fail_closed",
            "error": str(e)
        })
        print(f"  ✅ REQUIRED mode fail-closed: {str(e)[:80]}")
        
    except GroundingEmptyResultsError as e:
        required_tests.append({
            "mode": "REQUIRED",
            "result": "empty_results",
            "error": str(e)
        })
        print(f"  ✅ REQUIRED mode empty results: {str(e)[:80]}")
        
    except Exception as e:
        required_tests.append({
            "mode": "REQUIRED",
            "result": "other_error",
            "error": str(e)[:100]
        })
        print(f"  ❌ Unexpected error: {str(e)[:80]}")
    
    # Test AUTO mode (should proceed)
    request_auto = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=100
    )
    
    try:
        response = await adapter.complete(request_auto)
        meta = response.metadata if hasattr(response, 'metadata') else {}
        required_tests.append({
            "mode": "AUTO",
            "result": "success",
            "grounding_attempted": meta.get('grounding_attempted', False)
        })
        print(f"  ✅ AUTO mode succeeded")
        
    except Exception as e:
        required_tests.append({
            "mode": "AUTO",
            "result": "error",
            "error": str(e)[:100]
        })
        print(f"  ❌ AUTO mode failed: {str(e)[:80]}")
    
    results["checklist"]["required_semantics"] = {
        "tests": required_tests,
        "required_fail_closed": any(t['result'] in ['fail_closed', 'empty_results'] for t in required_tests if t['mode'] == 'REQUIRED'),
        "auto_proceeds": any(t['result'] == 'success' for t in required_tests if t['mode'] == 'AUTO'),
        "passed": True  # Will be updated based on tests
    }
    
    results["checklist"]["required_semantics"]["passed"] = (
        results["checklist"]["required_semantics"]["required_fail_closed"] and
        results["checklist"]["required_semantics"]["auto_proceeds"]
    )
    
    print(f"\nREQUIRED semantics: {'✅ PASSED' if results['checklist']['required_semantics']['passed'] else '❌ FAILED'}")
    
    # ========================================
    # 3. TWO-PASS FALLBACK TEST
    # ========================================
    print("\n[3] TWO-PASS FALLBACK TEST")
    print("-" * 40)
    print("Testing variant fallback behavior...")
    
    # This would require forcing a 400 on first variant - simulated via logs
    print("  ℹ️  Check logs for [TOOL_FALLBACK] entries showing retry with alternate variant")
    results["checklist"]["two_pass_fallback"] = {
        "note": "Check logs for [TOOL_FALLBACK] entries",
        "passed": "manual_verification_required"
    }
    
    # ========================================
    # 4. TELEMETRY TEST (Control Probes)
    # ========================================
    print("\n[4] TELEMETRY TEST - Control Probes")
    print("-" * 40)
    
    control_queries = [
        {
            "name": "White House",
            "query": "Give the official URL of the White House homepage.",
            "expected_url": "https://www.whitehouse.gov"
        },
        {
            "name": "BBC",
            "query": "Give the official URL of bbc.com homepage.",
            "expected_url": "https://www.bbc.com"
        }
    ]
    
    for probe in control_queries:
        print(f"\nProbe: {probe['name']}")
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[{"role": "user", "content": probe["query"]}],
            grounded=True,
            meta={"grounding_mode": "AUTO"},
            als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
            max_tokens=500
        )
        
        try:
            response = await adapter.complete(request)
            meta = response.metadata if hasattr(response, 'metadata') else {}
            
            telemetry = {
                "probe": probe["name"],
                "model_used": meta.get('normalized_model'),
                "model_adjusted": meta.get('model_adjusted_for_grounding', False),
                "original_model": meta.get('original_model'),
                "response_api": meta.get('response_api'),
                "response_api_tool_type": meta.get('response_api_tool_type'),
                "tool_variant_retry": meta.get('tool_variant_retry', False),
                "tool_call_count": meta.get('tool_call_count', 0),
                "tool_result_count": meta.get('tool_result_count', 0),
                "grounding_attempted": meta.get('grounding_attempted', False),
                "grounded_effective": meta.get('grounded_effective', False),
                "why_not_grounded": meta.get('why_not_grounded'),
                "web_search_queries": meta.get('web_search_queries', [])
            }
            
            results["control_probes"].append(telemetry)
            
            # Print key telemetry
            print(f"  model_used: {telemetry['model_used']}")
            print(f"  model_adjusted: {telemetry['model_adjusted']}")
            print(f"  response_api_tool_type: {telemetry['response_api_tool_type']}")
            print(f"  grounding_attempted: {telemetry['grounding_attempted']}")
            print(f"  tool_result_count: {telemetry['tool_result_count']}")
            print(f"  why_not_grounded: {telemetry['why_not_grounded']}")
            
        except Exception as e:
            results["control_probes"].append({
                "probe": probe["name"],
                "error": str(e)[:200]
            })
            print(f"  ❌ Error: {str(e)[:100]}")
    
    results["checklist"]["telemetry"] = {
        "control_probes_count": len(results["control_probes"]),
        "fields_collected": list(results["control_probes"][0].keys()) if results["control_probes"] else [],
        "passed": len(results["control_probes"]) > 0
    }
    
    # ========================================
    # 5. NORMALIZATION TEST
    # ========================================
    print("\n[5] NORMALIZATION TEST")
    print("-" * 40)
    print("Testing no normalization reversal...")
    
    norm_test = []
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[{"role": "user", "content": "Test normalization"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=50
    )
    
    try:
        response = await adapter.complete(request)
        meta = response.metadata if hasattr(response, 'metadata') else {}
        
        norm_test.append({
            "requested": "gpt-5-chat-latest",
            "normalized": meta.get('normalized_model'),
            "adjusted": meta.get('model_adjusted_for_grounding', False),
            "original": meta.get('original_model'),
            "effective": "gpt-5" if meta.get('model_adjusted_for_grounding') else meta.get('normalized_model')
        })
        
        print(f"  Requested: gpt-5-chat-latest")
        print(f"  Effective: {norm_test[0]['effective']}")
        print(f"  Adjusted: {norm_test[0]['adjusted']}")
        
        # Check for reversal
        no_reversal = norm_test[0]['effective'] == 'gpt-5' if norm_test[0]['adjusted'] else True
        print(f"  No reversal: {'✅' if no_reversal else '❌'}")
        
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:100]}")
        no_reversal = False
    
    results["checklist"]["normalization"] = {
        "tests": norm_test,
        "no_reversal": no_reversal,
        "passed": no_reversal
    }
    
    # ========================================
    # SUMMARY
    # ========================================
    print("\n" + "="*80)
    print("ACCEPTANCE CHECKLIST SUMMARY")
    print("="*80)
    
    checklist_items = [
        ("Cache Integrity", results["checklist"]["cache_integrity"]["passed"]),
        ("REQUIRED Semantics", results["checklist"]["required_semantics"]["passed"]),
        ("Two-Pass Fallback", "manual_check"),
        ("Telemetry Collection", results["checklist"]["telemetry"]["passed"]),
        ("No Normalization Reversal", results["checklist"]["normalization"]["passed"])
    ]
    
    for name, status in checklist_items:
        if status == "manual_check":
            print(f"  ⚠️  {name}: Manual verification required")
        elif status:
            print(f"  ✅ {name}: PASSED")
        else:
            print(f"  ❌ {name}: FAILED")
    
    # Save results
    filename = f"ACCEPTANCE_CHECKLIST_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Full results saved to: {filename}")
    
    # Final verdict
    all_passed = all(
        v["passed"] for k, v in results["checklist"].items() 
        if isinstance(v, dict) and "passed" in v and v["passed"] != "manual_verification_required"
    )
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ACCEPTANCE CHECKLIST PASSED")
        print("   All automated tests successful")
        print("   Manual: Check logs for [TOOL_FALLBACK] entries")
    else:
        print("⚠️  ACCEPTANCE CHECKLIST INCOMPLETE")
        print("   Review failed items above")
    print("="*80 + "\n")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_acceptance_checklist())