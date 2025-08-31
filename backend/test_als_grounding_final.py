#!/usr/bin/env python3
"""
Comprehensive ALS + Grounding Test Suite
Tests US and DE with/without ALS, all grounding modes
Saves full responses and citations to MD file
"""
import asyncio
import json
import logging
import sys
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, LLMResponse, ALSContext
from app.llm.domain_authority import authority_scorer

# Test configuration
TEST_PROMPT = "As of 2025-08-31, list 3 headlines about Tesla stock from authoritative sources and include URLs."
COUNTRIES = ["US", "DE"]
VENDORS = ["openai", "vertex"]
MODELS = {
    "openai": "gpt-5",
    "vertex": "publishers/google/models/gemini-2.0-flash"
}

class TestResult:
    """Container for test results"""
    def __init__(self, test_id: str, country: str, vendor: str, 
                 has_als: bool, grounded: bool, grounding_mode: str):
        self.test_id = test_id
        self.country = country
        self.vendor = vendor
        self.has_als = has_als
        self.grounded = grounded
        self.grounding_mode = grounding_mode
        self.response = None
        self.error = None
        self.metadata = {}
        self.citations = []
        self.duration_ms = 0
        self.authority_metrics = {}

def create_als_context(country: str) -> ALSContext:
    """Create ALS context for a country"""
    locales = {
        "US": "en-US",
        "DE": "de-DE"
    }
    
    # Create country-specific ALS block
    als_blocks = {
        "US": "Location: United States. Local time: EST. News sources prioritize US coverage.",
        "DE": "Location: Germany. Local time: CET. News sources prioritize German coverage."
    }
    
    return ALSContext(
        country_code=country,
        locale=locales.get(country, f"en-{country}"),
        als_block=als_blocks.get(country, f"Location: {country}")
    )

async def run_single_test(
    adapter: UnifiedLLMAdapter,
    vendor: str,
    country: str,
    has_als: bool,
    grounded: bool,
    grounding_mode: str = "AUTO"
) -> TestResult:
    """Run a single test configuration"""
    
    test_id = f"{vendor}_{country}_{'ALS' if has_als else 'NoALS'}_{grounding_mode if grounded else 'Ungrounded'}"
    result = TestResult(test_id, country, vendor, has_als, grounded, grounding_mode)
    
    try:
        # Build request
        request = LLMRequest(
            messages=[
                {"role": "user", "content": TEST_PROMPT}
            ],
            vendor=vendor,
            model=MODELS[vendor],
            grounded=grounded,
            json_mode=False,
            max_tokens=500,
            template_id=f"test_{test_id}",
            run_id=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{test_id}"
        )
        
        # Add ALS context if needed
        if has_als:
            request.als_context = create_als_context(country)
        
        # Add grounding mode to meta
        if grounded:
            request.meta = {"grounding_mode": grounding_mode}
        
        # Execute request
        start_time = datetime.now()
        response = await adapter.complete(request)
        duration = (datetime.now() - start_time).total_seconds() * 1000
        
        result.response = response
        result.duration_ms = duration
        
        # Extract metadata
        if hasattr(response, 'metadata'):
            result.metadata = response.metadata
            result.citations = response.metadata.get('citations', [])
            
            # Calculate authority metrics if we have citations
            if result.citations:
                result.authority_metrics = authority_scorer.score_citations(result.citations)
        
        logger.info(f"✓ Test {test_id} completed in {duration:.0f}ms")
        
    except Exception as e:
        result.error = str(e)
        logger.error(f"✗ Test {test_id} failed: {e}")
    
    return result

async def run_all_tests() -> List[TestResult]:
    """Run all test combinations"""
    adapter = UnifiedLLMAdapter()
    results = []
    
    for country in COUNTRIES:
        for vendor in VENDORS:
            # Test matrix for each vendor/country
            test_configs = [
                # Ungrounded tests
                (False, False, "N/A"),  # No ALS, Ungrounded
                (True, False, "N/A"),   # With ALS, Ungrounded
                
                # Grounded tests (Preferred/AUTO mode)
                (False, True, "AUTO"),  # No ALS, Grounded AUTO
                (True, True, "AUTO"),   # With ALS, Grounded AUTO
                
                # Grounded tests (Required mode) - only for verification
                (False, True, "REQUIRED"),  # No ALS, Grounded REQUIRED
                (True, True, "REQUIRED"),   # With ALS, Grounded REQUIRED
            ]
            
            for has_als, grounded, mode in test_configs:
                print(f"\nRunning: {vendor} / {country} / {'ALS' if has_als else 'NoALS'} / {mode if grounded else 'Ungrounded'}")
                result = await run_single_test(
                    adapter, vendor, country, has_als, grounded, mode
                )
                results.append(result)
                
                # Small delay between tests
                await asyncio.sleep(1)
    
    return results

