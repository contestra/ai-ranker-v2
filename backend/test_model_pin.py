#!/usr/bin/env python3
"""
Test model pinning and validation
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

async def test_allowed_models():
    """Test allowed models work"""
    adapter = UnifiedLLMAdapter()
    
    tests = [
        ("openai", "gpt-5", "OpenAI GPT-5"),
        ("openai", "gpt-5-chat-latest", "OpenAI GPT-5 latest"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", "Vertex Gemini 2.5-pro"),
    ]
    
    for vendor, model, name in tests:
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{"role": "user", "content": "Say 'hello'"}],
            temperature=0.5,
            max_tokens=10,
            grounded=False
        )
        
        print(f"\nTesting {name}...")
        try:
            response = await adapter.complete(request)
            if response.content:
                print(f"  ✅ Success: {response.content[:30]}")
            else:
                print(f"  ⚠️ Empty response but no error")
        except Exception as e:
            print(f"  ❌ Error: {e}")

async def test_disallowed_models():
    """Test disallowed models are rejected"""
    adapter = UnifiedLLMAdapter()
    
    disallowed = [
        ("vertex", "gemini-2.0-flash", "Gemini 2.0 flash"),
        ("vertex", "gemini-2.0-pro-exp", "Gemini 2.0 pro exp"),
        ("vertex", "flash", "Flash shorthand"),
        ("openai", "gpt-4", "GPT-4"),
        ("openai", "chatty", "Chatty"),
    ]
    
    for vendor, model, name in disallowed:
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{"role": "user", "content": "Test"}],
            max_tokens=10
        )
        
        print(f"\nTesting {name} (should fail)...")
        try:
            response = await adapter.complete(request)
            print(f"  ❌ UNEXPECTED: Model was allowed! Response: {response.content[:30] if response.content else 'empty'}")
        except ValueError as e:
            if "MODEL_NOT_ALLOWED" in str(e):
                print(f"  ✅ Correctly rejected: {e}")
            else:
                print(f"  ❌ Wrong error: {e}")
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")

async def main():
    print("="*60)
    print("MODEL PINNING VALIDATION TEST")
    print("="*60)
    
    print("\n--- Testing Allowed Models ---")
    await test_allowed_models()
    
    print("\n--- Testing Disallowed Models ---")
    await test_disallowed_models()
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())