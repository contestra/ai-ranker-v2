#!/usr/bin/env python3
"""
Citation validation test with current/past queries that should return citations.
Tests whether the V2 citation extractor properly handles real grounding evidence.
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List

# CRITICAL: Set environment variables BEFORE any imports
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATIONS_EXTRACTOR_ENABLE'] = 'true'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'false'  # Keep off for production testing
os.environ['DEBUG_GROUNDING'] = 'true'
os.environ['ALLOW_HTTP_RESOLVE'] = 'false'

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test queries - current/past events that should trigger grounding and return citations
TEST_QUERIES = {
    "2024_election": "What were the key results of the 2024 US presidential election?",
    "openai_news": "What are the latest developments from OpenAI in 2024?",
    "climate_2024": "What were the major climate change events and agreements in 2024?",
    "tech_news": "What are the most important technology breakthroughs announced in 2024?",
    "covid_update": "What is the current status of COVID-19 globally as of 2024?",
    "ai_regulation": "What new AI regulations were passed in the EU and US in 2024?",
    "future_test": "What will be the major technology breakthroughs in 2030?"  # Negative case
}

# Models to test
MODELS = {
    'openai': 'gpt-5',
    'vertex': 'gemini-2.5-pro'
}

async def run_single_test(adapter: UnifiedLLMAdapter, vendor: str, model: str, 
                         query_name: str, query: str, grounded: bool) -> Dict[str, Any]:
    """Run a single test configuration."""
    config_name = f"{vendor}_{query_name}_{'grounded' if grounded else 'ungrounded'}"
    print(f"\n{'='*60}")
    print(f"Testing: {config_name}")
    print(f"Query: {query[:80]}...")
    print(f"{'='*60}")
    
    # Create request
    request = LLMRequest(
        messages=[{"role": "user", "content": query}],
        model=model,
        vendor=vendor,
        grounded=grounded,
        max_tokens=1000,
        temperature=0.3  # Lower temp for more factual responses
    )
    
    request.template_id = "citation-validation-test"
    request.org_id = "test-org"
    
    result = {
        'config': config_name,
        'vendor': vendor,
        'model': model,
        'query_name': query_name,
        'query': query,
        'grounded_requested': grounded,
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        # Execute request
        response = await adapter.complete(request)
        
        # Extract results
        result['success'] = True
        result['content'] = response.content[:500] if response.content else ""
        result['metadata'] = response.metadata
        
        # Extract key metrics
        if response.metadata:
            result['grounded_effective'] = response.metadata.get('grounded_effective', False)
            result['tool_calls'] = response.metadata.get('tool_call_count', 0)
            result['citations_count'] = len(response.metadata.get('citations', []))
            result['anchored_citations_count'] = response.metadata.get('anchored_citations_count', 0)
            result['unlinked_sources_count'] = response.metadata.get('unlinked_sources_count', 0)
            result['grounded_evidence_unavailable'] = response.metadata.get('grounded_evidence_unavailable', False)
            result['citations_status_reason'] = response.metadata.get('citations_status_reason')
            
            # Get citation details
            citations = response.metadata.get('citations', [])
            if citations:
                result['citation_types'] = {}
                for cit in citations:
                    source_type = cit.get('source_type', 'unknown')
                    result['citation_types'][source_type] = result['citation_types'].get(source_type, 0) + 1
                result['sample_citations'] = citations[:3]  # First 3 for brevity
            
            # Check for audit data
            if 'citations_audit' in response.metadata:
                audit = response.metadata['citations_audit']
                result['audit_samples'] = audit.get('samples', {})
        
        # Check response quality
        content_lower = response.content.lower() if response.content else ""
        result['has_disclaimer'] = any(phrase in content_lower for phrase in [
            'knowledge cutoff', 'training data', "don't have access", "cannot access"
        ])
        result['appears_grounded'] = any(phrase in content_lower for phrase in [
            'according to', 'reported', 'announced', 'as of', 'in 2024', 'recently'
        ])
        
        print(f"✓ Success: grounded_effective={result.get('grounded_effective')}, "
              f"citations={result.get('citations_count')}, "
              f"anchored={result.get('anchored_citations_count')}, "
              f"evidence_unavailable={result.get('grounded_evidence_unavailable')}")
        
    except Exception as e:
        result['success'] = False
        result['error'] = str(e)
        result['error_type'] = type(e).__name__
        print(f"✗ Failed: {e}")
    
    return result

async def run_all_tests() -> List[Dict[str, Any]]:
    """Run all test configurations."""
    # Initialize adapter
    adapter = UnifiedLLMAdapter()
    
    results = []
    
    # Test each query with both vendors, grounded only (ungrounded won't have citations)
    for query_name, query in TEST_QUERIES.items():
        for vendor in ['openai', 'vertex']:
            # Grounded test (should have citations for current/past queries)
            result = await run_single_test(
                adapter=adapter,
                vendor=vendor,
                model=MODELS[vendor],
                query_name=query_name,
                query=query,
                grounded=True
            )
            results.append(result)
            
            # Small delay to avoid rate limits
            await asyncio.sleep(3)
    
    return results

def generate_report(results: List[Dict[str, Any]]):
    """Generate analysis report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"\n{'='*80}")
    print(f"CITATION VALIDATION REPORT - {timestamp}")
    print(f"{'='*80}\n")
    
    # Group by query
    by_query = {}
    for r in results:
        query_name = r['query_name']
        if query_name not in by_query:
            by_query[query_name] = []
        by_query[query_name].append(r)
    
    # Analyze each query
    print("## Results by Query\n")
    for query_name, query_results in by_query.items():
        print(f"\n### {query_name}")
        print(f"Query: {TEST_QUERIES[query_name][:100]}...")
        
        for r in query_results:
            vendor = r['vendor']
            success = "✓" if r.get('success') else "✗"
            grounded_eff = "✓" if r.get('grounded_effective') else "-"
            citations = r.get('citations_count', 0)
            anchored = r.get('anchored_citations_count', 0)
            evidence_unavail = "⚠️" if r.get('grounded_evidence_unavailable') else "-"
            
            print(f"  {vendor:8} | Success: {success} | Grounded: {grounded_eff} | "
                  f"Citations: {citations} | Anchored: {anchored} | Evidence Unavail: {evidence_unavail}")
            
            if r.get('citations_status_reason'):
                print(f"           | Status: {r['citations_status_reason']}")
            
            if r.get('sample_citations'):
                for i, cit in enumerate(r['sample_citations'][:2], 1):
                    print(f"           | Citation {i}: {cit.get('title', 'No title')[:50]}...")
            
            if r.get('audit_samples'):
                print(f"           | Audit samples: {list(r['audit_samples'].keys())}")
    
    # Summary statistics
    print(f"\n## Summary Statistics\n")
    
    successful = sum(1 for r in results if r.get('success'))
    grounded_effective = sum(1 for r in results if r.get('grounded_effective'))
    with_citations = sum(1 for r in results if r.get('citations_count', 0) > 0)
    with_anchored = sum(1 for r in results if r.get('anchored_citations_count', 0) > 0)
    evidence_unavailable = sum(1 for r in results if r.get('grounded_evidence_unavailable'))
    
    print(f"Total Tests: {len(results)}")
    print(f"Successful: {successful}/{len(results)} ({100*successful/len(results):.1f}%)")
    print(f"Grounded Effective: {grounded_effective}/{len(results)} ({100*grounded_effective/len(results):.1f}%)")
    print(f"With Citations: {with_citations}/{len(results)} ({100*with_citations/len(results):.1f}%)")
    print(f"With Anchored Citations: {with_anchored}/{len(results)} ({100*with_anchored/len(results):.1f}%)")
    print(f"Evidence Unavailable: {evidence_unavailable}/{len(results)} ({100*evidence_unavailable/len(results):.1f}%)")
    
    # By vendor
    print(f"\n## By Vendor\n")
    for vendor in ['openai', 'vertex']:
        vendor_results = [r for r in results if r['vendor'] == vendor]
        if vendor_results:
            v_success = sum(1 for r in vendor_results if r.get('success'))
            v_citations = sum(1 for r in vendor_results if r.get('citations_count', 0) > 0)
            v_anchored = sum(1 for r in vendor_results if r.get('anchored_citations_count', 0) > 0)
            print(f"{vendor}: {v_success}/{len(vendor_results)} successful, "
                  f"{v_citations} with citations, {v_anchored} with anchored")
    
    # Citation status reasons
    print(f"\n## Citation Status Reasons\n")
    status_reasons = {}
    for r in results:
        reason = r.get('citations_status_reason', 'none')
        status_reasons[reason] = status_reasons.get(reason, 0) + 1
    
    for reason, count in sorted(status_reasons.items()):
        print(f"  {reason}: {count}")
    
    # Save raw results
    timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = f"citation_validation_results_{timestamp_file}.json"
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n## Raw results saved to: {json_file}")

async def main():
    """Main execution."""
    print("Starting Citation Validation Tests...")
    print(f"Testing {len(TEST_QUERIES)} queries with 2 vendors (grounded only)")
    print(f"Total tests: {len(TEST_QUERIES) * 2}")
    
    # Run all tests
    results = await run_all_tests()
    
    # Generate report
    generate_report(results)

if __name__ == "__main__":
    asyncio.run(main())