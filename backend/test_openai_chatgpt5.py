#!/usr/bin/env python3
"""
Test OpenAI adapter with ChatGPT-5 model and grounding.
"""
import asyncio
import os
import json
from datetime import datetime
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, LLMResponse
from app.llm.adapters.openai_adapter import OpenAIAdapter


async def test_openai_grounding():
    """Test OpenAI ChatGPT-5 with grounding."""
    print("="*60)
    print("Testing OpenAI ChatGPT-5 with Grounding")
    print("="*60)
    
    try:
        # Initialize adapter
        print("\n1. Initializing OpenAI adapter...")
        adapter = OpenAIAdapter()
        print("✅ Adapter initialized")
        
        # Create request with grounding
        prompt = "give me a summary of health and wellness news during August 2025"
        
        request = LLMRequest(
            vendor="openai",
            model="chatgpt-5.0-latest",  # or "gpt-5" depending on model name
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant. Provide accurate, up-to-date information."},
                {"role": "user", "content": prompt}
            ],
            grounded=True,
            temperature=0.7,
            max_tokens=3000,
            meta={
                "grounding_mode": "REQUIRED"  # Force grounding
            }
        )
        
        print("\n2. Request Details:")
        print(f"   Model: {request.model}")
        print(f"   Grounded: {request.grounded}")
        print(f"   Grounding Mode: REQUIRED")
        print(f"   Prompt: {prompt}")
        
        print("\n3. Sending request to OpenAI...")
        start_time = datetime.now()
        
        try:
            response = await adapter.complete(request)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            print(f"\n✅ Response received in {elapsed:.1f} seconds")
            print("="*60)
            
            # Display response
            print("\nRESPONSE TEXT:")
            print("-"*60)
            print(response.text[:2000] if len(response.text) > 2000 else response.text)
            if len(response.text) > 2000:
                print(f"\n... (truncated, total length: {len(response.text)} chars)")
            print("-"*60)
            
            # Display metadata
            print("\nMETADATA:")
            print("-"*60)
            print(f"Model: {response.model}")
            print(f"Vendor: {response.vendor}")
            print(f"Total tokens: {response.total_tokens}")
            print(f"Response time: {elapsed:.1f}s")
            
            # Check grounding metadata
            if response.metadata:
                print("\nGROUNDING INFO:")
                print(f"  Grounded attempted: {response.metadata.get('grounding_attempted', False)}")
                print(f"  Grounded effective: {response.metadata.get('grounded_effective', False)}")
                print(f"  Grounding mode: {response.metadata.get('grounding_mode_requested', 'N/A')}")
                
                if response.metadata.get('why_not_grounded'):
                    print(f"  Why not grounded: {response.metadata.get('why_not_grounded')}")
                
                # Check for citations
                if response.citations:
                    print(f"\n  Citations found: {len(response.citations)}")
                    for i, citation in enumerate(response.citations[:5]):
                        print(f"    {i+1}. {citation.get('url', citation.get('title', 'N/A'))}")
                else:
                    print("  No citations found")
            
            # Save results
            output_file = f"openai_chatgpt5_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump({
                    "request": {
                        "model": request.model,
                        "prompt": prompt,
                        "grounded": request.grounded,
                        "grounding_mode": "REQUIRED"
                    },
                    "response": {
                        "text": response.text,
                        "total_tokens": response.total_tokens,
                        "elapsed_seconds": elapsed,
                        "model_used": response.model
                    },
                    "grounding": {
                        "attempted": response.metadata.get('grounding_attempted', False) if response.metadata else False,
                        "effective": response.metadata.get('grounded_effective', False) if response.metadata else False,
                        "citations_count": len(response.citations) if response.citations else 0
                    },
                    "timestamp": datetime.now().isoformat()
                }, f, indent=2)
            
            print(f"\n📄 Results saved to: {output_file}")
            
            print("\n" + "="*60)
            print("✅ TEST COMPLETE")
            print("="*60)
            
            return True
            
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"\n❌ Request failed after {elapsed:.1f}s")
            print(f"Error: {type(e).__name__}: {e}")
            
            # Check if it's a model availability issue
            if "model" in str(e).lower() or "not found" in str(e).lower():
                print("\n⚠️  Model availability issue. Trying alternative model names...")
                
                # Try alternative model names
                alternative_models = ["gpt-5", "gpt-5-turbo", "gpt-4o", "gpt-4-turbo-preview"]
                for alt_model in alternative_models:
                    print(f"\nTrying model: {alt_model}")
                    request.model = alt_model
                    try:
                        response = await adapter.complete(request)
                        print(f"✅ Success with model: {alt_model}")
                        print(f"Response preview: {response.text[:200]}...")
                        return True
                    except Exception as alt_e:
                        print(f"  Failed: {alt_e}")
                        continue
            
            raise e
            
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_available_models():
    """Test which OpenAI models are available."""
    print("\n" + "="*60)
    print("Testing Available OpenAI Models")
    print("="*60)
    
    adapter = OpenAIAdapter()
    
    test_models = [
        "gpt-5",
        "chatgpt-5.0-latest", 
        "gpt-5-turbo",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo-preview",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo"
    ]
    
    available = []
    
    for model in test_models:
        print(f"\nTesting {model}...", end=" ")
        request = LLMRequest(
            vendor="openai",
            model=model,
            messages=[
                {"role": "user", "content": "Say 'Hello' in one word"}
            ],
            max_tokens=10
        )
        
        try:
            response = await adapter.complete(request)
            print(f"✅ Available (response: {response.text.strip()})")
            available.append(model)
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg or "not found" in error_msg:
                print("❌ Not available")
            else:
                print(f"❌ Error: {error_msg[:50]}...")
    
    print("\n" + "-"*60)
    print("AVAILABLE MODELS:")
    for model in available:
        print(f"  ✅ {model}")
    
    return available


if __name__ == "__main__":
    # First check available models
    print("Checking available OpenAI models...")
    available = asyncio.run(test_available_models())
    
    # Then run the main test
    print("\n" + "="*60)
    input("Press Enter to run grounding test with available model...")
    
    success = asyncio.run(test_openai_grounding())
    exit(0 if success else 1)