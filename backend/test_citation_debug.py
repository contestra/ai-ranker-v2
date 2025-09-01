#!/usr/bin/env python3
"""
Debug why citations aren't being extracted in the longevity tests.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_vertex_grounding():
    """Test Vertex with grounding to see raw response."""
    print("\n" + "="*60)
    print("TESTING VERTEX WITH GROUNDING")
    print("="*60)
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        model="gemini-2.5-pro",
        messages=[
            {"role": "user", "content": "What are the latest developments in AI?"}
        ],
        grounded=True,
        max_tokens=300,
        temperature=0.7
    )
    
    # Add grounding mode
    request.meta = {"grounding_mode": "AUTO"}
    
    try:
        response = await adapter.complete(request)
        
        print(f"Success: {response.success}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Response Length: {len(response.content) if response.content else 0}")
        
        # Check metadata
        if response.metadata:
            print(f"\nMetadata keys: {list(response.metadata.keys())}")
            
            # Check for citations
            if 'citations' in response.metadata:
                citations = response.metadata['citations']
                print(f"Citations count: {len(citations)}")
                if citations:
                    print("\nFirst citation:")
                    print(json.dumps(citations[0], indent=2))
            else:
                print("No 'citations' key in metadata")
                
            # Check for grounding metadata
            grounding_keys = [k for k in response.metadata.keys() if 'ground' in k.lower()]
            if grounding_keys:
                print(f"\nGrounding-related keys: {grounding_keys}")
                for key in grounding_keys:
                    val = response.metadata[key]
                    if isinstance(val, (dict, list)):
                        print(f"{key}: {json.dumps(val, indent=2)[:500]}...")
                    else:
                        print(f"{key}: {val}")
        else:
            print("No metadata in response")
            
        # Check raw response
        if response.raw_response:
            print("\nRaw response keys:", list(response.raw_response.keys()) if isinstance(response.raw_response, dict) else type(response.raw_response))
            
            # Look for grounding in raw response
            if isinstance(response.raw_response, dict):
                if 'grounding_metadata' in response.raw_response:
                    print("\nFound grounding_metadata in raw_response!")
                    gm = response.raw_response['grounding_metadata']
                    print(f"Type: {type(gm)}")
                    if hasattr(gm, '__dict__'):
                        print(f"Attributes: {list(vars(gm).keys())}")
                        
                # Check candidates for grounding
                if 'candidates' in response.raw_response:
                    candidates = response.raw_response['candidates']
                    if candidates and len(candidates) > 0:
                        first_candidate = candidates[0]
                        if isinstance(first_candidate, dict):
                            if 'grounding_metadata' in first_candidate:
                                print("\nFound grounding_metadata in candidate!")
                                print(json.dumps(first_candidate['grounding_metadata'], indent=2)[:500])
                        elif hasattr(first_candidate, 'grounding_metadata'):
                            print("\nFound grounding_metadata attribute in candidate!")
                            gm = first_candidate.grounding_metadata
                            if gm:
                                print(f"Type: {type(gm)}")
                                if hasattr(gm, '__dict__'):
                                    print(f"Attributes: {list(vars(gm).keys())}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def test_openai_grounding():
    """Test OpenAI with grounding to see if web_search works."""
    print("\n" + "="*60)
    print("TESTING OPENAI WITH GROUNDING")
    print("="*60)
    
    adapter = UnifiedLLMAdapter()
    
    # Try with gpt-4o instead of gpt-5
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "What are the latest developments in AI?"}
        ],
        grounded=True,
        max_tokens=300,
        temperature=0.7
    )
    
    # Add grounding mode
    request.meta = {"grounding_mode": "AUTO"}
    
    try:
        response = await adapter.complete(request)
        
        print(f"Success: {response.success}")
        print(f"Grounded Effective: {response.grounded_effective}")
        print(f"Response Length: {len(response.content) if response.content else 0}")
        
        # Check metadata
        if response.metadata:
            print(f"\nMetadata keys: {list(response.metadata.keys())}")
            
            # Check for citations
            if 'citations' in response.metadata:
                citations = response.metadata['citations']
                print(f"Citations count: {len(citations)}")
                if citations:
                    print("\nFirst citation:")
                    print(json.dumps(citations[0], indent=2))
            else:
                print("No 'citations' key in metadata")
        else:
            print("No metadata in response")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Run both tests."""
    await test_vertex_grounding()
    await test_openai_grounding()

if __name__ == "__main__":
    asyncio.run(main())