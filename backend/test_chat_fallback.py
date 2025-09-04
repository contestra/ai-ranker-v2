#!/usr/bin/env python3
"""
Debug Chat Completions fallback for ungrounded.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_chat_fallback():
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Hook into the Chat Completions call
    original_chat_create = adapter.client.chat.completions.create
    chat_called = False
    
    async def hooked_chat_create(**kwargs):
        nonlocal chat_called
        chat_called = True
        print(f"\n🔧 Chat Completions call:")
        print(f"  Model: {kwargs.get('model')}")
        print(f"  Messages: {kwargs.get('messages')}")
        print(f"  Max tokens: {kwargs.get('max_tokens')} or max_completion_tokens: {kwargs.get('max_completion_tokens')}")
        
        response = await original_chat_create(**kwargs)
        
        print(f"\n📡 Chat response:")
        if hasattr(response, 'choices') and response.choices:
            msg = response.choices[0].message
            print(f"  Message content: '{msg.content}'")
            print(f"  Content type: {type(msg.content)}")
        else:
            print(f"  No choices in response")
        
        return response
    
    adapter.client.chat.completions.create = hooked_chat_create
    
    # Hook Responses API to ensure it's NOT called
    original_resp_create = adapter.client.responses.create
    resp_called = False
    
    async def hooked_resp_create(**kwargs):
        nonlocal resp_called
        resp_called = True
        print(f"\n⚠️ Responses API called (unexpected for ungrounded!)")
        return await original_resp_create(**kwargs)
    
    adapter.client.responses.create = hooked_resp_create
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'hello world'."}
        ],
        grounded=False,
        max_tokens=50
    )
    
    print("🚀 Testing ungrounded GPT-5...")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n📊 Results:")
    print(f"  Content: '{response.content}'")
    print(f"  Length: {len(response.content)}")
    print(f"  Chat API called: {chat_called}")
    print(f"  Responses API called: {resp_called}")
    print(f"  Metadata: {response.metadata}")
    
    success = len(response.content) > 0 and chat_called and not resp_called
    return success


if __name__ == "__main__":
    success = asyncio.run(test_chat_fallback())
    print(f"\n{'🎉 SUCCESS' if success else '❌ FAILED'}")