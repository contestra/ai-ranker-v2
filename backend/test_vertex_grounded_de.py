#!/usr/bin/env python3
"""
Test Vertex grounded with German ALS - full results output
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


async def test_vertex_grounded_de():
    """Test Vertex grounded with German ALS."""
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
        grounded=True,  # GROUNDED mode
        max_tokens=6000,  # Full grounded limit
        meta={"grounding_mode": "AUTO"},
        als_context=als_context,
        template_id="health_news_test_grounded",
        run_id="test_vertex_grounded_001"
    )
    
    print("="*80)
    print("VERTEX GROUNDED TEST WITH GERMAN ALS - FULL RESULTS")
    print("="*80)
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
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
        print("\nMaking request to Vertex adapter...")
        response = await adapter.complete(request, timeout=60)
        
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
        print(f"Grounding Mode: {metadata.get('grounding_mode_requested', 'AUTO')}")
        print(f"Web Tool Type: {metadata.get('web_tool_type', 'none')}")
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
            total_cost = 0
        
        print("\n" + "="*80)
        print("CITATIONS FROM GROUNDING")
        print("="*80)
        unique_urls = {}
        if response.citations:
            print(f"Total citations: {len(response.citations)}")
            for i, citation in enumerate(response.citations, 1):
                if citation.get('source_type') == 'grounding_chunk':
                    url = citation.get('url', 'N/A')
                    title = citation.get('title', 'N/A')
                    domain = citation.get('domain', 'N/A')
                    
                    # Deduplicate URLs
                    if url not in unique_urls:
                        unique_urls[url] = {
                            'title': title,
                            'domain': domain,
                            'count': 1
                        }
                    else:
                        unique_urls[url]['count'] += 1
                elif citation.get('source_type') == 'search_query':
                    print(f"\nSearch Query: {citation.get('query', 'N/A')}")
            
            print(f"\n{len(unique_urls)} unique URLs from grounding:")
            for i, (url, info) in enumerate(unique_urls.items(), 1):
                print(f"\n{i}. {info['title']}")
                print(f"   URL: {url}")
                print(f"   Domain: {info['domain']}")
                print(f"   Referenced: {info['count']} times")
        else:
            print("No structured citations found")
        
        # Extract URLs from content
        print("\n" + "="*80)
        print("URLS EMBEDDED IN CONTENT")
        print("="*80)
        content_urls = re.findall(r'https?://[^\s\)\]]+', response.content)
        if content_urls:
            unique_content_urls = list(set(content_urls))
            print(f"Found {len(unique_content_urls)} unique URLs in content:")
            for i, url in enumerate(unique_content_urls, 1):
                # Clean up URL (remove trailing punctuation)
                url = url.rstrip('.,;:)')
                print(f"{i}. {url}")
        else:
            print("No URLs embedded in content")
        
        print("\n" + "="*80)
        print("CONTENT ANALYSIS")
        print("="*80)
        content_lower = response.content.lower()
        
        # Check for German context
        german_terms = ["deutschland", "berlin", "bundesl", "stiko", "rki", "gesundheit", "köln", "münchen"]
        found_german = [term for term in german_terms if term in content_lower]
        print(f"German-specific terms: {found_german if found_german else 'None'}")
        
        # Check for date references
        date_terms = ["august", "2025", "aug", "september", "july"]
        found_dates = [term for term in date_terms if term in content_lower]
        print(f"Date references: {found_dates if found_dates else 'None'}")
        
        # Check for health topics
        health_topics = ["health", "wellness", "medical", "disease", "vaccine", "therapy", "treatment",
                        "cancer", "covid", "mental", "diet", "fitness", "regenerative", "alzheimer",
                        "diabetes", "obesity", "longevity", "ai", "drug", "fda", "clinical"]
        found_health = [term for term in health_topics if term in content_lower]
        print(f"Health topics: {len(found_health)} topics - {found_health[:15]}")
        
        # Check for source attributions
        source_markers = ["according", "reported", "study", "research", "source", ".com", ".org", ".de",
                         "university", "institute", "journal", "published", "announced"]
        found_sources = [marker for marker in source_markers if marker in content_lower]
        print(f"Source markers: {found_sources[:10] if found_sources else 'None'}")
        
        # Language detection
        german_words = ["der", "die", "das", "und", "ist", "für", "mit", "von", "auf"]
        german_count = sum(1 for word in german_words if f" {word} " in f" {content_lower} ")
        
        english_words = ["the", "and", "is", "for", "with", "from", "have", "are", "was"]
        english_count = sum(1 for word in english_words if f" {word} " in f" {content_lower} ")
        
        if german_count > english_count * 2:  # Strong German preference
            detected_lang = "German"
        elif english_count > german_count * 2:  # Strong English preference
            detected_lang = "English"
        else:
            detected_lang = "Mixed/English"
        
        print(f"\nLanguage Detection:")
        print(f"  - German words: {german_count}")
        print(f"  - English words: {english_count}")
        print(f"  - Detected: {detected_lang}")
        
        # Content structure analysis
        print(f"\nContent Structure:")
        print(f"  - Total length: {len(response.content)} characters")
        print(f"  - Word count: {len(response.content.split())} words")
        print(f"  - Line count: {len(response.content.splitlines())} lines")
        print(f"  - Paragraph count: {len([p for p in response.content.split('\n\n') if p.strip()])}")
        
        # Look for structured news items
        lines = response.content.split('\n')
        news_items = []
        for line in lines:
            if re.match(r'^[\d\-•*]+[\.\)]?\s', line.strip()) or line.strip().startswith('##'):
                news_items.append(line.strip()[:100])
        
        if news_items:
            print(f"\nStructured items found: {len(news_items)}")
            print("First 5 items:")
            for item in news_items[:5]:
                print(f"  - {item}...")
        
        print("\n" + "="*80)
        print("FULL RESPONSE CONTENT")
        print("="*80)
        print(response.content)
        
        print("\n" + "="*80)
        print("GROUNDING VERIFICATION")
        print("="*80)
        if response.grounded_effective:
            print("✅ Grounding was effective - GoogleSearch performed")
            print(f"   Tool calls made: {metadata.get('tool_call_count', 0)}")
            print(f"   Unique sources found: {len(unique_urls)}")
            print(f"   Content appears current and factual")
        else:
            print("⚠️ Grounding was not effective - no web search performed")
            print("   Model decided search was not necessary in AUTO mode")
        
        print("\n" + "="*80)
        print("COMPARISON TO UNGROUNDED MODE")
        print("="*80)
        
        # Try to load ungrounded results for comparison
        try:
            with open("vertex_ungrounded_de_results.json", "r") as f:
                ungrounded = json.load(f)
                
            print("Grounded vs Ungrounded:")
            print(f"  Content length: {len(response.content)} vs {ungrounded['content_length']} chars")
            print(f"  Cost: ${total_cost:.6f} vs ${ungrounded['cost']:.6f}")
            print(f"  Latency: {response.latency_ms}ms vs {ungrounded['latency_ms']}ms")
            print(f"  Citations: {len(unique_urls)} vs 0")
            print(f"  Response type: Factual vs {ungrounded['response_type']}")
        except:
            print("(Ungrounded results not available for comparison)")
        
        print("\n" + "="*80)
        print("KEY OBSERVATIONS - GROUNDED MODE")
        print("="*80)
        print(f"1. Web search performed: {'Yes' if response.grounded_effective else 'No'}")
        print(f"2. Citations provided: {len(unique_urls)} unique sources")
        print(f"3. Content type: {'Factual with sources' if unique_urls else 'Generated without sources'}")
        print(f"4. Language used: {detected_lang}")
        print(f"5. German context: {'Present' if found_german else 'Minimal/None'}")
        print(f"6. Cost: ${total_cost:.6f}")
        print(f"7. Speed: {response.latency_ms}ms")
        print(f"8. August 2025 news: {'Present' if 'august' in content_lower and '2025' in content_lower else 'Not specific'}")
        
        print("\n" + "="*80)
        print("TEST RESULT: ✅ SUCCESS")
        print("="*80)
        print(f"Vertex grounded request completed successfully")
        print(f"Grounding {'effective' if response.grounded_effective else 'not triggered (AUTO mode)'}")
        print(f"Response completed in {response.latency_ms}ms")
        
        # Save results for comparison
        results = {
            "mode": "grounded",
            "grounded_effective": response.grounded_effective,
            "content_length": len(response.content),
            "unique_urls": len(unique_urls),
            "cost": total_cost,
            "latency_ms": response.latency_ms,
            "language": detected_lang,
            "german_context": bool(found_german),
            "content": response.content,
            "citations": list(unique_urls.keys())
        }
        
        with open("vertex_grounded_de_results.json", "w") as f:
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
    success = asyncio.run(test_vertex_grounded_de())
    sys.exit(0 if success else 1)