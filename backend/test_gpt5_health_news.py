#!/usr/bin/env python3
"""Test GPT-5 with health and wellness news query - both ungrounded and grounded."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_gpt5_health_news():
    router = UnifiedLLMAdapter()
    
    # Create ALS context for Germany
    als_context = ALSContext(
        locale="de-DE",
        country_code="DE",
        als_block="[Location: Germany, Language: German]"
    )
    
    # The query
    query = "tell me the primary health and wellness news during August 2025"
    
    print("=" * 80)
    print("TEST 1: GPT-5 UNGROUNDED WITH ALS=DE")
    print("=" * 80)
    print(f"\nQuery: {query}")
    print(f"ALS: {als_context.country_code} ({als_context.locale})")
    print("-" * 80)
    
    # Test 1: Ungrounded
    request_ungrounded = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[{"role": "user", "content": query}],
        temperature=0.7,
        grounded=False,
        als_context=als_context
    )
    
    try:
        print("\nSending ungrounded request to GPT-5...")
        response = await router.complete(request_ungrounded)
        
        print("\n=== UNGROUNDED RESPONSE ===")
        print(f"\nContent:\n{'-' * 60}")
        print(response.content)
        print('-' * 60)
        
        print(f"\nModel Version: {response.model_version}")
        print(f"Grounded Effective: {response.grounded_effective}")
        
        if response.metadata:
            print(f"\nKey Metadata:")
            for key in ['als_present', 'als_country', 'finish_reason', 'tool_call_count', 'fallback_used']:
                if key in response.metadata:
                    print(f"  {key}: {response.metadata[key]}")
            
        if response.citations:
            print(f"\nCitations: {len(response.citations)}")
        else:
            print("\nNo citations (expected for ungrounded)")
            
        if response.usage:
            print(f"\nToken Usage:")
            print(f"  Input: {response.usage.get('input_tokens', 0)}")
            print(f"  Output: {response.usage.get('output_tokens', 0)}")
            print(f"  Total: {response.usage.get('total_tokens', 0)}")
            
    except Exception as e:
        print(f"\nError in ungrounded request: {e}")
    
    print("\n" + "=" * 80)
    print("TEST 2: GPT-5 GROUNDED WITH ALS=DE")
    print("=" * 80)
    print(f"\nQuery: {query}")
    print(f"ALS: {als_context.country_code} ({als_context.locale})")
    print("-" * 80)
    
    # Test 2: Grounded
    request_grounded = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[{"role": "user", "content": query}],
        temperature=0.7,
        grounded=True,
        als_context=als_context,
        meta={"grounding_mode": "AUTO"}  # Use AUTO mode
    )
    
    try:
        print("\nSending grounded request to GPT-5...")
        response = await router.complete(request_grounded)
        
        print("\n=== GROUNDED RESPONSE ===")
        print(f"\nContent:\n{'-' * 60}")
        print(response.content if response.content else "[No content in response]")
        print('-' * 60)
        
        print(f"\nModel Version: {response.model_version}")
        print(f"Grounded Effective: {response.grounded_effective}")
        
        if response.metadata:
            print(f"\nKey Metadata:")
            important_keys = [
                'als_present', 'als_country', 'finish_reason',
                'web_tool_type', 'web_tool_type_initial', 'web_tool_type_final',
                'tool_call_count', 'grounded_evidence_present',
                'citation_count', 'anchored_citations_count',
                'provoker_retry_used', 'initial_empty_reason'
            ]
            for key in important_keys:
                if key in response.metadata:
                    print(f"  {key}: {response.metadata[key]}")
            
        if response.citations:
            print(f"\n=== CITATIONS ({len(response.citations)}) ===")
            for i, citation in enumerate(response.citations[:10], 1):  # Show first 10
                print(f"\nCitation {i}:")
                if isinstance(citation, dict):
                    if 'url' in citation:
                        print(f"  URL: {citation['url']}")
                    if 'title' in citation:
                        print(f"  Title: {citation['title']}")
                    if 'snippet' in citation:
                        snippet = citation['snippet']
                        if len(snippet) > 150:
                            print(f"  Snippet: {snippet[:150]}...")
                        else:
                            print(f"  Snippet: {snippet}")
                else:
                    print(f"  {citation}")
        else:
            print("\nNo citations found")
            
        # Extract and display search queries if available
        if response.metadata and 'search_queries' in response.metadata:
            queries = response.metadata['search_queries']
            print(f"\n=== SEARCH QUERIES ({len(queries)}) ===")
            for i, q in enumerate(queries[:5], 1):  # Show first 5
                print(f"  {i}. {q}")
                
        if response.usage:
            print(f"\nToken Usage:")
            print(f"  Input: {response.usage.get('input_tokens', 0)}")
            print(f"  Output: {response.usage.get('output_tokens', 0)}")
            print(f"  Total: {response.usage.get('total_tokens', 0)}")
            
    except Exception as e:
        print(f"\nError in grounded request: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gpt5_health_news())