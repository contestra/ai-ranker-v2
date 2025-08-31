#!/usr/bin/env venv/bin/python
"""
Test matrix for empty results scenarios
Tests all 4 quadrants: attempted vs effective
"""

import asyncio
import os
import json
from datetime import datetime

# Setup environment
os.environ["MODEL_ADJUST_FOR_GROUNDING"] = "true"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"

import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from app.llm.grounding_empty_results import GroundingEmptyResultsError

async def run_test_matrix():
    """Run comprehensive test matrix for empty results scenarios"""
    
    adapter = UnifiedLLMAdapter()
    results = {
        "timestamp": datetime.now().isoformat(),
        "matrix": {
            "attempted_effective": [],    # Quadrant 1: Tool invoked, got results
            "attempted_ineffective": [],  # Quadrant 2: Tool invoked, empty results
            "not_attempted_effective": [], # Quadrant 3: No tool, but cited (shouldn't happen)
            "not_attempted_ineffective": [] # Quadrant 4: No tool, no citations
        },
        "tests": []
    }
    
    print("\n" + "="*80)
    print("Empty Results Test Matrix - 2x2 Quadrants")
    print("="*80)
    
    # Test 1: Obvious hit - should get results
    print("\n[TEST 1] Obvious query - White House URL")
    print("-" * 40)
    
    test1 = {
        "name": "obvious_hit",
        "query": "What is the official URL of the White House website?",
        "mode": "AUTO",
        "expected": "attempted_effective"
    }
    
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",  # Will be adjusted to gpt-5
        messages=[
            {"role": "user", "content": test1["query"]}
        ],
        grounded=True,
        meta={"grounding_mode": test1["mode"]},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=500
    )
    
    try:
        response1 = await adapter.complete(request1)
        
        if hasattr(response1, 'metadata') and response1.metadata:
            meta = response1.metadata
            test1["result"] = {
                "grounding_attempted": meta.get("grounding_attempted", False),
                "grounded_effective": meta.get("grounded_effective", False),
                "tool_call_count": meta.get("tool_call_count", 0),
                "tool_result_count": meta.get("tool_result_count", 0),
                "why_not_grounded": meta.get("why_not_grounded")
            }
            
            # Classify into quadrant
            if test1["result"]["grounding_attempted"] and test1["result"]["grounded_effective"]:
                quadrant = "attempted_effective"
            elif test1["result"]["grounding_attempted"] and not test1["result"]["grounded_effective"]:
                quadrant = "attempted_ineffective"
            elif not test1["result"]["grounding_attempted"] and test1["result"]["grounded_effective"]:
                quadrant = "not_attempted_effective"
            else:
                quadrant = "not_attempted_ineffective"
            
            test1["quadrant"] = quadrant
            results["matrix"][quadrant].append(test1["name"])
            
            print(f"✓ Attempted: {test1['result']['grounding_attempted']}")
            print(f"✓ Effective: {test1['result']['grounded_effective']}")
            print(f"✓ Tool calls: {test1['result']['tool_call_count']}")
            print(f"✓ Results: {test1['result']['tool_result_count']}")
            print(f"✓ Quadrant: {quadrant}")
            if test1['result']['why_not_grounded']:
                print(f"✓ Reason: {test1['result']['why_not_grounded']}")
        
        test1["success"] = True
        
    except Exception as e:
        test1["success"] = False
        test1["error"] = str(e)
        print(f"✗ Error: {e}")
    
    results["tests"].append(test1)
    
    # Test 2: Made-to-fail query (nonsense)
    print("\n[TEST 2] Nonsense query - empty results expected")
    print("-" * 40)
    
    test2 = {
        "name": "nonsense_query",
        "query": "What is the florblegab status of zxqwerty9999 on planet Klaxon?",
        "mode": "REQUIRED",
        "expected": "attempted_ineffective"
    }
    
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "user", "content": test2["query"]}
        ],
        grounded=True,
        meta={"grounding_mode": test2["mode"]},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=500
    )
    
    try:
        response2 = await adapter.complete(request2)
        test2["success"] = True
        test2["result"] = extract_grounding_metadata(response2)
        
    except GroundingEmptyResultsError as e:
        test2["success"] = False
        test2["error"] = str(e)
        test2["error_code"] = "GROUNDING_EMPTY_RESULTS"
        print(f"✓ Expected error: {e.code}")
        test2["quadrant"] = "attempted_ineffective"
        results["matrix"]["attempted_ineffective"].append(test2["name"])
        
    except Exception as e:
        test2["success"] = False
        test2["error"] = str(e)
        print(f"✗ Unexpected error: {e}")
    
    results["tests"].append(test2)
    
    # Test 3: Ungrounded request (no tools)
    print("\n[TEST 3] Ungrounded - no tools expected")
    print("-" * 40)
    
    test3 = {
        "name": "ungrounded",
        "query": "What is 2+2?",
        "mode": None,
        "expected": "not_attempted_ineffective"
    }
    
    request3 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "user", "content": test3["query"]}
        ],
        grounded=False,
        max_tokens=50
    )
    
    try:
        response3 = await adapter.complete(request3)
        
        if hasattr(response3, 'metadata') and response3.metadata:
            meta = response3.metadata
            test3["result"] = {
                "grounding_attempted": meta.get("grounding_attempted", False),
                "grounded_effective": meta.get("grounded_effective", False)
            }
            
            if not test3["result"]["grounding_attempted"] and not test3["result"]["grounded_effective"]:
                test3["quadrant"] = "not_attempted_ineffective"
                results["matrix"]["not_attempted_ineffective"].append(test3["name"])
                print(f"✓ Correctly ungrounded")
        
        test3["success"] = True
        
    except Exception as e:
        test3["success"] = False
        test3["error"] = str(e)
        print(f"✗ Error: {e}")
    
    results["tests"].append(test3)
    
    # Test 4: Regional query
    print("\n[TEST 4] Regional query - BBC news")
    print("-" * 40)
    
    test4 = {
        "name": "regional_query",
        "query": "What is the official URL of BBC News?",
        "mode": "AUTO",
        "expected": "attempted"
    }
    
    request4 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "user", "content": test4["query"]}
        ],
        grounded=True,
        meta={"grounding_mode": test4["mode"]},
        als_context=ALSContext(country_code="GB", locale="en-GB", als_block=""),
        max_tokens=500
    )
    
    try:
        response4 = await adapter.complete(request4)
        
        if hasattr(response4, 'metadata') and response4.metadata:
            meta = response4.metadata
            test4["result"] = extract_grounding_metadata(response4)
            
            # Classify
            if test4["result"]["grounding_attempted"]:
                if test4["result"]["grounded_effective"]:
                    test4["quadrant"] = "attempted_effective"
                else:
                    test4["quadrant"] = "attempted_ineffective"
                results["matrix"][test4["quadrant"]].append(test4["name"])
            
            print(f"✓ Attempted: {test4['result']['grounding_attempted']}")
            print(f"✓ Effective: {test4['result']['grounded_effective']}")
        
        test4["success"] = True
        
    except Exception as e:
        test4["success"] = False
        test4["error"] = str(e)
        print(f"✗ Error: {e}")
    
    results["tests"].append(test4)
    
    # Print matrix summary
    print("\n" + "="*80)
    print("2x2 MATRIX SUMMARY")
    print("="*80)
    print("\n              | Effective  | Ineffective")
    print("-" * 45)
    print(f"Attempted     | {len(results['matrix']['attempted_effective']):^10} | {len(results['matrix']['attempted_ineffective']):^11}")
    print(f"Not Attempted | {len(results['matrix']['not_attempted_effective']):^10} | {len(results['matrix']['not_attempted_ineffective']):^11}")
    print()
    
    # Detailed quadrant breakdown
    for quadrant, tests in results["matrix"].items():
        if tests:
            print(f"\n{quadrant.upper()}:")
            for test in tests:
                print(f"  - {test}")
    
    # Analysis
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)
    
    empty_results = [t for t in results["tests"] 
                     if t.get("result", {}).get("why_not_grounded") == "web_search_empty_results" or
                     t.get("error_code") == "GROUNDING_EMPTY_RESULTS"]
    
    if empty_results:
        print(f"\n✅ Empty Results Detection Working")
        print(f"   {len(empty_results)} tests identified as empty results")
        print(f"   This is NOT an entitlement issue")
        print(f"   The tool is invoked but returns no results")
    
    # Save results
    filename = f"EMPTY_RESULTS_MATRIX_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Results saved to: {filename}\n")
    
    return results


def extract_grounding_metadata(response):
    """Extract grounding metadata from response"""
    if hasattr(response, 'metadata') and response.metadata:
        meta = response.metadata
        return {
            "grounding_attempted": meta.get("grounding_attempted", False),
            "grounded_effective": meta.get("grounded_effective", False),
            "tool_call_count": meta.get("tool_call_count", 0),
            "tool_result_count": meta.get("tool_result_count", 0),
            "why_not_grounded": meta.get("why_not_grounded")
        }
    return {
        "grounding_attempted": False,
        "grounded_effective": False,
        "tool_call_count": 0,
        "tool_result_count": 0,
        "why_not_grounded": "no_metadata"
    }


if __name__ == "__main__":
    asyncio.run(run_test_matrix())