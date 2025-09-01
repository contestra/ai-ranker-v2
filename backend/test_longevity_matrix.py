#!/usr/bin/env python3
"""
Comprehensive longevity news test across all configurations  
Tests: OpenAI + Vertex, DE + US, grounded/ungrounded, with/without ALS
"""

import os
import sys

# MUST set env vars BEFORE importing any app modules
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATIONS_EXTRACTOR_ENABLE'] = 'true'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'true'  # Enable to see unlinked sources
os.environ['DEBUG_GROUNDING'] = 'false'  # Disable debug logs for cleaner output

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test configuration
PROMPT = "what was the top longevity and life-extension news during August, 2025"
TEMPLATE_ID = "longevity-matrix-test"
ORG_ID = "test-org"

# Test matrix: All combinations
TEST_CONFIGURATIONS = [
    # OpenAI - USA
    {"vendor": "openai", "model": "gpt-5", "country": "US", "grounded": True, "als": True},
    {"vendor": "openai", "model": "gpt-5", "country": "US", "grounded": True, "als": False},
    {"vendor": "openai", "model": "gpt-5-chat-latest", "country": "US", "grounded": False, "als": True},
    {"vendor": "openai", "model": "gpt-5-chat-latest", "country": "US", "grounded": False, "als": False},
    
    # OpenAI - Germany
    {"vendor": "openai", "model": "gpt-5", "country": "DE", "grounded": True, "als": True},
    {"vendor": "openai", "model": "gpt-5", "country": "DE", "grounded": True, "als": False},
    {"vendor": "openai", "model": "gpt-5-chat-latest", "country": "DE", "grounded": False, "als": True},
    {"vendor": "openai", "model": "gpt-5-chat-latest", "country": "DE", "grounded": False, "als": False},
    
    # Vertex/Gemini - USA
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": True, "als": True},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": True, "als": False},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": False, "als": True},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": False, "als": False},
    
    # Vertex/Gemini - Germany
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "DE", "grounded": True, "als": True},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "DE", "grounded": True, "als": False},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "DE", "grounded": False, "als": True},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "DE", "grounded": False, "als": False},
]

def create_request(config: Dict) -> LLMRequest:
    """Create an LLM request from configuration."""
    messages = [
        {"role": "user", "content": PROMPT}
    ]
    
    request = LLMRequest(
        vendor=config['vendor'],
        messages=messages,
        model=config['model'],
        grounded=config['grounded'],
        max_tokens=1000,
        temperature=0.7
    )
    
    # Initialize metadata
    request.meta = {
        'test_country': config['country'],
        'test_als': config['als'],
        'test_config': config
    }
    
    # Add grounding mode for grounded requests
    if config['grounded']:
        request.meta['grounding_mode'] = 'AUTO'
    
    # Add ALS context if requested
    if config['als']:
        country = config['country']
        timezone = 'America/New_York' if country == 'US' else 'Europe/Berlin'
        locale = f"{country.lower()}-{country}"
        
        als_block = f"""--- AMBIENT LOCATION SIGNALS ---
Country: {country}
Locale: {locale}
Time Zone: {timezone}
Date: September 1, 2025
"""
        request.als_context = ALSContext(
            country_code=country,
            locale=locale,
            als_block=als_block
        )
    
    request.template_id = TEMPLATE_ID
    request.org_id = ORG_ID
    
    return request

