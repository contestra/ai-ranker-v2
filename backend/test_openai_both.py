#!/usr/bin/env python3
"""Test both OpenAI models with grounded and ungrounded requests."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.adapters.openai_adapter import OpenAIAdapter

async def test_model(model_name: str, grounded: bool):
    adapter = OpenAIAdapter()
    
    # Different questions for grounded vs ungrounded
    if grounded:
        question = "What are the top longevity supplement brands in 2025?"
        mode = "GROUNDED"
    else:
        question = "What is the capital of Switzerland?"
        mode = "UNGROUNDED"
    
    temperature = 1.0 if model_name == "gpt-5" else 0.0
    
    request = LLMRequest(
        vendor='openai',
        model=model_name,
        messages=[
            {'role': 'user', 'content': question}
        ],
        grounded=grounded,
        max_tokens=500,
        temperature=temperature,
        meta={
            'grounding_mode': 'AUTO' if grounded else None
        }
    )
    
    print(f'\n{"="*60}')
    print(f'Testing {model_name} - {mode}')
    print(f'Question: {question}')
    print(f'Temperature: {temperature}')
    print('-' * 60)
    
    try:
        response = await adapter.complete(request, timeout=90)
        
        print(f'✅ Success: {response.success}')
        print(f'Content length: {len(response.content)}')
        
        if response.content:
            preview = response.content[:300]
            print(f'Content preview: {preview}{"..." if len(response.content) > 300 else ""}')
        else:
            print('⚠️  Content: EMPTY')
        
        if hasattr(response, 'metadata'):
            m = response.metadata
            print(f'\nMetadata:')
            print(f'  - Grounded effective: {response.grounded_effective}')
            print(f'  - Tool calls: {m.get("tool_call_count", 0)}')
            if grounded:
                print(f'  - Provoker retry used: {m.get("provoker_retry_used", False)}')
                print(f'  - Citations: {m.get("citation_count", 0)}')
            
        if response.usage:
            print(f'  - Tokens: {response.usage.get("total_tokens", 0)} total')
            
    except Exception as e:
        print(f'❌ Error: {str(e)[:200]}')

async def main():
    models = ["gpt-5", "gpt-4o"]
    
    for model in models:
        # Test ungrounded
        await test_model(model, grounded=False)
        
        # Test grounded
        await test_model(model, grounded=True)

if __name__ == "__main__":
    asyncio.run(main())
