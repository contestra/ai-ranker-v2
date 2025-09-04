#!/usr/bin/env python3
"""
Test GPT-5 directly with Chat Completions API.
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


async def test_gpt5_chat():
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI()
    
    print("🚀 Testing GPT-5 with Chat Completions API directly...")
    
    # Test different configurations
    tests = [
        ("GPT-5 with max_completion_tokens", {
            "model": "gpt-5-2025-08-07",
            "max_completion_tokens": 50
        }),
        ("GPT-5 with max_tokens", {
            "model": "gpt-5-2025-08-07", 
            "max_tokens": 50
        }),
        ("GPT-4 for comparison", {
            "model": "gpt-4o",
            "max_tokens": 50
        }),
    ]
    
    for name, params in tests:
        print(f"\n{'='*60}")
        print(f"Test: {name}")
        print(f"Params: {params}")
        
        try:
            response = await client.chat.completions.create(
                messages=[
                    {"role": "user", "content": "Say 'hello world'."}
                ],
                **params,
                timeout=30
            )
            
            content = ""
            if response.choices:
                content = response.choices[0].message.content or ""
            
            print(f"  ✓ Success")
            print(f"  Content: '{content}'")
            print(f"  Length: {len(content)}")
            
            # Check usage
            if hasattr(response, 'usage'):
                usage = response.usage
                print(f"  Usage: prompt={getattr(usage, 'prompt_tokens', 0)}, "
                      f"completion={getattr(usage, 'completion_tokens', 0)}")
            
        except Exception as e:
            error_msg = str(e)[:300]
            print(f"  ✗ Error: {error_msg}")
        
        await asyncio.sleep(2)  # Rate limit


if __name__ == "__main__":
    asyncio.run(test_gpt5_chat())