#!/usr/bin/env python3
"""
Test if omitting tools field entirely helps ungrounded responses.
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


async def test_no_tools_field():
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # Patch to remove tools field entirely for ungrounded
    original_build = adapter._build_ungrounded_responses_payload
    
    def patched_build(request, system_content, user_content, json_schema=None):
        payload, tokens = original_build(request, system_content, user_content, json_schema)
        # Remove tools field entirely
        payload.pop("tools", None)
        print(f"📦 Payload without tools field: {list(payload.keys())}")
        return payload, tokens
    
    adapter._build_ungrounded_responses_payload = patched_build
    
    # Hook to see raw response
    original_create = adapter.client.responses.create
    
    async def hooked_create(**kwargs):
        print(f"🔧 SDK payload keys: {list(kwargs.keys())}")
        print(f"🔧 Has tools: {'tools' in kwargs}")
        
        response = await original_create(**kwargs)
        
        print(f"📡 Response output_text: '{response.output_text}'")
        print(f"📡 Response output types: {[item.type for item in response.output] if response.output else []}")
        
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
    
    print("\n🚀 Testing without tools field...")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n✅ Final content: '{response.content}'")
    print(f"✅ Content length: {len(response.content)}")
    
    return len(response.content) > 0


if __name__ == "__main__":
    success = asyncio.run(test_no_tools_field())
    print(f"\n{'🎉 SUCCESS' if success else '❌ FAILED'}")