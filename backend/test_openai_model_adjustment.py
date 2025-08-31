#!/usr/bin/env venv/bin/python
"""
Test OpenAI model adjustment and two-pass fallback implementation
"""

import asyncio
import os
import json
from datetime import datetime

# Enable model adjustment
os.environ["MODEL_ADJUST_FOR_GROUNDING"] = "true"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"

# Add backend to path
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

async def test_model_adjustment():
    """Test the model adjustment and grounding improvements"""
    
    adapter = UnifiedLLMAdapter()
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "model_adjust_enabled": os.getenv("MODEL_ADJUST_FOR_GROUNDING"),
        "tests": []
    }
    
    print("\n" + "="*80)
    print("Testing OpenAI Model Adjustment & Two-Pass Fallback")
    print("="*80)
    
    # Test 1: Grounded request with gpt-5-chat-latest (should adjust to gpt-5)
    print("\n[TEST 1] Grounded with gpt-5-chat-latest (AUTO mode)")
    print("-" * 40)
    
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "user", "content": "What's the latest news about AI?"}
        ],
        grounded=True,
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=100
    )
    
    try:
        response1 = await adapter.complete(request1)
        
        test1_result = {
            "test": "grounded_auto_with_adjustment",
            "original_model": request1.model,
            "success": True,
            "metadata": {}
        }
        
        if hasattr(response1, 'metadata') and response1.metadata:
            meta = response1.metadata
            test1_result["metadata"] = {
                "model_adjusted_for_grounding": meta.get("model_adjusted_for_grounding", False),
                "original_model": meta.get("original_model"),
                "grounded_effective": meta.get("grounded_effective", False),
                "tool_call_count": meta.get("tool_call_count", 0),
                "web_search_count": meta.get("web_search_count", 0),
                "response_api": meta.get("response_api"),
                "response_api_tool_type": meta.get("response_api_tool_type"),
                "tool_variant_retry": meta.get("tool_variant_retry", False),
                "why_not_grounded": meta.get("why_not_grounded"),
                "grounding_mode_requested": meta.get("grounding_mode_requested")
            }
            
            print(f"✓ Model Adjusted: {meta.get('model_adjusted_for_grounding', False)}")
            print(f"✓ Original Model: {meta.get('original_model', 'N/A')}")
            print(f"✓ Grounded Effective: {meta.get('grounded_effective', False)}")
            print(f"✓ Tool Calls: {meta.get('tool_call_count', 0)}")
            print(f"✓ Web Searches: {meta.get('web_search_count', 0)}")
            print(f"✓ Tool Type: {meta.get('response_api_tool_type', 'N/A')}")
        
        results["tests"].append(test1_result)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        results["tests"].append({
            "test": "grounded_auto_with_adjustment",
            "success": False,
            "error": str(e)
        })
    
    # Test 2: REQUIRED mode with gpt-5-chat-latest
    print("\n[TEST 2] Grounded with gpt-5-chat-latest (REQUIRED mode)")
    print("-" * 40)
    
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "user", "content": "What's happening in tech?"}
        ],
        grounded=True,
        meta={"grounding_mode": "REQUIRED"},
        als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
        max_tokens=100
    )
    
    try:
        response2 = await adapter.complete(request2)
        
        test2_result = {
            "test": "grounded_required_with_adjustment",
            "success": True,
            "metadata": {}
        }
        
        if hasattr(response2, 'metadata') and response2.metadata:
            meta = response2.metadata
            test2_result["metadata"] = {
                "model_adjusted_for_grounding": meta.get("model_adjusted_for_grounding", False),
                "grounded_effective": meta.get("grounded_effective", False),
                "grounding_mode_requested": meta.get("grounding_mode_requested")
            }
            
            print(f"✓ Model Adjusted: {meta.get('model_adjusted_for_grounding', False)}")
            print(f"✓ Grounded Effective: {meta.get('grounded_effective', False)}")
            print(f"✓ Mode: {meta.get('grounding_mode_requested', 'N/A')}")
        
        results["tests"].append(test2_result)
        
    except Exception as e:
        error_code = getattr(e, 'code', 'UNKNOWN')
        print(f"✗ Expected failure: {error_code}")
        results["tests"].append({
            "test": "grounded_required_with_adjustment",
            "success": False,
            "error": str(e),
            "error_code": error_code
        })
    
    # Test 3: Ungrounded request (should NOT adjust model)
    print("\n[TEST 3] Ungrounded with gpt-5-chat-latest")
    print("-" * 40)
    
    request3 = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "user", "content": "Hello"}
        ],
        grounded=False,
        max_tokens=50
    )
    
    try:
        response3 = await adapter.complete(request3)
        
        test3_result = {
            "test": "ungrounded_no_adjustment",
            "success": True,
            "metadata": {}
        }
        
        if hasattr(response3, 'metadata') and response3.metadata:
            meta = response3.metadata
            test3_result["metadata"] = {
                "model_adjusted_for_grounding": meta.get("model_adjusted_for_grounding", False),
                "original_model": meta.get("original_model")
            }
            
            adjusted = meta.get("model_adjusted_for_grounding", False)
            print(f"✓ Model Adjusted: {adjusted} (should be False)")
            if not adjusted:
                print("✓ Correctly kept original model for ungrounded request")
        
        results["tests"].append(test3_result)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        results["tests"].append({
            "test": "ungrounded_no_adjustment",
            "success": False,
            "error": str(e)
        })
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    for test in results["tests"]:
        status = "✓" if test.get("success") else "✗"
        print(f"\n{status} {test['test']}")
        if test.get("metadata"):
            meta = test["metadata"]
            if meta.get("model_adjusted_for_grounding"):
                print(f"  → Model adjusted: {meta.get('original_model')} → gpt-5")
            if meta.get("grounded_effective"):
                print(f"  → Grounding successful")
            elif meta.get("why_not_grounded"):
                print(f"  → Not grounded: {meta.get('why_not_grounded')}")
    
    # Check if model adjustment is working
    adjustment_tests = [t for t in results["tests"] if "adjustment" in t["test"]]
    adjusted_count = sum(1 for t in adjustment_tests 
                        if t.get("metadata", {}).get("model_adjusted_for_grounding"))
    
    print(f"\n📊 Model Adjustment Stats:")
    print(f"   Tests with grounding: {len(adjustment_tests)}")
    print(f"   Models adjusted: {adjusted_count}")
    
    # Save results
    filename = f"OPENAI_MODEL_ADJUSTMENT_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Results saved to: {filename}\n")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_model_adjustment())