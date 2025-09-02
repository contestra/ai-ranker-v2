#!/usr/bin/env python3
"""
Direct test of OpenAI API with grounding.
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


async def test_openai_model(model_name="gpt-4o", with_grounding=True):
    """Test OpenAI model directly."""
    print("="*60)
    print(f"Testing OpenAI {model_name}")
    print("="*60)
    
    # Initialize client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return False
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Prepare messages
    prompt = "give me a summary of health and wellness news during August 2025"
    
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant. When answering questions about current events, provide accurate, up-to-date information based on web search."},
        {"role": "user", "content": prompt}
    ]
    
    # Add grounding instruction if requested
    if with_grounding:
        messages[0]["content"] += "\n\nIMPORTANT: You MUST search the web for current information about this topic. This is a REQUIRED grounding request. Include citations and sources in your response."
    
    print(f"\n1. Model: {model_name}")
    print(f"2. Grounding: {'Requested' if with_grounding else 'Not requested'}")
    print(f"3. Prompt: {prompt}")
    
    print("\n4. Sending request...")
    start_time = datetime.now()
    
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=3000
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print(f"\n✅ Response received in {elapsed:.1f} seconds")
        print("="*60)
        
        # Extract response
        response_text = response.choices[0].message.content
        
        print("\nRESPONSE:")
        print("-"*60)
        print(response_text[:2000] if len(response_text) > 2000 else response_text)
        if len(response_text) > 2000:
            print(f"\n... (truncated, total length: {len(response_text)} chars)")
        print("-"*60)
        
        # Display usage
        if response.usage:
            print(f"\nTOKEN USAGE:")
            print(f"  Prompt tokens: {response.usage.prompt_tokens}")
            print(f"  Completion tokens: {response.usage.completion_tokens}")
            print(f"  Total tokens: {response.usage.total_tokens}")
        
        # Check for grounding indicators
        grounding_indicators = [
            "as of", "according to", "recent", "2025", "August 2025",
            "source", "research", "study", "report", "news"
        ]
        
        indicators_found = [ind for ind in grounding_indicators if ind.lower() in response_text.lower()]
        
        print(f"\nGROUNDING ANALYSIS:")
        print(f"  Indicators found: {len(indicators_found)}/10")
        print(f"  Indicators: {', '.join(indicators_found[:5])}")
        
        # Look for specific August 2025 content
        has_august_2025 = "august 2025" in response_text.lower()
        has_health_content = any(term in response_text.lower() for term in ["health", "wellness", "medical", "healthcare"])
        
        print(f"  Mentions August 2025: {'✅' if has_august_2025 else '❌'}")
        print(f"  Has health content: {'✅' if has_health_content else '❌'}")
        
        # Save results
        output_file = f"openai_{model_name.replace('/', '_')}_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": model_name,
                    "prompt": prompt,
                    "grounding_requested": with_grounding
                },
                "response": {
                    "text": response_text,
                    "elapsed_seconds": elapsed,
                    "total_tokens": response.usage.total_tokens if response.usage else None
                },
                "grounding_analysis": {
                    "indicators_found": len(indicators_found),
                    "mentions_august_2025": has_august_2025,
                    "has_health_content": has_health_content
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n📄 Results saved to: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        
        # Check for specific errors
        error_str = str(e)
        if "model" in error_str.lower() and "does not exist" in error_str.lower():
            print(f"\n⚠️  Model '{model_name}' not available")
            return False
        elif "api_key" in error_str.lower():
            print("\n⚠️  API key issue - check OPENAI_API_KEY environment variable")
            return False
        else:
            import traceback
            traceback.print_exc()
            return False


async def check_available_models():
    """Check which models are available."""
    print("\n" + "="*60)
    print("Checking Available OpenAI Models")
    print("="*60)
    
    test_models = [
        "gpt-5",
        "chatgpt-5.0-latest",
        "gpt-5-turbo", 
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4",
        "gpt-3.5-turbo"
    ]
    
    available = []
    
    for model in test_models:
        print(f"\nTesting {model}...", end=" ")
        
        # Quick test with minimal tokens
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("❌ No API key")
                break
                
            client = AsyncOpenAI(api_key=api_key)
            
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            print(f"✅ Available")
            available.append(model)
            
        except Exception as e:
            if "does not exist" in str(e) or "not found" in str(e).lower():
                print("❌ Not found")
            else:
                print(f"❌ Error: {str(e)[:30]}...")
    
    if available:
        print("\n" + "-"*60)
        print("AVAILABLE MODELS:")
        for model in available:
            print(f"  ✅ {model}")
    else:
        print("\n⚠️  No models available - check API key")
    
    return available


async def main():
    """Main test function."""
    # Check available models first
    available = await check_available_models()
    
    if not available:
        print("\n❌ No models available to test")
        return False
    
    # Use the best available model
    best_model = available[0]
    
    print("\n" + "="*60)
    print(f"Running grounding test with: {best_model}")
    print("="*60)
    
    # Test with grounding
    success = await test_openai_model(best_model, with_grounding=True)
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)