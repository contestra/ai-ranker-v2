#!/usr/bin/env python3
"""
Test GPT-4 and GPT-5 ungrounded with German ALS
Prompt: Primary health and wellness news during August 2025
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

os.environ["OAI_DISABLE_LIMITER"] = "1"


async def test_model_ungrounded(model_name: str):
    """Test a model with ungrounded German ALS health news prompt."""
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    # German ALS template
    als_template = "de-DE, Deutschland, Europe/Berlin timezone"
    
    # Build messages with ALS
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"{als_template}\n\nTell me the primary health and wellness news during August 2025"}
    ]
    
    request = LLMRequest(
        vendor="openai",
        model=model_name,
        messages=messages,
        grounded=False,
        max_tokens=500  # More tokens for news response
    )
    
    print(f"\n{'='*80}")
    print(f"Testing {model_name.upper()} - UNGROUNDED with German ALS")
    print(f"{'='*80}")
    print(f"ALS: {als_template}")
    print(f"Prompt: Tell me the primary health and wellness news during August 2025")
    print(f"Grounded: False")
    print(f"Max tokens: 500")
    
    start_time = datetime.now()
    
    try:
        response = await adapter.complete(request, timeout=60)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print(f"\n📊 Response Metadata:")
        metadata = response.metadata or {}
        print(f"  Response API: {metadata.get('response_api', 'unknown')}")
        print(f"  ALS present: {metadata.get('als_present', False)}")
        print(f"  ALS position: {metadata.get('als_position', 'unknown')}")
        print(f"  Text source: {metadata.get('text_source', 'message')}")
        print(f"  Ungrounded retry: {metadata.get('ungrounded_retry', 0)}")
        print(f"  Response time: {elapsed:.2f}s")
        
        # Usage info
        if response.usage:
            print(f"\n📈 Token Usage:")
            print(f"  Prompt tokens: {response.usage.get('prompt_tokens', 0)}")
            print(f"  Completion tokens: {response.usage.get('completion_tokens', 0)}")
            print(f"  Total tokens: {response.usage.get('total_tokens', 0)}")
        
        print(f"\n📝 Response Content:")
        print(f"  Length: {len(response.content)} characters")
        print(f"\n--- CONTENT START ---")
        print(response.content)
        print("--- CONTENT END ---")
        
        # Check for German locale indicators
        german_indicators = []
        content_lower = response.content.lower()
        
        if "august 2025" in content_lower:
            german_indicators.append("Contains 'August 2025'")
        if "health" in content_lower or "gesundheit" in content_lower:
            german_indicators.append("Contains health terms")
        if "wellness" in content_lower:
            german_indicators.append("Contains wellness")
        
        if german_indicators:
            print(f"\n✅ Content Analysis:")
            for indicator in german_indicators:
                print(f"  • {indicator}")
        
        return True, response.content
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return False, str(e)


async def main():
    """Test both GPT-4 and GPT-5 with the same prompt."""
    print("\n" + "="*80)
    print("GPT-4 vs GPT-5 UNGROUNDED HEALTH NEWS TEST")
    print("WITH GERMAN ALS (de-DE)")
    print("="*80)
    
    models = [
        "gpt-4o",
        "gpt-5-2025-08-07"
    ]
    
    results = {}
    
    for model in models:
        success, content = await test_model_ungrounded(model)
        results[model] = {
            "success": success,
            "content": content,
            "content_length": len(content) if isinstance(content, str) else 0
        }
        await asyncio.sleep(3)  # Rate limiting
    
    # Summary comparison
    print(f"\n{'='*80}")
    print("COMPARISON SUMMARY")
    print(f"{'='*80}")
    
    for model, result in results.items():
        status = "✅" if result["success"] else "❌"
        print(f"\n{model}:")
        print(f"  Status: {status}")
        print(f"  Content length: {result['content_length']} chars")
        
        if result["success"] and result["content_length"] > 0:
            # Check if content seems appropriate
            content = result["content"]
            has_health = "health" in content.lower() or "wellness" in content.lower() or "gesundheit" in content.lower()
            has_date = "2025" in content or "august" in content.lower()
            print(f"  Has health terms: {'✅' if has_health else '❌'}")
            print(f"  Has date reference: {'✅' if has_date else '❌'}")
    
    # Final assessment
    all_success = all(r["success"] for r in results.values())
    all_have_content = all(r["content_length"] > 0 for r in results.values())
    
    print(f"\n{'='*80}")
    print("FINAL ASSESSMENT")
    print(f"{'='*80}")
    print(f"All models succeeded: {'✅' if all_success else '❌'}")
    print(f"All produced content: {'✅' if all_have_content else '❌'}")
    
    if all_success and all_have_content:
        print("\n🎉 Both GPT-4 and GPT-5 successfully generated health news content!")
    else:
        print("\n⚠️ Some issues detected - review the output above")
    
    return all_success and all_have_content


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)