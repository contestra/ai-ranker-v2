#!/usr/bin/env python3
"""
End-to-End Longevity Test Suite
Tests citation extraction, grounding, and telemetry across all model configurations.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import traceback

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test configuration
LONGEVITY_PROMPT = "today is 31st August, 2025 - tell me the top longevity news of August"
TEMPLATE_ID = "e2e-longevity-test"
ORG_ID = "test-org"

# Comprehensive test matrix
TEST_MATRIX = [
    # OpenAI configurations
    {"vendor": "openai", "model": "gpt-5", "country": "US", "grounded": True, "als": True, "mode": "AUTO"},
    {"vendor": "openai", "model": "gpt-5", "country": "US", "grounded": True, "als": False, "mode": "AUTO"},
    {"vendor": "openai", "model": "gpt-5", "country": "DE", "grounded": True, "als": True, "mode": "AUTO"},
    {"vendor": "openai", "model": "gpt-5", "country": "US", "grounded": True, "als": True, "mode": "REQUIRED"},
    {"vendor": "openai", "model": "gpt-5-chat-latest", "country": "US", "grounded": False, "als": True, "mode": None},
    {"vendor": "openai", "model": "gpt-5-chat-latest", "country": "US", "grounded": False, "als": False, "mode": None},
    
    # Vertex/Gemini configurations
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": True, "als": True, "mode": "AUTO"},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": True, "als": False, "mode": "AUTO"},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "DE", "grounded": True, "als": True, "mode": "AUTO"},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": True, "als": True, "mode": "REQUIRED"},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": False, "als": True, "mode": None},
    {"vendor": "vertex", "model": "gemini-2.5-pro", "country": "US", "grounded": False, "als": False, "mode": None},
]

class TestResult:
    """Container for test results."""
    def __init__(self, config: Dict):
        self.config = config
        self.config_name = self._generate_name(config)
        self.start_time = None
        self.end_time = None
        self.latency_ms = None
        self.success = False
        self.error = None
        self.response_length = 0
        self.citations_count = 0
        self.anchored_citations = 0
        self.unlinked_sources = 0
        self.grounded_effective = False
        self.response_api = None
        self.model_adjusted = False
        self.original_model = None
        self.why_not_grounded = None
        self.tool_calls = 0
        self.feature_flags = {}
        self.runtime_flags = {}
        
    def _generate_name(self, config: Dict) -> str:
        """Generate a descriptive name for this test configuration."""
        parts = [
            config['vendor'],
            config['model'].replace('-', '_'),
            config['country'],
            'grounded' if config['grounded'] else 'ungrounded',
            'ALS' if config['als'] else 'noALS'
        ]
        if config.get('mode'):
            parts.append(config['mode'])
        return '_'.join(parts)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'config_name': self.config_name,
            'config': self.config,
            'latency_ms': self.latency_ms,
            'success': self.success,
            'error': self.error,
            'response_length': self.response_length,
            'citations': {
                'total': self.citations_count,
                'anchored': self.anchored_citations,
                'unlinked': self.unlinked_sources
            },
            'grounding': {
                'requested': self.config['grounded'],
                'effective': self.grounded_effective,
                'mode': self.config.get('mode'),
                'why_not_grounded': self.why_not_grounded,
                'response_api': self.response_api
            },
            'model': {
                'requested': self.config['model'],
                'adjusted': self.model_adjusted,
                'original': self.original_model
            },
            'tool_calls': self.tool_calls,
            'feature_flags': self.feature_flags,
            'runtime_flags': self.runtime_flags
        }

def create_request(config: Dict) -> LLMRequest:
    """Create an LLM request from test configuration."""
    messages = [
        {"role": "user", "content": LONGEVITY_PROMPT}
    ]
    
    request = LLMRequest(
        vendor=config['vendor'],
        messages=messages,
        model=config['model'],
        grounded=config['grounded'],
        max_tokens=800,
        temperature=0.7
    )
    
    # Initialize metadata
    request.meta = {
        'test_country': config['country'],
        'test_als': config['als'],
        'test_config': config
    }
    
    # Add grounding mode if specified
    if config['grounded'] and config.get('mode'):
        request.meta['grounding_mode'] = config['mode']
    
    # Add ALS context if requested
    if config['als']:
        country = config['country']
        als_block = f"""--- AMBIENT LOCATION SIGNALS ---
