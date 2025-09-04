#!/usr/bin/env python3
"""
Test if system message helps.
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


async def test_variations():
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI()
    
    tests = [
        ("User only", [
            {"role": "user", "content": [{"type": "input_text", "text": "Say 'hello world'."}]}
        ]),
        ("With system", [
            {"role": "system", "content": [{"type": "input_text", "text": "You are a helpful assistant. Always respond to requests."}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Say 'hello world'."}]}
        ]),
        ("Explicit instruction", [
            {"role": "user", "content": [{"type": "input_text", "text": "Please respond with the text 'hello world'. Do not search the web, just output the text directly."}]}
        ]),
    ]
    
    for name, input_msgs in tests:
        print(f"\n{'='*60}")
        print(f"Test: {name}")
        
        try:
            response = await client.responses.create(
                model="gpt-5-2025-08-07",
                input=input_msgs,
                tools=[{"type": "web_search"}],
                max_output_tokens=50,
                timeout=30
            )
            
            output_text = response.output_text or ""
            output_types = [item.type for item in response.output] if response.output else []
            
            # Check for message content
            message_content = ""
            if response.output:
                for item in response.output:
                    if item.type == "message" and hasattr(item, "content"):
                        if isinstance(item.content, list):
                            for content_item in item.content:
                                if hasattr(content_item, "text"):
                                    message_content += content_item.text
            
            # Check usage
            reasoning_tokens = 0
            output_tokens = 0
            if hasattr(response, "usage"):
                reasoning_tokens = getattr(response.usage, "reasoning_tokens", 0)
                output_tokens = getattr(response.usage, "output_tokens", 0)
            
            print(f"  ✓ Success")
            print(f"  output_text: '{output_text}'")
            print(f"  message content: '{message_content}'")
            print(f"  output types: {output_types}")
            print(f"  reasoning tokens: {reasoning_tokens}")
            print(f"  output tokens: {output_tokens}")
            
        except Exception as e:
            print(f"  ✗ Error: {str(e)[:200]}")
        
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(test_variations())