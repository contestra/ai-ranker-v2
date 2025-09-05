#!/usr/bin/env python3
"""Debug test for Vertex grounded to see why grounding isn't triggered."""

import asyncio
import os
import sys
import json
import logging
from pathlib import Path

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.adapters.vertex_adapter import VertexAdapter
from app.llm.adapters.gemini_adapter import GeminiAdapter

async def test_both_adapters():
    """Test the same grounded request on both adapters to compare."""
    
    request = LLMRequest(
        vendor='test',
        model='gemini-2.5-pro',
        messages=[
            {'role': 'user', 'content': 'What are the latest AI developments in December 2024?'}
        ],
        grounded=True,
        max_tokens=300,
        temperature=0.0,
        meta={
            'grounding_mode': 'AUTO'
        }
    )
    
    print("=" * 70)
    print("Testing SAME request on both adapters")
    print("=" * 70)
    
    # Test Gemini Direct
    print("\n1. Testing Gemini Direct Adapter:")
    print("-" * 40)
    try:
        gemini_adapter = GeminiAdapter()
        response = await gemini_adapter.complete(request, timeout=30)
        print(f"✅ Success: {response.success}")
        print(f"Grounded effective: {response.grounded_effective}")
        if hasattr(response, 'metadata'):
            print(f"Tool calls: {response.metadata.get('tool_call_count', 0)}")
            print(f"Evidence present: {response.metadata.get('grounded_evidence_present', False)}")
        print(f"Content length: {len(response.content) if response.content else 0}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n2. Testing Vertex Adapter:")
    print("-" * 40)
    try:
        vertex_adapter = VertexAdapter()
        response = await vertex_adapter.complete(request, timeout=30)
        print(f"✅ Success: {response.success}")
        print(f"Grounded effective: {response.grounded_effective}")
        if hasattr(response, 'metadata'):
            print(f"Tool calls: {response.metadata.get('tool_call_count', 0)}")
            print(f"Evidence present: {response.metadata.get('grounded_evidence_present', False)}")
            print(f"Region: {response.metadata.get('region')}")
        print(f"Content length: {len(response.content) if response.content else 0}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_both_adapters())
