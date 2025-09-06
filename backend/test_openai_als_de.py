#!/usr/bin/env python3
"""Test OpenAI adapters with ALS=DE parameter"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.services.als.als_builder import ALSBuilder

async def test_openai_with_als():
    """Test OpenAI with ALS=DE for health news query"""
    
    prompt = "tell me the primary health and wellness news during August 2025"
    als_country = "DE"
    als_locale = "de-DE"
    
    # Build ALS block
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block(als_country)
    
    # Test 1: OpenAI Ungrounded with ALS=DE
    print("=" * 80)
    print(f"TEST 1: OPENAI (GPT-5-2025-08-07) UNGROUNDED with ALS={als_country}")
    print("=" * 80)
    print(f"Prompt: {prompt}")
    print(f"ALS Country: {als_country}")
    print(f"ALS Locale: {als_locale}")
    print("-" * 80)
    print()
    
    try:
        adapter = UnifiedLLMAdapter()
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": prompt}],
            grounded=False,
            temperature=1.0,
            als_context=ALSContext(
                country_code=als_country,
                locale=als_locale,
                als_block=als_block,
                als_variant_id="de_v1"
            )
        )
        result = await asyncio.wait_for(adapter.complete(request), timeout=60)
        
        success = result.success
        print(f"✅ Success: {success}")
        
        if success:
            metadata = result.metadata or {}
            print(f"Grounded Effective: {metadata.get('grounded_effective', False)}")
            print()
            
            # Print metadata
            print("📊 Metadata:")
            if 'als_present' in metadata:
                print(f"  - ALS Present: {metadata['als_present']}")
            if 'als_country' in metadata:
                print(f"  - ALS Country: {metadata['als_country']}")
            if 'als_locale' in metadata:
                print(f"  - ALS Locale: {metadata['als_locale']}")
            if 'tool_calls' in metadata:
                print(f"  - Tool Calls: {metadata['tool_calls']}")
            if 'response_api' in metadata:
                print(f"  - Response API: {metadata['response_api']}")
            print()
            
            # Print answer
            answer = result.content or ''
            print(f"📝 ANSWER (length: {len(answer)} chars):")
            print("-" * 40)
            print(answer if answer else "(No content)")
            print("-" * 40)
            print()
            
            # Print citations
            citations = result.citations or []
            if citations:
                print(f"📚 Citations: {len(citations)} sources")
                for i, citation in enumerate(citations, 1):
                    print(f"  [{i}] {citation.get('title', 'No title')}")
                    if 'url' in citation:
                        print(f"      URL: {citation['url']}")
            else:
                print("📚 Citations: None")
            print()
            
            # Print tokens
            tokens = result.usage or {}
            if tokens:
                print(f"💰 Tokens: {tokens}")
        else:
            print(f"❌ Error: {result.error or 'Unknown error'}")
    except asyncio.TimeoutError:
        print("❌ Error: Test timed out after 60 seconds")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    print()
    
    # Test 2: OpenAI Grounded with ALS=DE
    print("=" * 80)
    print(f"TEST 2: OPENAI (GPT-5-2025-08-07) GROUNDED with ALS={als_country}")
    print("=" * 80)
    print(f"Prompt: {prompt}")
    print(f"ALS Country: {als_country}")
    print(f"ALS Locale: {als_locale}")
    print("-" * 80)
    print()
    
    try:
        adapter = UnifiedLLMAdapter()
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-2025-08-07",
            messages=[{"role": "user", "content": prompt}],
            grounded=True,
            temperature=1.0,
            als_context=ALSContext(
                country_code=als_country,
                locale=als_locale,
                als_block=als_block,
                als_variant_id="de_v1"
            )
        )
        result = await asyncio.wait_for(adapter.complete(request), timeout=60)
        
        success = result.success
        print(f"✅ Success: {success}")
        
        if success:
            metadata = result.metadata or {}
            print(f"Grounded Effective: {metadata.get('grounded_effective', False)}")
            print()
            
            # Print metadata
            print("📊 Metadata:")
            if 'als_present' in metadata:
                print(f"  - ALS Present: {metadata['als_present']}")
            if 'als_country' in metadata:
                print(f"  - ALS Country: {metadata['als_country']}")
            if 'als_locale' in metadata:
                print(f"  - ALS Locale: {metadata['als_locale']}")
            if 'tool_calls' in metadata:
                print(f"  - Tool Calls: {metadata['tool_calls']}")
            if 'grounded_evidence_present' in metadata:
                print(f"  - Grounded Evidence Present: {metadata['grounded_evidence_present']}")
            if 'anchored_citations' in metadata:
                print(f"  - Anchored Citations: {metadata['anchored_citations']}")
            if 'unlinked_sources' in metadata:
                print(f"  - Unlinked Sources: {metadata['unlinked_sources']}")
            if 'response_api' in metadata:
                print(f"  - Response API: {metadata['response_api']}")
            print()
            
            # Print answer
            answer = result.content or ''
            print(f"📝 ANSWER (length: {len(answer)} chars):")
            print("-" * 40)
            if answer:
                # Print first 500 chars
                print(answer[:500] + ("..." if len(answer) > 500 else ""))
            else:
                print("(No content)")
            print("-" * 40)
            print()
            
            # Print citations with URLs
            citations = result.citations or []
            if citations:
                print(f"📚 Citations with URLs ({len(citations)} total):")
                print()
                for i, citation in enumerate(citations[:10], 1):  # Show first 10
                    print(f"  Citation {i}:")
                    print(f"    - Title: {citation.get('title', 'No title')}")
                    if 'url' in citation:
                        print(f"    - URL: {citation['url']}")
                    if 'domain' in citation:
                        print(f"    - Domain: {citation['domain']}")
                    print()
                if len(citations) > 10:
                    print(f"  ... and {len(citations) - 10} more citations")
            else:
                print("📚 Citations: None")
            print()
            
            # Print tokens
            tokens = result.usage or {}
            if tokens:
                print(f"💰 Tokens: {tokens}")
        else:
            print(f"❌ Error: {result.error or 'Unknown error'}")
    except asyncio.TimeoutError:
        print("❌ Error: Test timed out after 60 seconds")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_openai_with_als())