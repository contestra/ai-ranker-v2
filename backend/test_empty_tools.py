#!/usr/bin/env python3
"""
Test empty tools array behavior.
"""
import asyncio
import os
import sys
from pathlib import Path
import json

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


async def test_empty_tools():
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI()
    
    print("🚀 Testing empty tools behavior...")
    
    response = await client.responses.create(
        model="gpt-5-2025-08-07",
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": "You are a helpful assistant."}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Say 'hello world'."}]}
        ],
        tools=[],  # Empty tools
        max_output_tokens=50,
        timeout=30
    )
    
    print(f"\n📊 Response structure:")
    print(f"  output_text: '{response.output_text}'")
    print(f"  output_text type: {type(response.output_text)}")
    
    # Check if output_text has any hidden content
    if response.output_text is not None:
        print(f"  output_text repr: {repr(response.output_text)}")
        print(f"  output_text len: {len(response.output_text)}")
    
    # Check output array
    print(f"\n  output types: {[item.type for item in response.output] if response.output else []}")
    
    if response.output:
        for i, item in enumerate(response.output):
            print(f"\n  Item[{i}]:")
            print(f"    type: {item.type}")
            
            # Deep inspection of the item
            print(f"    __dict__: {item.__dict__}")
            
            # Try model_dump if it's a pydantic model
            if hasattr(item, "model_dump"):
                print(f"    model_dump: {json.dumps(item.model_dump(), indent=2)}")
    
    # Check usage
    if hasattr(response, "usage"):
        usage = response.usage
        print(f"\n📈 Usage:")
        print(f"  input_tokens: {getattr(usage, 'input_tokens', 0)}")
        print(f"  output_tokens: {getattr(usage, 'output_tokens', 0)}")
        print(f"  reasoning_tokens: {getattr(usage, 'reasoning_tokens', 0)}")
    
    # Check the entire response object
    print(f"\n🔍 Full response __dict__:")
    print(json.dumps(response.__dict__, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(test_empty_tools())