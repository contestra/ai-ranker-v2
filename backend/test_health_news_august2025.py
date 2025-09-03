#!/usr/bin/env python3
"""
Test gemini-2.5-pro with the exact health and wellness prompt.
Shows full response with citations and links.

⚠️ PRODUCTION: ONLY gemini-2.5-pro
"""
import os
import asyncio
import json
from pathlib import Path
from datetime import datetime

# Load .env
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")


async def test_health_news():
    """Test the exact health and wellness query with full citation details."""
    import google.genai as genai
    from google.genai.types import Tool, GoogleSearch
    
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ No API key")
        return False
    
    client = genai.Client(api_key=api_key)
    
    print("="*80)
    print("HEALTH AND WELLNESS NEWS - AUGUST 2025")
    print("Testing with gemini-2.5-pro ONLY")
    print("="*80)
    
    # The exact prompt
    prompt = "tell me a summary of health and wellness news during august 2025"
    
    print(f"\n📝 Prompt: {prompt}")
    print("-" * 40)
    
    # Retry logic for 503 errors
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"⏳ Waiting {wait_time} seconds before retry {attempt+1}/{max_retries}...")
                await asyncio.sleep(wait_time)
            
            response = client.models.generate_content(
                model="models/gemini-2.5-pro",
                contents=prompt,
                config={
                    "temperature": 0.7,
                    "max_output_tokens": 1000,
                    "tools": [Tool(google_search=GoogleSearch())]
                }
            )
            break  # Success, exit retry loop
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                continue  # Retry
            else:
                raise  # Re-raise on last attempt or non-503 error
    
    try:
        
        if hasattr(response, 'candidates') and response.candidates:
            # Get response text
            response_text = response.text or ""
            print(f"\n📄 RESPONSE ({len(response_text)} chars):")
            print("="*60)
            print(response_text)
            print("="*60)
            
            # Extract grounding metadata
            gm = response.candidates[0].grounding_metadata
            
            queries = getattr(gm, 'web_search_queries', []) or []
            chunks = getattr(gm, 'grounding_chunks', []) or []
            supports = getattr(gm, 'grounding_supports', []) or []
            
            print(f"\n📊 GROUNDING METRICS:")
            print(f"  • Search queries: {len(queries)}")
            print(f"  • Grounding chunks: {len(chunks)}")
            print(f"  • Grounding supports: {len(supports)}")
            
            # Show all search queries
            if queries:
                print(f"\n🔍 SEARCH QUERIES EXECUTED:")
                for i, query in enumerate(queries, 1):
                    print(f"  {i}. \"{query}\"")
            
            # Extract and show all sources/citations
            if chunks:
                print(f"\n📚 SOURCES/CITATIONS ({len(chunks)} total):")
                print("-" * 60)
                
                for i, chunk in enumerate(chunks):
                    print(f"\n  Source #{i+1}:")
                    
                    # Extract web info
                    if hasattr(chunk, 'web'):
                        web = chunk.web
                        if hasattr(web, 'uri'):
                            uri = web.uri
                            # Check if it's a Google redirect
                            if 'vertexaisearch.cloud.google.com' in uri:
                                print(f"    URL: [Google Search redirect]")
                                # Try to extract actual URL from redirect
                                if 'url=' in uri:
                                    actual_url = uri.split('url=')[1].split('&')[0]
                                    print(f"    Actual URL: {actual_url}")
                            else:
                                print(f"    URL: {uri}")
                        
                        if hasattr(web, 'title'):
                            print(f"    Title: {web.title}")
                    
                    # Show if this chunk is referenced by supports
                    chunk_refs = sum(1 for s in supports 
                                   if hasattr(s, 'grounding_chunk_indices') 
                                   and i in (s.grounding_chunk_indices or []))
                    if chunk_refs > 0:
                        print(f"    Referenced: {chunk_refs} time(s) in response")
            
            # Show anchored text segments
            if supports:
                print(f"\n📌 ANCHORED TEXT SEGMENTS ({len(supports)} total):")
                print("-" * 60)
                
                for i, support in enumerate(supports[:5]):  # Show first 5
                    segment = getattr(support, 'segment', None)
                    if segment:
                        text = getattr(segment, 'text', '')
                        start = getattr(segment, 'start_index', None)
                        end = getattr(segment, 'end_index', None)
                        
                        print(f"\n  Anchor #{i+1}:")
                        print(f"    Text: \"{text[:100]}...\"" if len(text) > 100 else f"    Text: \"{text}\"")
                        print(f"    Position: chars {start}-{end}")
                        
                        # Show which sources this text references
                        chunk_indices = getattr(support, 'grounding_chunk_indices', [])
                        if chunk_indices:
                            print(f"    Sources: #{', #'.join(str(idx+1) for idx in chunk_indices)}")
                
                if len(supports) > 5:
                    print(f"\n  ... and {len(supports) - 5} more anchored segments")
            
            # Calculate coverage
            if supports and response_text:
                covered_chars = sum(
                    (getattr(seg, 'end_index', 0) - getattr(seg, 'start_index', 0))
                    for s in supports
                    if (seg := getattr(s, 'segment', None))
                )
                coverage_pct = (covered_chars / len(response_text) * 100)
                
                print(f"\n📈 COVERAGE ANALYSIS:")
                print(f"  • Total response length: {len(response_text)} chars")
                print(f"  • Anchored text: {covered_chars} chars")
                print(f"  • Coverage percentage: {coverage_pct:.1f}%")
            
            # Summary
            print(f"\n" + "="*80)
            if len(supports) > 0:
                print("✅ FULL ANCHORED CITATIONS AVAILABLE")
                print(f"   {len(supports)} text segments linked to {len(chunks)} sources")
            elif len(chunks) > 0:
                print("⚠️  UNLINKED CITATIONS AVAILABLE")
                print(f"   {len(chunks)} sources found but not anchored to text")
            elif len(queries) > 0:
                print("⚠️  DEFENSIVE MODE - SEARCH RAN BUT NO RESULTS")
                print(f"   {len(queries)} searches executed but no grounding data returned")
            else:
                print("❌ NO GROUNDING - Search not executed")
            print("="*80)
            
            # Save full response data
            output = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "response_text": response_text,
                "metrics": {
                    "queries": len(queries),
                    "chunks": len(chunks),
                    "supports": len(supports),
                    "coverage_pct": coverage_pct if supports else 0
                },
                "search_queries": list(queries),
                "sources": [
                    {
                        "index": i,
                        "uri": chunk.web.uri if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri') else None,
                        "title": chunk.web.title if hasattr(chunk, 'web') and hasattr(chunk.web, 'title') else None
                    }
                    for i, chunk in enumerate(chunks)
                ]
            }
            
            output_file = f"health_news_august2025_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(output, f, indent=2)
            print(f"\nFull data saved to: {output_file}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    import sys
    success = asyncio.run(test_health_news())
    sys.exit(0 if success else 1)