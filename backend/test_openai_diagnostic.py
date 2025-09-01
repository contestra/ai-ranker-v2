#!/usr/bin/env python3
"""
OpenAI 3-Case Micro-Matrix Diagnostic Test
Based on ChatGPT's precise diagnostic plan to determine if OpenAI
can return citations in our setup.
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# Set environment variables BEFORE imports
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATIONS_EXTRACTOR_ENABLE'] = 'true'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'true'  # For full visibility
os.environ['DEBUG_GROUNDING'] = 'true'
os.environ['ALLOW_HTTP_RESOLVE'] = 'false'

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test prompt with provoker line
TEST_PROMPT = """What are the latest developments in AI regulation and policy in 2024?

As of today (2025-09-02), include an official source URL."""

# JSON schema for structured output
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["answer"]
}

async def run_case_a(adapter: UnifiedLLMAdapter) -> Dict[str, Any]:
    """Case A: OpenAI with REQUIRED grounding (smoking gun)"""
    print("\n" + "="*70)
    print("CASE A: OpenAI REQUIRED Grounding")
    print("="*70)
    print("Model: gpt-5")
    print("Tool choice: REQUIRED")
    print("Expected: Fail-closed if no tool call, or citations if tool called")
    
    request = LLMRequest(
        messages=[{"role": "user", "content": TEST_PROMPT}],
        model="gpt-5",
        vendor="openai",
        grounded=True,
        max_tokens=100,  # ≥64 as specified
        temperature=0.3,
        json_mode=True,  # Enable JSON mode
        meta={
            "grounding_mode": "REQUIRED",
            "test_case": "A_REQUIRED"
        }
    )
    
    result = {
        "case": "A_REQUIRED",
        "timestamp": datetime.now().isoformat(),
        "request": {
            "model": "gpt-5",
            "vendor": "openai",
            "grounded": True,
            "grounding_mode": "REQUIRED",
            "max_tokens": 100,
            "json_mode": True
        }
    }
    
    try:
        response = await adapter.complete(request)
        result["success"] = True
        result["content"] = response.content[:500] if response.content else ""
        
        # Extract all telemetry fields ChatGPT specified
        if response.metadata:
            meta = response.metadata
            result["telemetry"] = {
                # Routing & shape
                "response_api": meta.get("response_api"),
                "model_effective": meta.get("model", request.model),
                "tool_choice_sent": meta.get("tool_choice", "unknown"),
                "tool_type_sent": meta.get("response_api_tool_type"),
                
                # Tool evidence & outcomes
                "tool_call_count": meta.get("tool_call_count", 0),
                "tool_result_count": meta.get("tool_result_count", 0),
                "grounding_attempted": meta.get("grounding_attempted", False),
                "grounded_effective": meta.get("grounded_effective", False),
                "citations_total": len(meta.get("citations", [])),
                "citations_anchored": meta.get("anchored_citations_count", 0),
                "citations_unlinked": meta.get("unlinked_sources_count", 0),
                "why_not_grounded": meta.get("why_not_grounded") or meta.get("grounding_status_reason"),
                
                # Schema & usage
                "max_output_tokens": meta.get("max_output_tokens", request.max_tokens),
                "usage": meta.get("usage", {})
            }
            
            # Sample citations if any
            citations = meta.get("citations", [])
            if citations:
                result["sample_citations"] = citations[:3]
        
        print(f"\n✅ Request completed successfully")
        print(f"Tool calls: {result['telemetry']['tool_call_count']}")
        print(f"Grounded effective: {result['telemetry']['grounded_effective']}")
        print(f"Citations: {result['telemetry']['citations_total']}")
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        
        # Check if it's the expected fail-closed behavior
        if "GROUNDING_NOT_SUPPORTED" in str(e) or "GROUNDING_REQUIRED" in str(e):
            result["expected_failure"] = True
            print(f"\n⚠️ Expected fail-closed: {e}")
        else:
            print(f"\n❌ Unexpected error: {e}")
    
    return result

async def run_case_b(adapter: UnifiedLLMAdapter) -> Dict[str, Any]:
    """Case B: OpenAI with AUTO grounding (control with nudge)"""
    print("\n" + "="*70)
    print("CASE B: OpenAI AUTO Grounding")
    print("="*70)
    print("Model: gpt-5")
    print("Tool choice: AUTO")
    print("Expected: May or may not invoke tools")
    
    request = LLMRequest(
        messages=[{"role": "user", "content": TEST_PROMPT}],
        model="gpt-5",
        vendor="openai",
        grounded=True,
        max_tokens=100,
        temperature=0.3,
        json_mode=True,
        meta={
            "grounding_mode": "AUTO",
            "test_case": "B_AUTO"
        }
    )
    
    result = {
        "case": "B_AUTO",
        "timestamp": datetime.now().isoformat(),
        "request": {
            "model": "gpt-5",
            "vendor": "openai",
            "grounded": True,
            "grounding_mode": "AUTO",
            "max_tokens": 100,
            "json_mode": True
        }
    }
    
    try:
        response = await adapter.complete(request)
        result["success"] = True
        result["content"] = response.content[:500] if response.content else ""
        
        if response.metadata:
            meta = response.metadata
            result["telemetry"] = {
                "response_api": meta.get("response_api"),
                "model_effective": meta.get("model", request.model),
                "tool_choice_sent": meta.get("tool_choice", "unknown"),
                "tool_type_sent": meta.get("response_api_tool_type"),
                "tool_call_count": meta.get("tool_call_count", 0),
                "tool_result_count": meta.get("tool_result_count", 0),
                "grounding_attempted": meta.get("grounding_attempted", False),
                "grounded_effective": meta.get("grounded_effective", False),
                "citations_total": len(meta.get("citations", [])),
                "citations_anchored": meta.get("anchored_citations_count", 0),
                "citations_unlinked": meta.get("unlinked_sources_count", 0),
                "why_not_grounded": meta.get("why_not_grounded") or meta.get("grounding_status_reason"),
                "max_output_tokens": meta.get("max_output_tokens", request.max_tokens),
                "usage": meta.get("usage", {})
            }
            
            citations = meta.get("citations", [])
            if citations:
                result["sample_citations"] = citations[:3]
        
        print(f"\n✅ Request completed successfully")
        print(f"Tool calls: {result['telemetry']['tool_call_count']}")
        print(f"Grounded effective: {result['telemetry']['grounded_effective']}")
        print(f"Citations: {result['telemetry']['citations_total']}")
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        print(f"\n❌ Error: {e}")
    
    return result

async def run_case_c(adapter: UnifiedLLMAdapter) -> Dict[str, Any]:
    """Case C: OpenAI UNGROUNDED baseline"""
    print("\n" + "="*70)
    print("CASE C: OpenAI UNGROUNDED Baseline")
    print("="*70)
    print("Model: gpt-5-chat-latest")
    print("No tools attached")
    print("Expected: No tool calls, no citations")
    
    request = LLMRequest(
        messages=[{"role": "user", "content": TEST_PROMPT}],
        model="gpt-5-chat-latest",
        vendor="openai",
        grounded=False,  # Ungrounded
        max_tokens=100,
        temperature=0.3,
        json_mode=True,
        meta={
            "test_case": "C_UNGROUNDED"
        }
    )
    
    result = {
        "case": "C_UNGROUNDED",
        "timestamp": datetime.now().isoformat(),
        "request": {
            "model": "gpt-5-chat-latest",
            "vendor": "openai",
            "grounded": False,
            "max_tokens": 100,
            "json_mode": True
        }
    }
    
    try:
        response = await adapter.complete(request)
        result["success"] = True
        result["content"] = response.content[:500] if response.content else ""
        
        if response.metadata:
            meta = response.metadata
            result["telemetry"] = {
                "response_api": meta.get("response_api"),
                "model_effective": meta.get("model", request.model),
                "tool_choice_sent": meta.get("tool_choice", "none"),
                "tool_type_sent": meta.get("response_api_tool_type"),
                "tool_call_count": meta.get("tool_call_count", 0),
                "tool_result_count": meta.get("tool_result_count", 0),
                "grounding_attempted": meta.get("grounding_attempted", False),
                "grounded_effective": meta.get("grounded_effective", False),
                "citations_total": len(meta.get("citations", [])),
                "citations_anchored": meta.get("anchored_citations_count", 0),
                "citations_unlinked": meta.get("unlinked_sources_count", 0),
                "why_not_grounded": meta.get("why_not_grounded") or meta.get("grounding_status_reason"),
                "max_output_tokens": meta.get("max_output_tokens", request.max_tokens),
                "usage": meta.get("usage", {})
            }
            
            # Flag if any tools were unexpectedly called
            if result["telemetry"]["tool_call_count"] > 0:
                result["unexpected_tools"] = True
                print(f"\n⚠️ UNEXPECTED: Tool calls in ungrounded mode!")
        
        print(f"\n✅ Request completed successfully")
        print(f"Tool calls: {result['telemetry']['tool_call_count']}")
        print(f"Citations: {result['telemetry']['citations_total']}")
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        print(f"\n❌ Error: {e}")
    
    return result

def analyze_results(results: list) -> Dict[str, Any]:
    """Analyze results per ChatGPT's interpretation matrix"""
    analysis = {
        "timestamp": datetime.now().isoformat(),
        "conclusions": [],
        "evidence": {},
        "next_steps": []
    }
    
    # Get results by case
    case_a = next((r for r in results if r["case"] == "A_REQUIRED"), None)
    case_b = next((r for r in results if r["case"] == "B_AUTO"), None)
    case_c = next((r for r in results if r["case"] == "C_UNGROUNDED"), None)
    
    # Analyze Case A (REQUIRED)
    if case_a:
        if not case_a.get("success") and case_a.get("expected_failure"):
            analysis["conclusions"].append(
                "Case A failed-closed with GROUNDING_REQUIRED_ERROR (tool_call_count=0)"
            )
            analysis["evidence"]["case_a"] = "Model did not perform search in REQUIRED mode"
            analysis["next_steps"].append(
                "Very strong evidence this is a provider-side behavior/entitlement issue"
            )
        elif case_a.get("success") and case_a.get("telemetry", {}).get("tool_call_count", 0) > 0:
            cit_count = case_a.get("telemetry", {}).get("citations_total", 0)
            if cit_count > 0:
                analysis["conclusions"].append(
                    f"Case A succeeded with {cit_count} citations"
                )
                analysis["evidence"]["case_a"] = "OpenAI CAN return citations"
            else:
                analysis["conclusions"].append(
                    "Case A had tool calls but no citations extracted"
                )
                analysis["evidence"]["case_a"] = "Possible extraction issue"
                analysis["next_steps"].append("Inspect extraction logic")
    
    # Analyze Case B (AUTO)
    if case_b and case_b.get("success"):
        tool_count = case_b.get("telemetry", {}).get("tool_call_count", 0)
        if tool_count == 0:
            analysis["conclusions"].append(
                "Case B (AUTO) had tool_call_count=0"
            )
            analysis["evidence"]["case_b"] = "Aligns with known GPT-5 behavior: AUTO rarely searches"
        else:
            analysis["conclusions"].append(
                f"Case B (AUTO) made {tool_count} tool calls"
            )
            analysis["evidence"]["case_b"] = "Model searched in AUTO mode"
    
    # Analyze Case C (UNGROUNDED)
    if case_c and case_c.get("success"):
        if case_c.get("unexpected_tools"):
            analysis["conclusions"].append(
                "Case C (ungrounded) shows tool calls - ROUTING BUG"
            )
            analysis["evidence"]["case_c"] = "Tools attached when they shouldn't be"
            analysis["next_steps"].append("Fix router/mapping")
        else:
            analysis["conclusions"].append(
                "Case C (ungrounded) correctly had no tools"
            )
            analysis["evidence"]["case_c"] = "Router correctly handles ungrounded"
    
    return analysis

