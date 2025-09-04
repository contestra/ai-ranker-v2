#!/usr/bin/env python3
"""
Compare raw response structure between grounded and ungrounded.
"""
import asyncio
import json
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


async def compare_responses():
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    import openai
    
    adapter = OpenAIAdapter()
    
    # Hook into raw SDK response
    raw_responses = {}
    original_create = adapter.client.responses.create
    
    async def hooked_create(**kwargs):
        response = await original_create(**kwargs)
        
        # Store raw response
        mode = "grounded" if kwargs.get("tools") else "ungrounded"
        raw_responses[mode] = {
            "output_text": response.output_text,
            "output_types": [item.type for item in response.output] if response.output else [],
            "output_items": []
        }
        
        # Detailed output inspection
        if response.output:
            for item in response.output:
                item_info = {
                    "type": item.type,
                    "has_content": hasattr(item, "content"),
                    "content_value": str(item.content)[:100] if hasattr(item, "content") else None,
                    "has_text": hasattr(item, "text"),
                    "text_value": str(item.text)[:100] if hasattr(item, "text") else None,
                }
                raw_responses[mode]["output_items"].append(item_info)
        
        return response
    
    adapter.client.responses.create = hooked_create
    
    # Test UNGROUNDED
    print("\n" + "="*80)
    print("TESTING UNGROUNDED")
    print("="*80)
    
    request1 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'hello world'."}
        ],
        grounded=False,
        max_tokens=50
    )
    
    response1 = await adapter.complete(request1, timeout=30)
    
    # Test GROUNDED
    print("\n" + "="*80)
    print("TESTING GROUNDED")
    print("="*80)
    
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "What is the capital of France? Just say the city name."}
        ],
        grounded=True,
        max_tokens=50,
        meta={"grounding_mode": "AUTO"}
    )
    
    response2 = await adapter.complete(request2, timeout=30)
    
    # Compare
    print("\n" + "="*80)
    print("COMPARISON")
    print("="*80)
    
    for mode, data in raw_responses.items():
        print(f"\n{mode.upper()}:")
        print(f"  output_text: '{data['output_text']}'")
        print(f"  output types: {data['output_types']}")
        print(f"  output items:")
        for i, item in enumerate(data["output_items"]):
            print(f"    [{i}] type={item['type']}")
            if item["has_content"]:
                print(f"        content: {item['content_value']}")
            if item["has_text"]:
                print(f"        text: {item['text_value']}")
    
    # Final content
    print(f"\nFinal extracted content:")
    print(f"  UNGROUNDED: '{response1.content}'")
    print(f"  GROUNDED: '{response2.content}'")
    
    return raw_responses


if __name__ == "__main__":
    data = asyncio.run(compare_responses())