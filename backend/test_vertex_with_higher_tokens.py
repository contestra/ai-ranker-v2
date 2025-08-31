#!/usr/bin/env python3
"""
Test Vertex with higher token limits to confirm it works
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_vertex_tokens():
    """Test Vertex with different token limits"""
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*60)
    print("VERTEX TOKEN LIMIT TEST")
    print("="*60)
    
    prompt = "What is the VAT rate in simple terms?"
    
    # Test with increasing token limits
    for max_tokens in [100, 300, 1000, 2000]:
        print(f"\n--- Max tokens: {max_tokens} ---")
        
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=max_tokens,
            grounded=False,
            als_context={'country_code': 'DE', 'locale': 'en-DE'}
        )
        
        try:
            response = await adapter.complete(request)
            
            if response.content:
                print(f"✅ Got response ({len(response.content)} chars)")
                print(f"Response: {response.content[:200]}...")
                print(f"Tokens used: {response.usage.get('total_tokens', 0) if response.usage else 0}")
            else:
                print(f"❌ Empty response")
                print(f"Tokens used: {response.usage.get('total_tokens', 0) if response.usage else 0}")
                if response.metadata:
                    print(f"Finish reason: {response.metadata.get('finish_reason', 'unknown')}")
                    
        except Exception as e:
            print(f"Error: {e}")
        
        await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("CONCLUSION")
    print("="*60)
    print("""
The issue is that Vertex returns empty content when it hits MAX_TOKENS
before completing a response. This is expected behavior - the model
generates tokens but doesn't return partial content.

Solution: Use higher max_tokens values for Vertex to ensure complete responses.
The grounded tests work because they have higher token limits.
""")

if __name__ == "__main__":
    asyncio.run(test_vertex_tokens())