Country: {country}
Locale: {country.lower()}-{country}
Time Zone: {'America/New_York' if country == 'US' else 'Europe/Berlin'}
"""
        request.als_context = ALSContext(
            country_code=country,
            locale=f"{country.lower()}-{country}",
            als_block=als_block
        )
    
    request.template_id = TEMPLATE_ID
    request.org_id = ORG_ID
    
    return request

async def run_single_test(adapter: UnifiedLLMAdapter, config: Dict) -> TestResult:
    """Run a single test configuration."""
    result = TestResult(config)
    
    print(f"\n{'='*80}")
    print(f"Testing: {result.config_name}")
    print(f"Config: {json.dumps(config, indent=2)}")
    print("-" * 80)
    
    try:
        # Create request
        request = create_request(config)
        
        # Record start time
        result.start_time = time.time()
        
        # Execute request
        response = await adapter.complete(request)
        
        # Record end time
        result.end_time = time.time()
        result.latency_ms = (result.end_time - result.start_time) * 1000
        
        # Extract results
        result.success = True
        result.response_length = len(response.content) if response.content else 0
        
        # Extract metadata
        meta = response.metadata or {}
        result.citations_count = meta.get('citations_count', 0)
        result.anchored_citations = meta.get('anchored_citations_count', 0)
        result.unlinked_sources = meta.get('unlinked_sources_count', 0)
        result.grounded_effective = response.grounded_effective
        result.response_api = meta.get('response_api')
        result.model_adjusted = meta.get('model_adjusted_for_grounding', False)
        result.original_model = meta.get('original_model')
        result.why_not_grounded = meta.get('why_not_grounded')
        result.tool_calls = meta.get('tool_call_count', 0)
        result.feature_flags = meta.get('feature_flags', {})
        result.runtime_flags = meta.get('runtime_flags', {})
        
        # Print summary
        print(f"✅ SUCCESS in {result.latency_ms:.0f}ms")
        print(f"Response length: {result.response_length} chars")
        print(f"Citations: {result.citations_count} total ({result.anchored_citations} anchored, {result.unlinked_sources} unlinked)")
        print(f"Grounding: requested={config['grounded']}, effective={result.grounded_effective}")
        if result.response_api:
            print(f"Response API: {result.response_api}")
        if result.model_adjusted:
            print(f"Model adjusted: {result.original_model} → {config['model']}")
        if result.tool_calls > 0:
            print(f"Tool calls: {result.tool_calls}")
        
    except Exception as e:
        result.end_time = time.time()
        result.latency_ms = (result.end_time - result.start_time) * 1000 if result.start_time else 0
        result.success = False
        result.error = str(e)
        print(f"❌ FAILED: {e}")
        traceback.print_exc()
    
    return result

async def run_all_tests() -> List[TestResult]:
    """Run all test configurations."""
    print("=" * 80)
    print("END-TO-END LONGEVITY TEST SUITE")
    print(f"Starting at: {datetime.now().isoformat()}")
    print(f"Total configurations: {len(TEST_MATRIX)}")
    print("=" * 80)
    
    # Initialize adapter
    adapter = UnifiedLLMAdapter()
    
    # Run all tests
    results = []
    for i, config in enumerate(TEST_MATRIX, 1):
        print(f"\n[{i}/{len(TEST_MATRIX)}] Running test...")
        result = await run_single_test(adapter, config)
        results.append(result)
        
        # Small delay between tests to avoid rate limits
        await asyncio.sleep(2)
    
    return results

def generate_markdown_report(results: List[TestResult]) -> str:
    """Generate a comprehensive markdown report."""
    timestamp = datetime.now().isoformat()
    
    # Calculate statistics
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r.success)
    failed_tests = total_tests - successful_tests
    avg_latency = sum(r.latency_ms for r in results if r.latency_ms) / len(results)
    
    # Group by vendor
    openai_results = [r for r in results if r.config['vendor'] == 'openai']
    vertex_results = [r for r in results if r.config['vendor'] == 'vertex']
    
    # Grounding statistics
    grounded_requested = [r for r in results if r.config['grounded']]
    grounded_effective = [r for r in grounded_requested if r.grounded_effective]
    grounding_success_rate = len(grounded_effective) / len(grounded_requested) * 100 if grounded_requested else 0
    
    # Citation statistics
    tests_with_citations = [r for r in results if r.citations_count > 0]
    avg_citations = sum(r.citations_count for r in tests_with_citations) / len(tests_with_citations) if tests_with_citations else 0
    
    report = f"""# End-to-End Longevity Test Report

