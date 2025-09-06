#!/usr/bin/env python3
"""Test GPT-5 with today's news request."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

# Disable provoker for GPT-5 as recommended
os.environ["OPENAI_PROVOKER_ENABLED"] = "false"

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_gpt5_today_news():
    # Use the router
    adapter = UnifiedLLMAdapter()
    
    # Simple ALS context dict for Germany
    als_context_dict = {
        "country_code": "DE",
        "locale": "de-DE"
    }
    
    base_request = {
        "vendor": "openai",
        "model": "gpt-5",  # Use gpt-5 instead of gpt-5-chat-latest
        "messages": [
            {"role": "user", "content": "tell me the news today, September 5th, 2025"}
        ],
        "max_tokens": 1000,
        "temperature": 0.0,
        "als_context": als_context_dict
    }
    
    print("=" * 80)
    print("TEST 1: GPT-5 UNGROUNDED - Today's News")
    print("=" * 80)
    print(f"Prompt: {base_request['messages'][0]['content']}")
    print(f"Model: GPT-5")
    print(f"ALS Country: {als_context_dict['country_code']}")
    print(f"OPENAI_PROVOKER_ENABLED: {os.environ.get('OPENAI_PROVOKER_ENABLED', 'not set')}")
    print("-" * 80)
    
    # Test 1: Ungrounded
    request_ungrounded = LLMRequest(
        **base_request,
        grounded=False
    )
    
    try:
        response = await adapter.complete(request_ungrounded, session=None)
        print(f"\n✅ Success: {response.success}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Tool Calls: {response.metadata.get('tool_call_count', 0) if response.metadata else 0}")
        print(f"Response API: {response.metadata.get('response_api', 'N/A') if response.metadata else 'N/A'}")
        
        print(f"\n📝 ANSWER (length: {len(response.content) if response.content else 0} chars):")
        print("-" * 40)
        if response.content:
            print(response.content[:2000])
            if len(response.content) > 2000:
                print(f"\n... (truncated, total {len(response.content)} chars)")
        else:
            print("(No content)")
        print("-" * 40)
        
        if response.citations:
            print(f"\n📚 Citations: {len(response.citations)}")
        else:
            print("\n📚 Citations: None")
            
        if response.usage:
            print(f"\n💰 Tokens: {response.usage}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("TEST 2: GPT-5 GROUNDED - Today's News")
    print("=" * 80)
    print(f"Prompt: {base_request['messages'][0]['content']}")
    print(f"Model: GPT-5")
    print(f"ALS Country: {als_context_dict['country_code']}")
    print(f"OPENAI_PROVOKER_ENABLED: {os.environ.get('OPENAI_PROVOKER_ENABLED', 'not set')}")
    print("-" * 80)
    
    # Test 2: Grounded
    request_grounded = LLMRequest(
        **base_request,
        grounded=True,
        meta={"grounding_mode": "AUTO"}
    )
    
    try:
        response = await adapter.complete(request_grounded, session=None)
        print(f"\n✅ Success: {response.success}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Tool Calls: {response.metadata.get('tool_call_count', 0) if response.metadata else 0}")
        print(f"Response API: {response.metadata.get('response_api', 'N/A') if response.metadata else 'N/A'}")
        
        # Check for why_not_grounded if grounding didn't happen
        if response.metadata and not response.grounded_effective:
            why_not = response.metadata.get('why_not_grounded')
            if why_not:
                print(f"⚠️ Why not grounded: {why_not}")
        
        print(f"\n📝 ANSWER (length: {len(response.content) if response.content else 0} chars):")
        print("-" * 40)
        if response.content:
            print(response.content[:2000])
            if len(response.content) > 2000:
                print(f"\n... (truncated, total {len(response.content)} chars)")
        else:
            print("(No content - known GPT-5 grounded issue)")
        print("-" * 40)
        
        if response.citations:
            print(f"\n📚 Citations with URLs ({len(response.citations)} total):")
            for i, cit in enumerate(response.citations[:10], 1):
                if isinstance(cit, dict):
                    url = cit.get('url', 'N/A')
                    title = cit.get('title', 'No title')
                    domain = cit.get('domain', 'unknown')
                    print(f"\n  Citation {i}:")
                    print(f"    - Title: {title}")
                    print(f"    - URL: {url}")
                    print(f"    - Domain: {domain}")
                else:
                    print(f"  {i}. {cit}")
        else:
            print("\n📚 Citations: None")
            
        if response.usage:
            print(f"\n💰 Tokens: {response.usage}")
            
        # Show search queries if available
        if response.metadata and response.metadata.get('search_queries'):
            print(f"\n🔍 Search queries performed: {response.metadata['search_queries']}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gpt5_today_news())