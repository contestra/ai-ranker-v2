#!/usr/bin/env python3
"""
Test GPT-5 with COMPLETE response extraction including final message.
Following OpenAI Cookbook pattern: web_search_call → message with url_citation annotations
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


async def test_gpt5_complete_response():
    """Test GPT-5 and extract COMPLETE response including final message."""
    print("="*60)
    print("GPT-5 Complete Response Test (Following OpenAI Cookbook)")
    print("="*60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return False
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Simple, specific query as recommended
    user_prompt = "What did the FDA announce on August 15, 2025? Cite sources."
    system_instruction = "You are a helpful AI assistant. Use web search and include source URLs."
    
    print(f"\n1. Model: gpt-5")
    print(f"2. Mode: Plain text (NOT JSON)")
    print(f"3. Prompt: {user_prompt}")
    
    print("\n4. Sending request...")
    start_time = datetime.now()
    
    try:
        # Plain text mode with generous token budget
        response = await client.responses.create(
            model="gpt-5",
            input=user_prompt,
            instructions=system_instruction,
            tools=[{"type": "web_search"}],
            temperature=1.0,
            max_output_tokens=6000  # Need enough for searches + final message
            # NOT setting response_format to avoid JSON mode
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n✅ Response received in {elapsed:.1f} seconds")
        
        # Check the SDK-provided output_text first (as recommended)
        if hasattr(response, 'output_text'):
            print(f"\n✅ SDK provides output_text directly!")
            print(f"   Length: {len(response.output_text) if response.output_text else 0} chars")
            if response.output_text:
                print(f"   Preview: {response.output_text[:200]}...")
        
        # Analyze the complete response structure
        print("\n" + "="*60)
        print("RESPONSE STRUCTURE ANALYSIS:")
        print("-"*60)
        
        # Track what we find
        search_actions = []
        tool_results = []
        final_message = None
        url_citations = []
        message_items = []
        
        # Process ALL output items completely
        if hasattr(response, 'output') and isinstance(response.output, list):
            print(f"Total output items: {len(response.output)}")
            
            # Count item types
            item_types = {}
            for item in response.output:
                item_type = getattr(item, 'type', 'unknown')
                item_types[item_type] = item_types.get(item_type, 0) + 1
            
            print("\nItem type breakdown:")
            for item_type, count in item_types.items():
                print(f"  - {item_type}: {count}")
            
            # Now extract everything
            for i, item in enumerate(response.output):
                item_type = getattr(item, 'type', 'unknown')
                
                if item_type == 'web_search_call':
                    # Search action (query)
                    if hasattr(item, 'action') and hasattr(item.action, 'query'):
                        search_actions.append(item.action.query)
                
                elif item_type == 'tool_result':
                    # Tool results with URLs
                    if hasattr(item, 'results'):
                        for result in item.results:
                            tool_results.append({
                                'url': getattr(result, 'url', ''),
                                'title': getattr(result, 'title', ''),
                                'snippet': getattr(result, 'snippet', '')
                            })
                
                elif item_type == 'message':
                    # FINAL MESSAGE - this is where citations should be!
                    message_items.append(item)
                    print(f"\n🎯 Found MESSAGE item at index {i}!")
                    
                    # Extract content
                    if hasattr(item, 'content'):
                        if isinstance(item.content, str):
                            final_message = item.content
                            print(f"   Text content: {len(item.content)} chars")
                        elif isinstance(item.content, list):
                            # Content might be a list of parts
                            print(f"   Content is a list with {len(item.content)} parts")
                            for j, part in enumerate(item.content):
                                print(f"   Part {j}: {type(part)}")
                                
                                # Check for text
                                if hasattr(part, 'text'):
                                    final_message = part.text
                                    print(f"     - Has text: {len(part.text)} chars")
                                
                                # Check for annotations ON THE PART
                                if hasattr(part, 'annotations'):
                                    print(f"     - Has {len(part.annotations)} annotations!")
                                    for ann in part.annotations:
                                        if hasattr(ann, 'type') and ann.type == 'url_citation':
                                            url_citations.append({
                                                'url': getattr(ann, 'url', ''),
                                                'title': getattr(ann, 'title', ''),
                                                'text': getattr(ann, 'text', '')
                                            })
                                            print(f"       ✅ URL Citation: {ann.url[:50]}...")
        
        # Display complete results
        print("\n" + "="*60)
        print("COMPLETE EXTRACTION RESULTS:")
        print("-"*60)
        
        print(f"\n1. Web Searches: {len(search_actions)}")
        for i, q in enumerate(search_actions[:3]):
            print(f"   {i+1}. {q}")
        
        print(f"\n2. Tool Results: {len(tool_results)}")
        for i, r in enumerate(tool_results[:3]):
            print(f"   {i+1}. {r.get('title', 'No title')[:50]}...")
            print(f"      URL: {r.get('url', 'No URL')}")
        
        print(f"\n3. Message Items Found: {len(message_items)}")
        print(f"4. Final Message Text: {'✅ Yes' if final_message else '❌ No'}")
        if final_message:
            print(f"   Length: {len(final_message)} chars")
            print(f"   Contains 'FDA': {'✅' if 'FDA' in final_message else '❌'}")
            print(f"   Contains 'August': {'✅' if 'August' in final_message else '❌'}")
            print(f"   Contains URLs: {'✅' if 'http' in final_message else '❌'}")
        
        print(f"\n5. URL Citations (annotations): {len(url_citations)}")
        if url_citations:
            print("   🎉 CITATIONS FOUND!")
            for i, c in enumerate(url_citations[:5]):
                print(f"   {i+1}. {c.get('title', 'No title')[:50]}...")
                print(f"      URL: {c.get('url', 'No URL')}")
        
        # Final verdict
        print("\n" + "="*60)
        print("CITATION STATUS:")
        print("-"*60)
        
        has_any_citations = len(url_citations) > 0 or len(tool_results) > 0
        
        if len(url_citations) > 0:
            print("✅ SUCCESS! URL citations found in message annotations!")
            print("   (This matches OpenAI Cookbook pattern)")
        elif len(tool_results) > 0:
            print("✅ Citations found in tool_result frames")
        elif final_message and 'http' in final_message:
            print("⚠️  URLs in text but not as structured citations")
        elif not final_message:
            print("❌ No final message found - response may be incomplete")
        else:
            print("❌ No citations found in any expected location")
        
        # Save everything
        output_file = f"gpt5_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": "gpt-5",
                    "prompt": user_prompt,
                    "max_output_tokens": 6000
                },
                "response": {
                    "elapsed_seconds": elapsed,
                    "output_text": response.output_text if hasattr(response, 'output_text') else None,
                    "item_types": item_types,
                    "final_message": final_message[:500] if final_message else None
                },
                "extraction": {
                    "search_actions": len(search_actions),
                    "tool_results": len(tool_results),
                    "message_items": len(message_items),
                    "url_citations": url_citations,
                    "total_citations": len(url_citations) + len(tool_results)
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n📄 Complete analysis saved to: {output_file}")
        
        return has_any_citations
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_gpt5_complete_response())
    if success:
        print("\n" + "="*60)
        print("✅ GPT-5 CITATIONS TEST SUCCESSFUL!")
        print("Citations are available as expected!")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("⚠️  Check response structure and parsing")
        print("="*60)
    exit(0 if success else 1)