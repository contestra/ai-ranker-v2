#!/usr/bin/env python3
"""
Comprehensive test of "Tell me the latest news" prompt
Tests all combinations of:
- Vendors: OpenAI, Vertex
- Countries: US, DE
- Modes: Ungrounded, Grounded-Preferred, Grounded-Required
- ALS: With and Without
"""
import asyncio
import os
import sys
import json
from datetime import datetime, timezone
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

# Force proper grounding mode
os.environ["ALLOW_PREVIEW_COMPAT"] = "false"
os.environ["OPENAI_READ_TIMEOUT_MS"] = "120000"
os.environ["LLM_TIMEOUT_GR"] = "180"
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

PROMPT = "Tell me the latest news"

async def test_news_comprehensive():
    """Run comprehensive news test matrix"""
    
    adapter = UnifiedLLMAdapter()
    results = []
    
    # Test configurations
    # Format: (vendor_name, country, mode, with_als)
    configs = []
    
    for vendor_name in ["OpenAI", "Vertex"]:
        for country in ["US", "DE"]:
            for mode in ["UNGROUNDED", "GROUNDED_PREFERRED", "GROUNDED_REQUIRED"]:
                for with_als in [False, True]:
                    # Skip Required mode for Vertex (not supported)
                    if vendor_name == "Vertex" and mode == "GROUNDED_REQUIRED":
                        continue
                    configs.append((vendor_name, country, mode, with_als))
    
    for vendor_name, country, mode, with_als in configs:
        config_name = f"{vendor_name} {country} {mode} {'WITH-ALS' if with_als else 'NO-ALS'}"
        print(f"\n{'='*60}")
        print(f"Testing: {config_name}")
        print(f"{'='*60}")
        
        # Setup request
        vendor = vendor_name.lower()
        model = "gpt-5" if vendor == "openai" else "publishers/google/models/gemini-2.5-pro"
        
        # Build request
        messages = [{"role": "user", "content": PROMPT}]
        
        # Add ALS context if requested
        als_context = None
        if with_als:
            als_context = {
                "country_code": country,
                "locale": "en-US" if country == "US" else "de-DE"
            }
        
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=messages,
            grounded=(mode != "UNGROUNDED"),
            temperature=0.7,
            max_tokens=1500 if mode == "UNGROUNDED" else 1000,
            als_context=als_context
        )
        
        # Set grounding mode
        if mode == "GROUNDED_PREFERRED":
            request.meta = {"grounding_mode": "AUTO"}
            if vendor == "openai":
                request.tool_choice = "auto"
        elif mode == "GROUNDED_REQUIRED":
            request.meta = {"grounding_mode": "REQUIRED"}
            if vendor == "openai":
                request.tool_choice = "required"
        
        # Track timing
        import time
        t0 = time.perf_counter()
        
        try:
            print(f"  Vendor: {vendor}")
            print(f"  Model: {model}")
            print(f"  Country: {country}")
            print(f"  Mode: {mode}")
            print(f"  ALS: {'Yes' if with_als else 'No'}")
            print(f"  Max tokens: {request.max_tokens}")
            
            response = await adapter.complete(request)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            
            # Extract citations if present
            citations = []
            if response.metadata and 'citations' in response.metadata:
                for citation in response.metadata['citations']:
                    citations.append({
                        'title': citation.get('title', 'No title'),
                        'url': citation.get('uri', citation.get('url', 'No URL')),
                        'snippet': citation.get('snippet', '')[:200]
                    })
            
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "mode": mode,
                "als": with_als,
                "success": response.success,
                "content": response.content or "",
                "content_length": len(response.content) if response.content else 0,
                "latency_ms": latency_ms,
                "grounded_effective": response.grounded_effective,
                "tool_calls": response.metadata.get('tool_call_count', 0) if response.metadata else 0,
                "citations": citations,
                "citations_count": len(citations),
                "error": None,
                "is_na": False,
                "tokens_used": response.usage.get('total_tokens', 0) if response.usage else 0
            }
            
            # Add metadata about why not grounded
            if request.grounded and not response.grounded_effective:
                result["why_not_grounded"] = response.metadata.get('why_not_grounded', 'Unknown')
            
            print(f"\n  ✅ Success: {response.success}")
            print(f"  Content length: {result['content_length']} chars")
            print(f"  Latency: {latency_ms}ms")
            
            if request.grounded:
                print(f"  Grounded effective: {result.get('grounded_effective', False)}")
                print(f"  Tool calls: {result.get('tool_calls', 0)}")
                print(f"  Citations: {result.get('citations_count', 0)}")
                
                if mode == "GROUNDED_REQUIRED" and result.get('tool_calls', 0) == 0:
                    print(f"  ⚠️ WARNING: Grounded-Required had no tool calls!")
            
            # Show first 300 chars of response
            preview = result['content'][:300] + "..." if len(result['content']) > 300 else result['content']
            print(f"\n  Response preview: {preview}")
            
            # Show citations if any
            if citations:
                print(f"\n  Citations found ({len(citations)}):")
                for i, cit in enumerate(citations[:3]):  # Show first 3
                    print(f"    {i+1}. {cit['title'][:80]}")
                    print(f"       {cit['url'][:100]}")
            
        except Exception as e:
            error_msg = str(e)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            
            # Check if this is an expected Required mode failure
            is_grounding_unsupported = (
                mode == "GROUNDED_REQUIRED" and 
                "GROUNDING_NOT_SUPPORTED" in error_msg
            )
            
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "mode": mode,
                "als": with_als,
                "success": False,
                "content": "",
                "content_length": 0,
                "latency_ms": latency_ms,
                "grounded_effective": False,
                "tool_calls": 0,
                "citations": [],
                "citations_count": 0,
                "error": error_msg,
                "is_na": is_grounding_unsupported,
                "tokens_used": 0
            }
            
            if is_grounding_unsupported:
                print(f"\n  ℹ️ N/A: Grounding not supported for this model (Required mode)")
            else:
                print(f"\n  ❌ Failed: {error_msg[:200]}")
        
        results.append(result)
    
    # Generate comprehensive markdown report
    markdown = f"""# Comprehensive News Test Report

**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Prompt**: "{PROMPT}"

## Test Configuration

- **Vendors**: OpenAI (gpt-5), Vertex (gemini-2.5-pro)
- **Countries**: US, DE
- **Modes**: Ungrounded, Grounded-Preferred, Grounded-Required
- **ALS**: With and Without ALS context
- **Total Tests**: {len(results)}

## Summary Statistics

- **Successful**: {sum(1 for r in results if r['success'])}
- **Failed**: {sum(1 for r in results if not r['success'] and not r['is_na'])}
- **N/A (Unsupported)**: {sum(1 for r in results if r['is_na'])}

### Grounding Effectiveness
- **OpenAI Grounded Tests**: {sum(1 for r in results if r['vendor'] == 'OpenAI' and r['mode'] != 'UNGROUNDED')}
  - Effective: {sum(1 for r in results if r['vendor'] == 'OpenAI' and r['grounded_effective'])}
  - With Citations: {sum(1 for r in results if r['vendor'] == 'OpenAI' and r['citations_count'] > 0)}
- **Vertex Grounded Tests**: {sum(1 for r in results if r['vendor'] == 'Vertex' and r['mode'] != 'UNGROUNDED')}
  - Effective: {sum(1 for r in results if r['vendor'] == 'Vertex' and r['grounded_effective'])}
  - With Citations: {sum(1 for r in results if r['vendor'] == 'Vertex' and r['citations_count'] > 0)}

## Results Table

| Vendor | Country | Mode | ALS | Success | Grounded | Citations | Tokens | Latency |
|--------|---------|------|-----|---------|----------|-----------|--------|---------|
"""
    
    for r in results:
        success_icon = "N/A" if r['is_na'] else ("✅" if r['success'] else "❌")
        grounded_icon = "✓" if r['grounded_effective'] else ("—" if r['mode'] == 'UNGROUNDED' or r['is_na'] else "✗")
        als_icon = "✓" if r['als'] else "✗"
        
        markdown += f"| {r['vendor']} | {r['country']} | {r['mode'].replace('_', '-')} | {als_icon} | {success_icon} | {grounded_icon} | {r['citations_count']} | {r['tokens_used']} | {r['latency_ms']}ms |\n"
    
    markdown += "\n## Detailed Results\n\n"
    
    # Group results by vendor and mode for detailed display
    for vendor in ["OpenAI", "Vertex"]:
        markdown += f"\n### {vendor} Results\n\n"
        
        vendor_results = [r for r in results if r['vendor'] == vendor]
        
        for result in vendor_results:
            markdown += f"#### {result['config']}\n\n"
            
            if result['is_na']:
                markdown += "**Status**: N/A - Model does not support required grounding\n\n"
                continue
            
            markdown += f"**Status**: {'Success' if result['success'] else 'Failed'}\n"
            markdown += f"**Latency**: {result['latency_ms']}ms\n"
            markdown += f"**Content Length**: {result['content_length']} characters\n"
            
            if result['mode'] != 'UNGROUNDED':
                markdown += f"**Grounded Effective**: {result['grounded_effective']}\n"
                markdown += f"**Tool Calls**: {result['tool_calls']}\n"
                markdown += f"**Citations Count**: {result['citations_count']}\n"
                if 'why_not_grounded' in result:
                    markdown += f"**Why Not Grounded**: {result['why_not_grounded']}\n"
            
            markdown += f"\n**Response**:\n```\n{result['content']}\n```\n"
            
            if result['citations']:
                markdown += f"\n**Citations** ({len(result['citations'])}):\n"
                for i, cit in enumerate(result['citations'], 1):
                    markdown += f"{i}. **{cit['title']}**\n"
                    markdown += f"   - URL: {cit['url']}\n"
                    if cit['snippet']:
                        markdown += f"   - Snippet: {cit['snippet']}\n"
            
            if result['error']:
                markdown += f"\n**Error**: {result['error']}\n"
            
            markdown += "\n---\n\n"
    
    markdown += f"""
## Analysis

### ALS Impact
- Tests WITH ALS: {sum(1 for r in results if r['als'] and r['success'])} successful
- Tests WITHOUT ALS: {sum(1 for r in results if not r['als'] and r['success'])} successful

### Country-Specific Observations
- **US Tests**: {sum(1 for r in results if r['country'] == 'US' and r['success'])} successful
- **DE Tests**: {sum(1 for r in results if r['country'] == 'DE' and r['success'])} successful

### Mode Performance
- **Ungrounded**: {sum(1 for r in results if r['mode'] == 'UNGROUNDED' and r['success'])}/{sum(1 for r in results if r['mode'] == 'UNGROUNDED')} successful
- **Grounded-Preferred**: {sum(1 for r in results if r['mode'] == 'GROUNDED_PREFERRED' and r['success'])}/{sum(1 for r in results if r['mode'] == 'GROUNDED_PREFERRED')} successful
- **Grounded-Required**: {sum(1 for r in results if r['mode'] == 'GROUNDED_REQUIRED' and r['success'])}/{sum(1 for r in results if r['mode'] == 'GROUNDED_REQUIRED')} successful

---

*Test completed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    
    # Save to file
    filename = f"NEWS_TEST_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    print(f"\n{'='*60}")
    print(f"✅ Results saved to {filename}")
    print(f"{'='*60}")
    
    # Copy to Windows Downloads
    import shutil
    windows_path = f"/mnt/c/Users/leedr/Downloads/{filename}"
    shutil.copy(filename, windows_path)
    print(f"✅ Copied to {windows_path}")
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Total: {len(results)}")
    print(f"  Success: {sum(1 for r in results if r['success'])}")
    print(f"  Failed: {sum(1 for r in results if not r['success'] and not r['is_na'])}")
    print(f"  N/A: {sum(1 for r in results if r['is_na'])}")
    
    print(f"\nGrounding Effectiveness:")
    for vendor in ["OpenAI", "Vertex"]:
        grounded = [r for r in results if r['vendor'] == vendor and r['mode'] != 'UNGROUNDED' and not r['is_na']]
        if grounded:
            effective = sum(1 for r in grounded if r['grounded_effective'])
            citations = sum(1 for r in grounded if r['citations_count'] > 0)
            print(f"  {vendor}: {effective}/{len(grounded)} effective, {citations} with citations")
    
    print(f"\nResults file: {filename}")

if __name__ == "__main__":
    asyncio.run(test_news_comprehensive())