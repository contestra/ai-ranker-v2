#!/usr/bin/env python3
"""
Test without tools field entirely.
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


async def test_no_tools():
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI()
    
    print("🚀 Testing WITHOUT tools field...")
    
    # Don't include tools field at all
    response = await client.responses.create(
        model="gpt-5-2025-08-07",
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": "You are a helpful assistant."}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Say 'hello world'."}]}
        ],
        max_output_tokens=50,
        timeout=30
    )
    
    print(f"\n📊 Response:")
    print(f"  output_text: '{response.output_text}'")
    print(f"  output types: {[item.type for item in response.output] if response.output else []}")
    
    # Check for text
    has_text = False
    if response.output:
        for item in response.output:
            if item.type == "message":
                has_text = True
                if hasattr(item, "content") and isinstance(item.content, list):
                    for c in item.content:
                        if hasattr(c, "text"):
                            print(f"  Message text: '{c.text}'")
    
    # Check usage
    if hasattr(response, "usage"):
        usage = response.usage
        print(f"\n📈 Usage:")
        print(f"  output_tokens: {getattr(usage, 'output_tokens', 0)}")
        print(f"  reasoning_tokens: {getattr(usage, 'reasoning_tokens', 0)}")
    
    return response.output_text or has_text


if __name__ == "__main__":
    result = asyncio.run(test_no_tools())
    print(f"\n{'✅ Got output' if result else '❌ No output'}")