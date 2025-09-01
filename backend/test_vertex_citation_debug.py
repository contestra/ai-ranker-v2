#!/usr/bin/env python3
"""Debug Vertex citation extraction"""

import os
import sys

# MUST set env vars BEFORE importing any app modules
os.environ['DEBUG_GROUNDING'] = 'true'
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'true'

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_vertex_grounded():
    """Test Vertex grounded with detailed logging."""
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        messages=[{"role": "user", "content": "what was the top longevity news in August 2025"}],
        model="gemini-2.5-pro",
        grounded=True,
        max_tokens=500,
        temperature=0.7
    )
    
    request.meta = {
        'grounding_mode': 'AUTO',
        'country': 'US'
    }
    
    print("Testing Vertex grounded...")
    response = await adapter.complete(request)
    
    print(f"\nResponse text length: {len(response.content) if response.content else 0}")
    print(f"Grounded effective: {response.grounded_effective}")
    
    if hasattr(response, 'metadata') and response.metadata:
        meta = response.metadata
        print(f"Tool calls: {meta.get('tool_call_count', 0)}")
        print(f"Citations count: {meta.get('citations_count', 0)}")
        print(f"Anchored citations: {meta.get('anchored_citations_count', 0)}")
        print(f"Unlinked sources: {meta.get('unlinked_sources_count', 0)}")
        print(f"Citation shapes: {meta.get('citations_shape_set', [])}")
        
        # Print actual citations if any
        if 'citations' in meta:
            print(f"\nFound {len(meta['citations'])} citations:")
            for i, cit in enumerate(meta['citations'][:3]):
                print(f"  [{i+1}] Type: {cit.get('source_type')}, URL: {cit.get('url', 'N/A')[:80]}")
                if 'title' in cit:
                    print(f"       Title: {cit['title'][:80]}")
    
    return response

if __name__ == "__main__":
    asyncio.run(test_vertex_grounded())
