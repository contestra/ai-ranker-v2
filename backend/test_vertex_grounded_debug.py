#!/usr/bin/env python3
"""Debug Vertex grounded mode NoneType error."""

import asyncio
import json
import os
import sys
from datetime import datetime
import traceback

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Set required environment variables
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["LLM_TIMEOUT_GR"] = "120"
os.environ["GEMINI_PRO_THINKING_BUDGET"] = "256"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_UNGROUNDED"] = "768"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_GROUNDED"] = "1536"


async def test_vertex_grounded():
    """Test Vertex grounded mode and debug NoneType error."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*80)
    print("VERTEX GROUNDED MODE DEBUG")
    print("="*80 + "\n")
    
    # Create grounded request
    request = LLMRequest(
        vendor="vertex",
        model="gemini-2.5-pro",
        messages=[
            {
                "role": "user",
                "content": "Tell me the primary health and wellness news during August 2025"
            }
        ],
        grounded=True,
        max_tokens=1536,
        temperature=0.7,
        als_context={
            "country_code": "DE",
            "locale": "de-DE"
        }
    )
    
    request.metadata = {
        "als_country": "DE",
        "als_locale": "de-DE",
        "als_present": True,
        "thinking_budget_tokens": 256
    }
    
    request.meta = {"grounding_mode": "AUTO"}
    
    try:
        print("🚀 Executing request...")
        response = await adapter.complete(request)
        
        # Display results
        print("\n" + "="*80)
        print("RESULTS")
        print("="*80)
        print(f"\n✅ Success: {response.success}")
        print(f"📝 Content Length: {len(response.content) if response.content else 0} chars")
        
        if response.content:
            print(f"\nContent Preview:\n{response.content[:500]}...")
        else:
            print("\n⚠️ EMPTY CONTENT RETURNED")
        
        if hasattr(response, 'metadata') and response.metadata:
            print(f"\n📊 Metadata:")
            for key, value in response.metadata.items():
                if key != 'raw_response':  # Skip raw response in output
                    print(f"  - {key}: {value}")
        
        if hasattr(response, 'citations') and response.citations:
            print(f"\n📚 Citations: {len(response.citations)}")
            for i, cite in enumerate(response.citations[:3], 1):
                print(f"\n  Citation {i}:")
                print(f"    URL: {cite.get('url', 'N/A')}")
                print(f"    Title: {cite.get('title', 'N/A')[:80]}")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("\n📋 Full Traceback:")
        traceback.print_exc()
        
        # Try to debug the error location
        print("\n🔍 Debugging error location...")
        
        # Check if it's in the adapter
        try:
            from app.llm.adapters.vertex_adapter import VertexAdapter
            va = adapter.vertex_adapter
            
            # Create a minimal request to test
            print("\nTrying minimal grounded request...")
            minimal_request = LLMRequest(
                vendor="vertex",
                model="gemini-2.5-pro",
                messages=[{"role": "user", "content": "What is 2+2?"}],
                grounded=True,
                max_tokens=100
            )
            
            # Try to call directly
            result = await va.complete(minimal_request)
            print(f"Minimal test success: {result.success}")
            
        except Exception as e2:
            print(f"Minimal test also failed: {str(e2)}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_vertex_grounded())