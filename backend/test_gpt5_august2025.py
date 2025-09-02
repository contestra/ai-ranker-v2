#!/usr/bin/env python3
"""
Test gpt-5-2025-08-07 with a proper August 2025 prompt
"""

import os
import sys
import json
import asyncio
from datetime import datetime

# Add backend to path FIRST
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env file
from dotenv import load_dotenv
load_dotenv('/home/leedr/ai-ranker-v2/backend/.env')

# Verify API key
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    print("❌ OPENAI_API_KEY not found")
    sys.exit(1)
print(f"✅ OPENAI_API_KEY loaded: sk-...{api_key[-4:]}")

# Set environment variables
os.environ['ALLOWED_OPENAI_MODELS'] = 'gpt-4,gpt-4-turbo,gpt-4o,gpt-4o-mini,gpt-5,gpt-5-chat-latest,gpt-5-2025-08-07'
os.environ['DEBUG_GROUNDING'] = 'true'

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Much better prompt - asking about last month (August 2025)
TEST_PROMPT = "Please provide a summary of longevity and healthspan related news during August 2025"

async def test_model_with_prompt(model: str):
    """Test a model with the August 2025 prompt"""
    
    adapter = UnifiedLLMAdapter()
    
    print("="*70)
    print(f"Testing: {model}")
    print(f"Date context: September 2, 2025")
    print(f"Prompt: {TEST_PROMPT}")
    print("="*70)
    
    results = {}
    
    # Test AUTO mode
    print("\n📝 AUTO MODE TEST")
    print("-"*50)
    
    try:
        request = LLMRequest(
            messages=[{"role": "user", "content": TEST_PROMPT}],
            model=model,
            vendor="openai",
            grounded=True,
            max_tokens=500,  # More tokens for comprehensive summary
            temperature=0.3,
            meta={"grounding_mode": "AUTO"}
        )
        
        response = await adapter.complete(request)
        
        if response.success:
            meta = response.metadata or {}
            print(f"✅ Success")
            print(f"   Content length: {len(response.content or '')}")
            print(f"   Tool calls: {meta.get('tool_call_count', 0)}")
            print(f"   Grounded effective: {meta.get('grounded_effective', False)}")
            print(f"   Citations: {len(meta.get('citations', []))}")
            print(f"   Response API: {meta.get('response_api', 'Unknown')}")
            
            # Show snippet of content if available
            if response.content:
                print(f"\n   Content snippet: {response.content[:200]}...")
            
            # Check for grounding issues
            if meta.get('grounding_not_supported'):
                print(f"\n   ❌ Grounding not supported")
                print(f"   Reason: {meta.get('grounding_status_reason', 'Unknown')}")
            elif meta.get('tool_call_count', 0) > 0:
                print(f"\n   ✅ TOOLS WERE CALLED!")
                if len(meta.get('citations', [])) == 0:
                    print(f"   ⚠️ But no citations extracted")
            
            # Check for HTTP errors
            if meta.get('openai_error_message'):
                print(f"\n   ⚠️ HTTP {meta.get('openai_error_status', 400)}")
                print(f"   Error: {meta.get('openai_error_message')[:100]}")
            
            results['auto'] = {
                'success': True,
                'content_length': len(response.content or ''),
                'tool_calls': meta.get('tool_call_count', 0),
                'grounded': meta.get('grounded_effective', False),
                'citations': len(meta.get('citations', [])),
                'grounding_not_supported': meta.get('grounding_not_supported', False),
                'http_error': meta.get('openai_error_message'),
                'why_not_grounded': meta.get('grounding_status_reason')
            }
        else:
            print(f"❌ Failed")
            if hasattr(response, 'error') and response.error:
                print(f"   Error: {response.error[:200]}")
                results['auto'] = {'success': False, 'error': response.error}
            else:
                print(f"   No error details available")
                results['auto'] = {'success': False, 'error': 'Unknown error'}
            
    except Exception as e:
        print(f"❌ Exception: {str(e)[:200]}")
        results['auto'] = {'success': False, 'error': str(e)}
    
    # Analysis
    print("\n" + "="*70)
    print("VERDICT FOR " + model)
    print("="*70)
    
    auto = results.get('auto', {})
    
    if auto.get('tool_calls', 0) > 0:
        print(f"✅ {model} CAN use web_search tools!")
        print(f"   Made {auto.get('tool_calls')} tool call(s)")
        if auto.get('citations', 0) > 0:
            print(f"   Returned {auto.get('citations')} citation(s)")
        else:
            print(f"   But no citations were extracted")
    elif auto.get('grounding_not_supported'):
        print(f"❌ {model} CANNOT use web_search tools")
        print(f"   Reason: {auto.get('why_not_grounded', 'Unknown')}")
    elif auto.get('http_error') and "not supported" in (auto.get('http_error') or '').lower():
        print(f"❌ {model} CANNOT use web_search tools")
        print(f"   HTTP error: Tool not supported")
    elif auto.get('success') and auto.get('content_length', 0) > 0:
        print(f"🟡 {model} returned content but no tool calls")
        print(f"   May have answered without grounding")
    else:
        print(f"❓ Unclear - need more investigation")
    
    return results

async def main():
    """Test multiple models with the August 2025 prompt"""
    
    all_results = {}
    
    # Test models in order of interest
    test_models = [
        "gpt-5-2025-08-07",  # The new model we're testing
        "gpt-4o",            # Known to work
        "gpt-5"              # Regular GPT-5 for comparison
    ]
    
    for model in test_models:
        results = await test_model_with_prompt(model)
        all_results[model] = results
        await asyncio.sleep(3)  # Rate limiting
        
        # Stop if we find a working model
        if results.get('auto', {}).get('tool_calls', 0) > 0:
            print(f"\n🎯 Found working configuration with {model}")
    
    # Save all results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"august2025_grounding_test_{timestamp}.json"
    
    output = {
        "test_metadata": {
            "timestamp": timestamp,
            "prompt": TEST_PROMPT,
            "context": "Testing on September 2, 2025 - asking about August 2025",
            "models_tested": list(all_results.keys())
        },
        "results": all_results,
        "summary": {
            "any_model_worked": any(
                r.get('auto', {}).get('tool_calls', 0) > 0 
                for r in all_results.values()
            ),
            "working_models": [
                m for m, r in all_results.items() 
                if r.get('auto', {}).get('tool_calls', 0) > 0
            ]
        }
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n📁 Results saved to: {filename}")
    
    # Final summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    
    working = output['summary']['working_models']
    if working:
        print(f"✅ Models that can ground August 2025 queries: {', '.join(working)}")
    else:
        print("❌ No models successfully grounded the August 2025 query")
    
    return all_results

if __name__ == "__main__":
    results = asyncio.run(main())