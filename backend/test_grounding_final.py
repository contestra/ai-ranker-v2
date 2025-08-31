#!/usr/bin/env python3
"""
Final Grounding Validation - 4 Case Smoke Test
Tests all grounding scenarios per PRD requirements
"""
import asyncio
import json
import logging
import sys
import os
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

def print_test_header(test_num: str, title: str):
    print(f"\n{'='*70}")
    print(f"TEST {test_num}: {title}")
    print('='*70)

def print_result(label: str, value, indent=2):
    prefix = " " * indent
    if isinstance(value, bool):
        icon = "✅" if value else "❌"
        print(f"{prefix}{label}: {value} {icon}")
    elif isinstance(value, int) and label.endswith("Count"):
        icon = "✅" if value > 0 else "⚠️"
        print(f"{prefix}{label}: {value} {icon}")
    else:
        print(f"{prefix}{label}: {value}")

async def test_openai_preferred():
    """Test 1: OpenAI Preferred - should fallback gracefully"""
    print_test_header("1", "OpenAI Preferred (AUTO mode)")
    
    adapter = UnifiedLLMAdapter()
    request = LLMRequest(
        messages=[
            {"role": "user", "content": "What is the weather in Paris today?"}
        ],
        vendor="openai",
        model="gpt-5",
        grounded=True,
        json_mode=False,
        max_tokens=100,
        meta={"grounding_mode": "AUTO"},
        template_id="test_1",
        run_id="smoke_1"
    )
    
    try:
        response = await adapter.complete(request)
        
        print("\nResult:")
        print_result("Success", response.success)
        print_result("Grounded Effective", response.grounded_effective)
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            print_result("Grounding Not Supported", meta.get('grounding_not_supported', False))
            print_result("Why Not Grounded", meta.get('why_not_grounded', 'N/A'))
        
        # Validate expectation
        expected = not response.grounded_effective and response.metadata.get('grounding_not_supported', False)
        print(f"\n  Expected: Ungrounded with grounding_not_supported=true")
        print(f"  Actual: {'✅ PASS' if expected else '❌ FAIL'}")
        
        return "PASS" if expected else "FAIL"
        
    except Exception as e:
        print(f"\n  ❌ Unexpected error: {e}")
        return "FAIL"

async def test_openai_required():
    """Test 2: OpenAI Required - should fail-closed"""
    print_test_header("2", "OpenAI Required (REQUIRED mode)")
    
    adapter = UnifiedLLMAdapter()
    request = LLMRequest(
        messages=[
            {"role": "user", "content": "What is the weather in Paris today?"}
        ],
        vendor="openai",
        model="gpt-5",
        grounded=True,
        json_mode=False,
        max_tokens=100,
        meta={"grounding_mode": "REQUIRED"},
        template_id="test_2",
        run_id="smoke_2"
    )
    
    try:
        response = await adapter.complete(request)
        print("\n  ❌ Unexpected: Got response when failure was expected")
        return "FAIL"
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n  Expected error received: {error_msg[:100]}...")
        
        if "GROUNDING_NOT_SUPPORTED" in error_msg:
            print(f"\n  Expected: Fail-closed with GROUNDING_NOT_SUPPORTED")
            print(f"  Actual: ✅ PASS")
            return "PASS"
        else:
            print(f"\n  ❌ Wrong error type")
            return "FAIL"

async def test_vertex_preferred():
    """Test 3: Vertex Preferred - should ground with citations"""
    print_test_header("3", "Vertex Preferred (AUTO mode)")
    
    adapter = UnifiedLLMAdapter()
    request = LLMRequest(
        messages=[
            {"role": "user", "content": "What are Google's latest AI announcements in 2024?"}
        ],
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",
        grounded=True,
        json_mode=False,
        max_tokens=300,
        meta={"grounding_mode": "AUTO"},
        template_id="test_3",
        run_id="smoke_3"
    )
    
    try:
        response = await adapter.complete(request)
        
        print("\nResult:")
        print_result("Success", response.success)
        print_result("Grounded Effective", response.grounded_effective)
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            tool_count = meta.get('tool_call_count', 0)
            citations = meta.get('citations', [])
            
            print_result("Tool Call Count", tool_count)
            print_result("Citations Count", len(citations))
            
            if citations:
                print("\n  Sample citations:")
                for i, cit in enumerate(citations[:2], 1):
                    print(f"    [{i}] {cit.get('url', 'N/A')[:60]}...")
        
        # Validate expectation
        tool_count = response.metadata.get('tool_call_count', 0) if hasattr(response, 'metadata') else 0
        citation_count = len(response.metadata.get('citations', [])) if hasattr(response, 'metadata') else 0
        
        print(f"\n  Expected: tool_calls>0, citations>0, grounded_effective=true")
        
        if tool_count > 0 and citation_count > 0 and response.grounded_effective:
            print(f"  Actual: ✅ PASS")
            return "PASS"
        elif tool_count > 0 and citation_count == 0:
            print(f"  Actual: ⚠️ Tools used but no citations (check audit)")
            return "PARTIAL"
        else:
            print(f"  Actual: ❌ FAIL")
            return "FAIL"
        
    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        return "FAIL"

