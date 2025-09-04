#!/usr/bin/env python3
"""
Inspect reasoning item content.
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


async def test_reasoning():
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI()
    
    print("🚀 Testing reasoning item inspection...")
    
    # Simple ungrounded request
    response = await client.responses.create(
        model="gpt-5-2025-08-07",
        input=[
            {"role": "user", "content": [{"type": "input_text", "text": "Say 'hello world'."}]}
        ],
        tools=[{"type": "web_search"}],  # Include but don't use
        max_output_tokens=50,
        timeout=30
    )
    
    print(f"\nResponse structure:")
    print(f"  output_text: '{response.output_text}'")
    print(f"  output types: {[item.type for item in response.output] if response.output else []}")
    
    if response.output:
        for i, item in enumerate(response.output):
            print(f"\n  Item[{i}]:")
            print(f"    type: {item.type}")
            print(f"    attributes: {dir(item)}")
            
            # Try to access various properties
            for attr in ["content", "text", "value", "data", "reasoning", "message"]:
                if hasattr(item, attr):
                    value = getattr(item, attr)
                    print(f"    {attr}: {value}")
                    if value and hasattr(value, "__dict__"):
                        print(f"      {attr}.__dict__: {value.__dict__}")
    
    # Also check usage
    if hasattr(response, "usage"):
        usage = response.usage
        print(f"\nUsage:")
        print(f"  input_tokens: {getattr(usage, 'input_tokens', 0)}")
        print(f"  output_tokens: {getattr(usage, 'output_tokens', 0)}")
        print(f"  reasoning_tokens: {getattr(usage, 'reasoning_tokens', 0)}")


if __name__ == "__main__":
    asyncio.run(test_reasoning())