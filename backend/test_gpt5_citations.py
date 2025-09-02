#!/usr/bin/env python3
"""
Test GPT-5 specifically for citation retrieval.
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


async def test_gpt5_citations():
    """Test GPT-5 citation retrieval with simpler query."""
    print("="*60)
    print("Testing GPT-5 Citation Retrieval")
    print("="*60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return False
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Simple, specific query that should return citations
    user_prompt = "What did the FDA approve in August 2025? Please cite your sources."
    system_instruction = "You are a helpful assistant. Use web search to find accurate information and always cite your sources with URLs."
    
    print(f"\n1. Model: gpt-5")
    print(f"2. Prompt: {user_prompt}")
    print(f"3. Goal: Check if citations/URLs are returned")
    
    print("\n4. Sending request...")
    start_time = datetime.now()
    
    try:
        # Use Responses API with web_search
        response = await client.responses.create(
            model="gpt-5",
            input=user_prompt,
            instructions=system_instruction,
            tools=[{"type": "web_search"}],
            temperature=1.0,
            max_output_tokens=2000,
            text={"verbosity": "high"}  # Request detailed output
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n✅ Response received in {elapsed:.1f} seconds")
        
        # Examine the complete response structure
        print("\n" + "="*60)
        print("FULL RESPONSE STRUCTURE:")
        print("-"*60)
        
        # Check all response attributes
        print(f"Response type: {type(response)}")
        print(f"Response attributes: {dir(response)}")
        
        # Extract different parts of the response
        citations = []
        search_queries = []
        final_text = ""
        
        # Check for output
        if hasattr(response, 'output'):
            print(f"\nOutput type: {type(response.output)}")
            if isinstance(response.output, list):
                print(f"Output has {len(response.output)} items")
                
                for i, item in enumerate(response.output):
                    print(f"\nItem {i}: Type={type(item).__name__}")
                    
                    # Check item attributes
                    if hasattr(item, '__dict__'):
                        for key, value in item.__dict__.items():
                            if value and str(value).strip():
                                print(f"  {key}: {str(value)[:100]}...")
                    
                    # Look for web search results
                    if hasattr(item, 'type'):
                        if 'web_search' in str(item.type):
                            if hasattr(item, 'action'):
                                query = getattr(item.action, 'query', None)
                                if query:
                                    search_queries.append(query)
                            
                            # Check for results/citations
                            if hasattr(item, 'results'):
                                for result in item.results:
                                    if hasattr(result, 'url'):
                                        citations.append({
                                            'url': result.url,
                                            'title': getattr(result, 'title', 'N/A'),
                                            'snippet': getattr(result, 'snippet', 'N/A')
                                        })
                        
                        # Look for text content
                        elif hasattr(item, 'content'):
                            content = item.content
                            if content:
                                final_text += str(content) + "\n"
            else:
                final_text = str(response.output)
        
        # Check for citations in other attributes
        if hasattr(response, 'citations'):
            print(f"\nDirect citations attribute: {response.citations}")
        
        if hasattr(response, 'sources'):
            print(f"\nDirect sources attribute: {response.sources}")
        
        print("\n" + "="*60)
        print("EXTRACTION RESULTS:")
        print("-"*60)
        
        print(f"\nSearch queries made: {len(search_queries)}")
        if search_queries:
            for q in search_queries[:3]:
                print(f"  - {q}")
        
        print(f"\nCitations found: {len(citations)}")
        if citations:
            for c in citations[:3]:
                print(f"  - {c['title']}")
                print(f"    URL: {c['url']}")
        
        print(f"\nFinal text: {'Yes' if final_text else 'No'}")
        if final_text:
            print(final_text[:500])
        
        # Analysis
        print("\n" + "="*60)
        print("CITATION ANALYSIS:")
        print("-"*60)
        
        has_searches = len(search_queries) > 0
        has_citations = len(citations) > 0
        has_urls = any('http' in str(response.output).lower()) if response.output else False
        
        print(f"  Web searches performed: {'✅' if has_searches else '❌'}")
        print(f"  Citations with URLs found: {'✅' if has_citations else '❌'}")
        print(f"  URLs in response text: {'✅' if has_urls else '❌'}")
        
        if not has_citations and has_searches:
            print("\n⚠️  Searches were performed but citations not found in response structure")
            print("  This may require different response parsing or API parameters")
        
        # Save for analysis
        output_file = f"gpt5_citations_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": "gpt-5",
                    "prompt": user_prompt,
                    "instructions": system_instruction
                },
                "response": {
                    "elapsed_seconds": elapsed,
                    "search_queries": search_queries,
                    "citations_found": len(citations),
                    "citations": citations[:5] if citations else [],
                    "has_final_text": bool(final_text),
                    "final_text_preview": final_text[:500] if final_text else None
                },
                "analysis": {
                    "has_searches": has_searches,
                    "has_citations": has_citations,
                    "has_urls": has_urls
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n📄 Results saved to: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_gpt5_citations())
    exit(0 if success else 1)