async def run_single_test(adapter: UnifiedLLMAdapter, config: Dict) -> Dict:
    """Run a single test configuration."""
    # Generate descriptive name
    config_name = f"{config['vendor']}_{config['model'].replace('-', '_').replace('.', '_')}_{config['country']}_{'grounded' if config['grounded'] else 'ungrounded'}_{'ALS' if config['als'] else 'noALS'}"
    
    print(f"\n{'='*80}")
    print(f"Testing: {config_name}")
    print(f"Config: {json.dumps(config, indent=2)}")
    print("-" * 80)
    
    result = {
        'config': config,
        'config_name': config_name,
        'success': False,
        'error': None,
        'response': None,
        'metadata': {},
        'timing': {}
    }
    
    try:
        # Create request
        request = create_request(config)
        
        # Record start time
        start_time = time.time()
        
        # Execute request
        response = await adapter.complete(request)
        
        # Record end time
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        
        # Extract results
        result['success'] = True
        result['timing'] = {
            'start': start_time,
            'end': end_time,
            'latency_ms': latency_ms
        }
        
        # Extract response content
        result['response'] = {
            'content': response.content if response.content else "",
            'length': len(response.content) if response.content else 0,
            'truncated': response.content[:500] + "..." if response.content and len(response.content) > 500 else response.content
        }
        
        # Extract metadata
        meta = response.metadata or {}
        result['metadata'] = {
            'grounded_effective': response.grounded_effective,
            'citations_count': meta.get('citations_count', 0),
            'anchored_citations': meta.get('anchored_citations_count', 0),
            'unlinked_sources': meta.get('unlinked_sources_count', 0),
            'tool_calls': meta.get('tool_call_count', 0),
            'response_api': meta.get('response_api'),
            'model_adjusted': meta.get('model_adjusted_for_grounding', False),
            'original_model': meta.get('original_model'),
            'feature_flags': meta.get('feature_flags', {}),
            'runtime_flags': meta.get('runtime_flags', {}),
            'why_not_grounded': meta.get('why_not_grounded'),
            'extraction_path': meta.get('extraction_path')
        }
        
        # Extract usage
        result['usage'] = response.usage if response.usage else {}
        
        # Print summary
        print(f"✅ SUCCESS in {latency_ms:.0f}ms")
        print(f"Response length: {result['response']['length']} chars")
        print(f"Grounding: requested={config['grounded']}, effective={result['metadata']['grounded_effective']}")
        print(f"Citations: {result['metadata']['citations_count']} total")
        if result['metadata']['response_api']:
            print(f"Response API: {result['metadata']['response_api']}")
        if result['metadata']['tool_calls'] > 0:
            print(f"Tool calls: {result['metadata']['tool_calls']}")
        
        # Print snippet of response
        if result['response']['content']:
            snippet = result['response']['content'][:200]
            if len(snippet) < len(result['response']['content']):
                snippet += "..."
            print(f"\nResponse snippet: {snippet}")
        
    except Exception as e:
        result['success'] = False
        result['error'] = str(e)
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    return result

async def run_all_tests() -> List[Dict]:
    """Run all test configurations."""
    print("=" * 80)
    print("LONGEVITY NEWS TEST MATRIX")
    print(f"Prompt: \"{PROMPT}\"")
    print(f"Starting at: {datetime.now().isoformat()}")
    print(f"Total configurations: {len(TEST_CONFIGURATIONS)}")
    print("=" * 80)
    
    # Initialize adapter
    adapter = UnifiedLLMAdapter()
    
    # Run all tests
    results = []
    for i, config in enumerate(TEST_CONFIGURATIONS, 1):
        print(f"\n[{i}/{len(TEST_CONFIGURATIONS)}] Running test...")
        result = await run_single_test(adapter, config)
        results.append(result)
        
        # Small delay between tests to avoid rate limits
        if i < len(TEST_CONFIGURATIONS):
            await asyncio.sleep(2)
    
    return results

