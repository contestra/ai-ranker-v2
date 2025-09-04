#!/usr/bin/env python3
"""
Test OpenAI adapter with grounded mode, NO ALS, August 2025 health news.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

# Disable rate limiter for testing
os.environ["OAI_DISABLE_LIMITER"] = "1"

# Ensure 6000 tokens for grounded runs
os.environ["OAI_GROUNDED_MAX_TOKENS"] = "6000"


async def test_openai_grounded_no_als():
    """Test OpenAI with grounded AUTO mode, NO ALS."""
    print("\n" + "="*80)
    print("OPENAI GROUNDED TEST - NO ALS")
    print("="*80)
    
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    # Initialize adapter
    adapter = OpenAIAdapter()
    
    # Create request with AUTO mode - NO ALS, just the prompt
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "tell me the primary health and wellness news during August 2025"}
        ],
        grounded=True,
        temperature=0.7,
        max_tokens=6000,
        meta={"grounding_mode": "AUTO"}
    )
    
    print(f"\n📋 Configuration:")
    print(f"  • Model: {request.model}")
    print(f"  • Grounding mode: AUTO")
    print(f"  • Max tokens: 6000")
    print(f"  • ALS: NONE (no locale information sent)")
    print(f"  • Prompt: 'tell me the primary health and wellness news during August 2025'")
    
    print(f"\n⏳ Calling OpenAI adapter...")
    start = datetime.now()
    
    try:
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=120),
            timeout=120
        )
        
        duration = (datetime.now() - start).total_seconds()
        print(f"\n✅ Response received in {duration:.1f}s")
        
        # Extract metadata
        metadata = response.metadata or {}
        
        print(f"\n" + "="*80)
        print("METADATA")
        print("="*80)
        print(f"Response API: {metadata.get('response_api', 'N/A')}")
        print(f"Tool calls: {metadata.get('tool_call_count', 0)}")
        print(f"Grounded effective: {metadata.get('grounded_effective', False)}")
        print(f"Web tool type: {metadata.get('web_tool_type', 'N/A')}")
        print(f"Why not grounded: {metadata.get('why_not_grounded', 'N/A')}")
        
        # Usage stats
        if response.usage:
            print(f"\nToken Usage:")
            print(f"  • Prompt tokens: {response.usage.get('prompt_tokens', 0)}")
            print(f"  • Completion tokens: {response.usage.get('completion_tokens', 0)}")
            print(f"  • Total tokens: {response.usage.get('total_tokens', 0)}")
        
        # Tool evidence details
        if metadata.get('tool_evidence'):
            print(f"\n" + "="*80)
            print("TOOL EVIDENCE (Citations)")
            print("="*80)
            evidence = metadata['tool_evidence']
            if isinstance(evidence, list):
                for i, item in enumerate(evidence, 1):
                    print(f"\nCitation {i}:")
                    print(f"  Type: {item.get('type', 'N/A')}")
                    if item.get('search_results'):
                        for j, result in enumerate(item['search_results'][:3], 1):  # Show first 3
                            print(f"  Result {j}:")
                            print(f"    • Title: {result.get('title', 'N/A')}")
                            print(f"    • URL: {result.get('url', 'N/A')}")
                            print(f"    • Snippet: {result.get('snippet', 'N/A')[:150]}...")
        
        # Print full response
        print(f"\n" + "="*80)
        print("FULL RESPONSE CONTENT")
        print("="*80)
        print(response.content)
        
        # If there are inline citations, extract URLs
        if "[" in response.content and "]" in response.content:
            print(f"\n" + "="*80)
            print("INLINE CITATION URLS")
            print("="*80)
            
            # Extract bracketed numbers and try to find URLs
            import re
            citations = re.findall(r'\[(\d+)\]', response.content)
            unique_citations = sorted(set(int(c) for c in citations))
            
            print(f"Found {len(unique_citations)} unique citations: {unique_citations}")
            
            # Try to extract URLs from tool evidence if available
            if metadata.get('tool_evidence'):
                all_urls = []
                for item in metadata['tool_evidence']:
                    if item.get('search_results'):
                        for result in item['search_results']:
                            if result.get('url'):
                                all_urls.append(result['url'])
                
                if all_urls:
                    print(f"\nAll URLs from search results:")
                    for i, url in enumerate(all_urls[:20], 1):  # Limit to first 20
                        print(f"  [{i}] {url}")
        
        return True
        
    except asyncio.TimeoutError:
        print(f"❌ Request timed out after 120 seconds")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_openai_grounded_no_als())
    sys.exit(0 if success else 1)