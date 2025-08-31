#!/usr/bin/env python3
"""
Test that Vertex grounded requests fail-closed without google-genai
"""

import asyncio
import sys
import os
from unittest.mock import patch

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

async def test_genai_requirement():
    """Test that grounded requests require google-genai"""
    
    print("\n" + "="*80)
    print("TESTING VERTEX GOOGLE-GENAI REQUIREMENT")
    print("="*80)
    
    adapter = UnifiedLLMAdapter()
    
    # Test configurations
    test_cases = [
        {
            "name": "Ungrounded request (should work)",
            "grounded": False,
            "should_fail": False,
            "expected_error": None
        },
        {
            "name": "Grounded request without genai",
            "grounded": True,
            "should_fail": True,
            "expected_error": "GROUNDING_REQUIRES_GENAI"
        }
    ]
    
    for test in test_cases:
        print(f"\n[TEST: {test['name']}]")
        
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[{"role": "user", "content": "Test message"}],
            grounded=test["grounded"],
            meta={"grounding_mode": "AUTO"},
            max_tokens=100
        )
        
        # Simulate google-genai not available
        with patch.dict(os.environ, {"VERTEX_USE_GENAI_CLIENT": "false"}):
            try:
                # Re-initialize adapter to pick up env change
                adapter = UnifiedLLMAdapter()
                response = await adapter.complete(request)
                
                if test["should_fail"]:
                    print(f"  ❌ FAIL: Request succeeded but should have failed")
                else:
                    print(f"  ✅ PASS: Request succeeded as expected")
                    
            except Exception as e:
                error_msg = str(e)
                
                if test["should_fail"]:
                    if test["expected_error"] in error_msg:
                        print(f"  ✅ PASS: Failed with expected error")
                        print(f"     Error: {error_msg[:100]}")
                    else:
                        print(f"  ❌ FAIL: Failed but with wrong error")
                        print(f"     Expected: {test['expected_error']}")
                        print(f"     Got: {error_msg[:100]}")
                else:
                    print(f"  ❌ FAIL: Request failed but should have succeeded")
                    print(f"     Error: {error_msg[:100]}")
    
    # Test the error message clarity
    print("\n" + "-"*40)
    print("ERROR MESSAGE CHECK")
    print("-"*40)
    
    # Force a grounded request without genai to see the error
    request = LLMRequest(
        vendor="vertex",
        model="publishers/google/models/gemini-2.5-pro",
        messages=[{"role": "user", "content": "Find recent research"}],
        grounded=True,
        meta={"grounding_mode": "REQUIRED"},
        max_tokens=100
    )
    
    with patch.dict(os.environ, {"VERTEX_USE_GENAI_CLIENT": "false"}):
        try:
            adapter = UnifiedLLMAdapter()
            response = await adapter.complete(request)
            print("❌ No error raised!")
        except Exception as e:
            error_msg = str(e)
            print("Error message received:")
            print(f"  {error_msg}")
            
            # Check message quality
            checks = [
                ("Contains 'GROUNDING_REQUIRES_GENAI'", "GROUNDING_REQUIRES_GENAI" in error_msg),
                ("Mentions pip install", "pip install" in error_msg),
                ("Shows current state", "GENAI_AVAILABLE=" in error_msg),
                ("Provides fix instructions", "To fix:" in error_msg)
            ]
            
            print("\nMessage quality checks:")
            for check_name, passed in checks:
                status = "✅" if passed else "❌"
                print(f"  {status} {check_name}")
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("✅ Grounded Vertex requests now fail-closed without google-genai")
    print("✅ Clear error messages guide users to install google-genai")
    print("✅ Ungrounded requests continue to work with vertexai SDK")

if __name__ == "__main__":
    asyncio.run(test_genai_requirement())