**Generated:** {timestamp}  
**Test Prompt:** "{LONGEVITY_PROMPT}"

## Executive Summary

- **Total Tests:** {total_tests}
- **Successful:** {successful_tests} ({successful_tests/total_tests*100:.1f}%)
- **Failed:** {failed_tests} ({failed_tests/total_tests*100:.1f}%)
- **Average Latency:** {avg_latency:.0f}ms
- **Grounding Success Rate:** {grounding_success_rate:.1f}%
- **Tests with Citations:** {len(tests_with_citations)} ({len(tests_with_citations)/total_tests*100:.1f}%)
- **Average Citations (when present):** {avg_citations:.1f}

## Detailed Results by Configuration

### OpenAI Results ({len(openai_results)} tests)

| Configuration | Status | Latency | Citations | Grounding | Response API | Model |
|--------------|--------|---------|-----------|-----------|--------------|-------|
"""
    
    for r in openai_results:
        status = "✅" if r.success else "❌"
        citations = f"{r.citations_count} ({r.anchored_citations}+{r.unlinked_sources})"
        grounding = "✅" if r.grounded_effective else ("❌" if r.config['grounded'] else "N/A")
        model_info = f"{r.config['model']}"
        if r.model_adjusted:
            model_info += f" (adjusted from {r.original_model})"
        
        report += f"| {r.config_name} | {status} | {r.latency_ms:.0f}ms | {citations} | {grounding} | {r.response_api or 'N/A'} | {model_info} |\n"
    
    report += f"""

### Vertex/Gemini Results ({len(vertex_results)} tests)

| Configuration | Status | Latency | Citations | Grounding | Response API | Tool Calls |
|--------------|--------|---------|-----------|-----------|--------------|------------|
"""
    
    for r in vertex_results:
        status = "✅" if r.success else "❌"
        citations = f"{r.citations_count} ({r.anchored_citations}+{r.unlinked_sources})"
        grounding = "✅" if r.grounded_effective else ("❌" if r.config['grounded'] else "N/A")
        
        report += f"| {r.config_name} | {status} | {r.latency_ms:.0f}ms | {citations} | {grounding} | {r.response_api or 'N/A'} | {r.tool_calls} |\n"
    
    # Add grounding mode analysis
    report += """

## Grounding Mode Analysis

### AUTO Mode Performance
"""
    auto_tests = [r for r in results if r.config.get('mode') == 'AUTO']
    if auto_tests:
        auto_success = sum(1 for r in auto_tests if r.grounded_effective)
        report += f"- Tests: {len(auto_tests)}\n"
        report += f"- Grounded Successfully: {auto_success} ({auto_success/len(auto_tests)*100:.1f}%)\n"
        report += f"- Average Citations: {sum(r.citations_count for r in auto_tests)/len(auto_tests):.1f}\n"
    
    report += """

### REQUIRED Mode Performance
"""
    required_tests = [r for r in results if r.config.get('mode') == 'REQUIRED']
    if required_tests:
        required_success = sum(1 for r in required_tests if r.grounded_effective)
        required_failures = [r for r in required_tests if not r.grounded_effective and r.why_not_grounded]
        report += f"- Tests: {len(required_tests)}\n"
        report += f"- Grounded Successfully: {required_success} ({required_success/len(required_tests)*100:.1f}%)\n"
        if required_failures:
            report += f"- Failure Reasons:\n"
            for r in required_failures:
                report += f"  - {r.config_name}: {r.why_not_grounded}\n"
    
    # Add telemetry verification
    report += """

## Telemetry Contract Verification

