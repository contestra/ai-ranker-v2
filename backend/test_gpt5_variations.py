#!/usr/bin/env python3
"""
Test for GPT-5 model variations including gpt-5-2025-08-07.
"""
import os
import json
from datetime import datetime
from openai import AsyncOpenAI
import asyncio

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


async def test_gpt5_variations():
    """Test various GPT-5 model names."""
    print("="*60)
    print("Testing GPT-5 Model Variations")
    print("="*60)
    
    # Extended list of GPT-5 variations based on documentation
    test_models = [
        "gpt-5-2025-08-07",  # From documentation
        "gpt-5-2025-08",
        "gpt-5-2025",
        "gpt-5",
        "gpt-5-turbo",
        "gpt-5-turbo-2025-08-07",
        "gpt-5-latest",
        "gpt-5.0",
        "gpt-5.0-latest",
        "chatgpt-5",
        "chatgpt-5-latest",
        "chatgpt-5.0",
        "chatgpt-5.0-latest",
        "o1-preview",  # New reasoning model
        "o1-mini",     # Smaller reasoning model
    ]
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return []
    
    client = AsyncOpenAI(api_key=api_key)
    available = []
    
    print("\nTesting models...")
    print("-"*60)
    
    for model in test_models:
        print(f"Testing {model:30s} ... ", end="", flush=True)
        
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say 'Hello'"}],
                max_tokens=5,
                temperature=0
            )
            
            # Extract response
            response_text = response.choices[0].message.content.strip()
            print(f"✅ AVAILABLE (response: '{response_text}')")
            available.append({
                "model": model,
                "response": response_text,
                "model_id": response.model if hasattr(response, 'model') else model
            })
            
        except Exception as e:
            error_str = str(e)
            if "does not exist" in error_str or "not found" in error_str.lower():
                print("❌ Not found")
            elif "invalid_request_error" in error_str.lower():
                print(f"❌ Invalid: {error_str[:40]}...")
            else:
                print(f"❌ Error: {error_str[:40]}...")
    
    return available


async def test_best_model(model_info):
    """Test the best available model with grounding."""
    model = model_info["model"]
    
    print("\n" + "="*60)
    print(f"Testing {model} with Grounding Request")
    print("="*60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    client = AsyncOpenAI(api_key=api_key)
    
    # Test with August 2025 health news
    prompt = "give me a summary of health and wellness news during August 2025"
    
    messages = [
        {
            "role": "system", 
            "content": "You are a helpful AI assistant with access to web search. When asked about current events, search the web and provide accurate, up-to-date information with sources."
        },
        {"role": "user", "content": prompt}
    ]
    
    print(f"\nModel: {model}")
    print(f"Prompt: {prompt}")
    print("\nSending request...")
    
    start_time = datetime.now()
    
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=3000
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        response_text = response.choices[0].message.content
        
        print(f"✅ Response received in {elapsed:.1f} seconds")
        print("\n" + "-"*60)
        print("RESPONSE:")
        print("-"*60)
        print(response_text[:1500] if len(response_text) > 1500 else response_text)
        if len(response_text) > 1500:
            print(f"\n... (truncated, total length: {len(response_text)} chars)")
        
        # Check for grounding indicators
        indicators = {
            "mentions_august_2025": "august 2025" in response_text.lower(),
            "has_health_content": any(term in response_text.lower() for term in ["health", "wellness", "medical"]),
            "has_sources": any(term in response_text.lower() for term in ["source", "according to", "reported", "study"]),
            "has_future_content": "2025" in response_text,
            "acknowledges_limitations": "cannot" in response_text.lower() or "unable" in response_text.lower()
        }
        
        print("\n" + "-"*60)
        print("GROUNDING ANALYSIS:")
        for key, value in indicators.items():
            print(f"  {key}: {'✅' if value else '❌'}")
        
        # Save results
        output_file = f"gpt5_test_{model.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "model": model,
                "model_id": response.model if hasattr(response, 'model') else model,
                "prompt": prompt,
                "response": response_text,
                "elapsed_seconds": elapsed,
                "tokens": response.usage.total_tokens if response.usage else None,
                "grounding_analysis": indicators,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n📄 Results saved to: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


async def main():
    """Main test function."""
    # Test all GPT-5 variations
    available = await test_gpt5_variations()
    
    if not available:
        print("\n" + "="*60)
        print("❌ No GPT-5 models found")
        print("="*60)
        print("\nNone of the GPT-5 model variations are available:")
        print("  - gpt-5-2025-08-07 (from documentation)")
        print("  - gpt-5")
        print("  - gpt-5-turbo")
        print("  - chatgpt-5")
        print("\nThe model may not be released yet or requires special access.")
        return False
    
    print("\n" + "="*60)
    print("✅ AVAILABLE MODELS:")
    print("="*60)
    for model_info in available:
        print(f"  {model_info['model']} (actual: {model_info['model_id']})")
    
    # Test the first available model
    best_model = available[0]
    success = await test_best_model(best_model)
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)