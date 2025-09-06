#!/usr/bin/env python3
"""Test Vertex adapter with grounded request."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.adapters.vertex_adapter import VertexAdapter

async def test_vertex_grounded():
    adapter = VertexAdapter()
    
    request = LLMRequest(
        vendor='vertex',
        model='gemini-2.5-pro',
        messages=[
            {'role': 'user', 'content': 'what was the health news of August 2025?'}
        ],
        grounded=True,
        max_tokens=500,
        temperature=0.0,
        meta={
            'grounding_mode': 'AUTO'
        }
    )
    
    print('Testing Vertex (Gemini 2.5 Pro) GROUNDED request...')
    print(f'Model: {request.model}')
    print(f'Grounded: {request.grounded}')
    print(f'Temperature: {request.temperature}')
    print(f'Question: {request.messages[0]["content"]}')
    print(f'Grounding mode: {request.meta.get("grounding_mode")}')
    print('-' * 60)
    
    try:
        response = await adapter.complete(request, timeout=60)
        
        print(f'\n✅ Success: {response.success}')
        print(f'Content length: {len(response.content)}')
        
        if response.content:
            preview = response.content[:500]
            print(f'\nContent preview:\n{preview}{"..." if len(response.content) > 500 else ""}')
        else:
            print('\n⚠️  Content: EMPTY')
        
        print(f'\n📊 Response details:')
        print(f'  - Model version: {response.model_version}')
        print(f'  - Grounded effective: {response.grounded_effective}')
        
        if hasattr(response, 'metadata'):
            metadata = response.metadata
            print(f'\n🔧 Metadata:')
            print(f'  - Response API: {metadata.get("response_api")}')
            print(f'  - Region: {metadata.get("region")}')
            print(f'  - Tool calls: {metadata.get("tool_call_count", 0)}')
            print(f'  - Grounded evidence present: {metadata.get("grounded_evidence_present", False)}')
            print(f'  - Anchored citations: {metadata.get("anchored_citations_count", 0)}')
            print(f'  - Unlinked sources: {metadata.get("unlinked_sources_count", 0)}')
            print(f'  - Finish reason: {metadata.get("finish_reason")}')
            
        if hasattr(response, 'citations') and response.citations:
            print(f'\n📚 Citations found: {len(response.citations)}')
            # Show search queries
            queries = [c for c in response.citations if c.get('source_type') == 'search_query']
            if queries:
                print(f'\n  Search queries performed:')
                for q in queries[:3]:
                    print(f'    - "{q.get("query")}"')
            
            # Show sources
            sources = [c for c in response.citations if c.get('source_type') == 'grounding_chunk']
            if sources:
                print(f'\n  Sources used ({len(sources)} total):')
                for i, src in enumerate(sources[:5], 1):
                    title = src.get("title", "No title")[:60]
                    domain = src.get("domain", "unknown")
                    print(f'    {i}. [{domain}] {title}...')
                    
        if response.usage:
            print(f'\n💰 Tokens used: {response.usage}')
            
    except Exception as e:
        print(f'\n❌ Error: {str(e)[:500]}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vertex_grounded())