#!/usr/bin/env python3
"""
Test GPT-5 GROUNDED with German ALS (simplified)
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


async def test_gpt5_grounded():
    """Test GPT-5 grounded with health news prompt."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # German ALS
    als_template = "de-DE, Deutschland, Europe/Berlin timezone"
    
    messages = [
        {"role": "user", "content": f"{als_template}\n\nTell me the primary health and wellness news during August 2025"}
    ]
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=messages,
        grounded=True,
        max_tokens=500,  # Reduced for faster response
        meta={"grounding_mode": "AUTO"}
    )
    
    print("Testing GPT-5 GROUNDED")
    print("="*50)
    print(f"ALS: {als_template}")
    print(f"Grounded: True (AUTO mode)")
    
    try:
        print("\nMaking request...")
        response = await adapter.complete(request, timeout=30)  # Shorter timeout
        
        metadata = response.metadata or {}
        print(f"\n✅ Success!")
        print(f"Tool calls: {metadata.get('tool_call_count', 0)}")
        print(f"Grounded effective: {response.grounded_effective}")
        print(f"Web tool: {metadata.get('web_tool_type', 'none')}")
        print(f"Content length: {len(response.content)} chars")
        
        print(f"\n--- CONTENT (first 500 chars) ---")
        print(response.content[:500])
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)[:200]}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_gpt5_grounded())
    print(f"\n{'✅ TEST PASSED' if success else '❌ TEST FAILED'}")