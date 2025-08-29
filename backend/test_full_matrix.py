#!/usr/bin/env python3
"""
Full test matrix: Both vendors, US/DE, grounded/ungrounded
Capture complete responses for documentation
"""
import asyncio
import os
import sys
import json
import time
from datetime import datetime
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"
os.environ["ALLOWED_VERTEX_MODELS"] = "publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash"
os.environ["ALLOWED_OPENAI_MODELS"] = "gpt-5,gpt-5-chat-latest"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

# Test prompt - same for all tests
PROMPT = "List the 10 most trusted longevity supplement brands"

async def run_single_test(adapter, vendor, model, grounded, country, test_name):
    """Run a single test configuration and capture full response"""
    
    print(f"\nRunning: {test_name}...")
    
    # Build request with ALS context if country specified
    als_context = {'country_code': country, 'locale': f'en-{country}'} if country else None
    
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.3 if vendor == "openai" else 0.7,
        max_tokens=500,
        grounded=grounded,
        als_context=als_context
    )
    
    try:
        start = time.perf_counter()
        response = await adapter.complete(request)
        latency_ms = int((time.perf_counter() - start) * 1000)
        
        print(f"  ✅ Success in {latency_ms}ms")
        
        # Capture full result
        result = {
            'test_name': test_name,
            'success': True,
            'vendor': vendor,
            'model': model,
            'grounded': grounded,
            'country': country,
            'latency_ms': latency_ms,
            'full_response': response.content if response.content else "",
            'metadata': {}
        }
        
        # Capture ALS metadata
        if hasattr(request, 'metadata') and request.metadata.get('als_present'):
            result['als_applied'] = True
            result['als_sha256'] = request.metadata.get('als_block_sha256', '')
            result['als_variant'] = request.metadata.get('als_variant_id', '')
            result['als_length'] = request.metadata.get('als_nfc_length', 0)
        else:
            result['als_applied'] = False
        
        # Capture response metadata
        if hasattr(response, 'metadata') and response.metadata:
            result['metadata'] = {
                'grounded_effective': response.metadata.get('grounded_effective', False),
                'tool_call_count': response.metadata.get('tool_call_count', 0),
                'response_api': response.metadata.get('response_api', ''),
                'region': response.metadata.get('region', ''),
                'provider_api_version': response.metadata.get('provider_api_version', '')
            }
        
        # Capture token usage
        if response.usage:
            result['token_usage'] = {
                'prompt': response.usage.get('prompt_tokens', 0),
                'completion': response.usage.get('completion_tokens', 0),
                'total': response.usage.get('total_tokens', 0)
            }
        
        return result
        
    except Exception as e:
        print(f"  ❌ Failed: {str(e)[:100]}")
        return {
            'test_name': test_name,
            'success': False,
            'vendor': vendor,
            'model': model,
            'grounded': grounded,
            'country': country,
            'error': str(e)[:500],
            'full_response': None
        }

