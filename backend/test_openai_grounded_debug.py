#!/usr/bin/env python3
"""Debug OpenAI grounded mode empty response issue."""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Set required environment variables
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["LLM_TIMEOUT_GR"] = "120"


async def test_openai_grounded():
    """Test OpenAI grounded mode and debug response structure."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*80)
    print("OPENAI GROUNDED MODE DEBUG")
    print("="*80 + "\n")
    
    # Create grounded request
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {
                "role": "user",
                "content": "Tell me the primary health and wellness news during August 2025"
            }
        ],
        grounded=True,
        max_tokens=1000,
        temperature=0.7,
        als_context={
            "country_code": "DE",
            "locale": "de-DE"
        }
    )
    
    request.metadata = {
        "als_country": "DE",
        "als_locale": "de-DE",
        "als_present": True
    }
    
    request.meta = {"grounding_mode": "AUTO"}
    
    try:
        # Hook into the OpenAI adapter to capture raw response
        original_complete = adapter.openai_adapter.complete
        raw_response_capture = {}
        
        async def hooked_complete(req, timeout=60):
            """Hook to capture raw response."""
            from app.llm.adapters.openai_adapter import OpenAIAdapter
            
            # Get the actual adapter instance
            oa = adapter.openai_adapter
            
            # Build payload
            payload = oa._build_payload(req, req.grounded)
            print("\n📤 Request Payload:")
            print(json.dumps(payload, indent=2, default=str))
            
            # Make the actual API call
            if req.grounded:
                response, web_tool_type = await oa._call_with_tool_negotiation(payload, timeout)
                print(f"\n🔧 Web Tool Type: {web_tool_type}")
            else:
                response = await oa.client.responses.create(**payload, timeout=timeout)
            
            # Capture raw response structure
            print("\n📥 Raw Response Structure:")
            print(f"  - Type: {type(response)}")
            print(f"  - Has output: {hasattr(response, 'output')}")
            print(f"  - Has output_text: {hasattr(response, 'output_text')}")
            
            if hasattr(response, 'output'):
                print(f"  - Output type: {type(response.output)}")
                if isinstance(response.output, list):
                    print(f"  - Output items: {len(response.output)}")
                    for i, item in enumerate(response.output):
                        print(f"\n  Item {i}:")
                        print(f"    - Type: {type(item)}")
                        print(f"    - Has type attr: {hasattr(item, 'type')}")
                        if hasattr(item, 'type'):
                            print(f"    - Item type: {item.type}")
                        print(f"    - Has content: {hasattr(item, 'content')}")
                        
                        # Debug message items
                        if hasattr(item, 'type') and item.type == 'message':
                            if hasattr(item, 'content'):
                                print(f"    - Content type: {type(item.content)}")
                                if isinstance(item.content, list):
                                    print(f"    - Content items: {len(item.content)}")
                                    for j, c in enumerate(item.content):
                                        print(f"      Content {j}: type={type(c)}, has_text={hasattr(c, 'text')}")
                                        if hasattr(c, 'text'):
                                            text_preview = c.text[:100] if c.text else "[EMPTY]"
                                            print(f"        Text preview: {text_preview}")
                        
                        # Debug tool calls
                        if hasattr(item, 'type') and item.type == 'function':
                            print(f"    - Function name: {getattr(item, 'name', 'N/A')}")
                            if hasattr(item, 'arguments'):
                                print(f"    - Has arguments: {bool(item.arguments)}")
            
            if hasattr(response, 'output_text'):
                text = response.output_text
                print(f"\n  Output Text: {len(text) if text else 0} chars")
                if text:
                    print(f"  Preview: {text[:200]}...")
            
            # Now call the original complete
            result = await original_complete(req, timeout)
            
            # Debug what we extracted
            print(f"\n📝 Extracted Content: {len(result.content) if result.content else 0} chars")
            if result.content:
                print(f"  Preview: {result.content[:200]}...")
            else:
                print("  [EMPTY CONTENT]")
            
            return result
        
        # Replace the complete method temporarily
        adapter.openai_adapter.complete = hooked_complete
        
        # Execute request
        print("\n🚀 Executing request...")
        response = await adapter.complete(request)
        
        # Display results
        print("\n" + "="*80)
        print("RESULTS")
        print("="*80)
        print(f"\n✅ Success: {response.success}")
        print(f"📝 Content Length: {len(response.content) if response.content else 0} chars")
        
        if response.content:
            print(f"\nContent Preview:\n{response.content[:500]}...")
        else:
            print("\n⚠️ EMPTY CONTENT RETURNED")
        
        if hasattr(response, 'metadata') and response.metadata:
            print(f"\n📊 Metadata:")
            for key, value in response.metadata.items():
                print(f"  - {key}: {value}")
        
        if hasattr(response, 'citations') and response.citations:
            print(f"\n📚 Citations: {len(response.citations)}")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_openai_grounded())