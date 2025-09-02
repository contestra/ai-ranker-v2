#!/usr/bin/env python3
"""
OpenAI Capability Test - Single focused test to verify grounding capability
Tests one model with REQUIRED mode to definitively determine if web_search tools work
"""

import os
import sys
import json
import asyncio
from datetime import datetime

# Add backend to path FIRST
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env file BEFORE setting other environment variables
from dotenv import load_dotenv
load_dotenv('/home/leedr/ai-ranker-v2/backend/.env')

# Verify API key is loaded
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    print("❌ OPENAI_API_KEY not found in environment")
    sys.exit(1)
else:
    print(f"✅ OPENAI_API_KEY loaded: sk-...{api_key[-4:]}")

# Set environment variables for testing
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATIONS_EXTRACTOR_ENABLE'] = 'true'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'true'
os.environ['DEBUG_GROUNDING'] = 'true'
os.environ['ALLOW_HTTP_RESOLVE'] = 'false'
os.environ['ALLOWED_OPENAI_MODELS'] = 'gpt-4,gpt-4-turbo,gpt-4o,gpt-4o-mini,gpt-5,gpt-5-chat-latest'

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test with a query that REQUIRES recent information
TEST_PROMPT = """What are the latest AI developments announced by OpenAI in December 2024?
Include specific dates and official announcement URLs."""

async def test_single_model():
    """Test a single model with both AUTO and REQUIRED modes"""
    
    adapter = UnifiedLLMAdapter()
    model = "gpt-5"  # Start with GPT-5 since it's the primary model
    
    print("="*70)
    print(f"OpenAI Grounding Capability Test - {datetime.now().isoformat()}")
    print("="*70)
    print(f"Model: {model}")
    print(f"Prompt: {TEST_PROMPT[:60]}...")
    print()
    
    results = {}
    
    # Test 1: AUTO mode
    print("TEST 1: AUTO MODE")
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
            print(f"✅ AUTO mode succeeded")
            print(f"   Content length: {len(response.content or '')}")
            print(f"   Tool calls: {meta.get('tool_call_count', 0)}")
            print(f"   Grounded effective: {meta.get('grounded_effective', False)}")
            print(f"   Citations: {len(meta.get('citations', []))}")
            print(f"   Response API: {meta.get('response_api', 'None')}")
            
            if meta.get('why_not_grounded'):
                print(f"   ⚠️ Not grounded because: {meta.get('why_not_grounded')}")
            
            if meta.get('grounding_not_supported'):
                print(f"   ❌ Grounding not supported: {meta.get('grounding_status_reason', 'Unknown')}")
                
            results['auto'] = {
                'success': True,
                'tool_calls': meta.get('tool_call_count', 0),
                'grounded': meta.get('grounded_effective', False),
                'citations': len(meta.get('citations', [])),
                'why_not_grounded': meta.get('why_not_grounded'),
                'error': meta.get('error_message'),
                # Capture HTTP error details if present
                'openai_error_status': meta.get('openai_error_status'),
                'openai_error_message': meta.get('openai_error_message'),
                'openai_error_type': meta.get('openai_error_type'),
                'openai_request_id': meta.get('openai_request_id')
            }
        else:
            print(f"❌ AUTO mode failed: {response.error}")
            results['auto'] = {
                'success': False,
                'error': response.error
            }
            
    except Exception as e:
        print(f"❌ AUTO mode exception: {e}")
        results['auto'] = {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    
    print()
    await asyncio.sleep(2)  # Rate limiting
    
    # Test 2: REQUIRED mode
    print("TEST 2: REQUIRED MODE")
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
            print(f"✅ REQUIRED mode succeeded")
            print(f"   Content length: {len(response.content or '')}")
            print(f"   Tool calls: {meta.get('tool_call_count', 0)}")
            print(f"   Grounded effective: {meta.get('grounded_effective', False)}")
            print(f"   Citations: {len(meta.get('citations', []))}")
            print(f"   Anchored citations: {meta.get('anchored_citations_count', 0)}")
            
            results['required'] = {
                'success': True,
                'tool_calls': meta.get('tool_call_count', 0),
                'grounded': meta.get('grounded_effective', False),
                'citations': len(meta.get('citations', [])),
                'anchored': meta.get('anchored_citations_count', 0)
            }
        else:
            print(f"❌ REQUIRED mode failed: {response.error}")
            error_msg = response.error or ""
            
            # Check for specific error patterns
            if "GROUNDING_NOT_SUPPORTED" in error_msg:
                print("   📌 GROUNDING_NOT_SUPPORTED error - OpenAI account lacks entitlement")
            elif "GROUNDING_REQUIRED_FAILED" in error_msg:
                print("   📌 GROUNDING_REQUIRED_FAILED - Tools didn't return citations")
            elif "web_search" in error_msg and "not supported" in error_msg:
                print("   📌 Hosted tool not supported - Account limitation confirmed")
                
            results['required'] = {
                'success': False,
                'error': response.error,
                'is_entitlement_issue': "not supported" in error_msg or "GROUNDING_NOT_SUPPORTED" in error_msg
            }
            
    except Exception as e:
        print(f"❌ REQUIRED mode exception: {e}")
        error_str = str(e)
        
        if "GROUNDING_NOT_SUPPORTED" in error_str:
            print("   📌 GROUNDING_NOT_SUPPORTED exception - OpenAI account lacks entitlement")
        elif "not supported" in error_str and "web_search" in error_str:
            print("   📌 Hosted tool not supported - Account limitation confirmed")
            
        results['required'] = {
            'success': False,
            'error': error_str,
            'error_type': type(e).__name__,
            'is_entitlement_issue': "not supported" in error_str or "GROUNDING_NOT_SUPPORTED" in error_str
        }
    
    # Analysis
    print()
    print("="*70)
    print("DIAGNOSIS")
    print("="*70)
    
    # Determine the issue
    if results.get('auto', {}).get('tool_calls', 0) > 0:
        print("✅ OpenAI CAN invoke web_search tools")
        print("   The account HAS entitlement for grounding")
        if results['auto'].get('citations', 0) == 0:
            print("   ⚠️ But citation extraction may need debugging")
    elif results.get('required', {}).get('is_entitlement_issue'):
        print("❌ OpenAI CANNOT invoke web_search tools")
        print("   The account LACKS entitlement for grounding")
        print("   Action: Contact OpenAI support with this evidence")
    elif not results.get('auto', {}).get('success'):
        print("❓ Test inconclusive - AUTO mode failed")
        print(f"   Error: {results.get('auto', {}).get('error')}")
    else:
        print("❌ OpenAI is not invoking web_search tools")
        print("   Even though no explicit error was returned")
        print("   This suggests an account limitation")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"openai_capability_test_{timestamp}.json"
    
    output = {
        "test_metadata": {
            "timestamp": timestamp,
            "model": model,
            "prompt": TEST_PROMPT,
            "api_key_present": bool(api_key)
        },
        "results": results
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n📁 Results saved to: {filename}")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(test_single_model())
    
    # Exit with appropriate code
    if results.get('required', {}).get('is_entitlement_issue'):
        print("\n🔴 Confirmed: OpenAI account lacks web_search entitlement")
        sys.exit(1)
    elif results.get('auto', {}).get('tool_calls', 0) > 0:
        print("\n🟢 Success: OpenAI grounding is working")
        sys.exit(0)
    else:
        print("\n🟡 Unclear: Further investigation needed")
        sys.exit(2)