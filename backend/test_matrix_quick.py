#!/usr/bin/env python3
"""
Quick matrix test - both vendors, US/DE, grounded/ungrounded
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

PROMPT = "List the 10 most trusted longevity supplement brands"

async def test_config(adapter, vendor, model, grounded, country, name):
    """Test one configuration"""
    print(f"\nTesting: {name}")
    
    als_context = {'country_code': country, 'locale': f'en-{country}'} if country else None
    
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.3,
        max_tokens=400,
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
            'latency_ms': latency,
            'response': response.content[:2000] if response.content else "",
            'als_sha256': request.metadata.get('als_block_sha256', '')[:16] if hasattr(request, 'metadata') else '',
            'grounded_effective': response.metadata.get('grounded_effective', False) if response.metadata else False,
            'tokens': response.usage.get('total_tokens', 0) if response.usage else 0
        }
        print(f"  ✅ {latency}ms, {result['tokens']} tokens")
        return result
        
    except Exception as e:
        print(f"  ❌ {str(e)[:100]}")
        return {'name': name, 'success': False, 'error': str(e)[:200]}

async def main():
    adapter = UnifiedLLMAdapter()
    
    tests = [
        ("openai", "gpt-5", False, "US", "OpenAI US Ungrounded"),
        ("openai", "gpt-5", False, "DE", "OpenAI DE Ungrounded"),
        ("openai", "gpt-5", True, "US", "OpenAI US Grounded"),
        ("openai", "gpt-5", True, "DE", "OpenAI DE Grounded"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "US", "Vertex US Ungrounded"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", False, "DE", "Vertex DE Ungrounded"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "US", "Vertex US Grounded"),
        ("vertex", "publishers/google/models/gemini-2.5-pro", True, "DE", "Vertex DE Grounded"),
    ]
    
    results = []
    for vendor, model, grounded, country, name in tests:
        result = await test_config(adapter, vendor, model, grounded, country, name)
        results.append(result)
        await asyncio.sleep(1)
    
    # Generate report
    md = f"""# Full Matrix Test Results

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Prompt**: "{PROMPT}"

## Summary
- Total: {len(results)} tests
- Successful: {sum(1 for r in results if r.get('success'))}

## Results

"""
    
    for r in results:
        md += f"### {r['name']}\n\n"
        
        if r.get('success'):
            md += f"**Status**: ✅ Success\n"
            md += f"**Latency**: {r['latency_ms']}ms\n"
            md += f"**Tokens**: {r['tokens']}\n"
            if r.get('als_sha256'):
                md += f"**ALS SHA256**: {r['als_sha256']}...\n"
            md += f"**Grounded Effective**: {r.get('grounded_effective', False)}\n\n"
            md += f"**Response**:\n```\n{r['response']}\n```\n\n"
        else:
            md += f"**Status**: ❌ Failed\n"
            md += f"**Error**: {r.get('error', 'Unknown')}\n\n"
        
        md += "---\n\n"
    
    filename = f"MATRIX_TEST_RESULTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w') as f:
        f.write(md)
    
    print(f"\n✅ Report saved: {filename}")
    
    # Print summary
    print("\nSummary:")
    for r in results:
        status = "✅" if r.get('success') else "❌"
        print(f"  {status} {r['name']}")

if __name__ == "__main__":
    asyncio.run(main())