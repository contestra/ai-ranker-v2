#!/usr/bin/env python3
"""
Grounding Verification Test Suite
Tests OpenAI and Vertex grounding behavior per PRD requirements
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any

# Setup logging with both file and console output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'grounding_verification_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)

def print_result(label: str, value: Any, indent: int = 2):
    """Print a formatted result line"""
    prefix = " " * indent
    if isinstance(value, (dict, list)):
        print(f"{prefix}{label}: {json.dumps(value, indent=2)}")
    else:
        print(f"{prefix}{label}: {value}")

async def test_openai_preferred():
    """Test OpenAI with Preferred mode (grounded=true, should fallback gracefully)"""
    print_section("TEST 1: OpenAI Preferred Mode (grounded=true, tool_choice=auto)")
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the current weather in Tokyo?"}
        ],
        vendor="openai",
        model="gpt-5",
        grounded=True,  # Request grounding
        json_mode=False,
        max_tokens=200,
        meta={"grounding_mode": "AUTO"},  # Preferred mode
        template_id="test_openai_preferred",
        run_id="run_001"
    )
    
    try:
        response = await adapter.complete(request)
        
        print_result("Success", response.success)
        print_result("Vendor", response.vendor)
        print_result("Model", response.model)
        print_result("Grounded Effective", response.grounded_effective)
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            print_result("Grounding Not Supported", meta.get('grounding_not_supported', False))
            print_result("Why Not Grounded", meta.get('why_not_grounded', 'N/A'))
            print_result("Tool Call Count", meta.get('tool_call_count', 0))
            print_result("Response API", meta.get('response_api', 'N/A'))
        
        print_result("Content Preview", response.content[:200] if response.content else "No content")
        
        # Expectation check
        print("\n  EXPECTED: Ungrounded response with grounding_not_supported=true")
        print(f"  ACTUAL: grounded_effective={response.grounded_effective}, "
              f"grounding_not_supported={response.metadata.get('grounding_not_supported', False) if hasattr(response, 'metadata') else 'N/A'}")
        
        return response
        
    except Exception as e:
        print(f"\n  ERROR: {e}")
        logger.exception("OpenAI Preferred test failed")
        return None

async def test_openai_required():
    """Test OpenAI with Required mode (should fail-closed)"""
    print_section("TEST 2: OpenAI Required Mode (grounded=true, should fail)")
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the current weather in Tokyo?"}
        ],
        vendor="openai",
        model="gpt-5",
        grounded=True,  # Request grounding
        json_mode=False,
        max_tokens=200,
        meta={"grounding_mode": "REQUIRED"},  # Required mode - must fail if not supported
        template_id="test_openai_required",
        run_id="run_002"
    )
    
    try:
        response = await adapter.complete(request)
        
        # If we get here, something's wrong - Required should fail
        print("\n  UNEXPECTED: Got response when failure was expected!")
        print_result("Success", response.success)
        print_result("Grounded Effective", response.grounded_effective)
        
        return response
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n  EXPECTED ERROR (fail-closed): {error_msg}")
        
        # Check if it's the right kind of error
        if "GROUNDING_NOT_SUPPORTED" in error_msg:
            print("\n  ✓ CORRECT: Failed with GROUNDING_NOT_SUPPORTED as expected")
        else:
            print("\n  ⚠ WARNING: Failed but not with expected error type")
        
        return None

async def test_vertex_grounded():
    """Test Vertex with grounding (should use tools and hopefully get citations)"""
    print_section("TEST 3: Vertex Grounded (Preferred mode)")
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What are the latest AI developments from Google in 2024?"}
        ],
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",  # or gemini-2.5-pro
        grounded=True,
        json_mode=False,
        max_tokens=500,
        meta={"grounding_mode": "AUTO"},  # Preferred mode
        template_id="test_vertex_grounded",
        run_id="run_003"
    )
    
    try:
        response = await adapter.complete(request)
        
        print_result("Success", response.success)
        print_result("Vendor", response.vendor)
        print_result("Model", response.model)
        print_result("Grounded Effective", response.grounded_effective)
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            print_result("Tool Call Count", meta.get('tool_call_count', 0))
            print_result("Two Step Used", meta.get('two_step_used', False))
            print_result("Response API", meta.get('response_api', 'N/A'))
            
            # Check citations
            citations = meta.get('citations', [])
            print_result("Citations Count", len(citations))
            
            if citations:
                print("\n  Citations found:")
                for i, cit in enumerate(citations[:3]):  # Show first 3
                    print(f"    [{i+1}] {cit.get('url', 'N/A')}")
                    print(f"         Title: {cit.get('title', 'N/A')}")
            else:
                # Check for forensic audit
                print_result("Why Not Grounded", meta.get('why_not_grounded', 'N/A'))
                
                audit = meta.get('citations_audit', {})
                if audit:
                    print("\n  FORENSIC AUDIT:")
                    print_result("Candidates", audit.get('candidates', 0), 4)
                    print_result("Metadata Keys", audit.get('grounding_metadata_keys', []), 4)
                    print_result("Example Structure", audit.get('example', {}), 4)
        
        print_result("Content Preview", response.content[:200] if response.content else "No content")
        
        # Expectation check
        print("\n  EXPECTED: tool_call_count > 0")
        tool_count = response.metadata.get('tool_call_count', 0) if hasattr(response, 'metadata') else 0
        print(f"  ACTUAL: tool_call_count={tool_count}")
        
        if tool_count > 0:
            citations = response.metadata.get('citations', []) if hasattr(response, 'metadata') else []
            if citations:
                print(f"  ✓ SUCCESS: Found {len(citations)} citations, grounded_effective={response.grounded_effective}")
            else:
                print(f"  ⚠ NEEDS ATTENTION: Tools used but no citations. Check citations_audit for SDK structure.")
        
        return response
        
    except Exception as e:
        print(f"\n  ERROR: {e}")
        logger.exception("Vertex grounded test failed")
        return None

async def test_vertex_grounded_json():
    """Test Vertex with grounded JSON mode (two-step flow)"""
    print_section("TEST 4: Vertex Grounded + JSON Mode (two-step)")
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Provide structured JSON responses."},
            {"role": "user", "content": "Find information about Tesla's latest Model 3 features and return as JSON with keys: model, features (array), price_range"}
        ],
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",
        grounded=True,
        json_mode=True,  # This triggers two-step flow
        max_tokens=500,
        meta={"grounding_mode": "AUTO"},
        template_id="test_vertex_json",
        run_id="run_004"
    )
    
    try:
        response = await adapter.complete(request)
        
        print_result("Success", response.success)
        print_result("Grounded Effective", response.grounded_effective)
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            print_result("Two Step Used", meta.get('two_step_used', False))
            print_result("Tool Call Count", meta.get('tool_call_count', 0))
            print_result("Step2 Tools Invoked", meta.get('step2_tools_invoked', False))
            
            citations = meta.get('citations', [])
            print_result("Citations Count", len(citations))
            
            if not citations and meta.get('tool_call_count', 0) > 0:
                audit = meta.get('citations_audit', {})
                if audit:
                    print("\n  FORENSIC AUDIT (Two-step):")
                    print_result("Metadata Keys", audit.get('grounding_metadata_keys', []), 4)
        
        # Try to parse as JSON
        try:
            if response.content:
                json_data = json.loads(response.content)
                print("\n  JSON Output Valid: ✓")
                print_result("JSON Keys", list(json_data.keys()))
            else:
                print("\n  No content returned")
        except json.JSONDecodeError:
            print("\n  JSON Output Valid: ✗ (not valid JSON)")
        
        return response
        
    except Exception as e:
        print(f"\n  ERROR: {e}")
        logger.exception("Vertex JSON test failed")
        return None

async def main():
    """Run all verification tests"""
    print("\n" + "="*80)
    print(" GROUNDING VERIFICATION TEST SUITE")
    print(" Testing PRD compliance for OpenAI and Vertex grounding")
    print("="*80)
    
    results = {}
    
    # Test 1: OpenAI Preferred (should gracefully fallback)
    results['openai_preferred'] = await test_openai_preferred()
    await asyncio.sleep(1)
    
    # Test 2: OpenAI Required (should fail-closed)
    results['openai_required'] = await test_openai_required()
    await asyncio.sleep(1)
    
    # Test 3: Vertex Grounded
    results['vertex_grounded'] = await test_vertex_grounded()
    await asyncio.sleep(1)
    
    # Test 4: Vertex Grounded + JSON (two-step)
    results['vertex_json'] = await test_vertex_grounded_json()
    
    # Summary
    print_section("TEST SUMMARY")
    
    print("\nOpenAI Tests:")
    print("  Preferred Mode: ", end="")
    if results['openai_preferred']:
        print(f"✓ Completed (grounded_effective={results['openai_preferred'].grounded_effective})")
    else:
        print("✗ Failed")
    
    print("  Required Mode: ", end="")
    if results['openai_required'] is None:
        print("✓ Failed as expected (fail-closed)")
    else:
        print("⚠ Unexpected success")
    
    print("\nVertex Tests:")
    print("  Grounded Mode: ", end="")
    if results['vertex_grounded']:
        meta = results['vertex_grounded'].metadata if hasattr(results['vertex_grounded'], 'metadata') else {}
        tool_count = meta.get('tool_call_count', 0)
        citation_count = len(meta.get('citations', []))
        print(f"✓ Completed (tools={tool_count}, citations={citation_count})")
        
        if tool_count > 0 and citation_count == 0:
            print("    ⚠ ATTENTION: Tools used but no citations - check audit data above")
    else:
        print("✗ Failed")
    
    print("  JSON + Grounded: ", end="")
    if results['vertex_json']:
        meta = results['vertex_json'].metadata if hasattr(results['vertex_json'], 'metadata') else {}
        print(f"✓ Completed (two_step={meta.get('two_step_used', False)})")
    else:
        print("✗ Failed")
    
    print("\n" + "="*80)
    print(" Tests complete. Check logs for detailed output.")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())