#!/usr/bin/env python3
"""
Test the new robust tool detection implementation.
"""

import os
import sys
import asyncio
import json

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.tool_detection import detect_openai_websearch_usage, normalize_tool_detection

def test_openai_detection():
    """Test OpenAI web search detection with various response formats"""
    
    print("=" * 60)
    print("Testing Robust OpenAI Tool Detection")
    print("=" * 60)
    
    # Test case 1: Responses API with web_search_call
    response1 = {
        "output": [
            {"type": "web_search_call", "query": "latest AI news"},
            {"type": "web_search_result", "result": {"url": "https://example.com"}},
            {"type": "message", "content": "Here's what I found..."}
        ]
    }
    
    tools_used, call_count, kinds = detect_openai_websearch_usage(response=response1)
    print(f"\nTest 1 - Responses API:")
    print(f"  Tools used: {tools_used}")
    print(f"  Call count: {call_count}")
    print(f"  Kinds: {kinds}")
    assert tools_used == True
    assert call_count == 2  # Both call and result count
    
    # Test case 2: Chat Completions format with tool_calls
    response2 = {
        "choices": [{
            "message": {
                "tool_calls": [
                    {"function": {"name": "web_search"}, "id": "call_123"},
                    {"function": {"name": "web_search_preview"}, "id": "call_456"}
                ]
            }
        }]
    }
    
    tools_used, call_count, kinds = detect_openai_websearch_usage(response=response2)
    print(f"\nTest 2 - Chat Completions:")
    print(f"  Tools used: {tools_used}")
    print(f"  Call count: {call_count}")
    print(f"  Kinds: {kinds}")
    assert tools_used == True
    assert call_count == 2
    
    # Test case 3: No tools used
    response3 = {
        "output": [
            {"type": "message", "content": "Simple response without tools"}
        ]
    }
    
    tools_used, call_count, kinds = detect_openai_websearch_usage(response=response3)
    print(f"\nTest 3 - No tools:")
    print(f"  Tools used: {tools_used}")
    print(f"  Call count: {call_count}")
    print(f"  Kinds: {kinds}")
    assert tools_used == False
    assert call_count == 0
    
    # Test case 4: Streaming events
    stream_events = [
        {"type": "web_search.start", "query": "test"},
        {"type": "response.web_search.call", "id": "123"},
        {"item": {"type": "web_search_result"}},
        {"type": "message.delta", "content": "..."}
    ]
    
    tools_used, call_count, kinds = detect_openai_websearch_usage(stream_events=stream_events)
    print(f"\nTest 4 - Streaming:")
    print(f"  Tools used: {tools_used}")
    print(f"  Call count: {call_count}")
    print(f"  Kinds: {kinds}")
    assert tools_used == True
    assert call_count == 3  # All web_search related events
    
    # Test case 5: Mixed web_search and web_search_preview
    response5 = {
        "output": [
            {"type": "web_search_preview_call"},
            {"type": "web_search_preview_result"},
            {"type": "web_search_call"},
        ]
    }
    
    tools_used, call_count, kinds = detect_openai_websearch_usage(response=response5)
    print(f"\nTest 5 - Mixed variants:")
    print(f"  Tools used: {tools_used}")
    print(f"  Call count: {call_count}")
    print(f"  Kinds: {kinds}")
    assert tools_used == True
    assert call_count == 3
    
    print("\n" + "=" * 60)
    print("✅ All OpenAI detection tests passed!")
    print("=" * 60)

def test_normalized_detection():
    """Test normalized detection across vendors"""
    
    print("\n" + "=" * 60)
    print("Testing Normalized Tool Detection")
    print("=" * 60)
    
    # OpenAI test
    openai_response = {
        "output": [
            {"type": "web_search_call"},
            {"type": "web_search_result"}
        ]
    }
    
    result = normalize_tool_detection("openai", response=openai_response)
    print(f"\nOpenAI normalized:")
    print(f"  {json.dumps(result, indent=2)}")
    assert result["tools_used"] == True
    assert result["tool_call_count"] == 2
    
    # Vertex test
    vertex_response = {
        "grounding_metadata": {
            "step2_tools_invoked": False,  # Means grounding happened
            "grounding_chunks": [
                {"web": {"uri": "https://example.com"}}
            ]
        }
    }
    
    result = normalize_tool_detection("vertex", response=vertex_response)
    print(f"\nVertex normalized:")
    print(f"  {json.dumps(result, indent=2)}")
    assert result["tools_used"] == True
    
    print("\n" + "=" * 60)
    print("✅ All normalized detection tests passed!")
    print("=" * 60)

if __name__ == "__main__":
    test_openai_detection()
    test_normalized_detection()
    print("\n🎉 All tests passed! Robust detection is working correctly.")