async def main():
    """Run full test matrix"""
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*70)
    print("FULL TEST MATRIX - COMPLETE RESPONSES")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Prompt: {PROMPT}")
    
    # Define complete test matrix
    # Format: (vendor, model, grounded, country, test_name)
    test_matrix = [
        # OpenAI tests
        ("openai", "gpt-5", False, "US", "OpenAI Ungrounded US"),
        ("openai", "gpt-5", False, "DE", "OpenAI Ungrounded DE"),
        ("openai", "gpt-5", True, "US", "OpenAI Grounded US"),
        ("openai", "gpt-5", True, "DE", "OpenAI Grounded DE"),
        
        # Vertex tests
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "US", "Vertex Ungrounded US"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "DE", "Vertex Ungrounded DE"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "US", "Vertex Grounded US"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "DE", "Vertex Grounded DE"),
    ]
    
    results = []
    
    # Run all tests
    for vendor, model, grounded, country, name in test_matrix:
        result = await run_single_test(adapter, vendor, model, grounded, country, name)
        results.append(result)
        await asyncio.sleep(2)  # Rate limiting
    
    # Generate markdown report
    print("\n" + "="*70)
    print("Generating detailed report...")
    
    md_content = f"""# Complete Test Matrix Results

**Date**: {datetime.now().strftime('%B %d, %Y %H:%M')}
**Prompt**: "{PROMPT}"
**Test Configurations**: 8 (2 vendors × 2 countries × 2 grounding modes)

---

## Summary

Total Tests: {len(results)}
Successful: {sum(1 for r in results if r['success'])}
Failed: {sum(1 for r in results if not r['success'])}

---

## Detailed Results by Configuration

"""
    
    # Add each test result
    for i, result in enumerate(results, 1):
        md_content += f"""### {i}. {result['test_name']}

**Configuration:**
- Vendor: {result['vendor']}
- Model: {result['model'].split('/')[-1] if '/' in result['model'] else result['model']}
- Grounded: {result['grounded']}
- Country: {result['country']}
- Status: {'✅ Success' if result['success'] else '❌ Failed'}

"""
        
        if result['success']:
            # Add metrics
            md_content += f"""**Metrics:**
- Latency: {result.get('latency_ms', 'N/A')}ms
"""
            
            # Add ALS info if present
            if result.get('als_applied'):
                md_content += f"""- ALS Applied: Yes
- ALS SHA256: {result.get('als_sha256', '')[:16]}...
- ALS Variant: {result.get('als_variant', '')}
- ALS Length: {result.get('als_length', 0)} chars
"""
            else:
                md_content += "- ALS Applied: No\n"
            
            # Add metadata
            if result.get('metadata'):
                meta = result['metadata']
                md_content += f"""
**Metadata:**
- Grounded Effective: {meta.get('grounded_effective', False)}
- Tool Calls: {meta.get('tool_call_count', 0)}
- Response API: {meta.get('response_api', 'N/A')}
- Region: {meta.get('region', 'N/A')}
"""
            
            # Add token usage
            if result.get('token_usage'):
                tokens = result['token_usage']
                md_content += f"""
**Token Usage:**
- Prompt: {tokens.get('prompt', 0)}
- Completion: {tokens.get('completion', 0)}
- Total: {tokens.get('total', 0)}
"""
            
            # Add full response
            md_content += f"""
**Full Response:**

```
{result.get('full_response', 'No response content')}
```

"""
        else:
            # Add error info
            md_content += f"""**Error:**
```
{result.get('error', 'Unknown error')}
```

"""
        
        md_content += "---\n\n"
    
    # Add analysis section
    md_content += """## Analysis

### ALS Application
"""
    
    als_results = [r for r in results if r.get('als_applied')]
    if als_results:
        md_content += f"- ALS successfully applied in {len(als_results)}/{len(results)} tests\n"
        
        # Check SHA256 consistency by country
        us_shas = set(r['als_sha256'] for r in als_results if r['country'] == 'US')
        de_shas = set(r['als_sha256'] for r in als_results if r['country'] == 'DE')
        
        md_content += f"- US SHA256 consistency: {len(us_shas)} unique hash(es)\n"
        md_content += f"- DE SHA256 consistency: {len(de_shas)} unique hash(es)\n"
    
    md_content += """
### Grounding Effectiveness
"""
    
    grounded_tests = [r for r in results if r['grounded'] and r['success']]
    if grounded_tests:
        effective = sum(1 for r in grounded_tests if r.get('metadata', {}).get('grounded_effective'))
        md_content += f"- Grounding effective in {effective}/{len(grounded_tests)} grounded tests\n"
    
    md_content += """
### Response Quality
"""
    
    # Check if responses contain brand lists
    responses_with_brands = sum(1 for r in results 
                                if r['success'] and r.get('full_response') 
                                and ('1.' in r['full_response'] or '1)' in r['full_response']))
    md_content += f"- Responses with numbered lists: {responses_with_brands}/{len([r for r in results if r['success']])}\n"
    
    md_content += f"""
---

*Test completed: {datetime.now().isoformat()}*
"""
    
    # Save the report
    filename = f"FULL_MATRIX_RESULTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"Report saved to: {filename}")
    
    # Also save raw JSON for analysis
    json_filename = f"full_matrix_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Raw data saved to: {json_filename}")
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    successful = sum(1 for r in results if r['success'])
    print(f"Success rate: {successful}/{len(results)}")
    
    for result in results:
        status = "✅" if result['success'] else "❌"
        als = "🔒" if result.get('als_applied') else "  "
        print(f"{status} {als} {result['test_name']}")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(main())
    print("\nTest complete!")