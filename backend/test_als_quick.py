#!/usr/bin/env python3
"""Quick ALS test with OpenAI"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

async def test_als():
    adapter = UnifiedLLMAdapter()
    
    # Test with OpenAI (faster)
    request = LLMRequest(
        messages=[{"role": "user", "content": "Say hello"}],
        vendor="openai",
        model="gpt-5",
        grounded=False,
        json_mode=False,
        max_tokens=50,
        template_id="test_als_quick",
        run_id="quick_als_001"
    )
    
    # Add ALS context
    request.als_context = ALSContext(
        country_code="US",
        locale="en-US",
        als_block="You are in San Francisco"
    )
    
    print(f"Request metadata before: {getattr(request, 'metadata', {})}")
    print(f"Request has ALS context: {hasattr(request, 'als_context') and request.als_context is not None}")
    
    # Execute request
    try:
        response = await asyncio.wait_for(adapter.complete(request), timeout=10)
        
        print(f"\n=== RESULTS ===")
        print(f"Response metadata: {getattr(response, 'metadata', {})}")
        
        if hasattr(response, 'metadata') and response.metadata:
            print(f"\nALS Present: {response.metadata.get('als_present', False)}")
            print(f"ALS Country: {response.metadata.get('als_country', 'N/A')}")
            print(f"ALS Mirrored by Router: {response.metadata.get('als_mirrored_by_router', False)}")
            if response.metadata.get('als_block_sha256'):
                print(f"ALS SHA256: {response.metadata.get('als_block_sha256')[:16]}...")
        else:
            print("No metadata in response!")
            
    except asyncio.TimeoutError:
        print("Request timed out")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_als())