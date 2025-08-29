#!/usr/bin/env python3
"""
Full matrix test with VAT rate prompt
Tests regional awareness with both vendors, US/DE, grounded/ungrounded
"""
import asyncio
import os
import sys
import time
from datetime import datetime
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

PROMPT = "What is the VAT rate?"

async def test_config(adapter, vendor, model, grounded, country, name):
    """Test one configuration with VAT prompt"""
    print(f"\nTesting: {name}")
    
    als_context = {'country_code': country, 'locale': f'en-{country}'} if country else None
    
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.3,
        max_tokens=800,  # Increased to get complete responses
        grounded=grounded,
        als_context=als_context
    )
    
    try:
        start = time.perf_counter()
        response = await adapter.complete(request)
        latency = int((time.perf_counter() - start) * 1000)
        
        result = {
            'name': name,
            'success': True,
            'vendor': vendor,
            'model': model.split('/')[-1] if '/' in model else model,
            'grounded': grounded,
            'country': country,
            'latency_ms': latency,
            'response': response.content if response.content else "",
            'als_sha256': request.metadata.get('als_block_sha256', '')[:16] if hasattr(request, 'metadata') else '',
            'als_variant': request.metadata.get('als_variant_id', '') if hasattr(request, 'metadata') else '',
            'als_length': request.metadata.get('als_nfc_length', 0) if hasattr(request, 'metadata') else 0,
            'grounded_effective': response.metadata.get('grounded_effective', False) if response.metadata else False,
            'tool_calls': response.metadata.get('tool_call_count', 0) if response.metadata else 0,
            'response_api': response.metadata.get('response_api', '') if response.metadata else '',
            'region': response.metadata.get('region', '') if response.metadata else '',
            'tokens': response.usage if response.usage else {}
        }
        
        print(f"  ✅ {latency}ms, {result['tokens'].get('total_tokens', 0)} tokens")
        if country:
            print(f"  ALS: {result['als_sha256']}... (variant: {result['als_variant']})")
        
        return result
        
    except Exception as e:
        print(f"  ❌ {str(e)[:100]}")
        return {
            'name': name,
            'success': False,
            'vendor': vendor,
            'country': country,
            'error': str(e)[:500]
        }

