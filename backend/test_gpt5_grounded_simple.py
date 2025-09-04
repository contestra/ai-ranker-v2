#!/usr/bin/env python3
"""
Test GPT-5 GROUNDED with simple prompt
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


async def test_gpt5_grounded_simple():
    """Test GPT-5 grounded with simple current events prompt."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # German ALS
    als_template = "de-DE, Deutschland, Europe/Berlin timezone"
    
    messages = [
        {"role": "user", "content": f"{als_template}\n\nWhat is the current weather in Berlin?"}
    ]
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=messages,
        grounded=True,
        max_tokens=200,  # Small for rate limit
        meta={"grounding_mode": "AUTO"}
    )
    
    print("Testing GPT-5 GROUNDED (Simple Weather Query)")
    print("="*50)
    print(f"ALS: {als_template}")
    print(f"Prompt: What is the current weather in Berlin?")
    print(f"Grounded: True (AUTO mode)")
    
    try:
        print("\nMaking request...")
        response = await adapter.complete(request, timeout=30)
        
        metadata = response.metadata or {}
        print(f"\n✅ Success!")
        print(f"Tool calls: {metadata.get('tool_call_count', 0)}")
        print(f"Grounded effective: {response.grounded_effective}")
        print(f"Web tool: {metadata.get('web_tool_type', 'none')}")
        print(f"Content length: {len(response.content)} chars")
        
        # Check if search was performed
        if response.grounded_effective:
            print("✅ Model performed web search")
        else:
            print("ℹ️ Model decided search not needed")
        
        print(f"\n--- CONTENT ---")
        print(response.content)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)[:300]}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_gpt5_grounded_simple())
    print(f"\n{'✅ GPT-5 GROUNDED TEST PASSED' if success else '❌ GPT-5 GROUNDED TEST FAILED'}")