async def test_vertex_required():
    """Test 4: Vertex Required - should succeed or fail-closed if no citations"""
    print_test_header("4", "Vertex Required (REQUIRED mode)")
    
    adapter = UnifiedLLMAdapter()
    request = LLMRequest(
        messages=[
            {"role": "user", "content": "What is OpenAI's GPT-4 architecture?"}
        ],
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",
        grounded=True,
        json_mode=False,
        max_tokens=300,
        meta={"grounding_mode": "REQUIRED"},
        template_id="test_4",
        run_id="smoke_4"
    )
    
    try:
        response = await adapter.complete(request)
        
        print("\nResult:")
        print_result("Success", response.success)
        print_result("Grounded Effective", response.grounded_effective)
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            tool_count = meta.get('tool_call_count', 0)
            citations = meta.get('citations', [])
            
            print_result("Tool Call Count", tool_count)
            print_result("Citations Count", len(citations))
        
        if response.grounded_effective:
            print(f"\n  Expected: Grounded with citations OR fail-closed")
            print(f"  Actual: ✅ PASS (grounded successfully)")
            return "PASS"
        else:
            print(f"\n  ⚠️ Not grounded - should have failed in REQUIRED mode")
            return "PARTIAL"
        
    except Exception as e:
        error_msg = str(e)
        if "GROUNDING_REQUIRED_ERROR" in error_msg or "No grounding evidence" in error_msg:
            print(f"\n  Expected: Fail-closed when grounding not achieved")
            print(f"  Actual: ✅ PASS (correctly failed)")
            return "PASS"
        else:
            print(f"\n  ❌ Unexpected error: {error_msg[:100]}")
            return "FAIL"

async def main():
    print("\n" + "="*70)
    print(" FINAL GROUNDING VALIDATION - 4 CASE SMOKE TEST")
    print(" Testing PRD compliance for OpenAI and Vertex")
    print("="*70)
    
    results = {}
    
    # Run all tests
    print("\nStarting tests...")
    
    results['openai_preferred'] = await test_openai_preferred()
    await asyncio.sleep(1)
    
    results['openai_required'] = await test_openai_required()
    await asyncio.sleep(1)
    
    results['vertex_preferred'] = await test_vertex_preferred()
    await asyncio.sleep(1)
    
    results['vertex_required'] = await test_vertex_required()
    
    # Summary
    print("\n" + "="*70)
    print(" TEST SUMMARY")
    print("="*70)
    
    test_names = {
        'openai_preferred': 'OpenAI Preferred (AUTO)',
        'openai_required': 'OpenAI Required',
        'vertex_preferred': 'Vertex Preferred (AUTO)',
        'vertex_required': 'Vertex Required'
    }
    
    for key, name in test_names.items():
        result = results[key]
        icon = "✅" if result == "PASS" else "⚠️" if result == "PARTIAL" else "❌"
        print(f"  {icon} {name}: {result}")
    
    # Overall assessment
    pass_count = sum(1 for r in results.values() if r == "PASS")
    partial_count = sum(1 for r in results.values() if r == "PARTIAL")
    
    print(f"\n  Overall: {pass_count}/4 PASS, {partial_count} PARTIAL")
    
    if pass_count == 4:
        print("\n🎉 All tests PASSED! Grounding implementation is PRD-compliant.")
    elif pass_count >= 3:
        print("\n✅ Core functionality working. Check partial results for minor issues.")
    else:
        print("\n⚠️ Some tests failed. Review the results above.")
    
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())