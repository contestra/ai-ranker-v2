#!/usr/bin/env python3
"""Test OpenAI adapters with grounded requests - with debug info."""

import asyncio
import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.adapters.openai_adapter import OpenAIAdapter

async def test_openai_grounded_debug():
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[
            {'role': 'user', 'content': 'What is AVEA Life? Give me a brief answer.'}
        ],
        grounded=True,
        max_tokens=500,
        temperature=1.0,
        meta={
            'grounding_mode': 'AUTO'
        }
    )
    
    print(f'\nTesting OpenAI GPT-5 GROUNDED request with debug...')
    print(f'Model: {request.model}')
    print(f'Grounded: {request.grounded}')
    print(f'Question: What is AVEA Life?')
    print('-' * 50)
    
    try:
        response = await adapter.complete(request, timeout=90)
        
        print(f'\nResponse object attributes:')
        print(f'- success: {response.success}')
        print(f'- grounded_effective: {response.grounded_effective}')
        print(f'- content length: {len(response.content) if response.content else 0}')
        print(f'- content (first 500 chars): {repr(response.content[:500]) if response.content else "EMPTY"}')
        
        if hasattr(response, 'metadata'):
            metadata = response.metadata
            print(f'\nMetadata:')
            print(f'- response_api: {metadata.get("response_api")}')
            print(f'- tool_call_count: {metadata.get("tool_call_count", 0)}')
            print(f'- grounded_evidence_present: {metadata.get("grounded_evidence_present", False)}')
            
        if hasattr(response, 'citations') and response.citations:
            print(f'\nCitations found: {len(response.citations)}')
            for i, cit in enumerate(response.citations[:3]):
                print(f'  {i+1}. {cit}')
                
        if response.usage:
            print(f'\nTokens: {response.usage}')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_openai_grounded_debug())
