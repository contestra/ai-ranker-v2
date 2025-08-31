#!/usr/bin/env python3
"""
VAT Rate Test v2 - With ChatGPT's improvements:
1. Grounded-Required tests for OpenAI
2. Provoker line for Grounded-Preferred
3. Increased tokens for Vertex ungrounded
4. Citations extraction (placeholder for now)
"""
import asyncio
import os
import sys
import json
from datetime import datetime
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

# Apply ChatGPT's fixes:
# 1. Disable preview compatibility to force web_search (not web_search_preview)
os.environ["ALLOW_PREVIEW_COMPAT"] = "false"

# 2. Set appropriate timeouts for grounded runs (120s or more)
os.environ["OPENAI_READ_TIMEOUT_MS"] = "120000"
os.environ["LLM_TIMEOUT_GR"] = "180"  # 180 seconds for grounded
os.environ["LLM_TIMEOUT_UN"] = "60"   # 60 seconds for ungrounded

# Disable proxies for direct testing
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_vat_matrix_v2():
    """Test VAT rate question with improvements"""
    
    adapter = UnifiedLLMAdapter()
    base_prompt = "What is the VAT rate?"
    
    # Add provoker for preferred grounding
    today = datetime.now().strftime("%Y-%m-%d")
    grounded_preferred_prompt = f"{base_prompt} As of today ({today}), include an official source URL."
    
    # Test configurations with Required/Preferred variants
    configs = [
        # OpenAI tests
        ("OpenAI", "US", False, None, base_prompt),  # Ungrounded
        ("OpenAI", "US", True, "auto", grounded_preferred_prompt),  # Grounded-Preferred with provoker
        ("OpenAI", "US", True, "required", base_prompt),  # Grounded-Required
        ("OpenAI", "DE", False, None, base_prompt),  # Ungrounded
        ("OpenAI", "DE", True, "auto", grounded_preferred_prompt),  # Grounded-Preferred with provoker
        ("OpenAI", "DE", True, "required", base_prompt),  # Grounded-Required
        
        # Vertex tests
        ("Vertex", "US", False, None, base_prompt),  # Ungrounded
        ("Vertex", "US", True, "auto", base_prompt),  # Grounded-Auto
        ("Vertex", "DE", False, None, base_prompt),  # Ungrounded
        ("Vertex", "DE", True, "auto", base_prompt),  # Grounded-Auto
    ]
    
    results = []
    
    for vendor_name, country, grounded, tool_choice, prompt in configs:
        # Determine config name
        if grounded:
            if tool_choice == "required":
                mode = "Grounded-Required"
            else:
                mode = "Grounded-Preferred"
        else:
            mode = "Ungrounded"
        
        config_name = f"{vendor_name} {country} {mode}"
        print(f"\n{'='*60}")
        print(f"Testing: {config_name}")
        print(f"{'='*60}")
        
        # Set up request
        vendor = "openai" if vendor_name == "OpenAI" else "vertex"
        model = "gpt-5" if vendor == "openai" else "publishers/google/models/gemini-2.5-pro"
        locale = f"en-{country}"
        
        # Determine max_tokens
        if vendor == "vertex" and not grounded:
            # Increase tokens for Vertex ungrounded to match OpenAI verbosity
            max_tokens = 1500
        else:
            max_tokens = 1000
        
        # Create request WITHOUT JSON mode to allow plain-text retries
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=max_tokens,
            grounded=grounded,
            als_context={'country_code': country, 'locale': locale}
            # DO NOT set response_format to JSON - let it be text for retries to work
        )
        
        # Add tool_choice for OpenAI if specified
        if vendor == "openai" and tool_choice:
            request.tool_choice = tool_choice
        
        try:
            print(f"  Vendor: {vendor}")
            print(f"  Model: {model}")
            print(f"  Grounded: {grounded}")
            if tool_choice:
                print(f"  Tool choice: {tool_choice}")
            print(f"  Country: {country}")
            print(f"  Max tokens: {max_tokens}")
            print(f"  Prompt: {'with provoker' if 'official source URL' in prompt else 'standard'}")
            
            response = await adapter.complete(request)
            
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "grounded": grounded,
                "tool_choice": tool_choice,
                "success": response.success,
                "content": response.content or "",
                "content_length": len(response.content) if response.content else 0,
                "latency_ms": response.latency_ms,
                "usage": response.usage or {},
                "metadata": response.metadata or {},
                "has_provoker": "official source URL" in prompt
            }
            
            # Extract key metadata
            if response.metadata:
                result["grounded_effective"] = response.metadata.get("grounded_effective", False)
                result["tool_calls"] = response.metadata.get("tool_call_count", 0)
                result["finish_reason"] = response.metadata.get("finish_reason", "")
                result["retry_attempted"] = response.metadata.get("retry_attempted", False)
                result["retry_successful"] = response.metadata.get("retry_successful", False)
                result["retry_reason"] = response.metadata.get("retry_reason", "")
                result["als_sha256"] = response.metadata.get("als_sha256", "")[:16] + "..." if response.metadata.get("als_sha256") else ""
                
                # Placeholder for citations (will be added when adapter support is ready)
                result["citations"] = response.metadata.get("citations", [])
            
            results.append(result)
            
            print(f"\n  ✅ Success: {response.success}")
            print(f"  Content length: {result['content_length']} chars")
            print(f"  Latency: {response.latency_ms}ms")
            
            if result.get('retry_attempted'):
                print(f"  Retry: {result.get('retry_reason', 'Unknown reason')}")
                print(f"  Retry successful: {result.get('retry_successful', False)}")
            
            if grounded:
                print(f"  Grounded effective: {result.get('grounded_effective', False)}")
                print(f"  Tool calls: {result.get('tool_calls', 0)}")
                
                # Special handling for Required mode
                if tool_choice == "required" and result.get('tool_calls', 0) == 0:
                    print(f"  ⚠️ WARNING: Grounded-Required had no tool calls!")
            
            if result.get('citations'):
                print(f"  Citations found: {len(result['citations'])}")
            
            # Show first 200 chars of response
            preview = result['content'][:200] + "..." if len(result['content']) > 200 else result['content']
            print(f"\n  Response preview: {preview}")
            
        except Exception as e:
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "grounded": grounded,
                "tool_choice": tool_choice,
                "success": False,
                "error": str(e),
                "content": "",
                "content_length": 0,
                "has_provoker": "official source URL" in prompt
            }
            results.append(result)
            print(f"\n  ❌ Error: {e}")
        
        # Rate limiting
        await asyncio.sleep(2)
    
    # Generate markdown report
    markdown = f"""# VAT Rate Test v2 - Improved Matrix Results

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Base Prompt**: "{base_prompt}"
**Provoker Added**: "As of today ({today}), include an official source URL."

## Configuration

- ALLOW_PREVIEW_COMPAT: false (forces web_search, not web_search_preview)
- OPENAI_READ_TIMEOUT_MS: 120000 (120 seconds)
- LLM_TIMEOUT_GR: 180 seconds
- LLM_TIMEOUT_UN: 60 seconds
- JSON mode: DISABLED (allows plain-text retries)
- Vertex ungrounded tokens: 1500 (increased for verbosity)
- OpenAI tokens: 1000

## Summary

Total Tests: {len(results)}
Successful: {sum(1 for r in results if r.get('success', False))}
Failed: {sum(1 for r in results if not r.get('success', False))}

### Grounding Effectiveness

"""
    
    # Analyze grounding modes
    for vendor in ["OpenAI", "Vertex"]:
        vendor_results = [r for r in results if r['vendor'] == vendor]
        
        ungrounded = [r for r in vendor_results if not r.get('grounded')]
        grounded_preferred = [r for r in vendor_results if r.get('grounded') and r.get('tool_choice') != 'required']
        grounded_required = [r for r in vendor_results if r.get('grounded') and r.get('tool_choice') == 'required']
        
        markdown += f"**{vendor}**:\n"
        
        if ungrounded:
            avg_length = sum(r['content_length'] for r in ungrounded) / len(ungrounded)
            markdown += f"- Ungrounded: {len(ungrounded)} tests, avg {avg_length:.0f} chars\n"
        
        if grounded_preferred:
            effective = sum(1 for r in grounded_preferred if r.get('grounded_effective'))
            with_tools = sum(1 for r in grounded_preferred if r.get('tool_calls', 0) > 0)
            avg_length = sum(r['content_length'] for r in grounded_preferred) / len(grounded_preferred)
            markdown += f"- Grounded-Preferred: {effective}/{len(grounded_preferred)} effective, "
            markdown += f"{with_tools} had tool calls, avg {avg_length:.0f} chars\n"
        
        if grounded_required:
            effective = sum(1 for r in grounded_required if r.get('grounded_effective'))
            with_tools = sum(1 for r in grounded_required if r.get('tool_calls', 0) > 0)
            avg_length = sum(r['content_length'] for r in grounded_required if r.get('success')) / max(1, sum(1 for r in grounded_required if r.get('success')))
            markdown += f"- Grounded-Required: {effective}/{len(grounded_required)} effective, "
            markdown += f"{with_tools} had tool calls, avg {avg_length:.0f} chars\n"
        
        markdown += "\n"
    
    markdown += """## Detailed Results

"""
    
    for result in results:
        markdown += f"""### {result['config']}

**Status**: {'✅ Success' if result.get('success') else '❌ Failed'}
**Latency**: {result.get('latency_ms', 'N/A')}ms
**Content Length**: {result['content_length']} chars
"""
        
        if result.get('has_provoker'):
            markdown += "**Prompt**: With provoker line\n"
        
        if result.get('grounded') is not None:
            markdown += f"**Grounded Effective**: {result.get('grounded_effective', 'N/A')}\n"
            markdown += f"**Tool Calls**: {result.get('tool_calls', 0)}\n"
            
            if result.get('tool_choice'):
                markdown += f"**Tool Choice**: {result.get('tool_choice')}\n"
        
        if result.get('retry_attempted'):
            markdown += f"**Retry Attempted**: Yes\n"
            markdown += f"**Retry Reason**: {result.get('retry_reason', 'N/A')}\n"
            markdown += f"**Retry Successful**: {result.get('retry_successful', False)}\n"
        
        if result.get('als_sha256'):
            markdown += f"**ALS SHA256**: {result['als_sha256']}\n"
        
        if result.get('usage'):
            usage = result['usage']
            markdown += f"**Tokens Used**: {usage.get('total_tokens', 'N/A')} "
            markdown += f"(prompt: {usage.get('prompt_tokens', 'N/A')}, "
            markdown += f"completion: {usage.get('completion_tokens', 'N/A')})\n"
        
        if result.get('citations'):
            markdown += f"**Citations**: {len(result['citations'])} found\n"
            for i, citation in enumerate(result['citations'][:2]):  # Show first 2
                markdown += f"  {i+1}. {citation.get('url', 'N/A')}\n"
        
        markdown += f"""
**Full Response**:
```
{result.get('content', result.get('error', 'No content'))}
```

---

"""
    
    # Add regional analysis
    markdown += """## Regional Analysis

### US Responses (Expected: No VAT, mention sales tax)
"""
    
    us_results = [r for r in results if r['country'] == 'US' and r.get('success')]
    for r in us_results:
        has_no_vat = "no vat" in r['content'].lower() or "does not have" in r['content'].lower()
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
    
    # Add comparison section
    markdown += """
## Provoker Line Analysis

### OpenAI Grounded-Preferred (with provoker) vs Ungrounded
"""
    
    for country in ["US", "DE"]:
        ungrounded = [r for r in results if r['vendor'] == 'OpenAI' and r['country'] == country and not r.get('grounded')]
        preferred = [r for r in results if r['vendor'] == 'OpenAI' and r['country'] == country and r.get('grounded') and r.get('has_provoker')]
        
        if ungrounded and preferred:
            ung_len = ungrounded[0]['content_length']
            pref_len = preferred[0]['content_length']
            pref_tools = preferred[0].get('tool_calls', 0)
            
            markdown += f"- **{country}**: Ungrounded {ung_len} chars → Preferred {pref_len} chars "
            markdown += f"({'✓ grounded' if pref_tools > 0 else '✗ not grounded'})\n"
    
    markdown += f"""

---

*Test completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""
    
    # Save to file
    filename = f"VAT_MATRIX_V2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
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
    
    # Check for Required mode failures
    required_no_tools = [r for r in results if r.get('tool_choice') == 'required' and r.get('success') and r.get('tool_calls', 0) == 0]
    if required_no_tools:
        print(f"\n⚠️ WARNING: {len(required_no_tools)} Grounded-Required tests had no tool calls!")
        for r in required_no_tools:
            print(f"  - {r['config']}")
    
    return filename

if __name__ == "__main__":
    filename = asyncio.run(test_vat_matrix_v2())
    print(f"\nResults file: {filename}")