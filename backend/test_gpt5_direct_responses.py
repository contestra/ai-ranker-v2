#!/usr/bin/env python3
"""
Test GPT-5 directly with OpenAI Responses API - properly extract citations.
"""
import os
import json
from datetime import datetime
from openai import AsyncOpenAI
import asyncio

# Load .env file
from pathlib import Path
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


async def test_gpt5_with_proper_citation_extraction():
    """Test GPT-5 and properly extract citations from the response."""
    print("="*60)
    print("Testing GPT-5 with Proper Citation Extraction")
    print("="*60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return False
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Test prompt
    user_prompt = "What did the FDA approve in August 2025? Please cite your sources with URLs."
    system_instruction = "You are a helpful AI assistant. Use web search to find accurate information and always include source URLs."
    
    print(f"\n1. Model: gpt-5")
    print(f"2. API: Responses API")
    print(f"3. Prompt: {user_prompt}")
    
    print("\n4. Sending request with web_search tool...")
    start_time = datetime.now()
    
    try:
        # Use Responses API with proper parameters
        response = await client.responses.create(
            model="gpt-5",
            input=user_prompt,
            instructions=system_instruction,
            tools=[{"type": "web_search"}],
            temperature=1.0,
            max_output_tokens=3000
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n✅ Response received in {elapsed:.1f} seconds")
        print("="*60)
        
        # Properly extract citations from different parts of the response
        search_queries = []
        tool_results = []
        citations = []
        final_message = ""
        url_citations = []
        
        # Process the output items
        if hasattr(response, 'output') and isinstance(response.output, list):
            print(f"\nProcessing {len(response.output)} output items...")
            
            for item in response.output:
                item_type = getattr(item, 'type', 'unknown')
                
                # 1. Extract search queries (what we searched for)
                if item_type == 'web_search_call':
                    if hasattr(item, 'action') and hasattr(item.action, 'query'):
                        query = item.action.query
                        if query:
                            search_queries.append(query)
                            print(f"  Search: {query[:80]}...")
                
                # 2. Extract tool_result frames (the actual search results)
                elif item_type == 'tool_result':
                    print(f"  Found tool_result frame!")
                    if hasattr(item, 'results'):
                        for result in item.results:
                            tool_results.append({
                                'url': getattr(result, 'url', ''),
                                'title': getattr(result, 'title', ''),
                                'snippet': getattr(result, 'snippet', '')
                            })
                    elif hasattr(item, 'content'):
                        # Sometimes results are in content
                        content = item.content
                        if isinstance(content, dict) and 'results' in content:
                            for result in content['results']:
                                tool_results.append(result)
                
                # 3. Extract final message with url_citation annotations
                elif item_type == 'message':
                    print(f"  Found message frame!")
                    if hasattr(item, 'content'):
                        final_message = item.content
                        
                        # Check for url_citation annotations
                        if hasattr(item, 'annotations'):
                            for annotation in item.annotations:
                                if annotation.type == 'url_citation':
                                    url_citations.append({
                                        'url': annotation.url,
                                        'title': getattr(annotation, 'title', ''),
                                        'text': getattr(annotation, 'text', '')
                                    })
                
                # 4. Check for content in other item types
                elif hasattr(item, 'content') and item.content:
                    # This might be the final text
                    content = item.content
                    if isinstance(content, str) and len(content) > 100:
                        final_message = content
        
        # Also check if response has a direct text/output_text attribute
        if not final_message:
            if hasattr(response, 'output_text'):
                final_message = response.output_text
            elif hasattr(response, 'text'):
                final_message = response.text
        
        # Combine all citations
        all_citations = []
        
        # Add URL citations (these are the best - anchored to text)
        for citation in url_citations:
            all_citations.append({
                'type': 'anchored',
                'url': citation['url'],
                'title': citation.get('title', ''),
                'text': citation.get('text', '')
            })
        
        # Add tool results (unlinked but still useful)
        for result in tool_results:
            if result.get('url'):
                all_citations.append({
                    'type': 'tool_result',
                    'url': result['url'],
                    'title': result.get('title', ''),
                    'snippet': result.get('snippet', '')
                })
        
        # Display results
        print("\n" + "="*60)
        print("EXTRACTION RESULTS:")
        print("-"*60)
        
        print(f"\n1. Web Searches Performed: {len(search_queries)}")
        if search_queries:
            for i, q in enumerate(search_queries[:3]):
                print(f"   {i+1}. {q}")
        
        print(f"\n2. Tool Results Found: {len(tool_results)}")
        if tool_results:
            for i, r in enumerate(tool_results[:3]):
                print(f"   {i+1}. {r.get('title', 'No title')[:50]}...")
                print(f"      URL: {r.get('url', 'No URL')}")
        
        print(f"\n3. URL Citations (anchored): {len(url_citations)}")
        if url_citations:
            for i, c in enumerate(url_citations[:3]):
                print(f"   {i+1}. {c.get('title', 'No title')[:50]}...")
                print(f"      URL: {c.get('url', 'No URL')}")
        
        print(f"\n4. Final Message: {'Yes' if final_message else 'No'}")
        if final_message:
            print(f"   Length: {len(final_message)} chars")
            print(f"   Preview: {final_message[:300]}...")
        
        print(f"\n5. TOTAL CITATIONS FOUND: {len(all_citations)}")
        
        # Analysis
        print("\n" + "="*60)
        print("CITATION ANALYSIS:")
        print("-"*60)
        
        has_searches = len(search_queries) > 0
        has_tool_results = len(tool_results) > 0
        has_url_citations = len(url_citations) > 0
        has_any_citations = len(all_citations) > 0
        
        print(f"  ✅ Web searches performed: {len(search_queries)}")
        print(f"  {'✅' if has_tool_results else '❌'} Tool results retrieved: {len(tool_results)}")
        print(f"  {'✅' if has_url_citations else '❌'} URL citations anchored: {len(url_citations)}")
        print(f"  {'✅' if has_any_citations else '❌'} Total citations available: {len(all_citations)}")
        
        if has_searches and not has_any_citations:
            print("\n⚠️  Searches performed but no citations found.")
            print("  This might mean:")
            print("  - Response is still streaming (partial output)")
            print("  - Final message frame hasn't been parsed")
            print("  - Tool results are in a different format")
        elif has_any_citations:
            print("\n✅ SUCCESS! Citations were retrieved and are available for display.")
        
        # Save complete results
        output_file = f"gpt5_citations_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": "gpt-5",
                    "prompt": user_prompt
                },
                "response": {
                    "elapsed_seconds": elapsed,
                    "final_message": final_message[:1000] if final_message else None
                },
                "citations": {
                    "search_queries": search_queries,
                    "tool_results": tool_results[:10] if tool_results else [],
                    "url_citations": url_citations[:10] if url_citations else [],
                    "total_citations": len(all_citations)
                },
                "analysis": {
                    "has_searches": has_searches,
                    "has_tool_results": has_tool_results,
                    "has_url_citations": has_url_citations,
                    "has_any_citations": has_any_citations
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n📄 Complete results saved to: {output_file}")
        
        return has_any_citations
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_gpt5_with_proper_citation_extraction())
    if success:
        print("\n" + "="*60)
        print("✅ GPT-5 WITH CITATIONS TEST SUCCESSFUL!")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌ Citations not found - check response structure")
        print("="*60)
    exit(0 if success else 1)