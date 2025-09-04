#!/usr/bin/env python3
"""Debug the response structure from Responses API."""
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

async def debug_response():
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    import json
    
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'hello world'"}
        ],
        grounded=False,
        max_tokens=50
    )
    
    # Patch the adapter to log the raw response
    original_complete = adapter.complete
    
    async def patched_complete(req, timeout=60):
        print("\n🔍 Intercepting response...")
        response = await original_complete(req, timeout)
        
        print(f"\n📦 Response object type: {type(response)}")
        print(f"📦 Response.content: '{response.content}'")
        print(f"📦 Response attributes: {dir(response)}")
        
        # Try to get the raw SDK response
        if hasattr(adapter, '_last_raw_response'):
            raw = adapter._last_raw_response
            print(f"\n🔍 Raw SDK response type: {type(raw)}")
            print(f"🔍 Raw attributes: {dir(raw)}")
            
            if hasattr(raw, 'output_text'):
                print(f"🔍 raw.output_text: '{raw.output_text}'")
            if hasattr(raw, 'output'):
                print(f"🔍 raw.output: {raw.output}")
            if hasattr(raw, 'choices'):
                print(f"🔍 raw.choices: {raw.choices}")
                
        return response
    
    adapter.complete = patched_complete
    
    # Also patch the SDK call to capture raw response
    import openai
    client = adapter.client
    original_create = client.responses.create
    
    async def patched_create(**kwargs):
        print(f"\n📡 SDK call with payload: {json.dumps(kwargs, indent=2)}")
        response = await original_create(**kwargs)
        print(f"\n📡 SDK response type: {type(response)}")
        print(f"📡 SDK response attributes: {dir(response)}")
        
        if hasattr(response, 'output_text'):
            print(f"📡 response.output_text: '{response.output_text}'")
        if hasattr(response, 'text'):
            print(f"📡 response.text: '{response.text}'")
        if hasattr(response, 'output'):
            print(f"📡 response.output: {response.output}")
            if hasattr(response.output, '__iter__'):
                for i, item in enumerate(response.output):
                    print(f"📡 response.output[{i}]: type={type(item)}, {item}")
        
        # Store for later inspection
        adapter._last_raw_response = response
        return response
        
    client.responses.create = patched_create
    
    print("🚀 Making request...")
    response = await adapter.complete(request, timeout=30)
    
    print(f"\n✅ Final response.content: '{response.content}'")
    print(f"✅ Final response.metadata: {response.metadata}")
    
    return response.content

if __name__ == "__main__":
    content = asyncio.run(debug_response())
    print(f"\n🎯 FINAL CONTENT: '{content}'")