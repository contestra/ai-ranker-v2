#!/usr/bin/env python3
"""Test GPT-5 with news summary request."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.adapters.openai_adapter import OpenAIAdapter

async def test_gpt5_news():
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[
            {'role': 'user', 'content': 'summarise the news of August 2025 into 1 paragraph'}
        ],
        grounded=True,
        max_tokens=500,
        temperature=1.0,
        meta={
            'grounding_mode': 'AUTO'
        }
    )
    
    print('Testing GPT-5 with news summary request...')
    print(f'Prompt: "{request.messages[0]["content"]}"')
    print(f'Model: {request.model}')
    print(f'Grounded: {request.grounded}')
    print('-' * 60)
    
    try:
        response = await adapter.complete(request, timeout=90)
        
        print(f'\n✅ Success: {response.success}')
        print(f'Content length: {len(response.content)}')
        
        if response.content:
            print(f'\nContent:\n{response.content}')
        else:
            print('\n⚠️  Content: EMPTY')
        
        if hasattr(response, 'metadata'):
            m = response.metadata
            print(f'\nMetadata:')
            print(f'  - Grounded effective: {response.grounded_effective}')
            print(f'  - Tool calls: {m.get("tool_call_count", 0)}')
            print(f'  - Provoker retry used: {m.get("provoker_retry_used", False)}')
            print(f'  - Citations: {m.get("citation_count", 0)}')
            
        if response.usage:
            print(f'\nTokens: {response.usage}')
            
    except Exception as e:
        print(f'❌ Error: {e}')

if __name__ == "__main__":
    asyncio.run(test_gpt5_news())