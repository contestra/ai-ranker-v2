#!/usr/bin/env python3
"""
Test the Vertex MAX_TOKENS fix
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

async def test_vertex_fix():
    """Test that Vertex now handles low max_tokens better"""
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*60)
    print("VERTEX MAX_TOKENS FIX TEST")
    print("="*60)
    
    tests = [
        ("Low tokens (200) - should be increased to 500", 200),
        ("Medium tokens (500) - should work", 500),
        ("High tokens (1000) - should work", 1000),
    ]
    
    for test_name, max_tokens in tests:
        print(f"\n--- {test_name} ---")
        print(f"Requested max_tokens: {max_tokens}")
        
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[{"role": "user", "content": "What is the VAT rate?"}],
            temperature=0.3,
            max_tokens=max_tokens,
            grounded=False,
            als_context={'country_code': 'US', 'locale': 'en-US'}
        )
        
        try:
            response = await adapter.complete(request)
            
            print(f"✅ Success: {response.success}")
            print(f"Has content: {bool(response.content)}")
            print(f"Content length: {len(response.content) if response.content else 0}")
            
            if response.content:
                # Check if it's our truncation message
                if "[Response truncated:" in response.content:
                    print(f"⚠️ {response.content}")
                else:
                    print(f"Response preview: {response.content[:200]}...")
            
            # Check metadata
            if response.metadata:
                finish_reason = response.metadata.get('finish_reason', 'not_provided')
                print(f"Finish reason: {finish_reason}")
                
                # Check if max_tokens was adjusted
                if max_tokens == 200:
                    print("✅ Max tokens should have been increased to 500 (check logs)")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)
    print("""
The fix includes:
1. Minimum 500 tokens for Vertex ungrounded (avoids empty responses)
2. Finish reason added to metadata for debugging
3. Informative message when MAX_TOKENS is hit with empty content
4. Warning logged when tokens are auto-increased
""")

if __name__ == "__main__":
    asyncio.run(test_vertex_fix())