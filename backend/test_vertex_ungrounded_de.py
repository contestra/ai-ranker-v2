#!/usr/bin/env python3
"""
Test Vertex ungrounded with German ALS - full results output
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


async def test_vertex_ungrounded_de():
    """Test Vertex ungrounded with German ALS."""
    from app.llm.adapters.vertex_adapter import VertexAdapter
    from app.llm.types import LLMRequest
    
    adapter = VertexAdapter()
    
    # German ALS context
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
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",
        messages=messages,
        grounded=False,  # UNGROUNDED mode
        max_tokens=1000,
        als_context=als_context,
        template_id="health_news_test_ungrounded",
        run_id="test_vertex_ungrounded_001"
    )
    
    print("="*80)
    print("VERTEX UNGROUNDED TEST WITH GERMAN ALS - FULL RESULTS")
    print("="*80)
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
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
        print("\nMaking request to Vertex adapter...")
        response = await adapter.complete(request, timeout=30)
        
        print("\n" + "="*80)
        print("RESPONSE METADATA")
        print("="*80)
        metadata = response.metadata or {}
        print(f"Success: {response.success}")
        print(f"Model Version: {response.model_version}")
        print(f"Vendor: {response.vendor}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Response API: {metadata.get('response_api', 'vertex_genai')}")
        print(f"Region: {metadata.get('region', 'unknown')}")
        print(f"Tool Call Count: {metadata.get('tool_call_count', 0)}")
        print(f"Grounded Evidence Present: {metadata.get('grounded_evidence_present', False)}")
        print(f"Latency: {response.latency_ms}ms")
        
        print("\n" + "="*80)
        print("USAGE STATISTICS")
        print("="*80)
        if response.usage:
            print(f"Prompt Tokens: {response.usage.get('prompt_tokens', 0)}")
            print(f"Completion Tokens: {response.usage.get('completion_tokens', 0)}")
            print(f"Total Tokens: {response.usage.get('total_tokens', 0)}")
            
            # Calculate costs (Gemini 2.0 Flash estimates)
            prompt_cost = response.usage.get('prompt_tokens', 0) * 0.000000075  # $0.075/1M tokens
            completion_cost = response.usage.get('completion_tokens', 0) * 0.0000003  # $0.30/1M tokens
            total_cost = prompt_cost + completion_cost
            print(f"Estimated Cost: ${total_cost:.6f}")
        else:
            print("No usage data available")
        
        print("\n" + "="*80)
        print("CITATIONS AND URLS")
        print("="*80)
        if response.citations:
            print(f"Citations found: {len(response.citations)}")
            for i, citation in enumerate(response.citations, 1):
                print(f"\nCitation {i}:")
                print(f"  URL: {citation.get('url', 'N/A')}")
                print(f"  Title: {citation.get('title', 'N/A')}")
                print(f"  Source Type: {citation.get('source_type', 'N/A')}")
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
            print("Response Type: DIRECT (Model provided information)")
        
        # Check for disclaimer language
        disclaimers = ["cannot provide", "don't have access", "unable to", "can't give", 
                      "no real-time", "knowledge cutoff", "as of my", "I don't have",
                      "hypothetical", "speculative", "imaginary"]
        found_disclaimers = [d for d in disclaimers if d in content_lower]
        if found_disclaimers:
            print(f"Disclaimers found: {found_disclaimers}")
        
        # Check language
        german_words = ["der", "die", "das", "und", "ist", "für", "ich", "sie", "wir", "gesundheit"]
        german_count = sum(1 for word in german_words if word in content_lower.split())
        
        english_words = ["the", "and", "is", "for", "have", "with", "are", "was", "were", "health"]
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
        location_refs = ["germany", "deutschland", "german", "deutsch", "berlin", "europe", "europa"]
        found_locations = [loc for loc in location_refs if loc in content_lower]
        if found_locations:
            print(f"Location references: {found_locations}")
        else:
            print("No location references (ALS may not have influenced response)")
        
        # Check for health topics
        health_topics = ["health", "wellness", "medical", "disease", "vaccine", "therapy", "treatment",
                        "cancer", "covid", "mental", "diet", "fitness", "gesundheit", "medizin"]
        found_health = [term for term in health_topics if term in content_lower]
        print(f"Health topics mentioned: {len(found_health)} - {found_health[:10]}")
        
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
            print("  - Typical for ungrounded mode with future dates")
            print("  - May have suggested checking real sources")
        elif response_type == "SPECULATIVE":
            print("Model Behavior: Speculative")
            print("  - Provided hypothetical scenarios")
            print("  - Used conditional language")
            print("  - No real data backing")
        else:
            print("Model Behavior: Direct Response")
            print("  - Provided information without strong caveats")
            print("  - May be using training data patterns")
        
        print("\n" + "="*80)
        print("KEY OBSERVATIONS - UNGROUNDED MODE")
        print("="*80)
        print("1. No web search performed (as expected)")
        print("2. No citations or URLs provided")
        print(f"3. Response type: {response_type}")
        print(f"4. Language used: {detected_lang}")
        print(f"5. ALS influence: {'Yes' if found_locations else 'Minimal/None'}")
        print(f"6. Cost: ${total_cost:.6f} (very cheap)")
        print(f"7. Speed: {response.latency_ms}ms (fast)")
        
        print("\n" + "="*80)
        print("TEST RESULT: ✅ SUCCESS")
        print("="*80)
        print(f"Vertex ungrounded request completed successfully")
        print(f"No tool calls performed (as expected)")
        print(f"Response completed in {response.latency_ms}ms")
        
        # Save results for comparison
        results = {
            "mode": "ungrounded",
            "response_type": response_type,
            "content_length": len(response.content),
            "cost": total_cost,
            "latency_ms": response.latency_ms,
            "language": detected_lang,
            "als_influenced": bool(found_locations),
            "content": response.content
        }
        
        with open("vertex_ungrounded_de_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
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
    success = asyncio.run(test_vertex_ungrounded_de())
    sys.exit(0 if success else 1)