def format_citations(citations: List[Dict]) -> str:
    """Format citations for markdown"""
    if not citations:
        return "No citations"
    
    lines = []
    for i, cit in enumerate(citations, 1):
        url = cit.get('url', 'N/A')
        title = cit.get('title', 'No title')
        snippet = cit.get('snippet', '')
        
        lines.append(f"{i}. **{title}**")
        lines.append(f"   - URL: `{url}`")
        if snippet:
            snippet_preview = snippet[:150] + "..." if len(snippet) > 150 else snippet
            lines.append(f"   - Snippet: {snippet_preview}")
    
    return "\n".join(lines)

def save_results_to_markdown(results: List[TestResult], filename: str):
    """Save all results to a markdown file"""
    
    md_lines = [
        f"# ALS + Grounding Test Results",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Prompt:** \"{TEST_PROMPT}\"",
        "",
        "## Summary Table",
        "",
        "| Test ID | Country | Vendor | ALS | Grounded | Mode | Success | Grounded Effective | Citations | Duration |",
        "|---------|---------|--------|-----|----------|------|---------|-------------------|-----------|----------|"
    ]
    
    # Add summary rows
    for r in results:
        success = "✓" if not r.error else "✗"
        grounded_eff = r.metadata.get('grounded_effective', False) if r.metadata else False
        grounded_eff_str = "✓" if grounded_eff else "✗" if r.grounded else "N/A"
        citation_count = len(r.citations)
        
        md_lines.append(
            f"| {r.test_id} | {r.country} | {r.vendor} | "
            f"{'✓' if r.has_als else '✗'} | {'✓' if r.grounded else '✗'} | "
            f"{r.grounding_mode} | {success} | {grounded_eff_str} | "
            f"{citation_count} | {r.duration_ms:.0f}ms |"
        )
    
    md_lines.extend([
        "",
        "---",
        "",
        "## Detailed Results",
        ""
    ])
    
    # Group by country
    for country in COUNTRIES:
        md_lines.append(f"### {country} Results")
        md_lines.append("")
        
        country_results = [r for r in results if r.country == country]
        
        for r in country_results:
            md_lines.append(f"#### Test: {r.test_id}")
            md_lines.append("")
            
            # Test configuration
            md_lines.append("**Configuration:**")
            md_lines.append(f"- Country: {r.country}")
            md_lines.append(f"- Vendor: {r.vendor}")
            md_lines.append(f"- ALS: {'Enabled' if r.has_als else 'Disabled'}")
            md_lines.append(f"- Grounded: {'Yes' if r.grounded else 'No'}")
            if r.grounded:
                md_lines.append(f"- Grounding Mode: {r.grounding_mode}")
            md_lines.append(f"- Duration: {r.duration_ms:.0f}ms")
            md_lines.append("")
            
            # Error or Response
            if r.error:
                md_lines.append("**Error:**")
                md_lines.append(f"```")
                md_lines.append(r.error)
                md_lines.append(f"```")
            else:
                # Metadata
                md_lines.append("**Metadata:**")
                md_lines.append(f"- Grounded Effective: {r.metadata.get('grounded_effective', False)}")
                md_lines.append(f"- Tool Call Count: {r.metadata.get('tool_call_count', 0)}")
                md_lines.append(f"- Two Step Used: {r.metadata.get('two_step_used', False)}")
                
                # ALS metadata
                if r.has_als:
                    als_present = r.metadata.get('als_present', False)
                    als_sha = r.metadata.get('als_block_sha256', 'N/A')[:16] + "..."
                    md_lines.append(f"- ALS Present: {als_present}")
                    md_lines.append(f"- ALS SHA256: {als_sha}")
                
                md_lines.append("")
                
                # Citations
                md_lines.append("**Citations:**")
                md_lines.append(format_citations(r.citations))
                
                # Authority metrics
                if r.authority_metrics and r.authority_metrics.get('total_citations', 0) > 0:
                    md_lines.append("")
                    md_lines.append("**Authority Analysis:**")
                    metrics = r.authority_metrics
                    md_lines.append(f"- Authority Score: {metrics['authority_score']}/100")
                    md_lines.append(f"- Tier-1 Sources: {metrics['tier_1_count']}/{metrics['total_citations']} ({metrics['tier_1_percentage']}%)")
                    md_lines.append(f"- Premium Sources (Tier 1+2): {metrics['premium_percentage']}%")
                    if metrics['penalty_percentage'] > 0:
                        md_lines.append(f"- ⚠️ Low-quality Sources: {metrics['penalty_percentage']}%")
                
                md_lines.append("")
                
                # Response content
                if r.response and r.response.content:
                    md_lines.append("**Response:**")
                    md_lines.append("```")
                    # Limit response to 1000 chars for readability
                    content = r.response.content
                    if len(content) > 1000:
                        content = content[:1000] + "\n... [truncated]"
                    md_lines.append(content)
                    md_lines.append("```")
            
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
    
    # Statistics section
    md_lines.append("## Statistics")
    md_lines.append("")
    
    # Success rate
    total = len(results)
    successful = len([r for r in results if not r.error])
    md_lines.append(f"- Total Tests: {total}")
    md_lines.append(f"- Successful: {successful}")
    md_lines.append(f"- Failed: {total - successful}")
    md_lines.append(f"- Success Rate: {(successful/total*100):.1f}%")
    md_lines.append("")
    
    # Grounding effectiveness
    grounded_tests = [r for r in results if r.grounded and not r.error]
    if grounded_tests:
        effective = len([r for r in grounded_tests if r.metadata.get('grounded_effective', False)])
        md_lines.append(f"- Grounded Tests: {len(grounded_tests)}")
        md_lines.append(f"- Effectively Grounded: {effective}")
        md_lines.append(f"- Grounding Success Rate: {(effective/len(grounded_tests)*100):.1f}%")
        md_lines.append("")
    
    # Citations analysis
    tests_with_citations = [r for r in results if r.citations]
    if tests_with_citations:
        total_citations = sum(len(r.citations) for r in tests_with_citations)
        avg_citations = total_citations / len(tests_with_citations)
        md_lines.append(f"- Tests with Citations: {len(tests_with_citations)}")
        md_lines.append(f"- Total Citations: {total_citations}")
        md_lines.append(f"- Average Citations per Test: {avg_citations:.1f}")
    
    # Write to file
    with open(filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))
    
    print(f"\n✓ Results saved to {filename}")

