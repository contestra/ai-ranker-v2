#!/usr/bin/env python3
"""Debug grounding_chunks structure"""

import os
import sys
import json

# MUST set env vars BEFORE importing any app modules
os.environ['DEBUG_GROUNDING'] = 'true'
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'true'

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
import asyncio

async def test():
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        messages=[{"role": "user", "content": "what is the capital of France"}],
        model="gemini-2.5-pro",
        grounded=True,
        max_tokens=200,
        temperature=0.1
    )
    
    request.meta = {
        'grounding_mode': 'AUTO',
        'country': 'US'
    }
    
    print("Testing...")
    response = await adapter.complete(request)
    
    # Check metadata for raw citations info  
    if hasattr(response, 'metadata') and response.metadata:
        meta = response.metadata
        if 'citations_audit' in meta:
            audit = meta['citations_audit']
            print("\nCitations audit:")
            print(json.dumps(audit, indent=2))
            
        # Also print tool call count and why_not_grounded
        print(f"\nTool calls: {meta.get('tool_call_count', 0)}")
        print(f"Why not grounded: {meta.get('why_not_grounded', 'N/A')}")
                        
if __name__ == "__main__":
    asyncio.run(test())
