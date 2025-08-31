#!/usr/bin/env python3
"""Quick test to debug ALS propagation"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext

async def test_als():
    adapter = UnifiedLLMAdapter()
    
    # Create request with ALS
    request = LLMRequest(
        messages=[{"role": "user", "content": "What's the weather?"}],
        vendor="vertex",
        model="publishers/google/models/gemini-2.5-pro",
        grounded=False,
        json_mode=False,
        max_tokens=100,
        template_id="test_als_debug",
        run_id="debug_run_001"
    )
    
    # Add ALS context
    request.als_context = ALSContext(
        country_code="US",
        locale="en-US",
        als_block="You are in San Francisco, California"
    )
    
    print(f"Request metadata before complete: {getattr(request, 'metadata', {})}")
    
    # Execute request
    try:
        response = await asyncio.wait_for(adapter.complete(request), timeout=20)
        
        print(f"\nResponse metadata: {getattr(response, 'metadata', {})}")
        print(f"ALS present: {response.metadata.get('als_present', False)}")
        print(f"ALS country: {response.metadata.get('als_country', 'N/A')}")
        if response.metadata.get('als_block_sha256'):
            print(f"ALS SHA256: {response.metadata.get('als_block_sha256')[:16]}...")
    except asyncio.TimeoutError:
        print("Request timed out")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_als())