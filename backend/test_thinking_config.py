#!/usr/bin/env python3
"""Test that thinking configuration works with correct snake_case fields."""

import asyncio
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
os.environ["GEMINI_PRO_THINKING_BUDGET"] = "256"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_UNGROUNDED"] = "768"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_GROUNDED"] = "1536"


async def test_thinking_budget():
    """Test that thinking budget is properly applied and returns usage."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*80)
    print("THINKING CONFIGURATION TEST")
    print("="*80 + "\n")
    
    # Test both Vertex and Gemini Direct
    tests = [
        ("vertex", "gemini-2.5-pro"),
        ("gemini_direct", "gemini-2.5-pro")
    ]
    
    for vendor, model in tests:
        print(f"\nTesting {vendor}/{model}...")
        print("-" * 40)
        
        # Create request with thinking-worthy prompt
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{
                "role": "user",
                "content": "Explain step by step how to solve: If a train travels 120 miles in 2 hours, and then 180 miles in 3 hours, what is its average speed for the entire journey?"
            }],
            grounded=False,  # Ungrounded to focus on thinking
            max_tokens=500,
            temperature=0.7
        )
        
        # The router should apply thinking defaults for Gemini-2.5-Pro
        try:
            start = datetime.now()
            response = await adapter.complete(request)
            elapsed = (datetime.now() - start).total_seconds()
            
            print(f"✅ Success: {response.success}")
            print(f"⏱️  Time: {elapsed:.2f}s")
            
            # Check if we got thinking tokens in usage
            if hasattr(response, 'metadata') and response.metadata:
                metadata = response.metadata
                
                # Check for usage
                if 'usage' in metadata:
                    usage = metadata['usage']
                    thoughts_tokens = usage.get('thoughts_token_count', 0)
                    input_tokens = usage.get('input_token_count', 0)
                    output_tokens = usage.get('output_token_count', 0)
                    total_tokens = usage.get('total_token_count', 0)
                    
                    print(f"\n📊 Token Usage:")
                    print(f"  - Thoughts: {thoughts_tokens} {'✅' if thoughts_tokens > 0 else '❌ (not working!)'}")
                    print(f"  - Input: {input_tokens}")
                    print(f"  - Output: {output_tokens}")
                    print(f"  - Total: {total_tokens}")
                    
                    if thoughts_tokens > 0:
                        print(f"\n✅ THINKING BUDGET IS WORKING for {vendor}")
                    else:
                        print(f"\n⚠️  WARNING: No thinking tokens reported for {vendor}")
                        print("     This might mean the snake_case fix didn't work or the model didn't use thinking")
                else:
                    print("\n⚠️  No usage data in metadata")
                
                # Check thinking config was applied
                if 'thinking_budget_tokens' in metadata:
                    print(f"\n🎯 Thinking budget applied: {metadata['thinking_budget_tokens']} tokens")
            
            # Show a bit of the response to verify quality
            if response.content:
                print(f"\n📝 Response preview (first 200 chars):")
                print(response.content[:200] + "..." if len(response.content) > 200 else response.content)
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*80)
    print("Test complete. Check if thoughts_token_count > 0 for verification.")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_thinking_budget())