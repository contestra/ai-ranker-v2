#!/usr/bin/env python3
"""Test centralized REQUIRED mode enforcement in router."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

# Disable provoker for cleaner test
os.environ["OPENAI_PROVOKER_ENABLED"] = "false"

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_required_mode():
    adapter = UnifiedLLMAdapter()
    
    test_cases = [
        {
            "name": "OpenAI GPT-4o with REQUIRED mode",
            "vendor": "openai",
            "model": "gpt-4o",
            "prompt": "What is the capital of France?",
            "grounding_mode": "REQUIRED"
        },
        {
            "name": "Vertex Gemini with REQUIRED mode",
            "vendor": "vertex", 
            "model": "gemini-2.5-pro",
            "prompt": "What is the capital of France?",
            "grounding_mode": "REQUIRED"
        }
    ]
    
    for test in test_cases:
        print("=" * 80)
        print(f"TEST: {test['name']}")
        print("=" * 80)
        print(f"Vendor: {test['vendor']}")
        print(f"Model: {test['model']}")
        print(f"Grounding Mode: {test['grounding_mode']}")
        print(f"Prompt: {test['prompt']}")
        print("-" * 80)
        
        request = LLMRequest(
            vendor=test['vendor'],
            model=test['model'],
            messages=[{"role": "user", "content": test['prompt']}],
            grounded=True,
            meta={"grounding_mode": test['grounding_mode']},
            max_tokens=200,
            temperature=0.0
        )
        
        try:
            response = await adapter.complete(request, session=None)
            print(f"✅ Success: {response.success}")
            print(f"Grounded Effective: {response.grounded_effective}")
            
            if response.metadata:
                print(f"\n📊 Metadata:")
                print(f"  - Tool calls: {response.metadata.get('tool_call_count', 0)}")
                print(f"  - Anchored citations: {response.metadata.get('anchored_citations_count', 0)}")
                print(f"  - Unlinked sources: {response.metadata.get('unlinked_sources_count', 0)}")
                print(f"  - Required pass reason: {response.metadata.get('required_pass_reason', 'N/A')}")
                print(f"  - Why not grounded: {response.metadata.get('why_not_grounded', 'N/A')}")
            
            print(f"\nContent preview: {response.content[:200] if response.content else '(empty)'}")
            
        except Exception as e:
            error_str = str(e)
            print(f"❌ Failed with error: {error_str[:300]}")
            
            if "GROUNDING_REQUIRED_FAILED" in error_str:
                print("\n✓ REQUIRED mode properly enforced by router")
                print("  The router centrally enforces that grounding requirements weren't met")
            else:
                print("\n? Unexpected error type")
        
        print()

if __name__ == "__main__":
    # Set region for Vertex grounding
    os.environ["VERTEX_LOCATION"] = "us-central1"
    asyncio.run(test_required_mode())