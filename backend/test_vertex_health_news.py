#!/usr/bin/env python3
"""Test Vertex with health and wellness news query - both ungrounded and grounded."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_vertex_health_news():
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
    print("TEST 1: VERTEX UNGROUNDED WITH ALS=DE")
    print("=" * 80)
    print(f"\nQuery: {query}")
    print(f"ALS: {als_context.country_code} ({als_context.locale})")
    print("-" * 80)
    
    # Test 1: Ungrounded
    request_ungrounded = LLMRequest(
        vendor="vertex",
        model="gemini-1.5-flash-002",
        messages=[{"role": "user", "content": query}],
        temperature=0.7,
        grounded=False,
        als_context=als_context
    )
    
    try:
        print("\nSending ungrounded request...")
        response = await router.complete(request_ungrounded)
        
        print("\n=== UNGROUNDED RESPONSE ===")
        print(f"\nContent:\n{response.content}")
        print(f"\nModel Version: {response.model_version}")
        print(f"Grounded Effective: {response.grounded_effective}")
        
        if response.metadata:
            print(f"\nMetadata:")
            for key, value in response.metadata.items():
                if key.startswith('als_'):
                    print(f"  {key}: {value}")
            print(f"  finish_reason: {response.metadata.get('finish_reason')}")
            print(f"  tool_call_count: {response.metadata.get('tool_call_count', 0)}")
            
        if response.citations:
            print(f"\nCitations: {len(response.citations)}")
            for i, citation in enumerate(response.citations[:5], 1):
                print(f"  {i}. {citation}")
        else:
            print("\nNo citations (expected for ungrounded)")
            
        if response.usage:
            print(f"\nUsage: {response.usage}")
            
    except Exception as e:
        print(f"\nError in ungrounded request: {e}")
    
    print("\n" + "=" * 80)
    print("TEST 2: VERTEX GROUNDED WITH ALS=DE")
    print("=" * 80)
    print(f"\nQuery: {query}")
    print(f"ALS: {als_context.country_code} ({als_context.locale})")
    print("-" * 80)
    
    # Test 2: Grounded
    request_grounded = LLMRequest(
        vendor="vertex",
        model="gemini-1.5-flash-002",
        messages=[{"role": "user", "content": query}],
        temperature=0.7,
        grounded=True,
        als_context=als_context,
        meta={"grounding_mode": "AUTO"}  # Use AUTO mode
    )
    
    try:
        print("\nSending grounded request...")
        response = await router.complete(request_grounded)
        
        print("\n=== GROUNDED RESPONSE ===")
        print(f"\nContent:\n{response.content}")
        print(f"\nModel Version: {response.model_version}")
        print(f"Grounded Effective: {response.grounded_effective}")
        
        if response.metadata:
            print(f"\nMetadata:")
            for key, value in response.metadata.items():
                if key.startswith('als_'):
                    print(f"  {key}: {value}")
            print(f"  finish_reason: {response.metadata.get('finish_reason')}")
            print(f"  web_tool_type: {response.metadata.get('web_tool_type')}")
            print(f"  tool_call_count: {response.metadata.get('tool_call_count', 0)}")
            print(f"  grounded_evidence_present: {response.metadata.get('grounded_evidence_present')}")
            print(f"  citation_count: {response.metadata.get('citation_count', 0)}")
            
        if response.citations:
            print(f"\n=== CITATIONS ({len(response.citations)}) ===")
            for i, citation in enumerate(response.citations, 1):
                print(f"\nCitation {i}:")
                if isinstance(citation, dict):
                    for key, value in citation.items():
                        if key == 'url':
                            print(f"  URL: {value}")
                        elif key == 'title':
                            print(f"  Title: {value}")
                        elif key == 'snippet':
                            print(f"  Snippet: {value[:200]}..." if len(str(value)) > 200 else f"  Snippet: {value}")
                        elif key == 'grounding_confidence':
                            print(f"  Confidence: {value}")
                else:
                    print(f"  {citation}")
        else:
            print("\nNo citations found")
            
        # Extract and display search queries if available
        if response.metadata and 'search_queries' in response.metadata:
            queries = response.metadata['search_queries']
            print(f"\n=== SEARCH QUERIES ({len(queries)}) ===")
            for i, q in enumerate(queries, 1):
                print(f"  {i}. {q}")
                
        if response.usage:
            print(f"\nUsage: {response.usage}")
            
    except Exception as e:
        print(f"\nError in grounded request: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vertex_health_news())