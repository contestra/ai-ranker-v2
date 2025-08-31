#!/usr/bin/env python3
"""
ALS Ambient Quick Test - Subset for demonstration
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from tests.util.als_ambient_utils import (
    check_prompt_leak, extract_tld_counts, calculate_domain_diversity,
    format_tld_summary, calculate_als_hash
)

# Quick test - single prompt
PROMPT = (
    "As of August 31, 2025, summarize the most credible peer-reviewed findings "
    "(≤12 months) on spermidine for healthy adults. Include study design, sample size, "
    "primary outcomes, limitations, and provide URLs + publish dates. "
    "End with TOOL_STATUS: USED_WEB_SEARCH or NO_TOOLS."
)

async def quick_test():
    """Run quick subset of tests"""
    
    print("\n" + "="*80)
    print("ALS AMBIENT QUICK TEST")
    print("="*80)
    
    # Check prompt for leaks
    has_leak = check_prompt_leak(PROMPT)
    print(f"Prompt leak check: {'❌ FAILED' if has_leak else '✅ PASSED'}")
    
    adapter = UnifiedLLMAdapter()
    results = []
    
    # Test configs: OpenAI grounded with different ALS
    test_configs = [
        ("NONE", None),
        ("CH", ALSContext(country_code="CH", locale="de-CH", als_block="")),
        ("DE", ALSContext(country_code="DE", locale="de-DE", als_block="")),
        ("US", ALSContext(country_code="US", locale="en-US", als_block=""))
    ]
    
    print("\nRunning OpenAI grounded tests with different ALS contexts...")
    print("-" * 40)
    
    for als_name, als_context in test_configs:
        print(f"\n[ALS: {als_name}]")
        
        # Build request
        request = LLMRequest(
            vendor="openai",
            model="gpt-5",
            messages=[{"role": "user", "content": PROMPT}],
            grounded=True,
            meta={"grounding_mode": "AUTO"},
            als_context=als_context,
            max_tokens=300
        )
        
        try:
            response = await adapter.complete(request)
            content = response.content if hasattr(response, 'content') else ""
            metadata = response.metadata if hasattr(response, 'metadata') else {}
            
            # Extract citations
            citations = []
            if metadata.get('citations'):
                citations = [c.get('url', '') for c in metadata['citations'] if isinstance(c, dict)]
            
            # Analyze
            tld_counts = extract_tld_counts(citations)
            
            result = {
                "als": als_name,
                "grounded_effective": metadata.get('grounded_effective', False),
                "tool_calls": metadata.get('tool_call_count', 0),
                "citations_count": len(citations),
                "tld_counts": tld_counts,
                "tld_summary": format_tld_summary(tld_counts),
                "tool_status": "USED_WEB_SEARCH" if "USED_WEB_SEARCH" in content else "NO_TOOLS"
            }
            
            results.append(result)
            
            print(f"  Grounded: {result['grounded_effective']}")
            print(f"  Citations: {result['citations_count']}")
            print(f"  TLDs: {result['tld_summary']}")
            print(f"  Tool status: {result['tool_status']}")
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:100]}")
            results.append({
                "als": als_name,
                "error": str(e)[:100]
            })
    
    # Save quick results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # NDJSON
    ndjson_path = f"/home/leedr/ai-ranker-v2/backend/artifacts/ALS_AMBIENT_QUICK_{timestamp}.ndjson"
    with open(ndjson_path, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    print(f"\n✓ Saved NDJSON: {ndjson_path}")
    
    # Quick report
    report_path = f"/home/leedr/ai-ranker-v2/backend/reports/ALS_AMBIENT_QUICK_{timestamp}.md"
    with open(report_path, 'w') as f:
        f.write("# ALS Ambient Quick Test Report\n\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        f.write(f"**Prompt Leak Check**: {'❌ FAILED' if has_leak else '✅ PASSED'}\n\n")
        
        f.write("## Results\n\n")
        f.write("| ALS | Grounded | Citations | TLDs | Status |\n")
        f.write("|-----|----------|-----------|------|--------|\n")
        
        for r in results:
            if 'error' not in r:
                f.write(f"| {r['als']} | {r['grounded_effective']} | {r['citations_count']} | {r['tld_summary']} | {r['tool_status']} |\n")
            else:
                f.write(f"| {r['als']} | ERROR | - | - | - |\n")
        
        f.write("\n## Analysis\n\n")
        
        # Check for ALS effects
        if len(results) >= 2:
            baseline = results[0] if results[0]['als'] == 'NONE' else None
            ch_result = next((r for r in results if r['als'] == 'CH'), None)
            
            if baseline and ch_result and 'tld_counts' in baseline and 'tld_counts' in ch_result:
                baseline_ch = baseline['tld_counts'].get('.ch', 0)
                ch_ch = ch_result['tld_counts'].get('.ch', 0)
                
                if ch_ch > baseline_ch:
                    f.write("✅ **ALS Effect Observed**: CH context increased .ch domains\n")
                else:
                    f.write("⚠️ **Limited ALS Effect**: No clear increase in local domains\n")
        
        f.write(f"\n**Note**: This is a quick subset test. Full matrix test available.\n")
    
    print(f"✓ Saved Report: {report_path}")
    
    # Executive summary
    print("\n" + "="*80)
    print("EXECUTIVE SUMMARY")
    print("="*80)
    
    if not has_leak:
        print("✅ No prompt leakage - prompts are location-neutral")
    else:
        print("❌ Prompt contains location words - fix required")
    
    # Check if OpenAI invoked tools
    tools_used = any(r.get('grounded_effective', False) for r in results if 'error' not in r)
    if not tools_used:
        print("ℹ️ OpenAI did not invoke web_search tools (expected behavior)")
    else:
        print("✅ Some grounding observed")
    
    print(f"\nFiles generated:")
    print(f"  - {ndjson_path}")
    print(f"  - {report_path}")
    
    return results

if __name__ == "__main__":
    asyncio.run(quick_test())