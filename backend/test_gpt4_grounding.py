#!/usr/bin/env python3
"""
GPT-4 Grounding Test - Check if grounding works with GPT-4 models
Testing to see if the issue is specific to GPT-5 or affects all OpenAI models
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List

# Add backend to path FIRST
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env file BEFORE setting other environment variables
from dotenv import load_dotenv
load_dotenv('/home/leedr/ai-ranker-v2/backend/.env')

# Set environment variables AFTER loading .env
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATIONS_EXTRACTOR_ENABLE'] = 'true'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'true'  # For full visibility
os.environ['DEBUG_GROUNDING'] = 'true'
os.environ['ALLOW_HTTP_RESOLVE'] = 'false'
# Allow GPT-4 models for testing
os.environ['ALLOWED_OPENAI_MODELS'] = 'gpt-4,gpt-4-turbo,gpt-4-turbo-2024-04-09,gpt-4o,gpt-4o-mini,gpt-5,gpt-5-chat-latest'

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test prompt with explicit request for sources
TEST_PROMPT = """What are the latest developments in AI regulation and policy in 2024?

As of today (2025-09-02), include official source URLs."""

# Models to test - try various GPT-4 variants
TEST_MODELS = [
    "gpt-4-turbo",
    "gpt-4-turbo-2024-04-09",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-5",  # Include GPT-5 for comparison
]

async def test_model_grounding(adapter: UnifiedLLMAdapter, model: str, grounding_mode: str = "AUTO") -> Dict[str, Any]:
    """Test a specific model with grounding"""
    print(f"\n{'='*70}")
    print(f"Testing: {model}")
    print(f"Grounding Mode: {grounding_mode}")
    print(f"{'='*70}")
    
    request = LLMRequest(
        messages=[{"role": "user", "content": TEST_PROMPT}],
        model=model,
        vendor="openai",
        grounded=True,
        max_tokens=200,
        temperature=0.3,
        meta={
            "grounding_mode": grounding_mode,
            "test_model": model
        }
    )
    
    result = {
        "model": model,
        "grounding_mode": grounding_mode,
        "timestamp": datetime.now().isoformat(),
        "adapter_error_type": None,
        "adapter_error_message": None
    }
    
    try:
        response = await adapter.complete(request)
        
        # Check if adapter returned an error
        if not response.success:
            result["success"] = False
            result["adapter_error_type"] = "adapter_failure"
            result["adapter_error_message"] = response.error
            print(f"❌ Adapter returned error: {response.error}")
            return result
            
        result["success"] = True
        result["content_snippet"] = response.content[:300] if response.content else ""
        
        # Extract metadata/telemetry
        meta = response.metadata if response.metadata else {}
        if meta:
            result["telemetry"] = {
                # Model info
                "model_requested": model,
                "model_effective": meta.get("model"),
                "model_normalized": meta.get("normalized_model"),
                "model_adjusted": meta.get("model_adjusted_for_grounding", False),
                
                # Grounding info
                "response_api": meta.get("response_api"),
                "tool_type_sent": meta.get("response_api_tool_type"),
                "tool_choice": meta.get("tool_choice"),
                "grounding_attempted": request.grounded,
                "grounded_effective": meta.get("grounded_effective", False),
                "grounding_not_supported": meta.get("grounding_not_supported", False),
                
                # Tool metrics
                "tool_call_count": meta.get("tool_call_count", 0),
                "tool_result_count": meta.get("tool_result_count", 0),
                
                # Citation metrics
                "citations_total": len(meta.get("citations", [])),
                "anchored_citations": meta.get("anchored_citations_count", 0),
                "unlinked_sources": meta.get("unlinked_sources_count", 0),
                
                # Status
                "why_not_grounded": meta.get("why_not_grounded") or meta.get("grounding_status_reason"),
                "error_message": meta.get("error_message")
            }
            
            # Check for caching
            result["cached_tool_type"] = meta.get("cached_tool_type")
        else:
            # No metadata, create minimal telemetry
            result["telemetry"] = {
                "model_requested": model,
                "model_effective": None,
                "tool_call_count": 0,
                "grounded_effective": False,
                "citations_total": 0,
                "anchored_citations": 0,
                "why_not_grounded": "no_metadata"
            }
            
        print(f"✅ Success")
        print(f"  Model effective: {result.get('telemetry', {}).get('model_effective', 'Unknown')}")
        print(f"  Tool calls: {result.get('telemetry', {}).get('tool_call_count', 0)}")
        print(f"  Grounded effective: {result.get('telemetry', {}).get('grounded_effective', False)}")
        print(f"  Citations: {result.get('telemetry', {}).get('citations_total', 0)}")
        why_not = result.get('telemetry', {}).get('why_not_grounded')
        if why_not:
            print(f"  Reason: {why_not}")
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        result["adapter_error_type"] = "exception"
        result["adapter_error_message"] = str(e)
        
        # Check if it's an expected error
        if "GROUNDING_NOT_SUPPORTED" in str(e):
            result["grounding_not_supported"] = True
            print(f"⚠️ Grounding not supported: {model}")
        elif "Model not allowed" in str(e):
            result["model_not_allowed"] = True
            print(f"❌ Model not allowed: {model}")
        else:
            print(f"❌ Error: {e}")
        
        print(f"  Error type: {result['error_type']}")
    
    return result

async def test_all_models() -> List[Dict[str, Any]]:
    """Test all models"""
    adapter = UnifiedLLMAdapter()
    results = []
    
    # Test AUTO mode for all models
    print("\n" + "="*70)
    print("TESTING AUTO MODE")
    print("="*70)
    
    for model in TEST_MODELS:
        result = await test_model_grounding(adapter, model, "AUTO")
        results.append(result)
        await asyncio.sleep(2)  # Rate limiting
    
    # Test REQUIRED mode for models that passed AUTO
    print("\n" + "="*70)
    print("TESTING REQUIRED MODE (for models that support grounding)")
    print("="*70)
    
    for model in TEST_MODELS[:3]:  # Test first 3 with REQUIRED
        result = await test_model_grounding(adapter, model, "REQUIRED")
        results.append(result)
        await asyncio.sleep(2)
    
    return results

def analyze_results(results: List[Dict[str, Any]]):
    """Analyze and compare results"""
    print("\n" + "="*70)
    print("ANALYSIS")
    print("="*70)
    
    # Group by model
    by_model = {}
    for r in results:
        model = r["model"]
        if model not in by_model:
            by_model[model] = []
        by_model[model].append(r)
    
    print("\n## Model Comparison Table\n")
    print("| Model | Mode | Success | Tool Calls | Grounded | Citations | Issue |")
    print("|-------|------|---------|------------|----------|-----------|-------|")
    
    for model in TEST_MODELS:
        if model in by_model:
            for r in by_model[model]:
                mode = r["grounding_mode"]
                # Consider it a success only if it truly succeeded and has content
                has_content = bool(r.get("content_snippet"))
                success = "✅" if (r.get("success") and has_content) else "❌"
                
                if r.get("success") and r.get("telemetry"):
                    tool_calls = r["telemetry"]["tool_call_count"]
                    grounded = "✅" if r["telemetry"]["grounded_effective"] else "❌"
                    citations = r["telemetry"]["citations_total"]
                    issue = r["telemetry"].get("why_not_grounded", "-")
                else:
                    tool_calls = "-"
                    grounded = "-"
                    citations = "-"
                    if r.get("model_not_allowed"):
                        issue = "Model not allowed"
                    elif r.get("grounding_not_supported"):
                        issue = "Grounding not supported"
                    else:
                        issue = r.get("error", "Unknown error")[:30]
                
                print(f"| {model:<13} | {mode:<8} | {success} | {tool_calls:^10} | {grounded:^8} | {citations:^9} | {issue} |")
    
    # Summary
    print("\n## Summary\n")
    
    working_models = []
    not_allowed_models = []
    not_supported_models = []
    no_tools_models = []
    
    for model in TEST_MODELS:
        if model in by_model:
            auto_result = next((r for r in by_model[model] if r["grounding_mode"] == "AUTO"), None)
            if auto_result:
                if not auto_result.get("success"):
                    if auto_result.get("model_not_allowed"):
                        not_allowed_models.append(model)
                    elif auto_result.get("grounding_not_supported"):
                        not_supported_models.append(model)
                elif auto_result.get("telemetry", {}).get("tool_call_count", 0) > 0:
                    working_models.append(model)
                else:
                    no_tools_models.append(model)
    
    print(f"✅ Models with working grounding (tool calls > 0): {working_models or 'None'}")
    print(f"⚠️ Models where grounding not supported: {not_supported_models or 'None'}")
    print(f"🚫 Models not allowed: {not_allowed_models or 'None'}")
    print(f"❌ Models that don't invoke tools: {no_tools_models or 'None'}")
    
    # Key finding
    print("\n## Key Finding\n")
    if not working_models:
        print("❌ NO OpenAI models successfully invoke grounding tools")
        print("   This confirms it's an account-wide issue, not specific to GPT-5")
    else:
        print(f"✅ These models CAN use grounding: {', '.join(working_models)}")
        print("   The issue may be model-specific rather than account-wide")

async def main():
    """Main execution"""
    print("="*70)
    print("GPT-4 vs GPT-5 Grounding Comparison Test")
    print("="*70)
    print("\nObjective: Determine if grounding issues affect all OpenAI models")
    print(f"Testing models: {', '.join(TEST_MODELS)}")
    print(f"Test prompt: '{TEST_PROMPT[:50]}...'")
    
    # Run tests
    results = await test_all_models()
    
    # Analyze
    analyze_results(results)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gpt4_grounding_results_{timestamp}.json"
    
    output = {
        "test_metadata": {
            "timestamp": timestamp,
            "models_tested": TEST_MODELS,
            "prompt": TEST_PROMPT
        },
        "results": results
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n📁 Results saved to: {filename}")
    
    # Recommendation
    print("\n" + "="*70)
    print("RECOMMENDATION")
    print("="*70)
    
    if not any(r.get("success") and r.get("telemetry", {}).get("tool_call_count", 0) > 0 for r in results):
        print("\n🔴 The grounding issue affects ALL OpenAI models tested")
        print("   This is an account-wide limitation, not model-specific")
        print("   Action: Escalate to OpenAI with evidence that no models can use web_search tools")
    else:
        print("\n🟡 Some models may support grounding")
        print("   Action: Use the working models for grounded requests")

if __name__ == "__main__":
    asyncio.run(main())