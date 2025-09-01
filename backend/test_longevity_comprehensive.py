#!/usr/bin/env python3
"""
Comprehensive test for longevity news prompt across all combinations.
Tests: DE+US, grounded/ungrounded, ALS/no-ALS on both OpenAI and Vertex models.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test configuration
PROMPT = "today is 31st August, 2025 - tell me the top longevity news of August"
TEMPLATE_ID = "test-longevity-news"
ORG_ID = "test-org"

# Test matrix - now includes grounding mode
CONFIGS = [
    # Model, Country, Grounded, ALS, GroundingMode
    ("gpt-5", "US", False, False, None),
    ("gpt-5", "US", False, True, None),
    ("gpt-5", "US", True, False, "AUTO"),
    ("gpt-5", "US", True, True, "AUTO"),
    ("gpt-5", "US", True, False, "REQUIRED"),  # Test REQUIRED mode
    ("gpt-5", "DE", False, False, None),
    ("gpt-5", "DE", False, True, None),
    ("gpt-5", "DE", True, False, "AUTO"),
    ("gpt-5", "DE", True, True, "AUTO"),
    
    ("gemini-2.5-pro", "US", False, False, None),
    ("gemini-2.5-pro", "US", False, True, None),
    ("gemini-2.5-pro", "US", True, False, "AUTO"),
    ("gemini-2.5-pro", "US", True, True, "AUTO"),
    ("gemini-2.5-pro", "US", True, False, "REQUIRED"),  # Test REQUIRED mode
    ("gemini-2.5-pro", "DE", False, False, None),
    ("gemini-2.5-pro", "DE", False, True, None),
    ("gemini-2.5-pro", "DE", True, False, "AUTO"),
    ("gemini-2.5-pro", "DE", True, True, "AUTO"),
]

def create_request(model: str, country: str, grounded: bool, use_als: bool, grounding_mode: str = None) -> LLMRequest:
    """Create an LLM request with specified configuration."""
    messages = [
        {"role": "user", "content": PROMPT}
    ]
    
    # Determine vendor from model
    vendor = "openai" if model.startswith("gpt") else "vertex"
    
    request = LLMRequest(
        vendor=vendor,
        messages=messages,
        model=model,
        grounded=grounded,
        max_tokens=500,
        temperature=0.7
    )
    
    # Initialize meta dict with test metadata
    request.meta = {
        'test_country': country,
        'test_als': use_als
    }
    
    # Add grounding mode via meta if grounded
    if grounded and grounding_mode:
        request.meta['grounding_mode'] = grounding_mode
    
    # Add ALS context if requested
    if use_als:
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
    
    # Add template_id for tracking
    request.template_id = TEMPLATE_ID
    
    return request

async def run_single_test(adapter: UnifiedLLMAdapter, model: str, country: str, 
                         grounded: bool, use_als: bool, grounding_mode: str = None) -> Dict:
    """Run a single test configuration."""
    mode_suffix = f"_{grounding_mode}" if grounding_mode else ""
    config_name = f"{model}_{country}_{'grounded' if grounded else 'ungrounded'}_{'ALS' if use_als else 'noALS'}{mode_suffix}"
    print(f"\n{'='*60}")
    print(f"Testing: {config_name}")
    print(f"Model: {model}, Country: {country}, Grounded: {grounded}, ALS: {use_als}, Mode: {grounding_mode or 'N/A'}")
    print('-'*60)
    
    try:
        request = create_request(model, country, grounded, use_als, grounding_mode)
        response = await adapter.complete(request)
        
        # Extract key information
        result = {
            "config": config_name,
            "model": model,
            "country": country,
            "grounded": grounded,
            "als": use_als,
            "grounding_mode": grounding_mode,
            "success": response.success,
            "grounded_effective": response.grounded_effective,
            "response_length": len(response.content) if response.content else 0,
            "citations_count": len(response.metadata.get('citations', [])) if response.metadata else 0,
            "tool_call_count": response.metadata.get('tool_call_count', 0) if response.metadata else 0,
            "error": None
        }
        
        # Extract citations if present
        if response.metadata and response.metadata.get('citations'):
            citations = response.metadata['citations']
            result['citations'] = []
            for cit in citations[:5]:  # First 5 citations
                result['citations'].append({
                    'url': cit.get('url', '')[:50] + '...' if len(cit.get('url', '')) > 50 else cit.get('url', ''),
                    'source_domain': cit.get('source_domain', ''),
                    'title': cit.get('title', '')[:50] + '...' if len(cit.get('title', '')) > 50 else cit.get('title', ''),
                    'redirect': cit.get('redirect', False)
                })
            
            # Count TLDs
            tld_counts = {}
            for cit in citations:
                domain = cit.get('source_domain', '')
                if domain:
                    parts = domain.split('.')
                    if len(parts) >= 2:
                        tld = f".{parts[-1]}"
                        tld_counts[tld] = tld_counts.get(tld, 0) + 1
            result['tld_distribution'] = tld_counts
        
        # Extract ALS metadata if present
        if response.metadata:
            als_fields = {k: v for k, v in response.metadata.items() if k.startswith('als_')}
            if als_fields:
                result['als_metadata'] = als_fields
            
            # Extract citation audit if present (when tools used but no citations)
            if 'citations_audit' in response.metadata:
                result['citations_audit'] = response.metadata['citations_audit']
            
            # Extract why_not_grounded if present
            if 'why_not_grounded' in response.metadata:
                result['why_not_grounded'] = response.metadata['why_not_grounded']
        
        # Sample of response content
        if response.content:
            result['response_preview'] = response.content[:200] + '...' if len(response.content) > 200 else response.content
        
        print(f"✓ Success: {response.success}")
        print(f"✓ Grounded Effective: {response.grounded_effective}")
        print(f"✓ Tool Calls: {result['tool_call_count']}")
        print(f"✓ Response Length: {result['response_length']} chars")
        print(f"✓ Citations: {result['citations_count']}")
        if result.get('tld_distribution'):
            print(f"✓ TLD Distribution: {result['tld_distribution']}")
        if result.get('why_not_grounded'):
            print(f"⚠ Why not grounded: {result['why_not_grounded']}")
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        print(f"✗ Error: {error_msg}")
        return {
            "config": config_name,
            "model": model,
            "country": country,
            "grounded": grounded,
            "als": use_als,
            "success": False,
            "error": error_msg
        }

async def run_all_tests():
    """Run all test configurations."""
    print(f"\n{'#'*60}")
    print(f"# COMPREHENSIVE LONGEVITY NEWS TEST")
    print(f"# Timestamp: {datetime.now().isoformat()}")
    print(f"# Prompt: {PROMPT}")
    print(f"{'#'*60}")
    
    adapter = UnifiedLLMAdapter()
    results = []
    
    for config in CONFIGS:
        if len(config) == 5:
            model, country, grounded, use_als, grounding_mode = config
        else:
            model, country, grounded, use_als = config
            grounding_mode = None
        result = await run_single_test(adapter, model, country, grounded, use_als, grounding_mode)
        results.append(result)
        await asyncio.sleep(1)  # Rate limiting
    
    # Generate summary report
    print(f"\n{'#'*60}")
    print("# SUMMARY REPORT")
    print(f"{'#'*60}")
    
    # Success rate by model
    for model in ["gpt-5", "gemini-2.5-pro"]:
        model_results = [r for r in results if r['model'] == model]
        success_count = sum(1 for r in model_results if r.get('success'))
        print(f"\n{model}:")
        print(f"  Success Rate: {success_count}/{len(model_results)}")
        
        # Grounding effectiveness
        grounded_results = [r for r in model_results if r['grounded']]
        effective_count = sum(1 for r in grounded_results if r.get('grounded_effective'))
        print(f"  Grounding Effective: {effective_count}/{len(grounded_results)}")
        
        # ALS impact on TLDs
        for country in ["US", "DE"]:
            country_results = [r for r in model_results if r['country'] == country and r.get('tld_distribution')]
            if country_results:
                all_tlds = {}
                for r in country_results:
                    for tld, count in r.get('tld_distribution', {}).items():
                        all_tlds[tld] = all_tlds.get(tld, 0) + count
                print(f"  {country} TLDs: {dict(sorted(all_tlds.items(), key=lambda x: x[1], reverse=True)[:5])}")
    
    # Save detailed results
    output_file = f"longevity_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "prompt": PROMPT,
            "results": results
        }, f, indent=2)
    
    print(f"\n✓ Detailed results saved to: {output_file}")
    
    # Check for ALS effectiveness
    print(f"\n{'='*60}")
    print("ALS EFFECTIVENESS CHECK:")
    for model in ["gpt-5", "gemini-2.5-pro"]:
        print(f"\n{model}:")
        
        # Compare DE with ALS vs DE without ALS
        de_als = [r for r in results if r['model'] == model and r['country'] == 'DE' and r['als'] and r['grounded']]
        de_no_als = [r for r in results if r['model'] == model and r['country'] == 'DE' and not r['als'] and r['grounded']]
        
        if de_als and de_no_als:
            # Check for .de domain presence
            de_als_has_de = any('.de' in r.get('tld_distribution', {}) for r in de_als)
            de_no_als_has_de = any('.de' in r.get('tld_distribution', {}) for r in de_no_als)
            
            print(f"  DE+ALS has .de domains: {de_als_has_de}")
            print(f"  DE no-ALS has .de domains: {de_no_als_has_de}")
            
            if de_als_has_de and not de_no_als_has_de:
                print(f"  ✓ ALS is working! DE domains appear with ALS but not without.")
            elif de_als_has_de and de_no_als_has_de:
                print(f"  ⚠ Both have .de domains - ALS effect unclear")
            else:
                print(f"  ✗ No .de domains found - ALS may not be effective")

if __name__ == "__main__":
    asyncio.run(run_all_tests())