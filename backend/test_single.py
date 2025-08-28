#!/usr/bin/env python3
"""
Quick single test to debug issues
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env
from dotenv import load_dotenv
load_dotenv()

# Set DISABLE_PROXIES
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_single():
    """Test a single OpenAI call"""
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is 2+2? Give just the number."}],
        temperature=0,
        max_tokens=10,
        grounded=False
    )
    
    print(f"Testing: {request.vendor} / {request.model}")
    print(f"Message: {request.messages[0]['content']}")
    
    try:
        response = await adapter.complete(request)
        print(f"✅ Success!")
        print(f"Response: {response.content}")
        print(f"Tokens: {response.usage}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_single())