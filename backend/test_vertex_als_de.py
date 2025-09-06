#!/usr/bin/env python3
"""Test Vertex with ALS for Germany (DE) - both ungrounded and grounded."""

import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_vertex_with_als():
    adapter = UnifiedLLMAdapter()
    
    # Create ALS context for Germany
    from app.services.als.als_builder import ALSBuilder
    
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block("DE")
    
    als_context = ALSContext(
        locale="de-DE",
        country_code="DE",
        als_block=als_block,
        als_variant_id="de_v1"
    )
    
    base_request = {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "messages": [
            {"role": "user", "content": "tell me the primary health and wellness news during August 2025"}
        ],
        "max_tokens": 1000,
        "temperature": 0.0,
        "als_context": {
            "locale": als_context.locale,
            "country_code": als_context.country_code,
            "als_block": als_context.als_block,
            "als_variant_id": als_context.als_variant_id
        }
    }
    
    print("=" * 80)
    print("TEST 1: VERTEX UNGROUNDED with ALS=DE")
    print("=" * 80)
    print(f"Prompt: {base_request['messages'][0]['content']}")
    print(f"ALS Country: {als_context.country_code}")
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
        
        if hasattr(response, 'metadata'):
            print(f"\n📊 Metadata:")
            print(f"  - Region: {response.metadata.get('region', 'N/A')}")
            print(f"  - ALS Present: {response.metadata.get('als_present', False)}")
            print(f"  - ALS Country: {response.metadata.get('als_country', 'N/A')}")
            print(f"  - Tool Calls: {response.metadata.get('tool_call_count', 0)}")
            print(f"  - Response API: {response.metadata.get('response_api', 'N/A')}")
        
        print(f"\n📝 ANSWER (length: {len(response.content)} chars):")
        print("-" * 40)
        print(response.content)
        print("-" * 40)
        
        if response.citations:
            print(f"\n📚 Citations: {len(response.citations)}")
            for i, cit in enumerate(response.citations, 1):
                print(f"  {i}. {cit}")
        else:
            print("\n📚 Citations: None")
            
        if response.usage:
            print(f"\n💰 Tokens: {response.usage}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("\n" + "=" * 80)
    print("TEST 2: VERTEX GROUNDED with ALS=DE")
    print("=" * 80)
    print(f"Prompt: {base_request['messages'][0]['content']}")
    print(f"ALS Country: {als_context.country_code}")
    print("-" * 80)
    
    # Test 2: Grounded
    request_grounded = LLMRequest(
        **base_request,
        grounded=True,
        meta={"grounding_mode": "AUTO"}
    )
    
    # Use us-central1 for grounding
    os.environ["VERTEX_LOCATION"] = "us-central1"
    
    try:
        response = await adapter.complete(request_grounded, session=None)
        print(f"\n✅ Success: {response.success}")
        print(f"Grounded Effective: {response.grounded_effective}")
        
        if hasattr(response, 'metadata'):
            print(f"\n📊 Metadata:")
            print(f"  - Region: {response.metadata.get('region', 'N/A')}")
            print(f"  - ALS Present: {response.metadata.get('als_present', False)}")
            print(f"  - ALS Country: {response.metadata.get('als_country', 'N/A')}")
            print(f"  - Tool Calls: {response.metadata.get('tool_call_count', 0)}")
            print(f"  - Grounded Evidence Present: {response.metadata.get('grounded_evidence_present', False)}")
            print(f"  - Anchored Citations: {response.metadata.get('anchored_citations_count', 0)}")
            print(f"  - Unlinked Sources: {response.metadata.get('unlinked_sources_count', 0)}")
            print(f"  - Response API: {response.metadata.get('response_api', 'N/A')}")
        
        print(f"\n📝 ANSWER (length: {len(response.content)} chars):")
        print("-" * 40)
        print(response.content)
        print("-" * 40)
        
        if response.citations:
            print(f"\n📚 Citations with URLs ({len(response.citations)} total):")
            for i, cit in enumerate(response.citations, 1):
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
        else:
            print("\n📚 Citations: None")
            
        if response.usage:
            print(f"\n💰 Tokens: {response.usage}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_vertex_with_als())