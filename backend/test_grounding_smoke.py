#!/usr/bin/env venv/bin/python
"""
Grounding trigger smoke tests for longevity + AVEA
Tests both OpenAI and Vertex with AUTO and REQUIRED modes
"""

import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

# Test prompts
EVIDENCE_PROMPT = """As of August 31, 2025, summarize clinical evidence from the last 12 months for resveratrol, NMN/NR, spermidine, CoQ10, collagen activators. Include study design, sample size, outcomes, limitations, and add links + dates. Where relevant, cross-reference AVEA Life product pages on www.avea-life.com. End with TOOL_STATUS: USED_WEB_SEARCH or NO_TOOLS."""

PRESS_PROMPT = """Find independent press or collaborations mentioning AVEA Life in the past 6 months. For each: title, outlet, date, URL, 1–2 sentence summary. Prefer non-brand sources. End with TOOL_STATUS."""

async def run_smoke_test():
    adapter = UnifiedLLMAdapter()
    results = []
    
    print("\n" + "="*80)
    print("GROUNDING TRIGGER SMOKE TESTS")
    print("="*80)
    
    test_configs = [
        ("OpenAI", "AUTO", "openai", "gpt-5"),
        ("OpenAI", "REQUIRED", "openai", "gpt-5"),
        ("Vertex", "AUTO", "vertex", "publishers/google/models/gemini-2.5-pro"),
        ("Vertex", "REQUIRED", "vertex", "publishers/google/models/gemini-2.5-pro"),
    ]
    
    for provider, mode, vendor, model in test_configs:
        print(f"\n[{provider} - {mode} MODE]")
        print("-" * 40)
        
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{"role": "user", "content": EVIDENCE_PROMPT}],
            grounded=True,
            meta={"grounding_mode": mode},
            als_context=ALSContext(country_code="US", locale="en-US", als_block=""),
            max_tokens=500
        )
        
        try:
            response = await adapter.complete(request)
            content = response.content if hasattr(response, 'content') else ''
            meta = response.metadata if hasattr(response, 'metadata') else {}
            
            # Extract key metrics
            result = {
                "provider": provider,
                "mode": mode,
                "status": "success",
                "grounding_attempted": meta.get("grounding_attempted", False),
                "grounded_effective": meta.get("grounded_effective", False),
                "tool_type": meta.get("response_api_tool_type"),
                "tool_calls": meta.get("tool_call_count", 0),
                "tool_results": meta.get("tool_result_count", 0),
                "citations": meta.get("citations_count", 0),
                "why_not": meta.get("why_not_grounded"),
                "has_tool_status": "TOOL_STATUS" in content
            }
            
            print(f"✅ Success")
            print(f"   Grounded effective: {result['grounded_effective']}")
            print(f"   Tool calls: {result['tool_calls']}")
            print(f"   Citations: {result['citations']}")
            if result['why_not']:
                print(f"   Why not grounded: {result['why_not']}")
            
        except Exception as e:
            error_str = str(e)
            
            # Check for expected REQUIRED mode failure
            if mode == "REQUIRED" and provider == "OpenAI":
                if "GROUNDING_NOT_SUPPORTED" in error_str or "cannot guarantee REQUIRED" in error_str:
                    result = {
                        "provider": provider,
                        "mode": mode,
                        "status": "expected_fail",
                        "error": error_str[:100]
                    }
                    print(f"✅ Expected fail (API limitation)")
                else:
                    result = {
                        "provider": provider,
                        "mode": mode,
                        "status": "unexpected_error",
                        "error": error_str[:100]
                    }
                    print(f"❌ Unexpected error: {error_str[:100]}")
            else:
                result = {
                    "provider": provider,
                    "mode": mode,
                    "status": "error",
                    "error": error_str[:100]
                }
                print(f"❌ Error: {error_str[:100]}")
        
        results.append(result)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    for r in results:
        status_icon = "✅" if r["status"] in ["success", "expected_fail"] else "❌"
        print(f"{status_icon} {r['provider']}-{r['mode']}: {r['status']}")
        if r["status"] == "success":
            print(f"    Grounded: {r['grounded_effective']}, Citations: {r['citations']}")
    
    # Expected outcomes
    print("\nEXPECTED OUTCOMES:")
    print("✓ OpenAI-AUTO: May attempt grounding, falls back gracefully")
    print("✓ OpenAI-REQUIRED: Immediate fail with API limitation")
    print("✓ Vertex-AUTO: Tools invoked, citations present")
    print("✓ Vertex-REQUIRED: Tools invoked, grounding enforced")
    
    return results

if __name__ == "__main__":
    asyncio.run(run_smoke_test())