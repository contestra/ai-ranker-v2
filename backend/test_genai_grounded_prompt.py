#!/usr/bin/env python3
"""
Test grounded prompt against google-genai Vertex adapter.
Tests the prompt: "tell me the top longevity and healthspan news during august 2025"
"""
import asyncio
import os
import json
from datetime import datetime

# Set up environment
os.environ["VERTEX_PROJECT"] = os.getenv("VERTEX_PROJECT", os.getenv("GCP_PROJECT", "contestra-ai"))
os.environ["VERTEX_LOCATION"] = os.getenv("VERTEX_LOCATION", "europe-west4")

from app.llm.types import LLMRequest
from app.llm.adapters.vertex_adapter import VertexAdapter


async def test_grounded_prompt():
    """Test grounded prompt for longevity news."""
    print("="*60)
    print("Testing Grounded Prompt with google-genai")
    print("="*60)
    
    try:
        # Initialize adapter
        print("\n1. Initializing Vertex adapter with google-genai...")
        adapter = VertexAdapter()
        print("✅ Adapter initialized successfully")
        
        # Create grounded request
        request = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            messages=[
                {"role": "user", "content": "tell me the top longevity and healthspan news during august 2025"}
            ],
            grounded=True,
            temperature=0.7,
            max_tokens=2000,
            meta={
                "grounding_mode": "AUTO",
                "request_id": f"test_{datetime.now().isoformat()}"
            }
        )
        
        print("\n2. Sending grounded request...")
        print(f"   Model: {request.model}")
        print(f"   Grounded: {request.grounded}")
        print(f"   Mode: {request.meta.get('grounding_mode')}")
        print(f"   Prompt: {request.messages[0]['content']}")
        
        # Execute request
        print("\n3. Waiting for response...")
        response = await adapter.complete(request, timeout=30)
        
        print("\n4. Response received!")
        print("-"*60)
        
        # Display response text
        print("RESPONSE TEXT:")
        print("-"*40)
        print(response.text[:1500] if len(response.text) > 1500 else response.text)
        if len(response.text) > 1500:
            print(f"\n... (truncated, total length: {len(response.text)} chars)")
        
        # Display metadata
        print("\n" + "-"*40)
        print("METADATA:")
        print(f"  Provider: {response.metadata.get('provider')}")
        print(f"  Model: {response.metadata.get('model')}")
        print(f"  Response API: {response.metadata.get('response_api')}")
        print(f"  API Version: {response.metadata.get('provider_api_version')}")
        print(f"  Grounded Effective: {response.metadata.get('grounded_effective')}")
        print(f"  Grounding Mode: {response.metadata.get('grounding_mode_requested')}")
        print(f"  Response Time: {response.metadata.get('response_time_ms')}ms")
        
        # Display citation information
        if response.citations:
            print(f"\n  Citations Found: {len(response.citations)}")
            print("  Citation URLs:")
            for i, citation in enumerate(response.citations[:5], 1):
                print(f"    {i}. {citation.get('url', 'N/A')}")
                if citation.get('title'):
                    print(f"       Title: {citation['title']}")
            if len(response.citations) > 5:
                print(f"    ... and {len(response.citations) - 5} more")
        else:
            print("\n  No citations found")
        
        # Display citation telemetry
        print("\n  Citation Telemetry:")
        print(f"    Anchored Count: {response.metadata.get('anchored_count', 0)}")
        print(f"    Unlinked Count: {response.metadata.get('unlinked_count', 0)}")
        print(f"    Tool Calls: {response.metadata.get('vertex_tool_calls', 0)}")
        
        # Check if two-step was used (for JSON mode)
        if response.metadata.get('step2_tools_invoked') is not None:
            print("\n  Two-Step Process:")
            print(f"    Step 2 Tools: {response.metadata.get('step2_tools_invoked')}")
            print(f"    Source Ref: {response.metadata.get('step2_source_ref')}")
        
        print("\n" + "="*60)
        print("✅ Test completed successfully!")
        print("="*60)
        
        # Save response for analysis
        output_file = f"genai_grounded_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": request.model,
                    "messages": request.messages,
                    "grounded": request.grounded,
                    "meta": request.meta
                },
                "response": {
                    "text": response.text,
                    "metadata": response.metadata,
                    "citations": response.citations
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        print(f"\n📄 Full response saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ Error occurred: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_grounded_prompt())
    exit(0 if success else 1)