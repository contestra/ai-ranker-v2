#!/usr/bin/env python3
"""
OpenAI Bulletproof Evidence Test - Test one model from each GPT family
Captures complete HTTP 400 error details for irrefutable evidence
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

# Test one model from each family
TEST_MODELS = {
    "gpt-4": "GPT-4 Base",
    "gpt-4-turbo": "GPT-4 Turbo",
    "gpt-4o": "GPT-4 Optimized",
    "gpt-5": "GPT-5 Latest"
}

# Test with a query that REQUIRES recent information
TEST_PROMPT = """What are the latest AI breakthroughs announced in December 2024?
Include specific dates and official source URLs."""

async def test_model_grounding(adapter: UnifiedLLMAdapter, model: str, family: str) -> dict:
    """Test a single model in AUTO and REQUIRED modes"""
    
    print(f"\n{'='*70}")
    print(f"Testing: {model} ({family})")
    print(f"{'='*70}")
    
    result = {
        "model": model,
        "family": family,
        "timestamp": datetime.now().isoformat(),
        "api_key_present": bool(api_key)
    }
    
    # Test AUTO mode
    print("\nAUTO MODE:")
    print("-" * 40)
    
    try:
        request = LLMRequest(
            messages=[{"role": "user", "content": TEST_PROMPT}],
            model=model,
            vendor="openai",
            grounded=True,
            max_tokens=200,
            temperature=0.3,
            meta={"grounding_mode": "AUTO", "test_family": family}
        )
        
        response = await adapter.complete(request)
        meta = response.metadata or {}
        
        if response.success:
            print(f"✅ Response received")
            print(f"   Tool calls: {meta.get('tool_call_count', 0)}")
            print(f"   Grounded: {meta.get('grounded_effective', False)}")
            print(f"   Citations: {len(meta.get('citations', []))}")
            
            result['auto'] = {
                'success': True,
                'tool_calls': meta.get('tool_call_count', 0),
                'grounded': meta.get('grounded_effective', False),
                'citations': len(meta.get('citations', [])),
                'grounding_not_supported': meta.get('grounding_not_supported', False),
                'why_not_grounded': meta.get('grounding_status_reason'),
                # HTTP error details
                'openai_error_status': meta.get('openai_error_status'),
                'openai_error_message': meta.get('openai_error_message'),
                'openai_error_type': meta.get('openai_error_type'),
                'openai_request_id': meta.get('openai_request_id'),
                'openai_retry_error_status': meta.get('openai_retry_error_status'),
                'openai_retry_error_message': meta.get('openai_retry_error_message'),
                'openai_retry_request_id': meta.get('openai_retry_request_id')
            }
            
            # Print captured error if present
            if meta.get('openai_error_message'):
                print(f"   📌 HTTP {meta.get('openai_error_status', 400)}: {meta.get('openai_error_message')[:100]}")
                if meta.get('openai_request_id'):
                    print(f"   Request ID: {meta.get('openai_request_id')}")
                    
        else:
            print(f"❌ Failed: {response.error}")
            result['auto'] = {
                'success': False,
                'error': response.error
            }
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        result['auto'] = {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
    
    await asyncio.sleep(2)  # Rate limiting
    
    # Test REQUIRED mode
    print("\nREQUIRED MODE:")
    print("-" * 40)
    
    try:
        request = LLMRequest(
            messages=[{"role": "user", "content": TEST_PROMPT}],
            model=model,
            vendor="openai",
            grounded=True,
            max_tokens=200,
            temperature=0.3,
            meta={"grounding_mode": "REQUIRED", "test_family": family}
        )
        
        response = await adapter.complete(request)
        meta = response.metadata or {}
        
        if response.success:
            print(f"✅ Response received (unexpected - should fail)")
            result['required'] = {
                'success': True,
                'unexpected': True,
                'tool_calls': meta.get('tool_call_count', 0),
                'citations': len(meta.get('citations', []))
            }
        else:
            print(f"❌ Failed as expected: {response.error[:100]}")
            error_str = response.error or ""
            
            result['required'] = {
                'success': False,
                'error': response.error,
                'is_entitlement_issue': (
                    "GROUNDING_NOT_SUPPORTED" in error_str or 
                    "not supported" in error_str
                )
            }
            
            if result['required']['is_entitlement_issue']:
                print(f"   📌 Confirmed: Account lacks web_search entitlement")
                
    except Exception as e:
        error_str = str(e)
        print(f"❌ Exception: {error_str[:100]}")
        
        result['required'] = {
            'success': False,
            'error': error_str,
            'error_type': type(e).__name__,
            'is_entitlement_issue': (
                "GROUNDING_NOT_SUPPORTED" in error_str or 
                "not supported" in error_str
            )
        }
        
        if result['required']['is_entitlement_issue']:
            print(f"   📌 Confirmed: Account lacks web_search entitlement")
    
    return result

async def test_all_families():
    """Test one model from each GPT family"""
    
    adapter = UnifiedLLMAdapter()
    results = {}
    
    print("="*70)
    print("OpenAI Bulletproof Evidence Collection")
    print(f"Testing {len(TEST_MODELS)} model families")
    print("="*70)
    
    for model, family in TEST_MODELS.items():
        result = await test_model_grounding(adapter, model, family)
        results[model] = result
        
        # Early exit if we find a working model
        if result.get('auto', {}).get('tool_calls', 0) > 0:
            print(f"\n🟢 Found working model: {model}")
            break
    
    return results

def analyze_results(results: dict):
    """Analyze and summarize results"""
    
    print("\n" + "="*70)
    print("ANALYSIS")
    print("="*70)
    
    # Check for any working models
    working_models = []
    failed_models = []
    http_errors = []
    
    for model, data in results.items():
        auto = data.get('auto', {})
        if auto.get('success'):
            if auto.get('tool_calls', 0) > 0:
                working_models.append(model)
            else:
                failed_models.append(model)
                
            # Collect HTTP errors
            if auto.get('openai_error_message'):
                http_errors.append({
                    'model': model,
                    'status': auto.get('openai_error_status', 400),
                    'message': auto.get('openai_error_message'),
                    'request_id': auto.get('openai_request_id', '')
                })
    
    # Print summary
    if working_models:
        print(f"✅ Working models (can use web_search): {', '.join(working_models)}")
        print("   → Account HAS entitlement (at least for some models)")
    else:
        print("❌ NO models can use web_search tools")
        print("   → Account LACKS entitlement (confirmed across all families)")
    
    # Print HTTP error evidence
    if http_errors:
        print("\n📋 HTTP Error Evidence:")
        for err in http_errors:
            print(f"   • {err['model']}: HTTP {err['status']}")
            print(f"     Message: {err['message'][:80]}")
            if err['request_id']:
                print(f"     Request ID: {err['request_id']}")
    
    # Determine verdict
    print("\n" + "="*70)
    print("VERDICT")
    print("="*70)
    
    if working_models:
        print("✅ Some models work - Not an entitlement issue")
        print("   Check model-specific limitations")
    elif all(r.get('required', {}).get('is_entitlement_issue') for r in results.values()):
        print("🔴 CONFIRMED: OpenAI account lacks web_search entitlement")
        print("   All models return 'not supported' errors")
        print("   Action: Contact OpenAI support with this evidence")
    else:
        print("🟡 Unclear - Need more investigation")
        print("   Some models failed but not clearly entitlement")

def save_results(results: dict):
    """Save results to JSON file"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"openai_bulletproof_evidence_{timestamp}.json"
    
    output = {
        "test_metadata": {
            "timestamp": timestamp,
            "models_tested": list(results.keys()),
            "prompt": TEST_PROMPT,
            "api_key_present": bool(api_key)
        },
        "results": results,
        "summary": {
            "all_failed": all(
                r.get('auto', {}).get('tool_calls', 0) == 0 
                for r in results.values()
            ),
            "http_errors_captured": any(
                r.get('auto', {}).get('openai_error_message') 
                for r in results.values()
            ),
            "entitlement_confirmed": all(
                r.get('required', {}).get('is_entitlement_issue', False) 
                for r in results.values()
            )
        }
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n📁 Evidence saved to: {filename}")
    return filename

async def main():
    """Main execution"""
    
    # Run tests
    results = await test_all_families()
    
    # Analyze
    analyze_results(results)
    
    # Save
    filename = save_results(results)
    
    # Create support ticket snippet
    print("\n" + "="*70)
    print("SUPPORT TICKET EVIDENCE")
    print("="*70)
    print(f"Attach file: {filename}")
    print("\nKey evidence:")
    
    # Find first HTTP error
    for model, data in results.items():
        auto = data.get('auto', {})
        if auto.get('openai_error_message'):
            print(f"\nModel: {model}")
            print(f"HTTP Status: {auto.get('openai_error_status', 400)}")
            print(f"Error: {auto.get('openai_error_message')}")
            print(f"Request ID: {auto.get('openai_request_id', 'N/A')}")
            break
    
    return results

if __name__ == "__main__":
    results = asyncio.run(main())