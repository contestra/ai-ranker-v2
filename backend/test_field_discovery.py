#!/usr/bin/env python3
"""
Discover which fields make ungrounded responses emit message items.
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


async def test_field_combinations():
    """Test different field combinations to see what works."""
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI()
    
    # Base payload that we know doesn't work
    base_payload = {
        "model": "gpt-5-2025-08-07",
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": "You are a helpful assistant."}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Say 'hello world'."}]}
        ],
        "max_output_tokens": 50
    }
    
    # Test variations
    variations = [
        ("Base (no tools)", {}),
        ("Empty tools array", {"tools": []}),
        ("Modalities text", {"modalities": ["text"]}),
        ("Response format text", {"response_format": {"type": "text"}}),
        ("Both modalities and format", {"modalities": ["text"], "response_format": {"type": "text"}}),
        ("Tool choice none", {"tools": [], "tool_choice": "none"}),
        ("Text format hint", {"text": {"format": {"type": "text"}}}),
    ]
    
    results = []
    
    for name, extra_fields in variations:
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"Extra fields: {extra_fields}")
        
        payload = {**base_payload, **extra_fields}
        
        try:
            response = await client.responses.create(**payload, timeout=30)
            
            # Check response structure
            has_message = False
            output_text = response.output_text or ""
            output_types = []
            
            if response.output:
                output_types = [item.type for item in response.output]
                has_message = any(item.type == "message" for item in response.output)
            
            print(f"  ✓ Success")
            print(f"  output_text: '{output_text}'")
            print(f"  output types: {output_types}")
            print(f"  has message: {has_message}")
            
            results.append((name, True, has_message, output_text))
            
        except Exception as e:
            error_msg = str(e)[:100]
            print(f"  ✗ Error: {error_msg}")
            results.append((name, False, False, ""))
        
        await asyncio.sleep(2)  # Rate limit
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    for name, success, has_message, output_text in results:
        status = "✓" if success else "✗"
        msg_status = "MSG" if has_message else "NO-MSG"
        text_status = "TEXT" if output_text else "EMPTY"
        print(f"  {status} {name}: {msg_status}, {text_status}")
    
    # Find what worked
    working = [(name, extra) for (name, extra), (_, success, has_msg, _) in zip(variations, results) 
               if success and has_msg]
    
    if working:
        print(f"\n🎉 WORKING COMBINATIONS:")
        for name, fields in working:
            print(f"  • {name}: {fields}")
    else:
        print(f"\n❌ No combination produced message items")


if __name__ == "__main__":
    asyncio.run(test_field_combinations())