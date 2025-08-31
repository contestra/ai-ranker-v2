#!/usr/bin/env python3
"""
Test that web_search_preview retry only happens for grounded requests.
This verifies the fix for the retry gate.
"""

import asyncio
import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_retry_gate():
    """Test that retry with web_search_preview is gated by grounding"""
    
    print("\n" + "="*80)
    print("TESTING RETRY GATE FOR WEB_SEARCH_PREVIEW")
    print("="*80)
    
    adapter = UnifiedLLMAdapter()
    results = []
    
    # Test cases: grounded vs ungrounded with errors
    test_cases = [
        {
            "name": "Ungrounded request with error",
            "grounded": False,
            "expected_retry": False,
            "description": "Should NOT retry with web_search_preview"
        },
        {
            "name": "Grounded request with error", 
            "grounded": True,
            "expected_retry": True,
            "description": "Should retry with web_search_preview"
        }
    ]
    
    for test in test_cases:
        print(f"\n[TEST: {test['name']}]")
        print(f"  Grounded: {test['grounded']}")
        print(f"  Expected behavior: {test['description']}")
        
        # Create request
        request = LLMRequest(
            vendor="openai",
            model="gpt-5",
            messages=[{"role": "user", "content": "Test message"}],
            grounded=test["grounded"],
            meta={"grounding_mode": "AUTO"},
            max_tokens=100
        )
        
        # Mock the OpenAI client to simulate an error
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            # Set up mock to raise a generic error
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            
            # Track calls to see if retry happens
            call_count = 0
            retry_with_preview = False
            
            def track_call(**kwargs):
                nonlocal call_count, retry_with_preview
                call_count += 1
                
                # Check if this is a retry with web_search_preview
                if "tools" in kwargs:
                    tools = kwargs.get("tools", [])
                    if tools and tools[0].get("type") == "web_search_preview":
                        retry_with_preview = True
                
                # Simulate error on first call
                if call_count == 1:
                    raise Exception("Simulated API error (not web_search related)")
                else:
                    # Return mock response on retry
                    mock_resp = MagicMock()
                    mock_resp.content = "Test response"
                    mock_resp.model = "gpt-5"
                    return mock_resp
            
            mock_client.responses.create.side_effect = track_call
            
            try:
                # Attempt the request
                response = await adapter.complete(request)
                print(f"  ✓ Request completed")
            except Exception as e:
                print(f"  ✓ Request failed as expected: {str(e)[:50]}")
            
            # Check if retry behavior matches expectation
            if test["expected_retry"]:
                if retry_with_preview:
                    print(f"  ✅ PASS: Retry with web_search_preview occurred as expected")
                    results.append({"test": test["name"], "status": "PASS"})
                else:
                    print(f"  ❌ FAIL: Expected retry with web_search_preview but it didn't happen")
                    results.append({"test": test["name"], "status": "FAIL"})
            else:
                if not retry_with_preview:
                    print(f"  ✅ PASS: No retry with web_search_preview (correctly gated)")
                    results.append({"test": test["name"], "status": "PASS"})
                else:
                    print(f"  ❌ FAIL: Unexpected retry with web_search_preview for ungrounded request")
                    results.append({"test": test["name"], "status": "FAIL"})
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    
    print(f"Total tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n✅ All tests passed! Retry gate is working correctly.")
    else:
        print(f"\n❌ {failed} test(s) failed. Review the retry logic.")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_retry_gate())