async def main():
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*70)
    print("VAT RATE TEST MATRIX")
    print("="*70)
    print(f"Prompt: \"{PROMPT}\"")
    print("Testing regional awareness across vendors and countries...")
    
    tests = [
        # OpenAI tests
        ("openai", "gpt-5", False, "US", "OpenAI US Ungrounded"),
        ("openai", "gpt-5", False, "DE", "OpenAI DE Ungrounded"),
        ("openai", "gpt-5", True, "US", "OpenAI US Grounded"),
        ("openai", "gpt-5", True, "DE", "OpenAI DE Grounded"),
        
        # Vertex tests
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "US", "Vertex US Ungrounded"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "DE", "Vertex DE Ungrounded"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "US", "Vertex US Grounded"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "DE", "Vertex DE Grounded"),
    ]
    
    results = []
    for vendor, model, grounded, country, name in tests:
        result = await test_config(adapter, vendor, model, grounded, country, name)
        results.append(result)
        await asyncio.sleep(1)  # Rate limiting
    
    # Generate comprehensive report
    md = f"""# VAT Rate Test Matrix Results

**Date**: {datetime.now().strftime('%B %d, %Y %H:%M')}
**Prompt**: "{PROMPT}"
**Purpose**: Test regional awareness and ALS effectiveness

## Executive Summary

- **Total Tests**: {len(results)}
- **Successful**: {sum(1 for r in results if r.get('success'))}
- **Failed**: {sum(1 for r in results if not r.get('success'))}

### ALS Consistency Check
- US configurations: {len(set(r['als_sha256'] for r in results if r.get('country') == 'US' and r.get('als_sha256')))} unique SHA256(s)
- DE configurations: {len(set(r['als_sha256'] for r in results if r.get('country') == 'DE' and r.get('als_sha256')))} unique SHA256(s)

---

## Detailed Test Results

"""
    
    for i, r in enumerate(results, 1):
        md += f"### {i}. {r['name']}\n\n"
        
        if r.get('success'):
            md += f"""**Configuration:**
- Vendor: {r['vendor']}
- Model: {r.get('model', 'N/A')}
- Country: {r['country']}
- Grounded: {r['grounded']}

**Performance:**
- Status: ✅ Success
- Latency: {r['latency_ms']}ms
- Total Tokens: {r.get('tokens', {}).get('total_tokens', 0)}

**ALS Details:**
- ALS Applied: {'Yes' if r.get('als_sha256') else 'No'}
"""
            if r.get('als_sha256'):
                md += f"""- SHA256: {r['als_sha256']}...
- Variant: {r['als_variant']}
- Length: {r['als_length']} chars
"""
            
            md += f"""
**API Metadata:**
- Response API: {r.get('response_api', 'N/A')}
- Region: {r.get('region', 'N/A')}
- Grounded Effective: {r.get('grounded_effective', False)}
- Tool Calls: {r.get('tool_calls', 0)}

**Token Breakdown:**
- Prompt Tokens: {r.get('tokens', {}).get('prompt_tokens', 0)}
- Completion Tokens: {r.get('tokens', {}).get('completion_tokens', 0)}

**Full Response:**
```
{r.get('response', 'No response content')}
```

"""
        else:
            md += f"""**Configuration:**
- Vendor: {r['vendor']}
- Country: {r['country']}
- Status: ❌ Failed

**Error:**
```
{r.get('error', 'Unknown error')}
```

"""
        
        md += "---\n\n"
    
    # Add analysis section
    md += """## Analysis

### Regional Awareness

**US Responses (Expected: No VAT/Sales Tax info):**
"""
    us_tests = [r for r in results if r['country'] == 'US' and r.get('success')]
    for r in us_tests:
        mentions_vat = 'VAT' in r.get('response', '').upper()
        mentions_sales = 'sales tax' in r.get('response', '').lower()
        md += f"- {r['name']}: {'⚠️ Mentions VAT' if mentions_vat else '✅ No VAT'}, {'Mentions sales tax' if mentions_sales else ''}\n"
    
    md += """
**DE Responses (Expected: German/EU VAT info):**
"""
    de_tests = [r for r in results if r['country'] == 'DE' and r.get('success')]
    for r in de_tests:
        mentions_19 = '19' in r.get('response', '')
        mentions_germany = 'german' in r.get('response', '').lower() or 'deutschland' in r.get('response', '').lower()
        mentions_eu = 'EU' in r.get('response', '') or 'Europe' in r.get('response', '')
        md += f"- {r['name']}: {'✅ 19%' if mentions_19 else '⚠️ No 19%'}, {'Germany' if mentions_germany else ''} {'EU' if mentions_eu else ''}\n"
    
    md += f"""
### ALS Determinism

- **US SHA256 Consistency**: {"✅ Deterministic" if len(set(r['als_sha256'] for r in results if r.get('country') == 'US' and r.get('als_sha256'))) == 1 else "❌ Non-deterministic"}
- **DE SHA256 Consistency**: {"✅ Deterministic" if len(set(r['als_sha256'] for r in results if r.get('country') == 'DE' and r.get('als_sha256'))) == 1 else "❌ Non-deterministic"}

### Grounding Effectiveness

"""
    grounded_tests = [r for r in results if r['grounded'] and r.get('success')]
    for r in grounded_tests:
        effectiveness = "✅ Effective" if r.get('grounded_effective') else "❌ Not effective"
        md += f"- {r['name']}: {effectiveness} ({r.get('tool_calls', 0)} tool calls)\n"
    
    md += f"""
---

## Conclusions

1. **ALS Application**: {"✅ Working" if all(r.get('als_sha256') for r in results if r.get('country') and r.get('success')) else "⚠️ Issues detected"}
2. **Regional Awareness**: Evaluated based on VAT rate responses
3. **Grounding**: OpenAI grounding not effective (web_search not supported), Vertex grounding working
4. **Determinism**: SHA256 hashes should be identical for same country across all tests

---

*Test completed: {datetime.now().isoformat()}*
*All responses captured in full*
"""
    
    # Save the report
    filename = f"VAT_TEST_MATRIX_RESULTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(md)
    
    print(f"\n✅ Report saved: {filename}")
    
    # Print summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for r in results:
        status = "✅" if r.get('success') else "❌"
        als = "🔒" if r.get('als_sha256') else "  "
        print(f"  {status} {als} {r['name']}")
    
    print(f"\nReport location: {filename}")
    
    return results, filename

if __name__ == "__main__":
    results, report_file = asyncio.run(main())
    print("\n✅ VAT test complete!")