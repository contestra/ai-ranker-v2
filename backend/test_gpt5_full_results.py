#!/usr/bin/env python3
"""
Test GPT-5 grounded and ungrounded with full results output
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


async def test_gpt5_ungrounded():
    """Test GPT-5 ungrounded with detailed output."""
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
        grounded=False,  # UNGROUNDED
        max_tokens=1000
    )
    
    print("="*80)
    print("GPT-5 UNGROUNDED TEST - FULL RESULTS")
    print("="*80)
    print(f"Model: {request.model}")
    print(f"ALS: {als_template}")
    print(f"Prompt: Tell me the primary health and wellness news during August 2025")
    print(f"Grounded: False (UNGROUNDED mode)")
    print(f"Max tokens: {request.max_tokens}")
    print("="*80)
    
    try:
        print("\nMaking request...")
        response = await adapter.complete(request, timeout=60)
        
        print("\n" + "="*80)
        print("RESPONSE METADATA")
        print("="*80)
        metadata = response.metadata or {}
        print(f"Success: {response.success}")
        print(f"Model Version: {response.model_version}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Tool Call Count: {metadata.get('tool_call_count', 0)}")
        print(f"Fallback Used: {metadata.get('fallback_used', False)}")
        print(f"Text Source: {metadata.get('text_source', 'unknown')}")
        print(f"Latency: {response.latency_ms}ms")
        
        print("\n" + "="*80)
        print("USAGE STATISTICS")
        print("="*80)
        if response.usage:
            print(f"Prompt Tokens: {response.usage.get('prompt_tokens', 0)}")
            print(f"Completion Tokens: {response.usage.get('completion_tokens', 0)}")
            print(f"Reasoning Tokens: {response.usage.get('reasoning_tokens', 0)}")
            print(f"Total Tokens: {response.usage.get('total_tokens', 0)}")
        
        print("\n" + "="*80)
        print("FULL RESPONSE CONTENT")
        print("="*80)
        print(response.content[:2000] if len(response.content) > 2000 else response.content)
        if len(response.content) > 2000:
            print(f"\n... (truncated, total length: {len(response.content)} chars)")
        
        print("\n" + "="*80)
        print("CONTENT ANALYSIS")
        print("="*80)
        content_lower = response.content.lower()
        
        # Check response characteristics
        print(f"Response length: {len(response.content)} characters")
        print(f"Language: {'German' if any(term in content_lower for term in ['der', 'die', 'das', 'und', 'ist']) else 'English'}")
        
        # Check for specific content
        if "cannot" in content_lower or "don't have" in content_lower:
            print("Behavior: DECLINED (refused to speculate)")
        elif len(response.content) > 500:
            print("Behavior: SPECULATIVE (provided predictions)")
        else:
            print("Behavior: BRIEF")
        
        return response
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)[:500]}")
        return None


async def test_gpt5_grounded():
    """Test GPT-5 grounded with detailed output."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # German ALS - simpler prompt to avoid rate limits
    als_template = "de-DE, Deutschland, Europe/Berlin timezone"
    
    messages = [
        {"role": "user", "content": f"{als_template}\n\nWhat is the current weather in Berlin?"}
    ]
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=messages,
        grounded=True,  # GROUNDED
        max_tokens=300,  # Small to avoid rate limits
        meta={"grounding_mode": "AUTO"}
    )
    
    print("\n" + "="*80)
    print("GPT-5 GROUNDED TEST - FULL RESULTS")
    print("="*80)
    print(f"Model: {request.model}")
    print(f"ALS: {als_template}")
    print(f"Prompt: What is the current weather in Berlin?")
    print(f"Grounded: True (AUTO mode)")
    print(f"Max tokens: {request.max_tokens}")
    print("="*80)
    
    try:
        print("\nMaking request...")
        response = await adapter.complete(request, timeout=60)
        
        print("\n" + "="*80)
        print("RESPONSE METADATA")
        print("="*80)
        metadata = response.metadata or {}
        print(f"Success: {response.success}")
        print(f"Model Version: {response.model_version}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Web Tool Type: {metadata.get('web_tool_type', 'none')}")
        print(f"Tool Call Count: {metadata.get('tool_call_count', 0)}")
        print(f"Tool Types: {metadata.get('tool_types', [])}")
        print(f"Latency: {response.latency_ms}ms")
        
        print("\n" + "="*80)
        print("USAGE STATISTICS")
        print("="*80)
        if response.usage:
            print(f"Prompt Tokens: {response.usage.get('prompt_tokens', 0)}")
            print(f"Completion Tokens: {response.usage.get('completion_tokens', 0)}")
            print(f"Reasoning Tokens: {response.usage.get('reasoning_tokens', 0)}")
            print(f"Total Tokens: {response.usage.get('total_tokens', 0)}")
        
        # Extract URLs
        print("\n" + "="*80)
        print("EXTRACTED URLs")
        print("="*80)
        import re
        urls = re.findall(r'https?://[^\s\)]+', response.content)
        if urls:
            for url in set(urls):
                print(f"  - {url}")
        else:
            print("No URLs found")
        
        print("\n" + "="*80)
        print("FULL RESPONSE CONTENT")
        print("="*80)
        print(response.content)
        
        return response
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)[:500]}")
        if "rate" in str(e).lower():
            print("Note: Rate limit hit - GPT-5 has low TPM limits")
        return None


async def main():
    """Run both tests and compare."""
    print("\n" + "="*80)
    print("TESTING GPT-5 UNGROUNDED AND GROUNDED MODES")
    print("="*80)
    
    # Test ungrounded first
    ungrounded_response = await test_gpt5_ungrounded()
    
    # Wait a bit to avoid rate limits
    print("\nWaiting 5 seconds before grounded test...")
    await asyncio.sleep(5)
    
    # Test grounded
    grounded_response = await test_gpt5_grounded()
    
    # Summary comparison
    print("\n" + "="*80)
    print("GPT-5 COMPARISON SUMMARY")
    print("="*80)
    
    if ungrounded_response:
        print("\nUNGROUNDED:")
        print(f"  - Response length: {len(ungrounded_response.content)} chars")
        print(f"  - Latency: {ungrounded_response.latency_ms}ms")
        print(f"  - Tokens: {ungrounded_response.usage.get('total_tokens', 0) if ungrounded_response.usage else 'N/A'}")
        print(f"  - Behavior: {'Speculative' if len(ungrounded_response.content) > 500 else 'Conservative'}")
    
    if grounded_response:
        print("\nGROUNDED:")
        print(f"  - Response length: {len(grounded_response.content)} chars")
        print(f"  - Latency: {grounded_response.latency_ms}ms")
        print(f"  - Tokens: {grounded_response.usage.get('total_tokens', 0) if grounded_response.usage else 'N/A'}")
        print(f"  - Tool calls: {grounded_response.metadata.get('tool_call_count', 0) if grounded_response.metadata else 0}")
        print(f"  - Grounded effective: {grounded_response.grounded_effective}")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())