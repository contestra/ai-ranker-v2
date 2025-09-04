#!/usr/bin/env python3
"""
Test OpenAI grounded through router with German ALS - full results output
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_router_grounded_de():
    """Test OpenAI grounded through router with German ALS."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest, ALSContext
    
    router = UnifiedLLMAdapter()
    
    # German ALS context - using dict format
    als_context = {
        "country_code": "DE",
        "locale": "de-DE",
        "timezone": "Europe/Berlin",
        "detected_location": "Deutschland"
    }
    
    # Build request with ALS
    messages = [
        {"role": "user", "content": "Tell me the primary health and wellness news during August 2025"}
    ]
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=messages,
        grounded=True,
        max_tokens=6000,  # Full grounded limit
        meta={"grounding_mode": "AUTO"},
        als_context=als_context,
        template_id="health_news_test",
        run_id="test_run_001"
    )
    
    print("="*80)
    print("OPENAI GROUNDED TEST VIA ROUTER - FULL RESULTS")
    print("="*80)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print(f"Model: {request.model}")
    print(f"ALS Context:")
    print(f"  - Country: {als_context['country_code']}")
    print(f"  - Locale: {als_context['locale']}")
    print(f"  - Timezone: {als_context['timezone']}")
    print(f"  - Location: {als_context['detected_location']}")
    print(f"Prompt: Tell me the primary health and wellness news during August 2025")
    print(f"Grounded: True (AUTO mode)")
    print(f"Max tokens: {request.max_tokens}")
    print("="*80)
    
    try:
        print("\nMaking request through router...")
        response = await router.complete(request)
        
        print("\n" + "="*80)
        print("ROUTER METADATA")
        print("="*80)
        router_meta = response.metadata or {}
        print(f"Circuit Breaker Status: {router_meta.get('circuit_breaker_status', 'unknown')}")
        print(f"Reasoning Hint Dropped: {router_meta.get('reasoning_hint_dropped', False)}")
        print(f"Thinking Hint Dropped: {router_meta.get('thinking_hint_dropped', False)}")
        print(f"Capabilities Applied: {request.metadata.get('capabilities', {})}")
        
        print("\n" + "="*80)
        print("RESPONSE METADATA")
        print("="*80)
        print(f"Success: {response.success}")
        print(f"Model Version: {response.model_version}")
        print(f"Vendor: {response.vendor}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Response API: {router_meta.get('response_api', 'unknown')}")
        print(f"Web Tool Type: {router_meta.get('web_tool_type', 'none')}")
        print(f"Tool Call Count: {router_meta.get('tool_call_count', 0)}")
        print(f"Tool Types: {router_meta.get('tool_types', [])}")
        print(f"Grounded Evidence Present: {router_meta.get('grounded_evidence_present', False)}")
        print(f"Latency: {response.latency_ms}ms")
        
        print("\n" + "="*80)
        print("ALS METADATA")
        print("="*80)
        print(f"ALS Present: {router_meta.get('als_present', False)}")
        print(f"ALS Country: {router_meta.get('als_country', 'N/A')}")
        print(f"ALS Variant ID: {router_meta.get('als_variant_id', 'N/A')}")
        print(f"ALS Block SHA256: {router_meta.get('als_block_sha256', 'N/A')[:16]}...")
        print(f"ALS NFC Length: {router_meta.get('als_nfc_length', 0)}")
        
        print("\n" + "="*80)
        print("USAGE STATISTICS")
        print("="*80)
        if response.usage:
            print(f"Prompt Tokens: {response.usage.get('prompt_tokens', 0)}")
            print(f"Completion Tokens: {response.usage.get('completion_tokens', 0)}")
            print(f"Reasoning Tokens: {response.usage.get('reasoning_tokens', 0)}")
            print(f"Total Tokens: {response.usage.get('total_tokens', 0)}")
            
            # Calculate costs (rough estimates)
            prompt_cost = response.usage.get('prompt_tokens', 0) * 0.000005  # $5/1M tokens
            completion_cost = response.usage.get('completion_tokens', 0) * 0.000015  # $15/1M tokens
            total_cost = prompt_cost + completion_cost
            print(f"Estimated Cost: ${total_cost:.4f}")
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
                print(f"  Source Type: {citation.get('source_type', 'N/A')}")
                if 'snippet' in citation:
                    print(f"  Snippet: {citation['snippet'][:200]}...")
        else:
            print("No structured citations in response object")
        
        # Extract URLs from content
        print("\n" + "="*80)
        print("EXTRACTED URLs FROM CONTENT")
        print("="*80)
        urls = re.findall(r'https?://[^\s\)\]]+', response.content)
        if urls:
            unique_urls = list(set(urls))
            for i, url in enumerate(unique_urls, 1):
                # Clean up URL (remove trailing punctuation)
                url = url.rstrip('.,;:)')
                print(f"{i}. {url}")
            print(f"\nTotal unique URLs: {len(unique_urls)}")
        else:
            print("No URLs found in content")
        
        print("\n" + "="*80)
        print("CONTENT ANALYSIS")
        print("="*80)
        content_lower = response.content.lower()
        
        # Check for German context
        german_terms = ["deutschland", "berlin", "bundesl", "stiko", "rki", "gesundheit", "köln", "münchen"]
        found_german = [term for term in german_terms if term in content_lower]
        print(f"German terms found: {found_german if found_german else 'None'}")
        
        # Check for date references
        date_terms = ["august", "2025", "aug", "september"]
        found_dates = [term for term in date_terms if term in content_lower]
        print(f"Date references: {found_dates if found_dates else 'None'}")
        
        # Check for health topics
        health_topics = ["health", "wellness", "medical", "disease", "vaccine", "therapy", "treatment", 
                        "cancer", "covid", "mental", "diet", "fitness", "wellness", "regenerative"]
        found_health = [term for term in health_topics if term in content_lower]
        print(f"Health topics: {len(found_health)} topics - {found_health[:10]}")
        
        # Check for source attributions
        source_markers = ["according", "reported", "study", "research", "source", ".com", ".org", ".de"]
        found_sources = [marker for marker in source_markers if marker in content_lower]
        print(f"Source markers: {found_sources if found_sources else 'None'}")
        
        # Language detection
        if any(term in content_lower for term in ["der", "die", "das", "und", "ist", "für"]):
            detected_lang = "German"
        else:
            detected_lang = "English"
        print(f"Detected language: {detected_lang}")
        
        print("\n" + "="*80)
        print("FULL RESPONSE CONTENT")
        print("="*80)
        print(response.content)
        
        print("\n" + "="*80)
        print("GROUNDING VERIFICATION")
        print("="*80)
        if response.grounded_effective:
            print("✅ Grounding was effective - web search performed")
            print(f"   Tool calls made: {router_meta.get('tool_call_count', 0)}")
            print(f"   Tool types used: {router_meta.get('tool_types', [])}")
        else:
            print("⚠️ Grounding was not effective - no web search performed")
            print("   Model decided search was not necessary in AUTO mode")
        
        # Check for specific news items
        print("\n" + "="*80)
        print("NEWS ITEMS EXTRACTED")
        print("="*80)
        
        # Look for bullet points or numbered items
        lines = response.content.split('\n')
        news_items = []
        for line in lines:
            if re.match(r'^[\d\-•*]+[\.\)]\s', line.strip()) or '##' in line:
                news_items.append(line.strip())
        
        if news_items:
            print(f"Found {len(news_items)} news items/sections:")
            for item in news_items[:10]:  # First 10 items
                print(f"  - {item[:100]}...")
        else:
            print("No structured news items found")
        
        print("\n" + "="*80)
        print("TEST RESULT: ✅ SUCCESS")
        print("="*80)
        print(f"Response length: {len(response.content)} characters")
        print(f"Total execution time: {response.latency_ms}ms")
        
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
    success = asyncio.run(test_router_grounded_de())
    sys.exit(0 if success else 1)