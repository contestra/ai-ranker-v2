#!/usr/bin/env python3
"""
QA Visibility Test - Enable unlinked emission to see evidence trail.
This is for QA/debugging only, not production.
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Dict, Any

# CRITICAL: Enable unlinked emission for QA visibility
os.environ['CITATION_EXTRACTOR_V2'] = '1.0'
os.environ['CITATION_EXTRACTOR_ENABLE_LEGACY'] = 'false'
os.environ['CITATIONS_EXTRACTOR_ENABLE'] = 'true'
os.environ['CITATION_EXTRACTOR_EMIT_UNLINKED'] = 'true'  # QA ONLY - shows evidence trail
os.environ['DEBUG_GROUNDING'] = 'true'
os.environ['ALLOW_HTTP_RESOLVE'] = 'false'

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

# Test queries - mix of future and current
TEST_QUERIES = {
    "future_longevity": "What was the most interesting longevity and healthspan extension news during August 2025?",
    "current_ai": "What are the latest AI developments from OpenAI and Anthropic in 2024?",
    "current_election": "What were the key results of the 2024 US presidential election?"
}

MODELS = {
    'vertex': 'gemini-2.5-pro'
}

async def run_test(adapter: UnifiedLLMAdapter, query_name: str, query: str) -> Dict[str, Any]:
    """Run a single test with unlinked emission enabled."""
    print(f"\n{'='*70}")
    print(f"Testing: {query_name}")
    print(f"Query: {query[:70]}...")
    print(f"CITATION_EXTRACTOR_EMIT_UNLINKED: {os.environ.get('CITATION_EXTRACTOR_EMIT_UNLINKED')}")
    print(f"{'='*70}")
    
    request = LLMRequest(
        messages=[{"role": "user", "content": query}],
        model=MODELS['vertex'],
        vendor='vertex',
        grounded=True,
        max_tokens=1000,
        temperature=0.3
    )
    
    request.template_id = "qa-visibility-test"
    request.org_id = "test-org"
    
    result = {
        'query_name': query_name,
        'query': query,
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        response = await adapter.complete(request)
        
        result['success'] = True
        result['content_snippet'] = response.content[:300] if response.content else ""
        
        if response.metadata:
            result['grounded_effective'] = response.metadata.get('grounded_effective', False)
            result['tool_call_count'] = response.metadata.get('tool_call_count', 0)
            
            # Citation metrics
            citations = response.metadata.get('citations', [])
            result['total_citations'] = len(citations)
            result['anchored_count'] = response.metadata.get('anchored_citations_count', 0)
            result['unlinked_count'] = response.metadata.get('unlinked_sources_count', 0)
            
            # Citation breakdown by type
            citation_types = {}
            for cit in citations:
                source_type = cit.get('source_type', 'unknown')
                citation_types[source_type] = citation_types.get(source_type, 0) + 1
            result['citation_types'] = citation_types
            
            # Status reasons
            result['citations_status_reason'] = response.metadata.get('citations_status_reason')
            result['grounded_evidence_unavailable'] = response.metadata.get('grounded_evidence_unavailable', False)
            
            # Audit data
            if 'citations_audit' in response.metadata:
                audit = response.metadata['citations_audit']
                result['audit_keys'] = audit.get('grounding_metadata_keys', [])
                result['audit_samples'] = audit.get('samples', {})
            
            # Sample citations
            if citations:
                print(f"\n📋 CITATIONS FOUND: {len(citations)}")
                print(f"   Anchored: {result['anchored_count']}, Unlinked: {result['unlinked_count']}")
                print(f"   Types: {citation_types}")
                
                # Show first 3 citations
                for i, cit in enumerate(citations[:3], 1):
                    title = cit.get('title', 'No title')[:50]
                    url = cit.get('url', 'No URL')
                    source_type = cit.get('source_type', 'unknown')
                    print(f"\n   Citation {i}:")
                    print(f"     Type: {source_type}")
                    print(f"     Title: {title}...")
                    print(f"     Domain: {cit.get('source_domain', 'Unknown')}")
                    if url and len(url) < 100:
                        print(f"     URL: {url}")
            else:
                print(f"\n⚠️ NO CITATIONS despite tool_calls={result['tool_call_count']}")
                if result.get('audit_samples'):
                    print(f"   Audit samples found: {list(result['audit_samples'].keys())}")
        
        print(f"\n✅ Success - Tool calls: {result.get('tool_call_count', 0)}, "
              f"Citations: {result.get('total_citations', 0)} "
              f"(Anchored: {result.get('anchored_count', 0)}, "
              f"Unlinked: {result.get('unlinked_count', 0)})")
        
    except Exception as e:
        result['success'] = False
        result['error'] = str(e)
        print(f"\n❌ Failed: {e}")
    
    return result

async def main():
    """Run QA visibility tests."""
    print("="*70)
    print("QA VISIBILITY TEST - UNLINKED EMISSION ENABLED")
    print("="*70)
    print("\nThis test enables CITATION_EXTRACTOR_EMIT_UNLINKED=true")
    print("to surface ALL evidence when tools are called.")
    print("This is for QA/debugging only, NOT for production!")
    print("\nProduction should keep CITATION_EXTRACTOR_EMIT_UNLINKED=false")
    print("to maintain REQUIRED mode semantics (anchored-only).")
    
    adapter = UnifiedLLMAdapter()
    results = []
    
    for query_name, query in TEST_QUERIES.items():
        result = await run_test(adapter, query_name, query)
        results.append(result)
        await asyncio.sleep(3)
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    for r in results:
        query_name = r['query_name']
        success = "✅" if r.get('success') else "❌"
        citations = r.get('total_citations', 0)
        anchored = r.get('anchored_count', 0)
        unlinked = r.get('unlinked_count', 0)
        types = r.get('citation_types', {})
        
        print(f"\n{query_name}: {success}")
        print(f"  Citations: {citations} (Anchored: {anchored}, Unlinked: {unlinked})")
        if types:
            print(f"  Types: {types}")
        if r.get('citations_status_reason'):
            print(f"  Status: {r['citations_status_reason']}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"qa_visibility_results_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n📁 Results saved to: {filename}")
    
    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    print("\n1. QA/Staging: Enable CITATION_EXTRACTOR_EMIT_UNLINKED=true")
    print("   - Surfaces all evidence for debugging")
    print("   - Shows unlinked sources when tools are called")
    print("\n2. Production: Keep CITATION_EXTRACTOR_EMIT_UNLINKED=false")
    print("   - Maintains REQUIRED mode contract (anchored-only)")
    print("   - Cleaner citation metrics")
    print("\n3. Testing: Use current/past queries for positive cases")
    print("   - Future queries often return empty evidence")
    print("   - Keep one future case as negative control")

if __name__ == "__main__":
    asyncio.run(main())