#!/usr/bin/env python3
"""Test OpenAI adapter without model mapping to verify immutability."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

# Disable provoker as recommended
os.environ["OPENAI_PROVOKER_ENABLED"] = "false"

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_openai_models():
    adapter = UnifiedLLMAdapter()
    
    # Test different model variants to ensure no silent rewrites
    test_cases = [
        ("gpt-4o", "What is 2+2?"),
        ("gpt-5", "What is 3+3?"),
    ]
    
    for model, prompt in test_cases:
        print("=" * 80)
        print(f"Testing model: {model}")
        print(f"Prompt: {prompt}")
        print("-" * 80)
        
        request = LLMRequest(
            vendor="openai",
            model=model,
            messages=[{"role": "user", "content": prompt}],
            grounded=False,
            max_tokens=100,
            temperature=0.0
        )
        
        try:
            response = await adapter.complete(request, session=None)
            print(f"✅ Success: {response.success}")
            print(f"Model used: {response.model_version}")
            print(f"Response API: {response.metadata.get('response_api', 'N/A') if response.metadata else 'N/A'}")
            print(f"Content: {response.content[:200] if response.content else '(empty)'}")
            
            # Verify model immutability - the model_version should match what we requested
            if response.model_version and model in response.model_version:
                print(f"✓ Model immutability preserved: requested={model}, used={response.model_version}")
            else:
                print(f"⚠️ Model may have been rewritten: requested={model}, used={response.model_version}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            # If it's a model not found error with -chat variant, that's expected
            if "model_not_found" in str(e) and "-chat" in model:
                print("✓ This is expected - no silent rewrite happened, error thrown instead")
        
        print()

if __name__ == "__main__":
    asyncio.run(test_openai_models())