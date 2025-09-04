#!/usr/bin/env python3
"""
Test ungrounded with dummy tool fix.
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


async def test_ungrounded_fix():
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Hook to see the SDK call
    original_create = adapter.client.responses.create
    
    async def hooked_create(**kwargs):
        print(f"🔧 SDK payload:")
        print(f"  Model: {kwargs.get('model')}")
        print(f"  Tools: {kwargs.get('tools')}")
        print(f"  Max output tokens: {kwargs.get('max_output_tokens')}")
        
        # Check system message
        input_msgs = kwargs.get('input', [])
        for msg in input_msgs:
            if msg.get('role') == 'system':
                content = msg.get('content', [])
                if content and isinstance(content, list):
                    text = content[0].get('text', '')
                    print(f"  System message: '{text[:100]}...'")
        
        response = await original_create(**kwargs)
        
        print(f"\n📡 Response:")
        print(f"  output_text: '{response.output_text}'")
        print(f"  output types: {[item.type for item in response.output] if response.output else []}")
        
        # Check for message items
        has_message = False
        message_content = ""
        if response.output:
            for item in response.output:
                if item.type == "message" and hasattr(item, "content"):
                    has_message = True
                    if isinstance(item.content, list):
                        for content_item in item.content:
                            if hasattr(content_item, "text"):
                                message_content += content_item.text
        
        print(f"  Has message item: {has_message}")
        print(f"  Message content: '{message_content}'")
        
        return response
    
    adapter.client.responses.create = hooked_create
    
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
    
    print("🚀 Testing ungrounded with dummy tool fix...")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n✅ Final result:")
    print(f"  Content: '{response.content}'")
    print(f"  Length: {len(response.content)}")
    print(f"  Metadata: {response.metadata}")
    
    return len(response.content) > 0


if __name__ == "__main__":
    success = asyncio.run(test_ungrounded_fix())
    print(f"\n{'🎉 SUCCESS' if success else '❌ FAILED'}")