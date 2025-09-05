#!/usr/bin/env python3
"""Test multi-turn conversation preservation in all adapters."""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Set required environment variables
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["LLM_TIMEOUT_GR"] = "120"
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
os.environ["VERTEX_PROJECT"] = os.getenv("VERTEX_PROJECT", "")


async def test_multi_turn(vendor: str, model: str):
    """Test multi-turn conversation handling."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter_name = f"{vendor}/{model}"
    print(f"\n{'='*80}")
    print(f"Testing Multi-Turn: {adapter_name}")
    print('='*80)
    
    try:
        # Initialize adapter
        adapter = UnifiedLLMAdapter()
        
        # Create multi-turn conversation
        messages = [
            {
                "role": "system",
                "content": "You are a helpful health assistant. Keep track of the conversation context."
            },
            {
                "role": "user",
                "content": "Tell me about vitamin D benefits."
            },
            {
                "role": "assistant",
                "content": "Vitamin D has several important health benefits:\n\n1. **Bone Health**: Helps calcium absorption for strong bones\n2. **Immune Support**: Strengthens immune system function\n3. **Mood Regulation**: May help with seasonal depression\n4. **Heart Health**: Supports cardiovascular function\n\nMost people get vitamin D from sunlight, but supplements can help during winter months."
            },
            {
                "role": "user",
                "content": "What about dosage? How much should I take based on what you just told me?"
            }
        ]
        
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=messages,
            grounded=False,
            max_tokens=300,
            temperature=0.7
        )
        
        # Execute request
        start = datetime.now()
        response = await adapter.complete(request)
        elapsed = (datetime.now() - start).total_seconds()
        
        # Check response
        content = response.content if hasattr(response, 'content') else ""
        print(f"\n✅ Success in {elapsed:.2f}s")
        print(f"\n📝 Response ({len(content)} chars):")
        print("-" * 40)
        print(content[:500] + "..." if len(content) > 500 else content)
        print("-" * 40)
        
        # Verify context awareness
        context_aware = False
        if content:
            # Check if response references previous context
            keywords = ["mentioned", "discussed", "above", "earlier", "vitamin d", "benefits"]
            content_lower = content.lower()
            context_aware = any(kw in content_lower for kw in keywords)
        
        print(f"\n🧠 Context Awareness: {'YES' if context_aware else 'NO'}")
        
        return {
            "adapter": adapter_name,
            "success": True,
            "elapsed": elapsed,
            "content_length": len(content),
            "context_aware": context_aware,
            "response_preview": content[:200]
        }
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)[:200]}")
        return {
            "adapter": adapter_name,
            "success": False,
            "error": str(e)
        }


async def main():
    """Run all tests."""
    print("\n" + "#"*80)
    print("# MULTI-TURN CONVERSATION TESTS")
    print("# " + datetime.now().isoformat())
    print("#"*80)
    
    tests = [
        ("openai", "gpt-5-2025-08-07"),
        ("gemini_direct", "gemini-2.0-flash"),  # 2.5-pro returns empty via API
        ("vertex", "gemini-2.0-flash"),  # 2.5-pro returns empty in europe-west4
    ]
    
    results = []
    for vendor, model in tests:
        result = await test_multi_turn(vendor, model)
        results.append(result)
        await asyncio.sleep(2)  # Pause between tests
    
    # Summary
    print(f"\n{'#'*80}")
    print("# SUMMARY")
    print(f"{'#'*80}\n")
    
    print("| Adapter | Status | Context Aware | Time |")
    print("|---------|--------|---------------|------|")
    for r in results:
        status = "✅" if r.get('success') else "❌"
        aware = "YES" if r.get('context_aware') else "NO"
        time = f"{r.get('elapsed', 0):.2f}s" if r.get('success') else "N/A"
        print(f"| {r['adapter']:25} | {status:6} | {aware:13} | {time:6} |")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"multi_turn_test_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Results saved: {results_file}")


if __name__ == "__main__":
    asyncio.run(main())