#!/usr/bin/env python3
"""
Enhanced ALS Ambient Matrix Test with Clear QA Reporting
Improvements:
- Clear tags for (provider, model, grounded_mode_sent, grounded_effective)
- Better visibility of REQUIRED mode failures
- Explicit display of grounding intent vs outcome
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from tests.util.als_ambient_utils import *

# Test prompts (location-neutral)
PROMPTS = {
    "evidence": (
        "As of August 31, 2025, summarize the most credible peer-reviewed findings "
        "(≤12 months) on creatine monohydrate for healthy adults. Include study design, "
        "sample size, primary outcomes, limitations, and provide URLs + publish dates. "
        "End with TOOL_STATUS: USED_WEB_SEARCH or NO_TOOLS."
    ),
    "brand_cross_check": (
        "Search for claims made by the supplement brand 'Life Extension' about NAD+ "
        "precursors on their website or marketing materials. Cross-check these claims "
        "against recent scientific literature. End with TOOL_STATUS."
    ),
    "press_scan": (
        "Find recent health news articles (within 30 days) covering vitamin D research "
        "or recommendations. Include source, date, and key findings. End with TOOL_STATUS."
    )
}

# Test matrix configuration
TEST_MATRIX = [
    ("vertex", "publishers/google/models/gemini-2.5-pro", True, "AUTO"),
    ("vertex", "publishers/google/models/gemini-2.5-pro", True, "REQUIRED"),
    ("openai", "gpt-5", True, "AUTO"),
    ("openai", "gpt-5", True, "REQUIRED"),
    ("vertex", "publishers/google/models/gemini-2.5-pro", False, None),
    ("openai", "gpt-5", False, None),
]

ALS_CONFIGS = [
    ("NONE", None),
    ("CH", ALSContext(country_code="CH", locale="de-CH", als_block="")),
    ("DE", ALSContext(country_code="DE", locale="de-DE", als_block="")),
    ("US", ALSContext(country_code="US", locale="en-US", als_block=""))
]


def format_run_tag(result: Dict) -> str:
    """
    Format a clear run tag showing key parameters and outcomes
    Returns: "provider:model:mode_sent→effective"
    """
    provider = result.get('vendor', 'unknown')
    model = result.get('model', 'unknown').split('/')[-1]  # Short model name
    mode_sent = result.get('mode', 'NONE')
    grounded_sent = result.get('grounded', False)
    grounded_effective = result.get('grounded_effective', False)
    
    # Build status indicator
    if not grounded_sent:
        status = "ungrounded"
    elif mode_sent == "REQUIRED" and not grounded_effective:
        status = "REQUIRED_FAILED"
    elif mode_sent == "AUTO" and not grounded_effective:
        status = "auto_no_tools"
    elif grounded_effective:
        status = "grounded_ok"
    else:
        status = "unknown"
    
    return f"{provider}:{model}:{mode_sent}→{status}"


def generate_enhanced_report(results: List[Dict], stats: Dict, report_path: str):
    """Generate enhanced QA report with clear run tags"""
    
    report = []
    report.append("# ALS Ambient QA Report (Enhanced)")
    report.append(f"Generated: {datetime.now().isoformat()}\n")
    
    # Executive Summary
    report.append("## Executive Summary\n")
    
    # Check for prompt leaks
    any_prompt_leak = any(r.get('prompt_leak_detected', False) for r in results)
    if any_prompt_leak:
        report.append("❌ **FAILED**: Prompt leakage detected - location words found in user prompts\n")
    else:
        report.append("✅ **PASSED**: No prompt leakage - all prompts are location-neutral\n")
    
    # Count REQUIRED mode failures
    required_failures = [r for r in results if 
                         r.get('mode') == 'REQUIRED' and 
                         r.get('grounded') and 
                         not r.get('grounded_effective', False)]
    
    if required_failures:
        report.append(f"⚠️ **REQUIRED Mode Issues**: {len(required_failures)} runs failed to invoke tools despite REQUIRED mode")
        report.append("   (This is expected for OpenAI which cannot force tool usage)\n")
    
    # Stats
    report.append(f"**Stats**: {stats['total_runs']} runs | {stats['grounded_runs']} grounded | ")
    report.append(f"{len(required_failures)} REQUIRED failures\n")
    
    # Detailed Results by Prompt
    for prompt_name in PROMPTS.keys():
        report.append(f"\n## Prompt: {prompt_name}\n")
        
        # Filter results for this prompt
        prompt_results = [r for r in results if r['prompt_name'] == prompt_name]
        
        # Enhanced table with clear tags
        report.append("### Run Details\n")
        report.append("| Run Tag | ALS | Citations | TLDs | Status | Notes |")
        report.append("|---------|-----|-----------|------|--------|-------|")
        
        for result in prompt_results:
            tag = format_run_tag(result)
            als = result.get('als_name', 'NONE')
            citations = result.get('citations_count', 0)
            tld_summary = format_tld_summary(result.get('tld_counts', {}), 3)
            
            # Determine status and notes
            status = "✅" if result.get('grounded_effective') else "❌"
            notes = []
            
            if result.get('status') == 'error':
                status = "🔥"
                notes.append(f"Error: {result.get('error', 'Unknown')[:30]}")
            elif result.get('mode') == 'REQUIRED' and not result.get('grounded_effective'):
                notes.append("REQUIRED not met")
                if result.get('vendor') == 'openai':
                    notes.append("(OpenAI can't force)")
            elif result.get('grounded') and not result.get('grounded_effective'):
                notes.append("Tools not invoked")
            
            report.append(f"| `{tag}` | {als} | {citations} | {tld_summary} | {status} | {'; '.join(notes)} |")
        
        # Grounding Mode Analysis
        report.append("\n### Grounding Mode Analysis\n")
        
        # Group by mode sent
        for mode in ['AUTO', 'REQUIRED', None]:
            mode_results = [r for r in prompt_results if r.get('mode') == mode]
            if mode_results:
                effective_count = sum(1 for r in mode_results if r.get('grounded_effective'))
                total = len(mode_results)
                rate = (effective_count / total * 100) if total > 0 else 0
                
                report.append(f"- **{mode or 'UNGROUNDED'}**: {effective_count}/{total} effective ({rate:.0f}%)")
                
                # Special note for REQUIRED failures
                if mode == 'REQUIRED':
                    openai_required = [r for r in mode_results if r.get('vendor') == 'openai']
                    if openai_required:
                        openai_effective = sum(1 for r in openai_required if r.get('grounded_effective'))
                        report.append(f"  - OpenAI: {openai_effective}/{len(openai_required)} "
                                    f"(cannot force tools, will fail in router post-validation)")
        
        # ALS Effects
        report.append("\n### ALS Effects\n")
        
        # Compare baseline to ALS contexts
        baseline_results = [r for r in prompt_results if r.get('als_name') == 'NONE' and r.get('grounded_effective')]
        
        for als_name in ['CH', 'DE', 'US']:
            als_results = [r for r in prompt_results if r.get('als_name') == als_name and r.get('grounded_effective')]
            
            if baseline_results and als_results:
                # Compare TLD distributions
                baseline_tlds = Counter()
                for r in baseline_results:
                    baseline_tlds.update(r.get('tld_counts', {}))
                
                als_tlds = Counter()
                for r in als_results:
                    als_tlds.update(r.get('tld_counts', {}))
                
                # Check for local domain increase
                local_tld = f'.{als_name.lower()}' if als_name != 'US' else '.com'
                baseline_local = baseline_tlds.get(local_tld, 0)
                als_local = als_tlds.get(local_tld, 0)
                
                if als_local > baseline_local:
                    report.append(f"- **{als_name}**: ✅ Increased {local_tld} domains ({baseline_local}→{als_local})")
                else:
                    report.append(f"- **{als_name}**: ⚠️ No increase in {local_tld} domains")
    
    # Error Analysis
    errors = [r for r in results if r.get('status') == 'error']
    if errors:
        report.append("\n## Error Analysis\n")
        
        # Group errors by type
        error_types = Counter()
        for e in errors:
            error_msg = e.get('error', 'Unknown')
            if 'GROUNDING_REQUIRED_FAILED' in error_msg:
                error_types['REQUIRED validation failure'] += 1
            elif 'GROUNDING_NOT_SUPPORTED' in error_msg:
                error_types['Grounding not supported'] += 1
            elif 'timeout' in error_msg.lower():
                error_types['Timeout'] += 1
            else:
                error_types['Other'] += 1
        
        for error_type, count in error_types.most_common():
            report.append(f"- {error_type}: {count} occurrences")
    
    # Overall Summary
    report.append("\n## Overall Summary\n")
    
    # Determine pass/fail
    critical_issues = []
    warnings = []
    
    if any_prompt_leak:
        critical_issues.append("Prompt leakage detected")
    
    if required_failures:
        # Check if all are OpenAI (expected)
        all_openai = all(r.get('vendor') == 'openai' for r in required_failures)
        if all_openai:
            warnings.append(f"{len(required_failures)} OpenAI REQUIRED failures (expected - cannot force tools)")
        else:
            critical_issues.append(f"{len(required_failures)} REQUIRED mode failures including non-OpenAI providers")
    
    if critical_issues:
        report.append("### ❌ OVERALL: FAILED\n")
        for issue in critical_issues:
            report.append(f"- **Critical**: {issue}")
    elif warnings:
        report.append("### ⚠️ OVERALL: PASSED WITH WARNINGS\n")
        for warning in warnings:
            report.append(f"- **Warning**: {warning}")
    else:
        report.append("### ✅ OVERALL: PASSED\n")
        report.append("- No prompt leakage")
        report.append("- All grounding modes working as expected")
    
    # Key for interpreting run tags
    report.append("\n## Run Tag Format\n")
    report.append("```")
    report.append("provider:model:mode_sent→status")
    report.append("")
    report.append("Status values:")
    report.append("- grounded_ok: Tools successfully invoked")
    report.append("- auto_no_tools: AUTO mode, tools not invoked (model choice)")
    report.append("- REQUIRED_FAILED: REQUIRED mode but tools not invoked")
    report.append("- ungrounded: Request not configured for grounding")
    report.append("```")
    
    # Write report
    with open(report_path, 'w') as f:
        f.write('\n'.join(report))
    
    print(f"\n✓ Enhanced report saved: {report_path}")


# Example usage in test runner
async def run_single_test_enhanced(prompt_name, prompt_text, vendor, model, grounded, mode, als_name, als_context):
    """Run a single test with enhanced metadata capture"""
    
    adapter = UnifiedLLMAdapter()
    
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
    
    # Initialize result with complete metadata
    result = {
        "prompt_name": prompt_name,
        "vendor": vendor,
        "model": model,
        "grounded": grounded,  # What we requested
        "mode": mode,  # What mode we sent
        "als_name": als_name,
        "als_country": als_context.country_code if als_context else None,
        "als_locale": als_context.locale if als_context else None,
        "prompt_leak_detected": check_prompt_leak(prompt_text)
    }
    
    try:
        response = await adapter.complete(request)
        
        # Capture both what was sent and what actually happened
        metadata = response.metadata if hasattr(response, 'metadata') else {}
        
        result.update({
            "status": "success",
            "grounded_effective": metadata.get('grounded_effective', False),  # What actually happened
            "grounding_attempted": metadata.get('grounding_attempted', False),
            "tool_call_count": metadata.get('tool_call_count', 0),
            "citations_count": len(metadata.get('citations', [])),
            "tld_counts": extract_tld_counts(metadata.get('citations', [])),
            "response_preview": str(response.content)[:200] if hasattr(response, 'content') else ""
        })
        
    except Exception as e:
        error_msg = str(e)
        result.update({
            "status": "error",
            "error": error_msg,
            "grounded_effective": False,
            "is_required_failure": "GROUNDING_REQUIRED" in error_msg
        })
    
    return result


if __name__ == "__main__":
    # Example of how to use the enhanced reporting
    print("Enhanced ALS Ambient Matrix Test")
    print("This version provides clear visibility of:")
    print("- Provider and model for each run")
    print("- Grounding mode sent vs. effective outcome")
    print("- REQUIRED mode failures (especially for OpenAI)")
    print("- Clear run tags for easy issue identification")