#!/usr/bin/env python3
"""
Canary test for pinned model (gpt-5-2025-08-07) web search capability.
Mark as @slow and run in scheduled CI or manual guard.
"""

import os
import sys
import asyncio
import json
from datetime import datetime
from typing import Dict, Any

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env file
from dotenv import load_dotenv
load_dotenv('/home/leedr/ai-ranker-v2/backend/.env')

# Configure for production-like settings
os.environ['ALLOWED_OPENAI_MODELS'] = 'gpt-5-2025-08-07'

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_canary_openai_pinned_websearch() -> Dict[str, Any]:
    """
    Canary test for gpt-5-2025-08-07 with grounded search.
    
    Uses recency-biased prompt about central bank news to trigger web search.
    
    Expected outcomes:
    - tools_used == True
    - anchored_citations_count > 0  
    - response.model == "gpt-5-2025-08-07" (no remapping)
    
    Returns:
        Dict with test results and metrics
    """
    
    adapter = UnifiedLLMAdapter()
    
    # Recency-biased prompt about official sources
    request = LLMRequest(
        messages=[{
            "role": "user", 
            "content": "What are the latest announcements from the Federal Reserve or European Central Bank today?"
        }],
        model="gpt-5-2025-08-07",
        vendor="openai",
        grounded=True,
        max_tokens=200,
        meta={"grounding_mode": "AUTO"}
    )
    
    result = {
        "test": "canary_openai_pinned_websearch",
        "timestamp": datetime.now().isoformat(),
        "model": "gpt-5-2025-08-07",
        "passed": False,
        "metrics": {},
        "errors": []
    }
    
    try:
        response = await adapter.complete(request)
        meta = response.metadata or {}
        
        # Extract metrics
        tools_requested = bool(meta.get("response_api_tool_type"))
        tools_used = meta.get("grounding_detected", False)
        anchored_count = meta.get("anchored_citations_count", 0)
        model_echo = response.model == "gpt-5-2025-08-07"
        
        result["metrics"] = {
            "tools_requested": tools_requested,
            "tools_used": tools_used,
            "anchored_citations_count": anchored_count,
            "model_echo_match": model_echo,
            "grounded_effective": tools_used and anchored_count > 0,
            "response_api": meta.get("response_api"),
            "tool_type": meta.get("response_api_tool_type")
        }
        
        # Check assertions
        all_pass = (
            tools_used == True and
            anchored_count > 0 and
            model_echo == True
        )
        
        result["passed"] = all_pass
        
        if not all_pass:
            if not tools_used:
                result["errors"].append("Model did not invoke web_search tools")
            if anchored_count == 0:
                result["errors"].append("No anchored citations returned")
            if not model_echo:
                result["errors"].append(f"Model remapped: expected gpt-5-2025-08-07, got {response.model}")
        
    except Exception as e:
        result["errors"].append(f"Exception: {str(e)}")
        result["metrics"]["exception"] = str(e)[:200]
    
    return result

async def main():
    """Run canary test and output results"""
    
    print("=" * 60)
    print("OpenAI Pinned Model Web Search Canary Test")
    print("=" * 60)
    print(f"Model: gpt-5-2025-08-07")
    print(f"Mode: AUTO (grounded=True)")
    print(f"Time: {datetime.now().isoformat()}")
    print("-" * 60)
    
    result = await test_canary_openai_pinned_websearch()
    
    # Display results
    print("\n📊 METRICS:")
    for key, value in result["metrics"].items():
        status = "✅" if value else "❌" if isinstance(value, bool) else "📈"
        print(f"  {status} {key}: {value}")
    
    print("\n" + "=" * 60)
    if result["passed"]:
        print("✅ CANARY PASS: Pinned model web search working correctly")
    else:
        print("❌ CANARY FAIL: Issues detected")
        for error in result["errors"]:
            print(f"  - {error}")
    print("=" * 60)
    
    # Save results to file for CI
    filename = f"canary_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\n📁 Results saved to: {filename}")
    
    # Exit code for CI
    return 0 if result["passed"] else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)