### Response API Labels
"""
    for vendor in ['openai', 'vertex']:
        vendor_tests = [r for r in results if r.config['vendor'] == vendor and r.config['grounded']]
        if vendor_tests:
            report += f"\n**{vendor.title()}:**\n"
            api_counts = {}
            for r in vendor_tests:
                api = r.response_api or 'None'
                api_counts[api] = api_counts.get(api, 0) + 1
            for api, count in api_counts.items():
                report += f"- {api}: {count} tests\n"
    
    # Add feature flags analysis
    report += """

## Feature Flags & A/B Testing

### Active Feature Flags
"""
    all_flags = {}
    for r in results:
        for flag, value in r.feature_flags.items():
            if flag not in all_flags:
                all_flags[flag] = {}
            val_str = str(value)
            all_flags[flag][val_str] = all_flags[flag].get(val_str, 0) + 1
    
    for flag, values in all_flags.items():
        report += f"\n**{flag}:**\n"
        for val, count in values.items():
            report += f"- {val}: {count} tests ({count/total_tests*100:.1f}%)\n"
    
    # Add errors section if any
    failed = [r for r in results if not r.success]
    if failed:
        report += """

## Errors and Failures

"""
        for r in failed:
            report += f"### {r.config_name}\n"
            report += f"**Error:** {r.error}\n\n"
    
    # Add raw data section
    report += """

## Raw Test Data

<details>
<summary>Click to expand JSON data</summary>

```json
"""
    
    raw_data = {
        'timestamp': timestamp,
        'prompt': LONGEVITY_PROMPT,
        'total_tests': total_tests,
        'results': [r.to_dict() for r in results]
    }
    
    report += json.dumps(raw_data, indent=2)
    report += """
```

</details>

## Test Matrix Configuration

The following configurations were tested:

"""
    
    for i, config in enumerate(TEST_MATRIX, 1):
        report += f"{i}. **{config['vendor']}/{config['model']}** - "
        report += f"Country: {config['country']}, "
        report += f"Grounded: {config['grounded']}, "
        report += f"ALS: {config['als']}"
        if config.get('mode'):
            report += f", Mode: {config['mode']}"
        report += "\n"
    
    report += """

## Conclusions

### Key Findings

1. **Citation Extraction:** """
    
    if avg_citations > 0:
        report += f"Working correctly with average of {avg_citations:.1f} citations per grounded response\n"
    else:
        report += "⚠️ No citations found - requires investigation\n"
    
    report += "2. **Grounding Effectiveness:** "
    report += f"{grounding_success_rate:.1f}% success rate for grounded requests\n"
    
    report += "3. **Model Routing:** "
    openai_grounded = [r for r in openai_results if r.config['grounded']]
    correct_routing = sum(1 for r in openai_grounded if r.response_api == 'responses_http')
    if openai_grounded:
        report += f"{correct_routing}/{len(openai_grounded)} OpenAI grounded requests correctly routed\n"
    
    report += "4. **Telemetry Contract:** "
    telemetry_ok = all(r.response_api for r in results if r.config['grounded'] and r.success)
    report += "✅ All grounded calls have response_api\n" if telemetry_ok else "❌ Some grounded calls missing response_api\n"
    
    report += """

### Recommendations

"""
    
    if failed_tests > 0:
        report += f"- Investigate {failed_tests} test failures\n"
    
    if grounding_success_rate < 90:
        report += f"- Improve grounding success rate (currently {grounding_success_rate:.1f}%)\n"
    
    if avg_citations < 2:
        report += f"- Review citation extraction (average {avg_citations:.1f} is low)\n"
    
    report += """

---
*Generated by E2E Longevity Test Suite*
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
    report_file = f"E2E_LONGEVITY_TEST_REPORT_{timestamp}.md"
    
    with open(report_file, 'w') as f:
        f.write(report)
    
    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETE")
    print("=" * 80)
    print(f"Report saved to: {report_file}")
    
    # Also save raw JSON data
    json_file = f"e2e_longevity_test_results_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'results': [r.to_dict() for r in results]
        }, f, indent=2)
    print(f"Raw data saved to: {json_file}")
    
    # Print summary
    total = len(results)
    successful = sum(1 for r in results if r.success)
    print(f"\nSummary: {successful}/{total} tests passed ({successful/total*100:.1f}%)")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())