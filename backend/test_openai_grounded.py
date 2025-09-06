#!/usr/bin/env python3
"""Test OpenAI adapters with grounded requests."""

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

async def test_openai_grounded(model_name: str):
    adapter = OpenAIAdapter()
    
    # Use appropriate temperature for each model
    temperature = 1.0 if model_name == "gpt-5" else 0.0
    
    request = LLMRequest(
        vendor='openai',
        model=model_name,
        messages=[
            {'role': 'user', 'content': 'What are the current top 3 news headlines today?'}
        ],
        grounded=True,
        max_tokens=500,
        temperature=temperature,
        meta={
            'grounding_mode': 'AUTO'  # or REQUIRED
        }
    )
    
    print(f'\nTesting OpenAI {model_name} GROUNDED request...')
    print(f'Model: {request.model}')
    print(f'Grounded: {request.grounded}')
    print(f'Temperature: {request.temperature}')
    print(f'Grounding mode: {request.meta.get("grounding_mode")}')
    print('-' * 50)
    
    try:
        response = await adapter.complete(request, timeout=90)
        print(f'\nSuccess: {response.success}')
        print(f'Content preview: {response.content[:300]}...' if len(response.content) > 300 else f'Content: {response.content}')
        print(f'Model version: {response.model_version}')
        print(f'Grounded effective: {response.grounded_effective}')
        
        if hasattr(response, 'metadata'):
            metadata = response.metadata
            print(f'Response API: {metadata.get("response_api")}')
            print(f'Tool call count: {metadata.get("tool_call_count", 0)}')
            print(f'Grounded evidence present: {metadata.get("grounded_evidence_present", False)}')
            print(f'Anchored citations: {metadata.get("anchored_citations_count", 0)}')
            print(f'Unlinked sources: {metadata.get("unlinked_sources_count", 0)}')
            print(f'Finish reason: {metadata.get("finish_reason")}')
            
        if hasattr(response, 'citations') and response.citations:
            print(f'\nCitations found: {len(response.citations)}')
            for i, cit in enumerate(response.citations[:3]):  # Show first 3
                print(f'  {i+1}. {cit.get("title", "N/A")} - {cit.get("url", "N/A")[:60]}...')
                
        if response.usage:
            print(f'\nTokens used: {response.usage}')
    except Exception as e:
        print(f'Error: {str(e)[:500]}')

async def main():
    # Test GPT-5
    await test_openai_grounded("gpt-5")
    
    print("\n" + "="*70 + "\n")
    
    # Test GPT-4o
    await test_openai_grounded("gpt-4o")

if __name__ == "__main__":
    asyncio.run(main())