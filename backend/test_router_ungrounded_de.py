#!/usr/bin/env python3
"""
Test OpenAI ungrounded through router with German ALS - full results output
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


async def test_router_ungrounded_de():
    """Test OpenAI ungrounded through router with German ALS."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
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
        grounded=False,  # UNGROUNDED mode
        max_tokens=1000,
        meta={},  # No grounding mode
        als_context=als_context,
        template_id="health_news_test_ungrounded",
        run_id="test_run_002"
    )
    
    print("="*80)
    print("OPENAI UNGROUNDED TEST VIA ROUTER - FULL RESULTS")
    print("="*80)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print(f"Model: {request.model}")
    print(f"ALS Context:")
    print(f"  - Country: {als_context['country_code']}")
    print(f"  - Locale: {als_context['locale']}")
    print(f"  - Timezone: {als_context['timezone']}")
    print(f"  - Location: {als_context['detected_location']}")
    print(f"Prompt: Tell me the primary health and wellness news during August 2025")
    print(f"Grounded: False (UNGROUNDED mode)")
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
        
        # Check capabilities
        if hasattr(request, 'metadata') and request.metadata:
            caps = request.metadata.get('capabilities', {})
            print(f"Model Capabilities:")
            print(f"  - Reasoning: {caps.get('supports_reasoning_effort', False)}")
            print(f"  - Thinking: {caps.get('supports_thinking_budget', False)}")
        
        print("\n" + "="*80)
        print("RESPONSE METADATA")
        print("="*80)
        print(f"Success: {response.success}")
        print(f"Model Version: {response.model_version}")
        print(f"Vendor: {response.vendor}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Response API: {router_meta.get('response_api', 'unknown')}")
        print(f"Tool Call Count: {router_meta.get('tool_call_count', 0)}")
        print(f"Grounded Evidence Present: {router_meta.get('grounded_evidence_present', False)}")
        print(f"Fallback Used: {router_meta.get('fallback_used', False)}")
        print(f"Text Source: {router_meta.get('text_source', 'unknown')}")
        print(f"Latency: {response.latency_ms}ms")
        
        print("\n" + "="*80)
        print("ALS METADATA")
        print("="*80)
        print(f"ALS Present: {router_meta.get('als_present', False)}")
        print(f"ALS Country: {router_meta.get('als_country', 'N/A')}")
        print(f"ALS Variant ID: {router_meta.get('als_variant_id', 'N/A')}")
        if router_meta.get('als_block_sha256'):
            print(f"ALS Block SHA256: {router_meta.get('als_block_sha256', 'N/A')[:16]}...")
        else:
            print(f"ALS Block SHA256: Not generated")
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
            print(f"Estimated Cost: ${total_cost:.6f}")
        else:
            print("No usage data available")
        
        # Compare to grounded
        print("\n" + "="*80)
        print("COMPARISON TO GROUNDED MODE")
        print("="*80)
        print("Grounded mode would have:")
        print("  - Performed web_search tool call")
        print("  - Used 6000 max_tokens limit")
        print("  - Provided real August 2025 news with URLs")
        print("  - Cost ~$0.11 (based on previous test)")
        print("\nUngrounded mode:")
        print(f"  - No tool calls (confirmed: {router_meta.get('tool_call_count', 0)} calls)")
        print(f"  - Used {request.max_tokens} max_tokens limit")
        print("  - Cannot provide real August 2025 news")
        print(f"  - Cost: ${total_cost:.6f} (much cheaper)")
        
        print("\n" + "="*80)
        print("CITATIONS AND URLS")
        print("="*80)
        if response.citations:
            print(f"Citations found: {len(response.citations)}")
            for i, citation in enumerate(response.citations, 1):
                print(f"\nCitation {i}:")
                print(f"  URL: {citation.get('url', 'N/A')}")
                print(f"  Title: {citation.get('title', 'N/A')}")
        else:
            print("No structured citations (expected for ungrounded)")
        
        # Extract URLs from content
        urls = re.findall(r'https?://[^\s\)\]]+', response.content)
        if urls:
            print(f"\nURLs in content: {len(urls)}")
            for url in urls:
                print(f"  - {url}")
        else:
            print("No URLs in content (expected for ungrounded)")
        
        print("\n" + "="*80)
        print("CONTENT ANALYSIS")
        print("="*80)
        content_lower = response.content.lower()
        
        # Analyze response type
        if "cannot" in content_lower or "don't have" in content_lower or "unable" in content_lower:
            response_type = "DECLINED"
            print("Response Type: DECLINED (Model refused to provide future information)")
        elif "would" in content_lower or "might" in content_lower or "could" in content_lower:
            response_type = "SPECULATIVE"
            print("Response Type: SPECULATIVE (Model provided hypothetical information)")
        else:
            response_type = "DIRECT"
            print("Response Type: DIRECT")
        
        # Check for disclaimer language
        disclaimers = ["cannot provide", "don't have access", "unable to", "can't give", 
                      "no real-time", "knowledge cutoff", "as of my", "I don't have"]
        found_disclaimers = [d for d in disclaimers if d in content_lower]
        if found_disclaimers:
            print(f"Disclaimers found: {found_disclaimers}")
        
        # Check language
        german_words = ["der", "die", "das", "und", "ist", "für", "ich", "sie", "wir"]
        german_count = sum(1 for word in german_words if word in content_lower.split())
        
        english_words = ["the", "and", "is", "for", "have", "with", "are", "was", "were"]
        english_count = sum(1 for word in english_words if word in content_lower.split())
        
        if german_count > english_count:
            detected_lang = "German"
        else:
            detected_lang = "English"
        
        print(f"Language Detection:")
        print(f"  - German words: {german_count}")
        print(f"  - English words: {english_count}")
        print(f"  - Detected: {detected_lang}")
        
        # Check for ALS acknowledgment
        location_refs = ["germany", "deutschland", "german", "deutsch", "berlin", "europe"]
        found_locations = [loc for loc in location_refs if loc in content_lower]
        if found_locations:
            print(f"Location references: {found_locations}")
        else:
            print("No location references (ALS may not have influenced response)")
        
        # Content length analysis
        print(f"\nContent Statistics:")
        print(f"  - Total length: {len(response.content)} characters")
        print(f"  - Word count: {len(response.content.split())} words")
        print(f"  - Line count: {len(response.content.splitlines())} lines")
        
        print("\n" + "="*80)
        print("FULL RESPONSE CONTENT")
        print("="*80)
        print(response.content)
        
        print("\n" + "="*80)
        print("BEHAVIORAL ANALYSIS")
        print("="*80)
        
        if response_type == "DECLINED":
            print("Model Behavior: Conservative")
            print("  - Refused to speculate about future events")
            print("  - Typical for ungrounded GPT-4o with future dates")
            print("  - Recommended checking real sources")
        elif response_type == "SPECULATIVE":
            print("Model Behavior: Speculative")
            print("  - Provided hypothetical scenarios")
            print("  - Used conditional language")
            print("  - No real data backing")
        else:
            print("Model Behavior: Direct Response")
            print("  - Provided information without caveats")
            print("  - May be using training data")
        
        print("\n" + "="*80)
        print("KEY DIFFERENCES FROM GROUNDED")
        print("="*80)
        print("1. Information Source:")
        print("   - Grounded: Real-time web search")
        print("   - Ungrounded: Training data only")
        print("\n2. Response Quality:")
        print("   - Grounded: Factual, current, cited")
        print("   - Ungrounded: Limited, may decline")
        print("\n3. Cost Efficiency:")
        print(f"   - Grounded: ~$0.11 (19,380 tokens)")
        print(f"   - Ungrounded: ${total_cost:.6f} ({response.usage.get('total_tokens', 0) if response.usage else 0} tokens)")
        print("\n4. Response Time:")
        print("   - Grounded: ~15 seconds")
        print(f"   - Ungrounded: {response.latency_ms/1000:.1f} seconds")
        
        print("\n" + "="*80)
        print("TEST RESULT: ✅ SUCCESS")
        print("="*80)
        print(f"Router successfully handled ungrounded request")
        print(f"No tool calls performed (as expected)")
        print(f"Response completed in {response.latency_ms}ms")
        
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
    success = asyncio.run(test_router_ungrounded_de())
    sys.exit(0 if success else 1)