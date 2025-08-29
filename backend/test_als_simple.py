#!/usr/bin/env python3
"""
Simple ALS verification test
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

async def test_als():
    adapter = UnifiedLLMAdapter()
    
    # Test 1: Without ALS
    print("\n=== Test 1: Without ALS ===")
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        temperature=0,
        max_tokens=50,
        grounded=False
    )
    
    response1 = await adapter.complete(request1)
    print(f"Response: {response1.content}")
    
    # Test 2: With ALS context for Germany
    print("\n=== Test 2: With ALS (Germany) ===")
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        temperature=0,
        max_tokens=50,
        grounded=False,
        als_context={'country_code': 'DE', 'locale': 'en-DE'}
    )
    
    response2 = await adapter.complete(request2)
    print(f"Response: {response2.content}")
    
    # Check if messages were modified
    print(f"\nOriginal message: {request1.messages[0]['content']}")
    print(f"Modified message (should have ALS): {request2.messages[0]['content'][:200]}...")
    
    if request2.messages[0]['content'].startswith('[Context:'):
        print("✅ ALS was applied!")
    else:
        print("❌ ALS was NOT applied")

if __name__ == "__main__":
    asyncio.run(test_als())