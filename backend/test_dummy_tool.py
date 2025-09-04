#!/usr/bin/env python3
"""
Test if adding a dummy tool forces message output in ungrounded mode.
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


async def test_dummy_tool():
    """Test if a dummy tool forces message output."""
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI()
    
    # Base payload
    base_payload = {
        "model": "gpt-5-2025-08-07",
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": "You are a helpful assistant."}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Say 'hello world'. Do not use any tools."}]}
        ],
        "max_output_tokens": 50
    }
    
    # Dummy tool that won't be used
    dummy_tool = {
        "type": "function",
        "function": {
            "name": "dummy_never_use",
            "description": "Never use this tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        }
    }
    
    # Test variations
    variations = [
        ("No tools", {}),
        ("With dummy tool", {"tools": [dummy_tool]}),
        ("Dummy tool + tool_choice none", {"tools": [dummy_tool], "tool_choice": "none"}),
        ("Dummy tool + tool_choice auto", {"tools": [dummy_tool], "tool_choice": "auto"}),
    ]
    
    results = []
    
    for name, extra_fields in variations:
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"Extra fields keys: {list(extra_fields.keys())}")
        
        payload = {**base_payload, **extra_fields}
        
        try:
            response = await client.responses.create(**payload, timeout=30)
            
            # Check response structure
            has_message = False
            output_text = response.output_text or ""
            output_types = []
            message_content = ""
            
            if response.output:
                output_types = [item.type for item in response.output]
                has_message = any(item.type == "message" for item in response.output)
                
                # Extract message content
                for item in response.output:
                    if item.type == "message" and hasattr(item, "content"):
                        if isinstance(item.content, list):
                            for content_item in item.content:
                                if hasattr(content_item, "text"):
                                    message_content += content_item.text
            
            print(f"  ✓ Success")
            print(f"  output_text: '{output_text}'")
            print(f"  output types: {output_types}")
            print(f"  has message: {has_message}")
            print(f"  message content: '{message_content}'")
            
            results.append((name, True, has_message, output_text, message_content))
            
        except Exception as e:
            error_msg = str(e)[:200]
            print(f"  ✗ Error: {error_msg}")
            results.append((name, False, False, "", ""))
        
        await asyncio.sleep(2)  # Rate limit
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    for name, success, has_message, output_text, message_content in results:
        status = "✓" if success else "✗"
        msg_status = "MSG" if has_message else "NO-MSG"
        text_status = f"TEXT='{output_text[:20]}...'" if output_text else "EMPTY"
        content_status = f"CONTENT='{message_content[:20]}...'" if message_content else "NO-CONTENT"
        print(f"  {status} {name}: {msg_status}, {text_status}, {content_status}")
    
    # Find what worked
    working = [(name, extra) for (name, extra), (_, success, has_msg, out_txt, content) in zip(variations, results) 
               if success and (has_msg or out_txt or content)]
    
    if working:
        print(f"\n🎉 WORKING COMBINATIONS:")
        for name, fields in working:
            print(f"  • {name}: {list(fields.keys())}")
        
        # Show the winning content
        for name, _, _, out_txt, content in results:
            if out_txt or content:
                print(f"\nContent from '{name}':")
                print(f"  output_text: '{out_txt}'")
                print(f"  message content: '{content}'")
    else:
        print(f"\n❌ No combination produced message items or content")


if __name__ == "__main__":
    asyncio.run(test_dummy_tool())