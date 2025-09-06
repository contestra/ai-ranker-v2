#!/usr/bin/env python3
"""Test that -chat variants properly fail without silent rewrite."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

os.environ["OPENAI_PROVOKER_ENABLED"] = "false"

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_chat_variant():
    adapter = UnifiedLLMAdapter()
    
    print("=" * 80)
    print("Testing -chat variant to ensure no silent rewrite")
    print("=" * 80)
    
    # Test with a hypothetical -chat variant
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-chat",  # This should fail if Responses API doesn't support it
        messages=[{"role": "user", "content": "Hello"}],
        grounded=False,
        max_tokens=50,
        temperature=0.0
    )
    
    print(f"Requesting model: gpt-5-chat")
    print("Expected: Either works with exact model OR fails with clear error")
    print("NOT expected: Silent rewrite to 'gpt-5'")
    print("-" * 40)
    
    try:
        response = await adapter.complete(request, session=None)
        print(f"✅ Request succeeded")
        print(f"Model version returned: {response.model_version}")
        
        if response.model_version == "gpt-5-chat":
            print("✓ Model used exactly as requested (gpt-5-chat)")
        elif response.model_version == "gpt-5":
            print("⚠️ WARNING: Model was silently rewritten from gpt-5-chat to gpt-5")
            print("This violates immutability principle!")
        else:
            print(f"? Unexpected model version: {response.model_version}")
            
    except Exception as e:
        error_str = str(e)
        print(f"❌ Request failed with error: {error_str[:200]}")
        
        if "model_not_found" in error_str or "does not exist" in error_str:
            print("✓ GOOD: Request failed with model error - no silent rewrite occurred")
            print("  This preserves model immutability as intended")
        else:
            print("? Unexpected error type")

if __name__ == "__main__":
    asyncio.run(test_chat_variant())