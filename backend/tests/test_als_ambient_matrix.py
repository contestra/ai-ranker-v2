#!/usr/bin/env python3
"""
ALS Ambient Matrix Test
Verifies ALS steering without location leakage in prompts
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from tests.util.als_ambient_utils import (
    check_prompt_leak, check_assistant_location_mention,
    extract_tld_counts, calculate_domain_diversity,
    guess_language, assess_result_quality,
    extract_unique_local_domains, calculate_als_hash,
    format_tld_summary, check_als_effect
)

# Test prompts - NO location words
PROMPTS = {
    "evidence": (
        "As of August 31, 2025, summarize the most credible peer-reviewed findings "
        "(≤12 months) on spermidine for healthy adults. Include study design, sample size, "
        "primary outcomes, limitations, and provide URLs + publish dates. "
        "End with TOOL_STATUS: USED_WEB_SEARCH or NO_TOOLS."
    ),
    "brand_cross_check": (
        "Open the product page on www.avea-life.com for Collagen Activator. "
        "Then cite one independent source (≤12 months) about its core ingredients. "
        "Provide 2 bullets and 2 URLs + dates. End with TOOL_STATUS."
    ),
    "press_scan": (
        "List the latest 3 independent news items about AVEA Life in the last 6 months. "
        "Return title — outlet — date — URL. End with TOOL_STATUS."
    )
}

# ALS contexts
ALS_CONTEXTS = {
    "NONE": None,
    "CH": ALSContext(country_code="CH", locale="de-CH", als_block=""),
    "DE": ALSContext(country_code="DE", locale="de-DE", als_block=""),
    "US": ALSContext(country_code="US", locale="en-US", als_block="")
}

# Test configurations
TEST_CONFIGS = [
    # Vertex grounded
    ("vertex", "publishers/google/models/gemini-2.5-pro", True, "AUTO"),
    # OpenAI grounded (REQUIRED is N/A for web_search)
    ("openai", "gpt-5", True, "AUTO"),
    # Ungrounded controls
    ("vertex", "publishers/google/models/gemini-2.5-pro", False, None),
    ("openai", "gpt-5", False, None),
]


async def run_single_test(
    adapter: UnifiedLLMAdapter,
    prompt_name: str,
    prompt_text: str,
    vendor: str,
    model: str,
    grounded: bool,
    mode: Optional[str],
    als_name: str,
    als_context: Optional[ALSContext]
) -> Dict[str, Any]:
    """Run a single test and collect metrics"""
    
    # Check for prompt leakage
    prompt_leak = check_prompt_leak(prompt_text)
    if prompt_leak:
        print(f"  ⚠️ PROMPT LEAK DETECTED in {prompt_name}")
    
    # Build ALS block if context provided
    als_block = ""
    als_hash = ""
    if als_context:
        # Build ALS block (router handles this, but we track it)
        als_parts = []
        if als_context.country_code:
            als_parts.append(f"You are in {als_context.country_code}")
        if als_context.locale:
            als_parts.append(f"Locale: {als_context.locale}")
        als_block = ". ".join(als_parts) if als_parts else ""
        als_hash = calculate_als_hash(als_block) if als_block else ""
    
    # Build request
    request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        grounded=grounded,
        meta={"grounding_mode": mode} if mode else {},
        als_context=als_context,
        max_tokens=500
    )
    
    # Initialize result
    result = {
        "prompt_name": prompt_name,
        "vendor": vendor,
        "model": model,
        "grounded": grounded,
        "mode": mode,
        "als_name": als_name,
        "als_country": als_context.country_code if als_context else None,
        "als_locale": als_context.locale if als_context else None,
        "als_present": als_context is not None,
        "als_block_sha256": als_hash,
        "als_nfc_length": len(als_block),
        "prompt_leak_detected": prompt_leak,
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        # Execute request
        response = await adapter.complete(request)
        
        # Extract content and metadata
        content = response.content if hasattr(response, 'content') else ""
        metadata = response.metadata if hasattr(response, 'metadata') else {}
        
        # Extract citations
        citations = []
        if metadata.get('citations'):
            citations = [c.get('url', '') for c in metadata['citations'] if isinstance(c, dict)]
        
        # Analyze response
        tld_counts = extract_tld_counts(citations)
        domain_diversity = calculate_domain_diversity(citations)
        language = guess_language(content, tld_counts)
        assistant_leak = check_assistant_location_mention(content)
        
        # Determine tool status
        tool_status = "NO_TOOLS"
        if "USED_WEB_SEARCH" in content:
            tool_status = "USED_WEB_SEARCH"
        elif metadata.get('grounding_attempted'):
            tool_status = "ATTEMPTED"
        
        # Update result
        result.update({
            "status": "success",
            "tool_status": tool_status,
            "grounding_attempted": metadata.get('grounding_attempted', False),
            "grounded_effective": metadata.get('grounded_effective', False),
            "tool_call_count": metadata.get('tool_call_count', 0),
            "tool_result_count": metadata.get('tool_result_count', 0),
            "citations": citations,
            "citations_count": len(citations),
            "tld_counts": tld_counts,
            "domain_diversity": domain_diversity,
            "language_guess": language,
            "assistant_leak_note": assistant_leak,
            "quality_met": assess_result_quality(
                metadata.get('grounded_effective', False),
                domain_diversity
            ),
            "response_preview": content[:200] + "..." if len(content) > 200 else content
        })
        
    except Exception as e:
        result.update({
            "status": "error",
            "error": str(e)[:200],
            "tool_status": "ERROR",
            "citations": [],
            "tld_counts": {},
            "domain_diversity": 0
        })
    
    return result


async def run_matrix():
    """Run the complete test matrix"""
    
    print("\n" + "="*80)
    print("ALS AMBIENT MATRIX TEST")
    print("="*80)
    print(f"Start time: {datetime.now().isoformat()}")
    
    # Initialize adapter
    adapter = UnifiedLLMAdapter()
    
    # Results storage
    all_results = []
    
    # Statistics
    stats = {
        "total_runs": 0,
        "grounded_runs": 0,
        "ungrounded_runs": 0,
        "openai_no_tools": 0,
        "prompt_leaks": 0,
        "errors": 0
    }
    
    # Run matrix
    for prompt_name, prompt_text in PROMPTS.items():
        print(f"\n[PROMPT: {prompt_name}]")
        print("-" * 40)
        
        # Check prompt for leaks upfront
        if check_prompt_leak(prompt_text):
            print(f"⚠️ WARNING: Prompt contains location words!")
            stats["prompt_leaks"] += 1
        
        for vendor, model, grounded, mode in TEST_CONFIGS:
            for als_name, als_context in ALS_CONTEXTS.items():
                
                test_desc = f"{vendor}-{als_name}-{'grounded' if grounded else 'ungrounded'}"
                print(f"\n  Testing: {test_desc}")
                
                # Run test
                result = await run_single_test(
                    adapter, prompt_name, prompt_text,
                    vendor, model, grounded, mode,
                    als_name, als_context
                )
                
                # Update stats
                stats["total_runs"] += 1
                if grounded:
                    stats["grounded_runs"] += 1
                else:
                    stats["ungrounded_runs"] += 1
                
                if result.get("tool_status") == "NO_TOOLS" and vendor == "openai":
                    stats["openai_no_tools"] += 1
                
                if result.get("status") == "error":
                    stats["errors"] += 1
                    print(f"    ❌ Error: {result.get('error', 'Unknown')[:100]}")
                else:
                    print(f"    ✓ Grounded: {result.get('grounded_effective', False)}")
                    print(f"    ✓ Citations: {result.get('citations_count', 0)}")
                    print(f"    ✓ TLDs: {format_tld_summary(result.get('tld_counts', {}))}")
                
                # Store result
                all_results.append(result)
    
    # Save artifacts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Write NDJSON
    ndjson_path = f"/home/leedr/ai-ranker-v2/backend/artifacts/ALS_AMBIENT_RUNS_{timestamp}.ndjson"
    with open(ndjson_path, 'w') as f:
        for result in all_results:
            f.write(json.dumps(result) + '\n')
    
    print(f"\n✓ Saved NDJSON: {ndjson_path}")
    
    # Generate report
    report_path = f"/home/leedr/ai-ranker-v2/backend/reports/ALS_AMBIENT_QA_REPORT_{timestamp}.md"
    generate_report(all_results, stats, report_path)
    
    print(f"✓ Saved Report: {report_path}")
    
    # Print summary
    print("\n" + "="*80)
    print("EXECUTION SUMMARY")
    print("="*80)
    print(f"Total runs: {stats['total_runs']}")
    print(f"Grounded: {stats['grounded_runs']}")
    print(f"Ungrounded: {stats['ungrounded_runs']}")
    print(f"OpenAI NO_TOOLS: {stats['openai_no_tools']}")
    print(f"Prompt leaks: {stats['prompt_leaks']}")
    print(f"Errors: {stats['errors']}")
    
    return all_results, stats


def generate_report(results: List[Dict], stats: Dict, report_path: str):
    """Generate the QA report in Markdown format"""
    
    report = []
    report.append("# ALS Ambient QA Report")
    report.append(f"Generated: {datetime.now().isoformat()}\n")
    
    # Executive Summary
    report.append("## Executive Summary\n")
    
    # Check for prompt leaks
    any_prompt_leak = any(r.get('prompt_leak_detected', False) for r in results)
    if any_prompt_leak:
        report.append("❌ **FAILED**: Prompt leakage detected - location words found in user prompts\n")
    else:
        report.append("✅ **PASSED**: No prompt leakage - all prompts are location-neutral\n")
    
    # Analyze ALS effects
    als_effects_observed = analyze_als_effects(results)
    
    if als_effects_observed:
        report.append("✅ **ALS Effects Observed**: Clear geographic steering via ALS without prompt contamination\n")
    else:
        report.append("⚠️ **Limited ALS Effects**: Geographic steering not clearly demonstrated\n")
    
    report.append(f"\n**Stats**: {stats['total_runs']} runs | {stats['grounded_runs']} grounded | {stats['openai_no_tools']} OpenAI NO_TOOLS\n")
    
    # Per-prompt analysis
    for prompt_name in PROMPTS.keys():
        report.append(f"\n## Prompt: {prompt_name}\n")
        
        # Filter results for this prompt
        prompt_results = [r for r in results if r['prompt_name'] == prompt_name]
        
        # Build comparison table
        report.append("### Grounded Results Comparison\n")
        report.append("| Metric | ALS_NONE | ALS_CH | ALS_DE | ALS_US |")
        report.append("|--------|----------|---------|---------|---------|")
        
        # Vertex grounded results
        report.append("| **Vertex** | | | | |")
        for metric in ['grounded_effective', 'tool_calls/results', 'top_tlds', 'unique_local', 'language']:
            row = ["| " + metric]
            for als in ['NONE', 'CH', 'DE', 'US']:
                result = find_result(prompt_results, 'vertex', True, als)
                if result:
                    if metric == 'grounded_effective':
                        row.append(str(result.get('grounded_effective', False)))
                    elif metric == 'tool_calls/results':
                        row.append(f"{result.get('tool_call_count', 0)}/{result.get('tool_result_count', 0)}")
                    elif metric == 'top_tlds':
                        row.append(format_tld_summary(result.get('tld_counts', {}), 3))
                    elif metric == 'unique_local':
                        local_tlds = {
                            'CH': ['.ch'],
                            'DE': ['.de'],
                            'US': ['.com', '.gov'],
                            'NONE': []
                        }
                        if als in local_tlds:
                            domains = extract_unique_local_domains(
                                result.get('citations', []),
                                local_tlds[als]
                            )
                            row.append(f"{len(domains)} domains")
                        else:
                            row.append("-")
                    elif metric == 'language':
                        row.append(result.get('language_guess', '-'))
                else:
                    row.append("N/A")
            row.append("|")
            report.append(" | ".join(row))
        
        # OpenAI grounded results
        report.append("| **OpenAI** | | | | |")
        for metric in ['grounded_effective', 'tool_status']:
            row = ["| " + metric]
            for als in ['NONE', 'CH', 'DE', 'US']:
                result = find_result(prompt_results, 'openai', True, als)
                if result:
                    if metric == 'grounded_effective':
                        row.append(str(result.get('grounded_effective', False)))
                    elif metric == 'tool_status':
                        row.append(result.get('tool_status', '-'))
                else:
                    row.append("N/A")
            row.append("|")
            report.append(" | ".join(row))
        
        # Analysis
        report.append("\n### Analysis\n")
        analysis = analyze_prompt_results(prompt_results)
        report.append(analysis)
        
        # Leakage check
        report.append("\n### Leakage Check\n")
        prompt_leak = any(r.get('prompt_leak_detected', False) for r in prompt_results)
        assistant_leak = any(r.get('assistant_leak_note', False) for r in prompt_results)
        
        if prompt_leak:
            report.append("❌ **Prompt leakage detected** - location words in user text\n")
        else:
            report.append("✅ **No prompt leakage** - user text is location-neutral\n")
        
        if assistant_leak:
            report.append("⚠️ **Note**: Assistant mentioned country (acceptable)\n")
        
        # Pass/Fail for prompt
        prompt_pass = evaluate_prompt_pass(prompt_results)
        if prompt_pass:
            report.append("\n**Result**: ✅ PASSED\n")
        else:
            report.append("\n**Result**: ❌ FAILED\n")
    
    # Overall summary
    report.append("\n## Overall Summary\n")
    
    overall_pass = not any_prompt_leak and als_effects_observed
    
    if overall_pass:
        report.append("### ✅ OVERALL: PASSED\n")
        report.append("- No prompt leakage detected")
        report.append("- ALS effects clearly observed in grounded search")
        report.append("- Geographic steering achieved without location words in prompts")
    else:
        report.append("### ❌ OVERALL: FAILED\n")
        if any_prompt_leak:
            report.append("- **Critical**: Prompt leakage detected - remove location words from prompts")
        if not als_effects_observed:
            report.append("- **Issue**: ALS effects not clearly demonstrated")
    
    # Write report
    with open(report_path, 'w') as f:
        f.write('\n'.join(report))


def find_result(results: List[Dict], vendor: str, grounded: bool, als: str) -> Optional[Dict]:
    """Find a specific result in the list"""
    for r in results:
        if (r['vendor'] == vendor and 
            r['grounded'] == grounded and 
            r['als_name'] == als):
            return r
    return None


def analyze_als_effects(results: List[Dict]) -> bool:
    """Analyze if ALS effects are clearly visible"""
    effects_seen = False
    
    # Look for Vertex grounded results
    vertex_grounded = [r for r in results if r['vendor'] == 'vertex' and r['grounded']]
    
    for prompt_name in PROMPTS.keys():
        prompt_results = [r for r in vertex_grounded if r['prompt_name'] == prompt_name]
        
        # Compare NONE baseline with CH/DE/US
        baseline = find_result(prompt_results, 'vertex', True, 'NONE')
        ch_result = find_result(prompt_results, 'vertex', True, 'CH')
        de_result = find_result(prompt_results, 'vertex', True, 'DE')
        
        if baseline and ch_result and de_result:
            # Check if CH has more .ch domains than baseline
            ch_effect = check_als_effect(
                baseline.get('tld_counts', {}),
                ch_result.get('tld_counts', {}),
                '.ch'
            )
            # Check if DE has more .de domains than baseline
            de_effect = check_als_effect(
                baseline.get('tld_counts', {}),
                de_result.get('tld_counts', {}),
                '.de'
            )
            
            if ch_effect or de_effect:
                effects_seen = True
                break
    
    return effects_seen


def analyze_prompt_results(results: List[Dict]) -> str:
    """Generate analysis text for a prompt's results"""
    analysis = []
    
    # Check Vertex grounded ALS effects
    vertex_results = {
        als: find_result(results, 'vertex', True, als)
        for als in ['NONE', 'CH', 'DE', 'US']
    }
    
    if all(vertex_results.values()):
        # Compare TLD distributions
        baseline_tlds = vertex_results['NONE'].get('tld_counts', {})
        ch_tlds = vertex_results['CH'].get('tld_counts', {})
        de_tlds = vertex_results['DE'].get('tld_counts', {})
        us_tlds = vertex_results['US'].get('tld_counts', {})
        
        # Check for ALS-driven shifts
        ch_shift = ch_tlds.get('.ch', 0) > baseline_tlds.get('.ch', 0)
        de_shift = de_tlds.get('.de', 0) > baseline_tlds.get('.de', 0)
        us_shift = us_tlds.get('.com', 0) > baseline_tlds.get('.com', 0)
        
        if ch_shift or de_shift:
            analysis.append("**ALS effects observed**: Clear geographic steering in citation sources.")
            if ch_shift:
                analysis.append(f"- CH context increased .ch domains ({ch_tlds.get('.ch', 0)} vs baseline {baseline_tlds.get('.ch', 0)})")
            if de_shift:
                analysis.append(f"- DE context increased .de domains ({de_tlds.get('.de', 0)} vs baseline {baseline_tlds.get('.de', 0)})")
        else:
            analysis.append("**Limited ALS effects**: Geographic steering not clearly demonstrated in TLD distribution.")
    else:
        analysis.append("**Incomplete data**: Not all Vertex grounded runs completed successfully.")
    
    # Check OpenAI behavior
    openai_results = [r for r in results if r['vendor'] == 'openai' and r['grounded']]
    if openai_results:
        no_tools_count = sum(1 for r in openai_results if r.get('tool_status') == 'NO_TOOLS')
        if no_tools_count > 0:
            analysis.append(f"\n**OpenAI Note**: {no_tools_count}/{len(openai_results)} runs did not invoke tools (expected behavior).")
    
    return '\n'.join(analysis) if analysis else "No significant patterns observed."


def evaluate_prompt_pass(results: List[Dict]) -> bool:
    """Evaluate if a prompt passes all criteria"""
    # No prompt leakage
    if any(r.get('prompt_leak_detected', False) for r in results):
        return False
    
    # At least some grounded results should be effective
    grounded_results = [r for r in results if r['grounded'] and r['vendor'] == 'vertex']
    if grounded_results:
        effective_count = sum(1 for r in grounded_results if r.get('grounded_effective', False))
        if effective_count == 0:
            return False
    
    return True


if __name__ == "__main__":
    asyncio.run(run_matrix())