def generate_markdown_report(results: List[Dict]) -> str:
    """Generate a comprehensive markdown report."""
    timestamp = datetime.now().isoformat()
    
    # Calculate statistics
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r['success'])
    failed_tests = total_tests - successful_tests
    
    # Group by vendor and country
    openai_us = [r for r in results if r['config']['vendor'] == 'openai' and r['config']['country'] == 'US']
    openai_de = [r for r in results if r['config']['vendor'] == 'openai' and r['config']['country'] == 'DE']
    vertex_us = [r for r in results if r['config']['vendor'] == 'vertex' and r['config']['country'] == 'US']
    vertex_de = [r for r in results if r['config']['vendor'] == 'vertex' and r['config']['country'] == 'DE']
    
    report = f"""# Longevity News Test Matrix Report

**Generated:** {timestamp}  
**Prompt:** "{PROMPT}"

## Executive Summary

- **Total Tests:** {total_tests}
- **Successful:** {successful_tests} ({successful_tests/total_tests*100:.1f}%)
- **Failed:** {failed_tests} ({failed_tests/total_tests*100:.1f}%)

## Results by Configuration

### OpenAI - United States ({len(openai_us)} tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
"""
    
    for r in openai_us:
        status = "✅" if r['success'] else "❌"
        latency = f"{r['timing']['latency_ms']:.0f}ms" if r.get('timing') else "N/A"
        length = r['response']['length'] if r.get('response') else 0
        grounded_eff = "✅" if r['metadata'].get('grounded_effective') else "❌"
        citations = r['metadata'].get('citations_count', 0) if r.get('metadata') else 0
        als = "✅" if r['config']['als'] else "❌"
        grounded = "Yes" if r['config']['grounded'] else "No"
        
        report += f"| {r['config']['model']} (G:{grounded}) | {status} | {latency} | {length} | {grounded_eff} | {citations} | {als} |\n"
    
    report += f"""

### OpenAI - Germany ({len(openai_de)} tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
"""
    
    for r in openai_de:
        status = "✅" if r['success'] else "❌"
        latency = f"{r['timing']['latency_ms']:.0f}ms" if r.get('timing') else "N/A"
        length = r['response']['length'] if r.get('response') else 0
        grounded_eff = "✅" if r['metadata'].get('grounded_effective') else "❌"
        citations = r['metadata'].get('citations_count', 0) if r.get('metadata') else 0
        als = "✅" if r['config']['als'] else "❌"
        grounded = "Yes" if r['config']['grounded'] else "No"
        
        report += f"| {r['config']['model']} (G:{grounded}) | {status} | {latency} | {length} | {grounded_eff} | {citations} | {als} |\n"
    
    report += f"""

### Vertex/Gemini - United States ({len(vertex_us)} tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
"""
    
    for r in vertex_us:
        status = "✅" if r['success'] else "❌"
        latency = f"{r['timing']['latency_ms']:.0f}ms" if r.get('timing') else "N/A"
        length = r['response']['length'] if r.get('response') else 0
        grounded_eff = "✅" if r['metadata'].get('grounded_effective') else "❌"
        citations = r['metadata'].get('citations_count', 0) if r.get('metadata') else 0
        als = "✅" if r['config']['als'] else "❌"
        grounded = "Yes" if r['config']['grounded'] else "No"
        
        report += f"| {r['config']['model']} (G:{grounded}) | {status} | {latency} | {length} | {grounded_eff} | {citations} | {als} |\n"
    
    report += f"""

### Vertex/Gemini - Germany ({len(vertex_de)} tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
"""
    
    for r in vertex_de:
        status = "✅" if r['success'] else "❌"
        latency = f"{r['timing']['latency_ms']:.0f}ms" if r.get('timing') else "N/A"
        length = r['response']['length'] if r.get('response') else 0
        grounded_eff = "✅" if r['metadata'].get('grounded_effective') else "❌"
        citations = r['metadata'].get('citations_count', 0) if r.get('metadata') else 0
        als = "✅" if r['config']['als'] else "❌"
        grounded = "Yes" if r['config']['grounded'] else "No"
        
        report += f"| {r['config']['model']} (G:{grounded}) | {status} | {latency} | {length} | {grounded_eff} | {citations} | {als} |\n"
    
    # Add analysis sections
    report += """

## Analysis

### Grounding Effectiveness
"""
    
    grounded_tests = [r for r in results if r['config']['grounded'] and r['success']]
    if grounded_tests:
        grounded_effective = sum(1 for r in grounded_tests if r['metadata'].get('grounded_effective'))
        report += f"- Grounded requests: {len(grounded_tests)}\n"
        report += f"- Actually grounded: {grounded_effective} ({grounded_effective/len(grounded_tests)*100:.1f}%)\n"
    
    report += """

### ALS Impact
"""
    
    als_tests = [r for r in results if r['config']['als'] and r['success']]
    no_als_tests = [r for r in results if not r['config']['als'] and r['success']]
    
    if als_tests and no_als_tests:
        als_avg_length = sum(r['response']['length'] for r in als_tests) / len(als_tests)
        no_als_avg_length = sum(r['response']['length'] for r in no_als_tests) / len(no_als_tests)
        report += f"- Average response with ALS: {als_avg_length:.0f} chars\n"
        report += f"- Average response without ALS: {no_als_avg_length:.0f} chars\n"
    
    report += """

### Citation Extraction
"""
    
    grounded_with_citations = [r for r in results if r['config']['grounded'] and r['success'] and r['metadata'].get('citations_count', 0) > 0]
    report += f"- Grounded tests with citations: {len(grounded_with_citations)}\n"
    if grounded_with_citations:
        avg_citations = sum(r['metadata']['citations_count'] for r in grounded_with_citations) / len(grounded_with_citations)
        report += f"- Average citations per grounded response: {avg_citations:.1f}\n"
    
    # Add errors section if any
    failed = [r for r in results if not r['success']]
    if failed:
        report += """

## Errors and Failures

"""
        for r in failed:
            report += f"### {r['config_name']}\n"
            report += f"**Error:** {r['error']}\n\n"
    
    # Add response samples
    report += """

## Response Samples

"""
    
    # Sample one from each major configuration
    samples = [
        ("OpenAI US Grounded with ALS", next((r for r in results if r['config']['vendor'] == 'openai' and r['config']['country'] == 'US' and r['config']['grounded'] and r['config']['als'] and r['success']), None)),
        ("OpenAI DE Grounded with ALS", next((r for r in results if r['config']['vendor'] == 'openai' and r['config']['country'] == 'DE' and r['config']['grounded'] and r['config']['als'] and r['success']), None)),
        ("Vertex US Grounded with ALS", next((r for r in results if r['config']['vendor'] == 'vertex' and r['config']['country'] == 'US' and r['config']['grounded'] and r['config']['als'] and r['success']), None)),
        ("Vertex DE Grounded with ALS", next((r for r in results if r['config']['vendor'] == 'vertex' and r['config']['country'] == 'DE' and r['config']['grounded'] and r['config']['als'] and r['success']), None)),
    ]
    
    for label, result in samples:
        if result and result.get('response'):
            report += f"### {label}\n\n"
            report += "```\n"
            report += result['response'].get('truncated', 'No response')
            report += "\n```\n\n"
    
    # Add raw data
    report += """

## Raw Test Data

<details>
<summary>Click to expand JSON data</summary>

```json
"""
    
    # Prepare clean JSON (remove non-serializable items)
    clean_results = []
    for r in results:
        clean_result = {
            'config': r['config'],
            'config_name': r['config_name'],
            'success': r['success'],
            'error': r['error'],
            'response_length': r['response']['length'] if r.get('response') else 0,
            'metadata': r.get('metadata', {}),
            'usage': r.get('usage', {}),
            'latency_ms': r['timing']['latency_ms'] if r.get('timing') else None
        }
        clean_results.append(clean_result)
    
    report += json.dumps({
        'timestamp': timestamp,
        'prompt': PROMPT,
        'results': clean_results
    }, indent=2)
    
    report += """
```

</details>

---
*Generated by Longevity News Test Matrix*
"""
    
    return report

async def main():
    """Main test execution."""
    # Run all tests
    results = await run_all_tests()
    
    # Generate report
    report = generate_markdown_report(results)
    
    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"LONGEVITY_MATRIX_REPORT_{timestamp}.md"
    
    with open(report_file, 'w') as f:
        f.write(report)
    
    print("\n" + "=" * 80)
    print("TEST MATRIX COMPLETE")
    print("=" * 80)
    print(f"Report saved to: {report_file}")
    
    # Also save raw JSON data
    json_file = f"longevity_matrix_results_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'prompt': PROMPT,
            'results': results
        }, f, indent=2, default=str)
    print(f"Raw data saved to: {json_file}")
    
    # Print summary
    total = len(results)
    successful = sum(1 for r in results if r['success'])
    print(f"\nSummary: {successful}/{total} tests passed ({successful/total*100:.1f}%)")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())