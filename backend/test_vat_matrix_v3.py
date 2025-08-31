#!/usr/bin/env python3
"""
VAT Rate Test v3 - Final version with all ChatGPT improvements:
1. Grounded-Required for QA ceiling
2. Grounded-Preferred with provoker line
3. Citations extraction and display
4. Proper timeouts and no JSON mode
"""
import asyncio
import os
import sys
import json
from datetime import datetime, timezone
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

# Apply ChatGPT's fixes:
# 1. Disable preview compatibility to force web_search (not web_search_preview)
os.environ["ALLOW_PREVIEW_COMPAT"] = "false"

# 2. Give grounded runs breathing room (tool spin-up + synthesis)
os.environ["OPENAI_READ_TIMEOUT_MS"] = "120000"  # 120 seconds for grounded
os.environ["LLM_TIMEOUT_GR"] = "180"  # 180 seconds for grounded
os.environ["LLM_TIMEOUT_UN"] = "60"   # 60 seconds for ungrounded

# Disable proxies for direct testing
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

def _top2_citations(citations):
    """Format top 2 citations for display"""
    if not isinstance(citations, list) or not citations:
        return ""
    items = []
    for c in citations[:2]:
        url = c.get("url") or ""
        title = c.get("title") or ""
        if url:
            # Truncate URL for display
            display_url = url[:50] + "..." if len(url) > 50 else url
            items.append(f"[{title or 'source'}]({display_url})" if title else display_url)
        elif title:
            items.append(title)
    return " · ".join(items)

def build_request(vendor, model, country, mode):
    """Build request with proper grounding mode and provoker"""
    base_prompt = "What is the VAT rate?"
    messages = [{"role": "user", "content": base_prompt}]
    
    # Always measure "real user" behavior → keep JSON mode OFF for VAT probes
    req = LLMRequest(
        vendor=vendor,
        model=model,
        messages=messages,
        temperature=0.7,
        grounded=False,  # Will be set based on mode
        als_context={'country_code': country, 'locale': f"en-{country}"}
        # NO json_mode - let it be text for retries to work
    )
    
    # Set max_tokens based on vendor and mode
    if vendor == "vertex" and mode == "UNGROUNDED":
        req.max_tokens = 1500  # Increased for verbosity
    else:
        req.max_tokens = 1000
    
    if mode == "GROUNDED_PREFERRED":
        req.grounded = True
        # Gentle "provoker" line per guide – nudges search without forcing it
        today = datetime.now(timezone.utc).date()
        req.messages[-1]["content"] += f"\n\nAs of today ({today}), include an official source URL."
        # Let the adapter default tool_choice=auto
        if vendor == "openai":
            req.tool_choice = "auto"
        req.meta = {"grounding_mode": "AUTO"}
        
    elif mode == "GROUNDED_REQUIRED":
        req.grounded = True
        # Required = QA ceiling, fail-closed without evidence
        if vendor == "openai":
            req.tool_choice = "required"
        req.meta = {"grounding_mode": "REQUIRED"}
    
    return req