async def main():
    """Main test runner"""
    print("="*60)
    print("ALS + GROUNDING COMPREHENSIVE TEST SUITE")
    print("="*60)
    print(f"Testing: {', '.join(COUNTRIES)}")
    print(f"Vendors: {', '.join(VENDORS)}")
    print(f"Prompt: \"{TEST_PROMPT}\"")
    print("="*60)
    
    # Run all tests
    results = await run_all_tests()
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ALS_GROUNDING_RESULTS_{timestamp}.md"
    
    # Save to markdown
    save_results_to_markdown(results, filename)
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    total = len(results)
    successful = len([r for r in results if not r.error])
    
    print(f"Total Tests: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {total - successful}")
    
    # Group by vendor
    for vendor in VENDORS:
        vendor_results = [r for r in results if r.vendor == vendor]
        vendor_success = len([r for r in vendor_results if not r.error])
        print(f"\n{vendor.upper()}:")
        print(f"  Tests: {len(vendor_results)}")
        print(f"  Success: {vendor_success}/{len(vendor_results)}")
        
        # Check grounding
        grounded = [r for r in vendor_results if r.grounded and not r.error]
        if grounded:
            effective = len([r for r in grounded if r.metadata.get('grounded_effective', False)])
            print(f"  Grounded Effective: {effective}/{len(grounded)}")
    
    print("\n" + "="*60)
    print(f"Full results saved to: {filename}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())