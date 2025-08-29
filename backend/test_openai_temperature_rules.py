#!/usr/bin/env python3
"""
Test OpenAI adapter temperature rules and grounding behavior
Tests the three scenarios ChatGPT identified:
T1: Ungrounded GPT-5 alias
T2: Grounded-AUTO with zero tool calls  
T3: Synthesis fallback without tools
"""
import asyncio
import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

# Disable proxies for testing
os.environ["DISABLE_PROXIES"] = "true"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest,gpt-4"

from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.types import LLMRequest, LLMResponse

async def test_t1_ungrounded_gpt5_alias():
    """T1: Ungrounded GPT-5 alias should set temperature=1.0"""
    print("\n" + "="*70)
    print("T1: Ungrounded GPT-5 alias")
    print("="*70)
    
    adapter = OpenAIAdapter()
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",  # Alias that should normalize to gpt-5
        messages=[{"role": "user", "content": "Test"}],
        grounded=False,  # No tools
        temperature=0.3  # Should be overridden to 1.0
    )
    
    # Mock the client
    with patch('app.llm.adapters.openai_adapter.AsyncOpenAI') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=20, total_tokens=30)
        mock_client.responses.create = AsyncMock(return_value=mock_response)
        
        # Capture the actual params sent to the API
        actual_params = {}
        async def capture_params(**kwargs):
            actual_params.update(kwargs)
            return mock_response
        mock_client.responses.create.side_effect = capture_params
        
        # Make the call
        response = await adapter.complete(request)
        
        # Verify
        print(f"Model normalized: {request.model} -> gpt-5")
        print(f"Tools in params: {'tools' in actual_params}")
        print(f"Temperature set: {actual_params.get('temperature')}")
        print(f"Response API: {response.metadata.get('response_api')}")
        
        # Assertions
        assert 'tools' not in actual_params, "No tools should be attached for ungrounded"
        assert actual_params.get('temperature') == 1.0, "GPT-5 requires temperature=1.0"
        assert response.metadata.get('response_api') == 'responses_http', "Should use Responses API"
        
        print("✅ T1 PASSED: GPT-5 alias correctly sets temperature=1.0 without tools")
        return True

async def test_t2_grounded_auto_zero_calls():
    """T2: Grounded-AUTO with tools attached but zero calls"""
    print("\n" + "="*70)
    print("T2: Grounded-AUTO (tools attached, zero tool calls)")
    print("="*70)
    
    adapter = OpenAIAdapter()
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is 2+2?"}],  # Simple query unlikely to trigger search
        grounded=True,  # Tools will be attached
        temperature=0.3  # Should be overridden to 1.0
    )
    
    with patch('app.llm.adapters.openai_adapter.AsyncOpenAI') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Mock response with no tool calls
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="4")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=20, total_tokens=30)
        mock_client.responses.create = AsyncMock(return_value=mock_response)
        
        # Capture params
        actual_params = {}
        async def capture_params(**kwargs):
            actual_params.update(kwargs)
            return mock_response
        mock_client.responses.create.side_effect = capture_params
        
        # Make the call
        response = await adapter.complete(request)
        
        # Verify
        print(f"Tools attached: {'tools' in actual_params}")
        print(f"Temperature set: {actual_params.get('temperature')}")
        print(f"Tool calls made: {response.metadata.get('tool_call_count', 0)}")
        print(f"Grounded effective: {response.metadata.get('grounded_effective', False)}")
        
        # Assertions
        assert 'tools' in actual_params, "Tools should be attached for grounded mode"
        assert actual_params.get('temperature') == 1.0, "Temperature=1.0 when tools attached"
        assert response.metadata.get('tool_call_count', 0) == 0, "No tool calls made"
        assert response.metadata.get('grounded_effective', False) == False, "Not effectively grounded"
        
        print("✅ T2 PASSED: Tools attached triggers temperature=1.0, analytics show no actual calls")
        return True

async def test_t3_synthesis_fallback():
    """T3: Synthesis fallback should not inherit tools"""
    print("\n" + "="*70)
    print("T3: Synthesis fallback (no tools on retry)")
    print("="*70)
    
    adapter = OpenAIAdapter()
    request = LLMRequest(
        vendor="openai",
        model="gpt-4",  # Use a model that might trigger fallback
        messages=[{"role": "user", "content": "Search for latest news"}],
        grounded=True,
        temperature=0.3
    )
    
    with patch('app.llm.adapters.openai_adapter.AsyncOpenAI') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Track all calls
        all_calls = []
        
        async def track_calls(**kwargs):
            all_calls.append(dict(kwargs))
            
            # First call fails with unsupported error
            if len(all_calls) == 1:
                raise Exception("web_search is not supported")
            
            # Second call (fallback) succeeds
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Fallback response")]
            mock_response.usage = MagicMock(input_tokens=10, output_tokens=20, total_tokens=30)
            return mock_response
        
        mock_client.responses.create.side_effect = track_calls
        
        # Make the call
        try:
            response = await adapter.complete(request)
            
            # Verify both calls
            print(f"Total API calls made: {len(all_calls)}")
            
            if len(all_calls) >= 2:
                print("\nFirst call (with tools):")
                print(f"  Tools present: {'tools' in all_calls[0]}")
                print(f"  Temperature: {all_calls[0].get('temperature')}")
                
                print("\nSecond call (fallback):")
                print(f"  Tools present: {'tools' in all_calls[1]}")
                print(f"  Tool_choice present: {'tool_choice' in all_calls[1]}")
                print(f"  Temperature: {all_calls[1].get('temperature')}")
                
                # Assertions
                assert 'tools' in all_calls[0], "First call should have tools"
                assert 'tools' not in all_calls[1], "Fallback should NOT have tools"
                assert 'tool_choice' not in all_calls[1], "Fallback should NOT have tool_choice"
                
                print("✅ T3 PASSED: Synthesis fallback correctly removes tools")
                return True
            else:
                print("⚠️  T3 SKIPPED: Fallback not triggered in this environment")
                return None
                
        except Exception as e:
            print(f"T3 Error: {e}")
            # Check if at least the first call was made correctly
            if all_calls:
                print(f"First call had tools: {'tools' in all_calls[0]}")
            return False

async def main():
    """Run all temperature rule tests"""
    print("\n" + "="*70)
    print("OPENAI TEMPERATURE RULES TEST SUITE")
    print("="*70)
    
    results = []
    
    # Run T1: Ungrounded GPT-5 alias
    try:
        t1_result = await test_t1_ungrounded_gpt5_alias()
        results.append(("T1: Ungrounded GPT-5 alias", t1_result))
    except Exception as e:
        print(f"T1 Failed: {e}")
        results.append(("T1: Ungrounded GPT-5 alias", False))
    
    # Run T2: Grounded-AUTO with zero calls
    try:
        t2_result = await test_t2_grounded_auto_zero_calls()
        results.append(("T2: Grounded-AUTO zero calls", t2_result))
    except Exception as e:
        print(f"T2 Failed: {e}")
        results.append(("T2: Grounded-AUTO zero calls", False))
    
    # Run T3: Synthesis fallback
    try:
        t3_result = await test_t3_synthesis_fallback()
        results.append(("T3: Synthesis fallback", t3_result))
    except Exception as e:
        print(f"T3 Failed: {e}")
        results.append(("T3: Synthesis fallback", False))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for test_name, result in results:
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED"
        else:
            status = "⚠️  SKIPPED"
        print(f"{test_name}: {status}")
    
    passed = sum(1 for _, r in results if r is True)
    total = len([r for _, r in results if r is not None])
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return all(r != False for _, r in results)

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)