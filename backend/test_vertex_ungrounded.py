#!/usr/bin/env python3
"""Test Vertex adapter with ungrounded request."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.adapters.vertex_adapter import VertexAdapter

async def test_vertex_ungrounded():
    adapter = VertexAdapter()
    
    request = LLMRequest(
        vendor='vertex',
        model='gemini-2.5-pro',
        messages=[
            {'role': 'user', 'content': 'What is the capital of France? Answer in one word.'}
        ],
        grounded=False,
        max_tokens=100,
        temperature=0.0
    )
    
    print('Testing Vertex (Gemini 2.5 Pro) ungrounded request...')
    print(f'Model: {request.model}')
    print(f'Grounded: {request.grounded}')
    print(f'Temperature: {request.temperature}')
    print(f'Question: {request.messages[0]["content"]}')
    print('-' * 60)
    
    try:
        response = await adapter.complete(request, timeout=30)
        
        print(f'\n✅ Success: {response.success}')
        print(f'Content: {response.content}')
        print(f'Model version: {response.model_version}')
        print(f'Grounded effective: {response.grounded_effective}')
        
        if hasattr(response, 'metadata'):
            metadata = response.metadata
            print(f'\nMetadata:')
            print(f'  - Response API: {metadata.get("response_api")}')
            print(f'  - Vendor: {metadata.get("vendor")}')
            print(f'  - Region: {metadata.get("region")}')
            print(f'  - Tool calls: {metadata.get("tool_call_count", 0)}')
            print(f'  - Finish reason: {metadata.get("finish_reason")}')
            
        if response.usage:
            print(f'\nTokens used: {response.usage}')
            
    except Exception as e:
        print(f'\n❌ Error: {str(e)[:500]}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vertex_ungrounded())