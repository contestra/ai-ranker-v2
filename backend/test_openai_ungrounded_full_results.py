#!/usr/bin/env python3
"""
Test OpenAI ungrounded with full results output
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from pprint import pprint

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_openai_ungrounded_full():
    """Test OpenAI ungrounded with detailed output."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # German ALS
    als_template = "de-DE, Deutschland, Europe/Berlin timezone"
    
    messages = [
        {"role": "user", "content": f"{als_template}\n\nTell me the primary health and wellness news during August 2025"}
    ]
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=messages,
        grounded=False,  # UNGROUNDED mode
        max_tokens=1000
    )
    
    print("="*80)
    print("OPENAI UNGROUNDED TEST - FULL RESULTS")
    print("="*80)
    print(f"Model: {request.model}")
    print(f"ALS: {als_template}")
    print(f"Prompt: Tell me the primary health and wellness news during August 2025")
    print(f"Grounded: False (UNGROUNDED mode)")
    print(f"Max tokens: {request.max_tokens}")
    print("="*80)
    
    try:
        print("\nMaking request...")
        response = await adapter.complete(request, timeout=60)
        
        print("\n" + "="*80)
        print("RESPONSE METADATA")
        print("="*80)
        metadata = response.metadata or {}
        print(f"Success: {response.success}")
        print(f"Model Version: {response.model_version}")
        print(f"Vendor: {response.vendor}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Response API: {metadata.get('response_api', 'unknown')}")
        print(f"Tool Call Count: {metadata.get('tool_call_count', 0)}")
        print(f"Grounded Evidence Present: {metadata.get('grounded_evidence_present', False)}")
        print(f"Fallback Used: {metadata.get('fallback_used', False)}")
        print(f"Text Source: {metadata.get('text_source', 'unknown')}")
        print(f"Latency: {response.latency_ms}ms")
        
        print("\n" + "="*80)
        print("USAGE STATISTICS")
        print("="*80)
        if response.usage:
            print(f"Prompt Tokens: {response.usage.get('prompt_tokens', 0)}")
            print(f"Completion Tokens: {response.usage.get('completion_tokens', 0)}")
            print(f"Reasoning Tokens: {response.usage.get('reasoning_tokens', 0)}")
            print(f"Total Tokens: {response.usage.get('total_tokens', 0)}")
        else:
            print("No usage data available")
        
        print("\n" + "="*80)
        print("CITATIONS")
        print("="*80)
        if response.citations:
            for i, citation in enumerate(response.citations, 1):
                print(f"\nCitation {i}:")
                print(f"  URL: {citation.get('url', 'N/A')}")
                print(f"  Title: {citation.get('title', 'N/A')}")
                if 'snippet' in citation:
                    print(f"  Snippet: {citation['snippet'][:200]}...")
        else:
            print("No structured citations in response (expected for ungrounded)")
        
        # Extract URLs from content
        print("\n" + "="*80)
        print("EXTRACTED URLs FROM CONTENT")
        print("="*80)
        import re
        urls = re.findall(r'https?://[^\s\)]+', response.content)
        if urls:
            unique_urls = list(set(urls))
            for url in unique_urls:
                print(f"  - {url}")
        else:
            print("No URLs found in content (expected for ungrounded)")
        
        print("\n" + "="*80)
        print("FULL RESPONSE CONTENT")
        print("="*80)
        print(response.content)
        
        print("\n" + "="*80)
        print("CONTENT ANALYSIS")
        print("="*80)
        content_lower = response.content.lower()
        
        # Check response type
        if "cannot" in content_lower or "don't have" in content_lower or "unable" in content_lower:
            print("Response Type: DECLINED (Model refused to speculate about future)")
        elif len(response.content) > 500:
            print("Response Type: SPECULATIVE (Model provided detailed predictions)")
        else:
            print("Response Type: BRIEF")
        
        # Check for German context
        german_terms = ["deutschland", "berlin", "bundesl", "stiko", "rki", "gesundheit"]
        found_german = [term for term in german_terms if term in content_lower]
        print(f"German terms found: {found_german if found_german else 'None'}")
        
        # Check for date references
        date_terms = ["august", "2025", "aug", "future", "will", "would"]
        found_dates = [term for term in date_terms if term in content_lower]
        print(f"Date/temporal references: {found_dates if found_dates else 'None'}")
        
        # Check for health topics
        health_topics = ["health", "wellness", "medical", "disease", "vaccine", "therapy", "treatment", "gesundheit", "medizin"]
        found_health = [term for term in health_topics if term in content_lower]
        print(f"Health topics: {found_health if found_health else 'None'}")
        
        # Check for speculation markers
        speculation_markers = ["could", "might", "may", "potentially", "likely", "expect", "würde", "könnte"]
        found_speculation = [marker for marker in speculation_markers if marker in content_lower]
        print(f"Speculation markers: {found_speculation if found_speculation else 'None'}")
        
        # Check for disclaimer/limitation statements
        disclaimer_markers = ["cannot", "don't have", "unable", "knowledge cutoff", "can't provide", "nicht möglich"]
        found_disclaimers = [marker for marker in disclaimer_markers if marker in content_lower]
        print(f"Disclaimer markers: {found_disclaimers if found_disclaimers else 'None'}")
        
        print("\n" + "="*80)
        print("UNGROUNDED BEHAVIOR ANALYSIS")
        print("="*80)
        
        # Analyze behavior differences from grounded
        print("Key Observations:")
        print(f"1. Web search performed: No (ungrounded mode)")
        print(f"2. Content length: {len(response.content)} characters")
        print(f"3. Language: {'German' if any(term in content_lower for term in ['der', 'die', 'das', 'und', 'ist']) else 'English'}")
        
        if found_disclaimers:
            print("4. Model behavior: Conservative - declined to speculate about future")
            print("   - This is typical for ungrounded GPT-4 with future dates")
        elif found_speculation:
            print("4. Model behavior: Speculative - provided predictions without real data")
            print("   - Content is generated without web search verification")
        else:
            print("4. Model behavior: Direct response without caveats")
        
        print("\n" + "="*80)
        print("COMPARISON TO GROUNDED MODE")
        print("="*80)
        print("Grounded mode would have:")
        print("  - Performed web_search tool call")
        print("  - Provided URLs with utm_source=openai")
        print("  - Had grounded_effective=True")
        print("  - Included real August 2025 news if available")
        print("\nUngrounded mode:")
        print("  - No tool calls")
        print("  - No URLs or citations")
        print("  - grounded_effective=False")
        print("  - Either declined or speculated about future")
        
        print("\n" + "="*80)
        print("TEST RESULT: ✅ SUCCESS")
        print("="*80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        print("\n" + "="*80)
        print("TEST RESULT: ❌ FAILED")
        print("="*80)
        
        return False


if __name__ == "__main__":
    success = asyncio.run(test_openai_ungrounded_full())
    sys.exit(0 if success else 1)