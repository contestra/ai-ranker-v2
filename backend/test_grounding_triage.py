#!/usr/bin/env venv/bin/python
"""
Fast triage checklist for OpenAI grounding empty results
Tests control probes, variant flips, and region variations
"""

import asyncio
import os
import json
from datetime import datetime

# Setup
os.environ["MODEL_ADJUST_FOR_GROUNDING"] = "true"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"

import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from app.llm.grounding_empty_results import GroundingEmptyResultsError

async def run_triage():
    """Run comprehensive triage tests"""
    
    adapter = UnifiedLLMAdapter()
    results = {
        "timestamp": datetime.now().isoformat(),
        "control_probes": [],
        "variant_tests": [],
        "region_tests": [],
        "summary": {}
    }
    
    print("\n" + "="*80)
    print("OpenAI Grounding Triage - Fast Diagnostic")
    print("="*80)
    
    # ==========================
    # CONTROL PROBES
    # ==========================
    print("\n[CONTROL PROBES] Testing obvious queries")
    print("-" * 40)
    
    control_queries = [
        {
            "name": "whitehouse",
            "query": "Give the official URL of the White House homepage.",
            "expected": "https://www.whitehouse.gov"
        },
        {
            "name": "bbc",
            "query": "Give the official URL of bbc.com homepage.",
            "expected": "https://www.bbc.com"
        }
    ]
    
    for probe in control_queries:
        print(f"\nTesting: {probe['name']}")
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[{"role": "user", "content": probe["query"]}],
            grounded=True,
            meta={"grounding_mode": "REQUIRED"},
            als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
            max_tokens=500
        )
        
        try:
            response = await adapter.complete(request)
            probe_result = extract_detailed_metadata(response)
            probe_result["name"] = probe["name"]
            probe_result["query_sent"] = probe["query"]
            probe_result["status"] = "completed"
            
            print(f"  Attempted: {probe_result['grounding_attempted']}")
            print(f"  Results: {probe_result['tool_result_count']}")
            if probe_result['web_search_queries']:
                print(f"  Search queries: {probe_result['web_search_queries']}")
            
        except GroundingEmptyResultsError as e:
            probe_result = {
                "name": probe["name"],
                "query_sent": probe["query"],
                "status": "empty_results",
                "error": str(e)
            }
            print(f"  ❌ Empty results error")
            
        except Exception as e:
            probe_result = {
                "name": probe["name"],
                "query_sent": probe["query"],
                "status": "error",
                "error": str(e)
            }
            print(f"  ❌ Error: {e}")
        
        results["control_probes"].append(probe_result)
    
    # ==========================
    # VARIANT FLIP TEST
    # ==========================
    print("\n[VARIANT FLIP] Testing web_search vs web_search_preview")
    print("-" * 40)
    
    for variant in ["web_search", "web_search_preview"]:
        print(f"\nForcing variant: {variant}")
        os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"] = variant
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[{"role": "user", "content": "Give the official URL of the White House homepage."}],
            grounded=True,
            meta={"grounding_mode": "AUTO"},
            als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
            max_tokens=500
        )
        
        try:
            response = await adapter.complete(request)
            variant_result = extract_detailed_metadata(response)
            variant_result["variant_forced"] = variant
            
            print(f"  Tool type used: {variant_result.get('response_api_tool_type', 'unknown')}")
            print(f"  Results: {variant_result['tool_result_count']}")
            
        except Exception as e:
            variant_result = {
                "variant_forced": variant,
                "error": str(e)
            }
            print(f"  ❌ Error: {e}")
        
        results["variant_tests"].append(variant_result)
    
    # Clear override
    if "OPENAI_WEB_SEARCH_TOOL_TYPE" in os.environ:
        del os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"]
    
    # ==========================
    # REGION/PHRASING TESTS
    # ==========================
    print("\n[REGION TESTS] Testing query phrasing variations")
    print("-" * 40)
    
    phrasings = [
        "White House homepage",
        "Washington D.C. White House homepage",
        "US federal government White House homepage",
        "site:whitehouse.gov",
        "World Health Organization homepage"
    ]
    
    for phrasing in phrasings:
        print(f"\nQuery: '{phrasing}'")
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[{"role": "user", "content": f"Give the official URL for: {phrasing}"}],
            grounded=True,
            meta={"grounding_mode": "AUTO"},
            als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
            max_tokens=500
        )
        
        try:
            response = await adapter.complete(request)
            region_result = extract_detailed_metadata(response)
            region_result["phrasing"] = phrasing
            
            if region_result['web_search_queries']:
                print(f"  Model searched for: '{region_result['web_search_queries'][0]}'")
            print(f"  Results: {region_result['tool_result_count']}")
            
        except Exception as e:
            region_result = {
                "phrasing": phrasing,
                "error": str(e)
            }
            print(f"  ❌ Error: {e}")
        
        results["region_tests"].append(region_result)
    
    # ==========================
    # ANALYSIS
    # ==========================
    print("\n" + "="*80)
    print("TRIAGE ANALYSIS")
    print("="*80)
    
    # Control probe analysis
    control_empty = sum(1 for p in results["control_probes"] 
                       if p.get("status") == "empty_results" or 
                       p.get("tool_result_count", 0) == 0)
    
    if control_empty == len(results["control_probes"]):
        print("\n🔴 ALL control probes returned empty")
        print("   This is NOT a query issue - basic queries fail")
        print("   Likely: Regional restriction or index issue")
    elif control_empty > 0:
        print(f"\n🟡 {control_empty}/{len(results['control_probes'])} control probes empty")
        print("   Partial functionality - investigate specific queries")
    else:
        print("\n🟢 Control probes successful")
        print("   Grounding is working for basic queries")
    
    # Variant analysis
    web_search_works = any(v.get("tool_result_count", 0) > 0 
                           for v in results["variant_tests"] 
                           if v.get("variant_forced") == "web_search")
    preview_works = any(v.get("tool_result_count", 0) > 0 
                        for v in results["variant_tests"] 
                        if v.get("variant_forced") == "web_search_preview")
    
    print(f"\n📊 Variant Analysis:")
    print(f"   web_search: {'✅ Works' if web_search_works else '❌ Empty'}")
    print(f"   web_search_preview: {'✅ Works' if preview_works else '❌ Empty'}")
    
    # Query formation analysis
    unique_queries = set()
    for test in results["control_probes"] + results["region_tests"]:
        if isinstance(test.get("web_search_queries"), list):
            unique_queries.update(test["web_search_queries"])
    
    if unique_queries:
        print(f"\n🔍 Model's search queries:")
        for q in list(unique_queries)[:5]:
            print(f"   - '{q}'")
    
    # Summary
    total_attempted = sum(1 for t in results["control_probes"] + results["variant_tests"] + results["region_tests"]
                         if t.get("grounding_attempted"))
    total_effective = sum(1 for t in results["control_probes"] + results["variant_tests"] + results["region_tests"]
                         if t.get("grounded_effective"))
    
    results["summary"] = {
        "total_tests": len(results["control_probes"]) + len(results["variant_tests"]) + len(results["region_tests"]),
        "grounding_attempted": total_attempted,
        "grounding_effective": total_effective,
        "empty_results_rate": f"{(total_attempted - total_effective) / max(total_attempted, 1) * 100:.1f}%",
        "web_search_works": web_search_works,
        "preview_works": preview_works
    }
    
    print(f"\n📈 Overall Stats:")
    print(f"   Attempted: {total_attempted}")
    print(f"   Effective: {total_effective}")
    print(f"   Empty rate: {results['summary']['empty_results_rate']}")
    
    # Save results
    filename = f"GROUNDING_TRIAGE_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Full results saved to: {filename}\n")
    
    # Recommendations
    print("📋 RECOMMENDATIONS:")
    if control_empty == len(results["control_probes"]):
        print("   1. Open support ticket with OpenAI")
        print("   2. Reference: web_search returns empty for all queries")
        print("   3. Provide this diagnostic data as evidence")
    elif unique_queries:
        print("   1. Model is forming queries correctly")
        print("   2. Issue is with search index/service")
        print("   3. Consider retry-on-empty strategy")
    
    return results


def extract_detailed_metadata(response):
    """Extract detailed grounding metadata"""
    if hasattr(response, 'metadata') and response.metadata:
        meta = response.metadata
        return {
            "grounding_attempted": meta.get("grounding_attempted", False),
            "grounded_effective": meta.get("grounded_effective", False),
            "tool_call_count": meta.get("tool_call_count", 0),
            "tool_result_count": meta.get("tool_result_count", 0),
            "web_search_count": meta.get("web_search_count", 0),
            "web_search_queries": meta.get("web_search_queries", []),
            "why_not_grounded": meta.get("why_not_grounded"),
            "response_api_tool_type": meta.get("response_api_tool_type")
        }
    return {
        "grounding_attempted": False,
        "grounded_effective": False,
        "tool_call_count": 0,
        "tool_result_count": 0,
        "web_search_count": 0,
        "web_search_queries": [],
        "why_not_grounded": "no_metadata"
    }


if __name__ == "__main__":
    asyncio.run(run_triage())