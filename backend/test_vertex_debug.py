#!/usr/bin/env python3
"""
Debug Vertex ungrounded response issue
"""
import asyncio
import os
import sys
import json
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_vertex_ungrounded():
    """Test Vertex ungrounded to see why responses are empty"""
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*60)
    print("VERTEX UNGROUNDED DEBUG TEST")
    print("="*60)
    
    # Test with different max_tokens values
    tests = [
        ("Short prompt, low tokens", "Say hello", 50),
        ("Short prompt, medium tokens", "Say hello", 200),
        ("VAT prompt, medium tokens", "What is the VAT rate?", 200),
        ("VAT prompt, high tokens", "What is the VAT rate?", 500),
        ("Complex prompt, high tokens", "List 5 longevity supplement brands", 500),
    ]
    
    for test_name, prompt, max_tokens in tests:
        print(f"\n--- {test_name} ---")
        print(f"Prompt: {prompt}")
        print(f"Max tokens: {max_tokens}")
        
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=max_tokens,
            grounded=False,
            als_context={'country_code': 'US', 'locale': 'en-US'}
        )
        
        try:
            response = await adapter.complete(request)
            
            print(f"Success: {response.success}")
            print(f"Has content: {bool(response.content)}")
            print(f"Content length: {len(response.content) if response.content else 0}")
            
            if response.content:
                print(f"Response preview: {response.content[:200]}...")
            else:
                print("Response is empty")
            
            # Check metadata for clues
            if response.metadata:
                print(f"Finish reason: {response.metadata.get('finish_reason', 'unknown')}")
                if 'raw_response' in response.metadata:
                    raw = response.metadata['raw_response']
                    if isinstance(raw, str):
                        print(f"Raw response preview: {raw[:200]}")
            
            # Check usage
            if response.usage:
                print(f"Tokens used: {response.usage.get('total_tokens', 0)}")
                
        except Exception as e:
            print(f"Error: {e}")
        
        await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("DIAGNOSIS")
    print("="*60)
    
    print("""
Possible issues:
1. MAX_TOKENS limit being hit before response completes
2. Safety filters blocking content
3. Response extraction logic failing
4. Model behavior difference between grounded/ungrounded

Let's check the actual Vertex response format...
""")
    
    # Test with raw Vertex SDK
    print("\nTesting with raw Vertex SDK...")
    
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        
        vertexai.init(project="contestra-ai", location="europe-west4")
        
        model = GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            "What is the VAT rate?",
            generation_config={
                "max_output_tokens": 500,
                "temperature": 0.3,
            }
        )
        
        print(f"Raw SDK response text: {response.text[:200] if hasattr(response, 'text') else 'No text attribute'}")
        print(f"Raw SDK candidates: {len(response.candidates) if hasattr(response, 'candidates') else 'No candidates'}")
        
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            print(f"Candidate finish reason: {candidate.finish_reason}")
            if hasattr(candidate, 'content'):
                print(f"Candidate content: {candidate.content}")
        
    except Exception as e:
        print(f"Raw SDK error: {e}")

if __name__ == "__main__":
    asyncio.run(test_vertex_ungrounded())