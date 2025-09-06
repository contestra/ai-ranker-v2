#!/usr/bin/env python3
"""Test OpenAI GPT-5 adapter with ungrounded request."""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.adapters.openai_adapter import OpenAIAdapter

async def test_openai_ungrounded():
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor='openai',
        model='gpt-5',  # Use base GPT-5 model
        messages=[
            {'role': 'user', 'content': 'What is the capital of France? Answer in one word.'}
        ],
        grounded=False,
        max_tokens=100,
        temperature=1.0  # GPT-5 requires temperature 1.0
    )
    
    print('Testing OpenAI GPT-5 ungrounded request...')
    print(f'Model: {request.model}')
    print(f'Grounded: {request.grounded}')
    print(f'Temperature: {request.temperature}')
    print('-' * 50)
    
    try:
        response = await adapter.complete(request, timeout=90)  # GPT-5 needs longer timeout
        print(f'\nSuccess: {response.success}')
        print(f'Content: {response.content[:200]}...' if len(response.content) > 200 else f'Content: {response.content}')
        print(f'Model version: {response.model_version}')
        print(f'Grounded effective: {response.grounded_effective}')
        if hasattr(response, 'metadata'):
            print(f'Response API: {response.metadata.get("response_api")}')
            print(f'Finish reason: {response.metadata.get("finish_reason")}')
        if response.usage:
            print(f'Tokens used: {response.usage}')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    asyncio.run(test_openai_ungrounded())