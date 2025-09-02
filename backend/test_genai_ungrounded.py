#!/usr/bin/env python3
"""
Test ungrounded prompt against google-genai Vertex adapter.
Tests basic functionality without tools parameter.
"""
import asyncio
import os
import json
from datetime import datetime

# Set up environment
os.environ["VERTEX_PROJECT"] = os.getenv("VERTEX_PROJECT", os.getenv("GCP_PROJECT", "contestra-ai"))
os.environ["VERTEX_LOCATION"] = os.getenv("VERTEX_LOCATION", "europe-west4")

from google import genai
from google.genai.types import GenerateContentConfig


async def test_ungrounded_prompt():
    """Test ungrounded prompt for longevity news."""
    print("="*60)
    print("Testing Ungrounded Prompt with google-genai")
    print("="*60)
    
    try:
        # Initialize client
        print("\n1. Initializing google-genai client...")
        client = genai.Client(
            vertexai=True,
            project=os.environ["VERTEX_PROJECT"],
            location=os.environ["VERTEX_LOCATION"]
        )
        print("✅ Client initialized successfully")
        
        # Create request
        prompt = "tell me the top longevity and healthspan news during august 2025"
        
        config = GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=2000
        )
        
        print("\n2. Sending ungrounded request...")
        print(f"   Model: gemini-2.5-pro")
        print(f"   Grounded: False (no tools parameter in this test)")
        print(f"   Prompt: {prompt}")
        
        # Create GenerativeModel instance (correct approach)
        model = genai.GenerativeModel(
            model_name="publishers/google/models/gemini-2.5-pro",
            # Optional: could add system_instruction here
        )
        
        # Execute request
        print("\n3. Waiting for response...")
        start_time = datetime.now()
        
        # Run synchronously in async context
        from starlette.concurrency import run_in_threadpool
        response = await run_in_threadpool(
            model.generate_content,
            prompt,  # Just pass the prompt string directly
            generation_config=config
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print("\n4. Response received!")
        print("-"*60)
        
        # Extract and display response text
        response_text = ""
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'text'):
                            response_text = part.text
                            break
                    if response_text:
                        break
        
        print("RESPONSE TEXT:")
        print("-"*40)
        print(response_text[:1500] if len(response_text) > 1500 else response_text)
        if len(response_text) > 1500:
            print(f"\n... (truncated, total length: {len(response_text)} chars)")
        
        print("\n" + "-"*40)
        print("METADATA:")
        print(f"  Model: gemini-2.5-pro")
        print(f"  Response API: google-genai")
        print(f"  Response Time: {elapsed:.2f}s")
        
        # Check for grounding metadata (even though we didn't request it)
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                print(f"  Grounding Metadata: Present (unexpected)")
            else:
                print(f"  Grounding Metadata: None (expected for ungrounded)")
        
        print("\n" + "="*60)
        print("✅ Test completed successfully!")
        print("="*60)
        
        # Save response for analysis
        output_file = f"genai_ungrounded_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": "gemini-2.5-pro",
                    "prompt": prompt,
                    "grounded": False,
                    "note": "No tools parameter used in this test"
                },
                "response": {
                    "text": response_text,
                    "elapsed_seconds": elapsed
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        print(f"\n📄 Full response saved to: {output_file}")
        
        # Note about this test
        print("\n📝 Note: This test does not use the tools parameter.")
        print("    For grounded requests, use the vertex_adapter.py implementation")
        print("    which properly configures tools with GenerativeModel.")
        
    except Exception as e:
        print(f"\n❌ Error occurred: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_ungrounded_prompt())
    exit(0 if success else 1)