#!/usr/bin/env python3
"""
Test GPT-5 with proper Responses API and web search.
"""
import os
import sys
import json
from datetime import datetime
import asyncio

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file
from pathlib import Path
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

from app.llm.types import LLMRequest
from app.llm.adapters.openai_adapter import OpenAIAdapter


async def test_gpt5_model(model_name="gpt-5", with_grounding=True):
    """Test GPT-5 model through the adapter with proper Responses API."""
    print("="*60)
    print(f"Testing {model_name} with OpenAI Adapter")
    print("="*60)
    
    try:
        # Initialize adapter
        print("\n1. Initializing OpenAI adapter...")
        adapter = OpenAIAdapter()
        print("✅ Adapter initialized")
        
        # Create request
        prompt = "give me a summary of health and wellness news during August 2025"
        
        request = LLMRequest(
            vendor="openai",
            model=model_name,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful AI assistant. Provide accurate, up-to-date information."
                },
                {"role": "user", "content": prompt}
            ],
            grounded=with_grounding,
            temperature=0.7,  # Will be overridden to 1.0 for GPT-5
            max_tokens=3000,
            meta={
                "grounding_mode": "REQUIRED" if with_grounding else "AUTO"
            }
        )
        
        print(f"\n2. Request Details:")
        print(f"   Model: {model_name}")
        print(f"   Grounded: {with_grounding}")
        print(f"   Grounding Mode: {'REQUIRED' if with_grounding else 'AUTO'}")
        print(f"   Prompt: {prompt}")
        print(f"   Using: Responses API with web_search tool")
        
        print("\n3. Sending request...")
        start_time = datetime.now()
        
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
        print(f"  Model: {response.model}")
        print(f"  Vendor: {response.vendor}")
        print(f"  Total tokens: {response.total_tokens}")
        print(f"  Response time: {elapsed:.1f}s")
        
        # Check grounding
        if response.metadata:
            print("\nGROUNDING INFO:")
            print(f"  Grounded attempted: {response.metadata.get('grounding_attempted', False)}")
            print(f"  Grounded effective: {response.metadata.get('grounded_effective', False)}")
            print(f"  Web search count: {response.metadata.get('web_search_count', 0)}")
            print(f"  Tool call count: {response.metadata.get('tool_call_count', 0)}")
            
            # Check for web search queries
            queries = response.metadata.get('web_search_queries', [])
            if queries:
                print(f"  Web search queries ({len(queries)}):")
                for i, query in enumerate(queries[:5]):
                    print(f"    {i+1}. {query}")
            
            # Citations
            if response.citations:
                print(f"\n  Citations found: {len(response.citations)}")
                for i, citation in enumerate(response.citations[:5]):
                    url = citation.get('url', citation.get('uri', 'N/A'))
                    title = citation.get('title', 'N/A')
                    print(f"    {i+1}. {title[:50]}... - {url[:50]}...")
        
        # Check content indicators
        print("\nCONTENT ANALYSIS:")
        has_august_2025 = "august 2025" in response.text.lower()
        has_health = any(term in response.text.lower() for term in ["health", "wellness", "medical"])
        has_sources = any(term in response.text.lower() for term in ["according to", "reported", "study", "research"])
        
        print(f"  Mentions August 2025: {'✅' if has_august_2025 else '❌'}")
        print(f"  Has health content: {'✅' if has_health else '❌'}")
        print(f"  References sources: {'✅' if has_sources else '❌'}")
        
        # Save results
        output_file = f"gpt5_adapter_test_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": model_name,
                    "prompt": prompt,
                    "grounded": with_grounding,
                    "grounding_mode": "REQUIRED" if with_grounding else "AUTO"
                },
                "response": {
                    "text": response.text,
                    "model_used": response.model,
                    "total_tokens": response.total_tokens,
                    "elapsed_seconds": elapsed
                },
                "grounding": {
                    "attempted": response.metadata.get('grounding_attempted', False) if response.metadata else False,
                    "effective": response.metadata.get('grounded_effective', False) if response.metadata else False,
                    "web_search_count": response.metadata.get('web_search_count', 0) if response.metadata else 0,
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
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        
        # Check error details
        error_str = str(e)
        if "model" in error_str.lower() and ("does not exist" in error_str.lower() or "not found" in error_str.lower()):
            print(f"\n⚠️  Model '{model_name}' not available")
        elif "web_search" in error_str.lower() and "not supported" in error_str.lower():
            print(f"\n⚠️  Web search not supported for model '{model_name}'")
        elif "400" in error_str:
            print(f"\n⚠️  Bad request - check model name and parameters")
        
        import traceback
        traceback.print_exc()
        return False


async def test_all_gpt5_variants():
    """Test all GPT-5 model variants."""
    models_to_test = [
        "gpt-5",         # Primary reasoning model
        "gpt-5-mini",    # Smaller variant
        "gpt-5-nano",    # Smallest variant
        "gpt-4o"         # Fallback to known working model
    ]
    
    for model in models_to_test:
        print(f"\n{'='*60}")
        print(f"Testing model: {model}")
        print('='*60)
        
        success = await test_gpt5_model(model, with_grounding=True)
        
        if success:
            print(f"\n✅ {model} test successful with grounding!")
            return True
        else:
            print(f"\n❌ {model} test failed, trying next model...")
            continue
    
    return False


if __name__ == "__main__":
    success = asyncio.run(test_all_gpt5_variants())
    exit(0 if success else 1)