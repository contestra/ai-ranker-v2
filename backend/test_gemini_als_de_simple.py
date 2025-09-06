#!/usr/bin/env python3
"""Test Gemini with ALS for Germany (DE) - both ungrounded and grounded via router."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_gemini_with_als():
    # Use the router, not direct adapter
    adapter = UnifiedLLMAdapter()
    
    # Simple ALS context dict for Germany
    als_context_dict = {
        "country_code": "DE",
        "locale": "de-DE"
    }
    
    base_request = {
        "vendor": "gemini_direct",  # Use gemini_direct for Gemini API
        "model": "gemini-2.5-pro",
        "messages": [
            {"role": "user", "content": "tell me the primary health and wellness news during August 2025"}
        ],
        "max_tokens": 1000,
        "temperature": 0.0,
        "als_context": als_context_dict  # Pass as simple dict
    }
    
    print("=" * 80)
    print("TEST 1: GEMINI UNGROUNDED with ALS=DE (via Router)")
    print("=" * 80)
    print(f"Prompt: {base_request['messages'][0]['content']}")
    print(f"ALS Country: {als_context_dict['country_code']}")
    print(f"ALS Locale: {als_context_dict['locale']}")
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
        
        if hasattr(response, 'metadata') and response.metadata:
            print(f"\n📊 Metadata:")
            print(f"  - ALS Present: {response.metadata.get('als_present', False)}")
            print(f"  - ALS Country: {response.metadata.get('als_country', 'N/A')}")
            print(f"  - ALS Locale: {response.metadata.get('als_locale', 'N/A')}")
            print(f"  - ALS SHA256: {response.metadata.get('als_block_sha256', 'N/A')[:16]}..." if response.metadata.get('als_block_sha256') else "N/A")
            print(f"  - ALS Variant: {response.metadata.get('als_variant_id', 'N/A')}")
            print(f"  - Tool Calls: {response.metadata.get('tool_call_count', 0)}")
            print(f"  - Response API: {response.metadata.get('response_api', 'N/A')}")
        
        print(f"\n📝 ANSWER (length: {len(response.content) if response.content else 0} chars):")
        print("-" * 40)
        if response.content:
            # Print first 1500 chars of answer
            print(response.content[:1500])
            if len(response.content) > 1500:
                print(f"\n... (truncated, total {len(response.content)} chars)")
        else:
            print("(No content)")
        print("-" * 40)
        
        if response.citations:
            print(f"\n📚 Citations: {len(response.citations)}")
            for i, cit in enumerate(response.citations[:5], 1):
                print(f"  {i}. {cit}")
        else:
            print("\n📚 Citations: None")
            
        if response.usage:
            print(f"\n💰 Tokens: {response.usage}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("TEST 2: GEMINI GROUNDED with ALS=DE (via Router)")
    print("=" * 80)
    print(f"Prompt: {base_request['messages'][0]['content']}")
    print(f"ALS Country: {als_context_dict['country_code']}")
    print(f"ALS Locale: {als_context_dict['locale']}")
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
        
        if hasattr(response, 'metadata') and response.metadata:
            print(f"\n📊 Metadata:")
            print(f"  - ALS Present: {response.metadata.get('als_present', False)}")
            print(f"  - ALS Country: {response.metadata.get('als_country', 'N/A')}")
            print(f"  - ALS Locale: {response.metadata.get('als_locale', 'N/A')}")
            print(f"  - ALS SHA256: {response.metadata.get('als_block_sha256', 'N/A')[:16]}..." if response.metadata.get('als_block_sha256') else "N/A")
            print(f"  - ALS Variant: {response.metadata.get('als_variant_id', 'N/A')}")
            print(f"  - Tool Calls: {response.metadata.get('tool_call_count', 0)}")
            print(f"  - Grounded Evidence Present: {response.metadata.get('grounded_evidence_present', False)}")
            print(f"  - Anchored Citations: {response.metadata.get('anchored_citations_count', 0)}")
            print(f"  - Unlinked Sources: {response.metadata.get('unlinked_sources_count', 0)}")
            print(f"  - Response API: {response.metadata.get('response_api', 'N/A')}")
        
        print(f"\n📝 ANSWER (length: {len(response.content) if response.content else 0} chars):")
        print("-" * 40)
        if response.content:
            # Print first 2000 chars of answer
            print(response.content[:2000])
            if len(response.content) > 2000:
                print(f"\n... (truncated, total {len(response.content)} chars)")
        else:
            print("(No content)")
        print("-" * 40)
        
        if response.citations:
            print(f"\n📚 Citations with URLs ({len(response.citations)} total):")
            for i, cit in enumerate(response.citations[:10], 1):
                if isinstance(cit, dict):
                    url = cit.get('url', 'N/A')
                    title = cit.get('title', 'No title')
                    domain = cit.get('domain', 'unknown')
                    source_type = cit.get('source_type', 'unknown')
                    print(f"\n  Citation {i}:")
                    print(f"    - Title: {title}")
                    print(f"    - URL: {url}")
                    print(f"    - Domain: {domain}")
                    print(f"    - Type: {source_type}")
                else:
                    print(f"  {i}. {cit}")
            if len(response.citations) > 10:
                print(f"\n  ... and {len(response.citations) - 10} more citations")
        else:
            print("\n📚 Citations: None")
            
        if response.usage:
            print(f"\n💰 Tokens: {response.usage}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gemini_with_als())