async def test_vat_matrix_v3():
    """Test VAT rate question with all improvements"""
    
    adapter = UnifiedLLMAdapter()
    
    # Test configurations with all three modes
    configs = []
    
    for vendor_name in ["OpenAI", "Vertex"]:
        for country in ["US", "DE"]:
            # Add all three modes
            configs.append((vendor_name, country, "UNGROUNDED"))
            configs.append((vendor_name, country, "GROUNDED_PREFERRED"))
            
            # Only add Required mode for OpenAI (Vertex doesn't have required mode)
            if vendor_name == "OpenAI":
                configs.append((vendor_name, country, "GROUNDED_REQUIRED"))
    
    results = []
    
    for vendor_name, country, mode in configs:
        config_name = f"{vendor_name} {country} {mode.replace('_', '-')}"
        print(f"\n{'='*60}")
        print(f"Testing: {config_name}")
        print(f"{'='*60}")
        
        # Set up request
        vendor = "openai" if vendor_name == "OpenAI" else "vertex"
        model = "gpt-5" if vendor == "openai" else "publishers/google/models/gemini-2.5-pro"
        
        request = build_request(vendor, model, country, mode)
        
        try:
            print(f"  Vendor: {vendor}")
            print(f"  Model: {model}")
            print(f"  Country: {country}")
            print(f"  Mode: {mode}")
            print(f"  Max tokens: {request.max_tokens}")
            if mode == "GROUNDED_PREFERRED":
                print(f"  Prompt: With provoker line")
            elif mode == "GROUNDED_REQUIRED":
                print(f"  Prompt: Standard (Required mode)")
            else:
                print(f"  Prompt: Standard")
            
            response = await adapter.complete(request)
            
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "mode": mode,
                "success": response.success,
                "content": response.content or "",
                "content_length": len(response.content) if response.content else 0,
                "latency_ms": response.latency_ms,
                "usage": response.usage or {},
                "metadata": response.metadata or {}
            }
            
            # Extract key metadata
            if response.metadata:
                result["grounded_effective"] = response.metadata.get("grounded_effective", False)
                result["tool_calls"] = response.metadata.get("tool_call_count", 0)
                result["citations"] = response.metadata.get("citations", [])
                result["citations_count"] = len(result["citations"])
                result["finish_reason"] = response.metadata.get("finish_reason", "")
                result["retry_attempted"] = response.metadata.get("retry_attempted", False)
                result["retry_successful"] = response.metadata.get("retry_successful", False)
                result["retry_reason"] = response.metadata.get("retry_reason", "")
                result["als_sha256"] = response.metadata.get("als_sha256", "")[:16] + "..." if response.metadata.get("als_sha256") else ""
            else:
                result["citations"] = []
                result["citations_count"] = 0
            
            results.append(result)
            
            print(f"\n  ✅ Success: {response.success}")
            print(f"  Content length: {result['content_length']} chars")
            print(f"  Latency: {response.latency_ms}ms")
            
            if request.grounded:
                print(f"  Grounded effective: {result.get('grounded_effective', False)}")
                print(f"  Tool calls: {result.get('tool_calls', 0)}")
                print(f"  Citations: {result.get('citations_count', 0)}")
                
                # Special handling for Required mode
                if mode == "GROUNDED_REQUIRED" and result.get('tool_calls', 0) == 0:
                    print(f"  ⚠️ WARNING: Grounded-Required had no tool calls!")
            
            if result.get('retry_attempted'):
                print(f"  Retry: {result.get('retry_reason', 'Unknown reason')}")
                print(f"  Retry successful: {result.get('retry_successful', False)}")
            
            # Show first 200 chars of response
            preview = result['content'][:200] + "..." if len(result['content']) > 200 else result['content']
            print(f"\n  Response preview: {preview}")
            
        except Exception as e:
            error_msg = str(e)
            # Check if this is an expected Required mode failure for unsupported grounding
            is_grounding_unsupported = (
                mode == "GROUNDED_REQUIRED" and 
                "GROUNDING_NOT_SUPPORTED" in error_msg
            )
            
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "mode": mode,
                "success": False,
                "error": error_msg,
                "content": "",
                "content_length": 0,
                "citations": [],
                "citations_count": 0,
                "is_na": is_grounding_unsupported  # Mark as N/A for unsupported combos
            }
            results.append(result)
            
            if is_grounding_unsupported:
                print(f"\n  ℹ️ N/A: Grounding not supported for this model (Required mode)")
            else:
                print(f"\n  ❌ Error: {e}")
        
        # Rate limiting
        await asyncio.sleep(2)
    
    # Generate markdown report
    markdown = f"""# VAT Rate Test v3 - Complete Matrix with Citations

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Base Prompt**: "What is the VAT rate?"
**Provoker (Preferred)**: "As of today (YYYY-MM-DD), include an official source URL."

## Configuration

- ALLOW_PREVIEW_COMPAT: false (forces web_search, not web_search_preview)
- OPENAI_READ_TIMEOUT_MS: 120000 (120 seconds)
- LLM_TIMEOUT_GR: 180 seconds
- LLM_TIMEOUT_UN: 60 seconds
- JSON mode: DISABLED (allows plain-text retries)
- Vertex ungrounded tokens: 1500 (increased for verbosity)
- OpenAI/Vertex grounded tokens: 1000

## Summary

Total Tests: {len(results)}
Successful: {sum(1 for r in results if r.get('success', False))}
Failed: {sum(1 for r in results if not r.get('success', False))}

## Results Table

| Vendor | Country | Mode | Success | Tool Calls | Citations | Top 2 Citations | Tokens | Content Length |
|--------|---------|------|---------|------------|-----------|-----------------|--------|----------------|
"""
    
    for result in results:
        vendor = result['vendor']
        country = result['country']
        mode = result['mode'].replace('_', '-')
        
        # Check if this is N/A (unsupported grounding)
        if result.get('is_na'):
            success = "N/A"
            tool_calls = "—"
            citations_count = "—"
            top2 = "Tool unsupported"
            tokens = "—"
            content_len = "—"
        else:
            success = "✅" if result.get('success') else "❌"
            tool_calls = result.get('tool_calls', 0)
            citations_count = result.get('citations_count', 0)
            top2 = _top2_citations(result.get('citations', []))
            tokens = result.get('usage', {}).get('completion_tokens', 'N/A')
            content_len = result['content_length']
        
        markdown += f"| {vendor} | {country} | {mode} | {success} | {tool_calls} | {citations_count} | {top2 or 'None'} | {tokens} | {content_len} |\n"
    
    markdown += """

## Grounding Analysis

### OpenAI Grounding Modes
"""
    
    # Analyze OpenAI grounding modes
    openai_ungrounded = [r for r in results if r['vendor'] == 'OpenAI' and r['mode'] == 'UNGROUNDED']
    openai_preferred = [r for r in results if r['vendor'] == 'OpenAI' and r['mode'] == 'GROUNDED_PREFERRED']
    openai_required = [r for r in results if r['vendor'] == 'OpenAI' and r['mode'] == 'GROUNDED_REQUIRED']
    
    if openai_ungrounded:
        avg_len = sum(r['content_length'] for r in openai_ungrounded) / len(openai_ungrounded)
        markdown += f"- **Ungrounded**: {len(openai_ungrounded)} tests, avg {avg_len:.0f} chars\n"
    
    if openai_preferred:
        effective = sum(1 for r in openai_preferred if r.get('grounded_effective'))
        with_tools = sum(1 for r in openai_preferred if r.get('tool_calls', 0) > 0)
        with_citations = sum(1 for r in openai_preferred if r.get('citations_count', 0) > 0)
        avg_len = sum(r['content_length'] for r in openai_preferred) / len(openai_preferred)
        markdown += f"- **Grounded-Preferred**: {effective}/{len(openai_preferred)} effective, "
        markdown += f"{with_tools} had tool calls, {with_citations} had citations, avg {avg_len:.0f} chars\n"
    
    if openai_required:
        effective = sum(1 for r in openai_required if r.get('grounded_effective'))
        with_tools = sum(1 for r in openai_required if r.get('tool_calls', 0) > 0)
        with_citations = sum(1 for r in openai_required if r.get('citations_count', 0) > 0)
        failed = sum(1 for r in openai_required if not r.get('success'))
        avg_len = sum(r['content_length'] for r in openai_required if r.get('success')) / max(1, sum(1 for r in openai_required if r.get('success')))
        markdown += f"- **Grounded-Required**: {effective}/{len(openai_required)} effective, "
        markdown += f"{with_tools} had tool calls, {with_citations} had citations, "
        markdown += f"{failed} failed (QA ceiling), avg {avg_len:.0f} chars\n"
    
    markdown += """
### Vertex Grounding Modes
"""
    
    # Analyze Vertex grounding modes
    vertex_ungrounded = [r for r in results if r['vendor'] == 'Vertex' and r['mode'] == 'UNGROUNDED']
    vertex_preferred = [r for r in results if r['vendor'] == 'Vertex' and r['mode'] == 'GROUNDED_PREFERRED']
    
    if vertex_ungrounded:
        avg_len = sum(r['content_length'] for r in vertex_ungrounded) / len(vertex_ungrounded)
        markdown += f"- **Ungrounded**: {len(vertex_ungrounded)} tests, avg {avg_len:.0f} chars\n"
    
    if vertex_preferred:
        effective = sum(1 for r in vertex_preferred if r.get('grounded_effective'))
        with_tools = sum(1 for r in vertex_preferred if r.get('tool_calls', 0) > 0)
        with_citations = sum(1 for r in vertex_preferred if r.get('citations_count', 0) > 0)
        avg_len = sum(r['content_length'] for r in vertex_preferred) / len(vertex_preferred)
        markdown += f"- **Grounded-Preferred**: {effective}/{len(vertex_preferred)} effective, "
        markdown += f"{with_tools} had tool calls, {with_citations} had citations, avg {avg_len:.0f} chars\n"
    
    markdown += """

## Regional Analysis

### US Responses (Expected: No VAT, mention sales tax)
"""
    
    us_results = [r for r in results if r['country'] == 'US' and r.get('success')]
    for r in us_results:
        has_no_vat = "no vat" in r['content'].lower() or "does not have" in r['content'].lower() or "no value" in r['content'].lower()
        has_sales_tax = "sales tax" in r['content'].lower()
        markdown += f"- **{r['config']}**: "
        markdown += f"{'✓' if has_no_vat else '✗'} No VAT, "
        markdown += f"{'✓' if has_sales_tax else '✗'} Sales tax\n"
    
    markdown += """
### DE Responses (Expected: 19% VAT/Mehrwertsteuer)
"""
    
    de_results = [r for r in results if r['country'] == 'DE' and r.get('success')]
    for r in de_results:
        has_19 = "19%" in r['content'] or "19 %" in r['content']
        has_7 = "7%" in r['content'] or "7 %" in r['content']
        has_mwst = "mehrwertsteuer" in r['content'].lower() or "mwst" in r['content'].lower()
        has_vat = "vat" in r['content'].lower() or "value-added" in r['content'].lower()
        markdown += f"- **{r['config']}**: "
        markdown += f"{'✓' if has_19 else '✗'} 19%, "
        markdown += f"{'✓' if has_7 else '✗'} 7%, "
        markdown += f"{'✓' if (has_mwst or has_vat) else '✗'} VAT/MwSt\n"
    
    markdown += """

## Citations Analysis

### Citations by Configuration
"""
    
    for config in sorted(set(r['config'] for r in results)):
        config_results = [r for r in results if r['config'] == config]
        if config_results and config_results[0].get('citations_count', 0) > 0:
            r = config_results[0]
            markdown += f"\n**{config}**: {r['citations_count']} citations\n"
            for i, citation in enumerate(r.get('citations', [])[:3]):  # Show top 3
                url = citation.get('url', 'N/A')
                title = citation.get('title', 'No title')
                snippet = citation.get('snippet', '')
                if snippet and len(snippet) > 100:
                    snippet = snippet[:100] + "..."
                markdown += f"  {i+1}. [{title}]({url})\n"
                if snippet:
                    markdown += f"     *{snippet}*\n"
    
    # Add warnings section
    warnings = []
    
    # Exclude N/A cases (unsupported tools) from Required mode warnings
    required_no_tools = [r for r in results 
                         if r.get('mode') == 'GROUNDED_REQUIRED' 
                         and r.get('success') 
                         and r.get('tool_calls', 0) == 0
                         and not r.get('is_na', False)]  # Exclude N/A cases
    if required_no_tools:
        warnings.append(f"{len(required_no_tools)} Grounded-Required tests had no tool calls (should fail-close)")
    
    empty_completions = [r for r in results if r.get('success') and r.get('content_length', 0) == 0]
    if empty_completions:
        warnings.append(f"{len(empty_completions)} tests returned empty content but marked as success")
    
    if warnings:
        markdown += """

## ⚠️ Warnings

"""
        for warning in warnings:
            markdown += f"- {warning}\n"
            if required_no_tools:
                for r in required_no_tools:
                    markdown += f"  - {r['config']}\n"
    
    markdown += f"""

---

*Test completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*ChatGPT improvements: Citations extraction, Required/Preferred modes, proper timeouts, no JSON mode*
"""
    
    # Save to file
    filename = f"VAT_MATRIX_V3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w') as f:
        f.write(markdown)
    
    print(f"\n{'='*60}")
    print(f"✅ Results saved to {filename}")
    print(f"{'='*60}")
    
    # Copy to Downloads
    import shutil
    downloads_path = "/mnt/c/Users/leedr/Downloads/" + filename
    shutil.copy(filename, downloads_path)
    print(f"✅ Copied to {downloads_path}")
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Total: {len(results)}")
    print(f"  Success: {sum(1 for r in results if r.get('success'))}")
    print(f"  Failed: {sum(1 for r in results if not r.get('success'))}")
    
    # Print grounding effectiveness
    print(f"\nGrounding Effectiveness:")
    for vendor in ["OpenAI", "Vertex"]:
        preferred = [r for r in results if r['vendor'] == vendor and r['mode'] == 'GROUNDED_PREFERRED']
        if preferred:
            effective = sum(1 for r in preferred if r.get('grounded_effective'))
            citations = sum(1 for r in preferred if r.get('citations_count', 0) > 0)
            print(f"  {vendor} Preferred: {effective}/{len(preferred)} effective, {citations} with citations")
        
        required = [r for r in results if r['vendor'] == vendor and r['mode'] == 'GROUNDED_REQUIRED']
        if required:
            effective = sum(1 for r in required if r.get('grounded_effective'))
            citations = sum(1 for r in required if r.get('citations_count', 0) > 0)
            print(f"  {vendor} Required: {effective}/{len(required)} effective, {citations} with citations")
    
    # Check for Required mode failures
    if required_no_tools:
        print(f"\n⚠️ WARNING: {len(required_no_tools)} Grounded-Required tests had no tool calls!")
        for r in required_no_tools:
            print(f"  - {r['config']}")
    
    return filename

if __name__ == "__main__":
    filename = asyncio.run(test_vat_matrix_v3())
    print(f"\nResults file: {filename}")