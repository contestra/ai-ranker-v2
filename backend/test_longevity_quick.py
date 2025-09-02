#!/usr/bin/env python3
"""
Quick test of key configurations for longevity prompt.
"""

import os
import sys
import asyncio
import json
from datetime import datetime

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env
from dotenv import load_dotenv
load_dotenv('/home/leedr/ai-ranker-v2/backend/.env')

# Configure models
os.environ['ALLOWED_OPENAI_MODELS'] = 'gpt-5-2025-08-07,gpt-4o'

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test prompt
LONGEVITY_PROMPT = "What was the most interesting longevity and healthspan extension news during August 2025?"

async def test_config(model: str, country: str, grounded: bool, with_als: bool = False):
    """Test a single configuration"""
    
    adapter = UnifiedLLMAdapter()
    
    # Build metadata
    metadata = {
        "country": country,
        "grounding_mode": "AUTO"
    }
    
    if with_als:
        metadata["als_present"] = True
        metadata["als_country"] = country
        metadata["als_locale"] = f"{country.lower()}_US" if country == "US" else f"{country.lower()}_DE"
        
    request = LLMRequest(
        messages=[{"role": "user", "content": LONGEVITY_PROMPT}],
        model=model,
        vendor="openai",
        grounded=grounded,
        max_tokens=150,
        meta=metadata
    )
    
    if with_als:
        request.metadata = metadata
    
    config_str = f"{model}/{country}/{'grounded' if grounded else 'ungrounded'}/{'ALS' if with_als else 'no-ALS'}"
    print(f"\nTesting: {config_str}")
    
    try:
        response = await adapter.complete(request)
        meta = response.metadata or {}
        
        print(f"  ✅ Success")
        if grounded:
            print(f"  Tool type: {meta.get('chosen_web_tool_type', 'none')}")
            print(f"  Tool used: {meta.get('grounding_detected', False)}")
            print(f"  Effective: {meta.get('grounded_effective', False)}")
            print(f"  Citations: {meta.get('anchored_citations_count', 0)} anchored")
        
        if response.content:
            print(f"  Response preview: {response.content[:80]}...")
        
        return {
            "config": config_str,
            "success": True,
            "grounded_effective": meta.get("grounded_effective", False),
            "tool_used": meta.get("grounding_detected", False),
            "tool_type": meta.get("chosen_web_tool_type"),
            "citations": meta.get("anchored_citations_count", 0)
        }
        
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:100]}")
        return {
            "config": config_str,
            "success": False,
            "error": str(e)[:200]
        }

async def main():
    print("=" * 60)
    print("QUICK LONGEVITY TEST")
    print("=" * 60)
    print(f"Prompt: {LONGEVITY_PROMPT[:50]}...")
    print(f"Time: {datetime.now().isoformat()}")
    print("-" * 60)
    
    # Test key configurations
    results = []
    
    # GPT-5 tests
    results.append(await test_config("gpt-5-2025-08-07", "US", True))
    results.append(await test_config("gpt-5-2025-08-07", "US", False))
    results.append(await test_config("gpt-5-2025-08-07", "DE", True))
    results.append(await test_config("gpt-5-2025-08-07", "US", True, with_als=True))
    
    # GPT-4o tests
    results.append(await test_config("gpt-4o", "US", True))
    results.append(await test_config("gpt-4o", "US", False))
    results.append(await test_config("gpt-4o", "DE", True))
    results.append(await test_config("gpt-4o", "US", True, with_als=True))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    successful = sum(1 for r in results if r["success"])
    print(f"\nSuccess Rate: {successful}/{len(results)}")
    
    # Grounding effectiveness
    grounded_results = [r for r in results if "grounded/no-ALS" in r["config"] and r["success"]]
    if grounded_results:
        tools_used = sum(1 for r in grounded_results if r["tool_used"])
        print(f"\nGrounding Tool Usage: {tools_used}/{len(grounded_results)}")
        
        for model in ["gpt-5-2025-08-07", "gpt-4o"]:
            model_grounded = [r for r in grounded_results if model in r["config"]]
            if model_grounded:
                model_tools = sum(1 for r in model_grounded if r["tool_used"])
                print(f"  {model}: {model_tools}/{len(model_grounded)} invoked tools")
    
    # Tool type used
    tool_types = set(r["tool_type"] for r in results if r.get("tool_type"))
    if tool_types:
        print(f"\nTool types negotiated: {', '.join(tool_types)}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"longevity_quick_results_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "prompt": LONGEVITY_PROMPT,
            "results": results
        }, f, indent=2)
    
    print(f"\n📁 Results saved to: {filename}")

if __name__ == "__main__":
    asyncio.run(main())