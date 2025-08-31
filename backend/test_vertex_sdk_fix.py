#!/usr/bin/env python3
"""
Test the complete Vertex SDK-only fix
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

async def test_vertex_sdk_fix():
    """Test all SDK-only fixes"""
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*60)
    print("VERTEX SDK-ONLY FIX TEST")
    print("="*60)
    
    tests = [
        ("Very low (100) - will increase to 500 then retry at 750", "What is the VAT rate?", 100),
        ("Low (200) - will increase to 500 then retry at 750", "What is the VAT rate?", 200),
        ("Medium (500) - should retry at 750", "What is the VAT rate?", 500),
        ("High (1000) - should work", "What is the VAT rate?", 1000),
        ("Very high (6000) - definitely works", "What is the VAT rate?", 6000),
    ]
    
    for test_name, prompt, max_tokens in tests:
        print(f"\n--- {test_name} ---")
        print(f"Prompt: {prompt}")
        print(f"Max tokens: {max_tokens}")
        
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
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
            
            # Check metadata
            if response.metadata:
                print("\nMetadata:")
                print(f"  finish_reason: {response.metadata.get('finish_reason', 'not_provided')}")
                print(f"  retry_attempted: {response.metadata.get('retry_attempted', False)}")
                print(f"  retry_successful: {response.metadata.get('retry_successful', 'N/A')}")
                print(f"  retry_reason: {response.metadata.get('retry_reason', 'N/A')}")
                
                if response.metadata.get('error_type'):
                    print(f"  error_type: {response.metadata['error_type']}")
                    print(f"  why_no_content: {response.metadata.get('why_no_content', '')}")
            
            # Check usage
            if response.usage:
                print(f"\nToken usage:")
                print(f"  prompt_tokens: {response.usage.get('prompt_tokens', 0)}")
                print(f"  completion_tokens: {response.usage.get('completion_tokens', 0)}")
                print(f"  total_tokens: {response.usage.get('total_tokens', 0)}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("FIX SUMMARY")
    print("="*60)
    print("""
✅ Implemented:
1. Multi-part extraction (checks all candidates & parts)
2. Smart retry on MAX_TOKENS/empty (with text/plain + 50% more tokens)
3. Proper system_instruction (system separate, ALS in user)
4. Truthful telemetry (success=False when empty)
5. Temperature stays user-like (0.6-0.7, not 0.3)

🔍 What to check:
- Retry should trigger for low token limits
- System instruction properly separated
- ALS order preserved (system → ALS → user)
- Success=False for truly empty responses
""")

if __name__ == "__main__":
    asyncio.run(test_vertex_sdk_fix())