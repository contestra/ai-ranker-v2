#!/usr/bin/env python3
"""
Test gpt-5-2025-08-07 specific version for grounding capability
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

TEST_PROMPT = """What are the latest AI developments from OpenAI in 2024?
Include specific dates and official URLs."""

async def test_gpt5_version():
    """Test gpt-5-2025-08-07 grounding capability"""
    
    adapter = UnifiedLLMAdapter()
    model = "gpt-5-2025-08-07"
    
    print("="*70)
    print(f"Testing: {model}")
    print(f"Prompt: {TEST_PROMPT[:50]}...")
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
            max_tokens=300,
            temperature=0.3,
            meta={"grounding_mode": "AUTO"}
        )
        
        response = await adapter.complete(request)
        
        if response.success:
            meta = response.metadata or {}
            print(f"✅ Success")
            print(f"   Model effective: {meta.get('model', 'Unknown')}")
            print(f"   Tool calls: {meta.get('tool_call_count', 0)}")
            print(f"   Grounded effective: {meta.get('grounded_effective', False)}")
            print(f"   Citations: {len(meta.get('citations', []))}")
            print(f"   Response API: {meta.get('response_api', 'Unknown')}")
            
            # Check for errors
            if meta.get('openai_error_message'):
                print(f"\n   ⚠️ HTTP {meta.get('openai_error_status', 400)}")
                print(f"   Error: {meta.get('openai_error_message')[:100]}")
                
            if meta.get('grounding_not_supported'):
                print(f"   ❌ Grounding not supported")
                print(f"   Reason: {meta.get('grounding_status_reason', 'Unknown')}")
            
            results['auto'] = {
                'success': True,
                'tool_calls': meta.get('tool_call_count', 0),
                'grounded': meta.get('grounded_effective', False),
                'citations': len(meta.get('citations', [])),
                'http_error': meta.get('openai_error_message'),
                'http_status': meta.get('openai_error_status')
            }
        else:
            print(f"❌ Failed: {response.error}")
            results['auto'] = {'success': False, 'error': response.error}
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        results['auto'] = {'success': False, 'error': str(e)}
    
    await asyncio.sleep(2)
    
    # Test REQUIRED mode
    print("\n📝 REQUIRED MODE TEST")
    print("-"*50)
    
    try:
        request = LLMRequest(
            messages=[{"role": "user", "content": TEST_PROMPT}],
            model=model,
            vendor="openai",
            grounded=True,
            max_tokens=300,
            temperature=0.3,
            meta={"grounding_mode": "REQUIRED"}
        )
        
        response = await adapter.complete(request)
        
        if response.success:
            meta = response.metadata or {}
            print(f"✅ Success (unexpected)")
            print(f"   Tool calls: {meta.get('tool_call_count', 0)}")
            print(f"   Citations: {len(meta.get('citations', []))}")
            results['required'] = {
                'success': True,
                'unexpected': True,
                'tool_calls': meta.get('tool_call_count', 0)
            }
        else:
            print(f"❌ Failed (expected): {response.error[:100]}")
            error_str = response.error or ""
            
            if "GROUNDING_NOT_SUPPORTED" in error_str:
                print(f"   📌 Confirmed: Model doesn't support web_search")
            elif "not supported" in error_str:
                print(f"   📌 Confirmed: Hosted tool not supported")
                
            results['required'] = {
                'success': False,
                'error': response.error,
                'is_not_supported': "not supported" in error_str.lower()
            }
            
    except Exception as e:
        error_str = str(e)
        print(f"❌ Exception: {error_str[:100]}")
        
        if "GROUNDING_NOT_SUPPORTED" in error_str or "not supported" in error_str.lower():
            print(f"   📌 Confirmed: Model doesn't support web_search")
            
        results['required'] = {
            'success': False,
            'error': error_str,
            'is_not_supported': "not supported" in error_str.lower()
        }
    
    # Analysis
    print("\n" + "="*70)
    print("VERDICT")
    print("="*70)
    
    auto = results.get('auto', {})
    required = results.get('required', {})
    
    if auto.get('tool_calls', 0) > 0:
        print(f"✅ {model} CAN use web_search tools!")
        print("   This model supports grounding")
    elif auto.get('http_error') and "not supported" in auto.get('http_error', '').lower():
        print(f"❌ {model} CANNOT use web_search tools")
        print(f"   HTTP {auto.get('http_status', 400)}: Tool not supported")
    elif required.get('is_not_supported'):
        print(f"❌ {model} CANNOT use web_search tools")
        print("   REQUIRED mode confirms lack of support")
    else:
        print(f"❓ Unclear - need more investigation")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gpt5_version_test_{timestamp}.json"
    
    output = {
        "model": model,
        "timestamp": timestamp,
        "results": results
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n📁 Results saved to: {filename}")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(test_gpt5_version())
    
    # Exit code based on capability
    if results.get('auto', {}).get('tool_calls', 0) > 0:
        print(f"\n🟢 SUCCESS: gpt-5-2025-08-07 supports grounding!")
        sys.exit(0)
    else:
        print(f"\n🔴 FAILURE: gpt-5-2025-08-07 does not support grounding")
        sys.exit(1)