async def main():
    """Run the 3-case micro-matrix diagnostic"""
    print("="*70)
    print("OpenAI 3-Case Micro-Matrix Diagnostic")
    print("="*70)
    print("\nObjective: Determine if OpenAI can return citations in our setup")
    print("Based on ChatGPT's precise diagnostic plan")
    print(f"\nTest prompt includes provoker: 'As of today (2025-09-02), include an official source URL.'")
    
    adapter = UnifiedLLMAdapter()
    results = []
    
    # Run all three cases
    print("\nRunning diagnostic tests...")
    
    # Case A: REQUIRED
    result_a = await run_case_a(adapter)
    results.append(result_a)
    await asyncio.sleep(2)
    
    # Case B: AUTO
    result_b = await run_case_b(adapter)
    results.append(result_b)
    await asyncio.sleep(2)
    
    # Case C: UNGROUNDED
    result_c = await run_case_c(adapter)
    results.append(result_c)
    
    # Analyze results
    print("\n" + "="*70)
    print("ANALYSIS (per ChatGPT's interpretation matrix)")
    print("="*70)
    
    analysis = analyze_results(results)
    
    print("\nConclusions:")
    for conclusion in analysis["conclusions"]:
        print(f"  • {conclusion}")
    
    print("\nEvidence:")
    for case, evidence in analysis["evidence"].items():
        print(f"  • {case}: {evidence}")
    
    if analysis["next_steps"]:
        print("\nNext Steps:")
        for step in analysis["next_steps"]:
            print(f"  • {step}")
    
    # Save full results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"openai_diagnostic_results_{timestamp}.json"
    
    output = {
        "test_metadata": {
            "timestamp": timestamp,
            "prompt": TEST_PROMPT,
            "environment": {
                "CITATION_EXTRACTOR_V2": os.environ.get("CITATION_EXTRACTOR_V2"),
                "CITATION_EXTRACTOR_EMIT_UNLINKED": os.environ.get("CITATION_EXTRACTOR_EMIT_UNLINKED")
            }
        },
        "results": results,
        "analysis": analysis
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n📁 Full results saved to: {filename}")
    
    # Print escalation packet info if needed
    if any("provider-side" in step for step in analysis.get("next_steps", [])):
        print("\n" + "="*70)
        print("ESCALATION PACKET (for OpenAI support)")
        print("="*70)
        print("\nInclude in ticket:")
        print("1. Model used: gpt-5")
        print("2. Tool choice: REQUIRED")
        print("3. Tool type attempted: web_search")
        print(f"4. Timestamp: {timestamp}")
        print(f"5. Result: {analysis['evidence'].get('case_a', 'Unknown')}")
        print("6. Policy: Our adapter fails-closed in REQUIRED when no tool call occurs")

if __name__ == "__main__":
    asyncio.run(main())