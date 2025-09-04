#!/usr/bin/env python3
"""
Test GPT-4 GROUNDED with German ALS
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


async def test_gpt4_grounded():
    """Test GPT-4 grounded with health news prompt."""
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
        model="gpt-4o",
        messages=messages,
        grounded=True,
        max_tokens=500,
        meta={"grounding_mode": "AUTO"}
    )
    
    print("Testing GPT-4 GROUNDED")
    print("="*50)
    print(f"ALS: {als_template}")
    print(f"Model: gpt-4o")
    print(f"Grounded: True (AUTO mode)")
    
    try:
        print("\nMaking request...")
        response = await adapter.complete(request, timeout=30)
        
        metadata = response.metadata or {}
        print(f"\n✅ Success!")
        print(f"Response API: {metadata.get('response_api', 'unknown')}")
        print(f"Tool calls: {metadata.get('tool_call_count', 0)}")
        print(f"Grounded effective: {response.grounded_effective}")
        print(f"Content length: {len(response.content)} chars")
        
        # Check for grounding markers
        content_lower = response.content.lower()
        has_sources = any(marker in content_lower for marker in ["according", "source", "http", "www"])
        print(f"Has source markers: {'✅' if has_sources else '❌'}")
        
        print(f"\n--- CONTENT ---")
        print(response.content)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_gpt4_grounded())
    print(f"\n{'✅ GPT-4 GROUNDED TEST PASSED' if success else '❌ GPT-4 GROUNDED TEST FAILED'}")