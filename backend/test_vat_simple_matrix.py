#!/usr/bin/env python3
"""
Simplified VAT matrix test - focus on ungrounded first
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

async def test_vat_simple():
    """Test VAT rate question - simplified"""
    
    adapter = UnifiedLLMAdapter()
    prompt = "What is the VAT rate?"
    
    # Test all configurations with ChatGPT's fixes applied
    configs = [
        ("OpenAI", "US", False),  # OpenAI US Ungrounded
        ("OpenAI", "US", True),   # OpenAI US Grounded
        ("OpenAI", "DE", False),  # OpenAI DE Ungrounded
        ("OpenAI", "DE", True),   # OpenAI DE Grounded
        ("Vertex", "US", False),  # Vertex US Ungrounded
        ("Vertex", "US", True),   # Vertex US Grounded
        ("Vertex", "DE", False),  # Vertex DE Ungrounded
        ("Vertex", "DE", True),   # Vertex DE Grounded
    ]
    
    results = []
    
    for vendor_name, country, grounded in configs:
        config_name = f"{vendor_name} {country} {'Grounded' if grounded else 'Ungrounded'}"
        print(f"\n{'='*60}")
        print(f"Testing: {config_name}")
        print(f"{'='*60}")
        
        # Set up request
        vendor = "openai" if vendor_name == "OpenAI" else "vertex"
        model = "gpt-5" if vendor == "openai" else "publishers/google/models/gemini-2.5-pro"
        locale = f"en-{country}"
        
        # Create request WITHOUT JSON mode to allow plain-text retries
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000,  # Standard, will auto-retry if needed
            grounded=grounded,
            als_context={'country_code': country, 'locale': locale}
            # DO NOT set response_format to JSON - let it be text for retries to work
        )
        
        try:
            print(f"  Vendor: {vendor}")
            print(f"  Model: {model}")
            print(f"  Grounded: {grounded}")
            print(f"  Country: {country}")
            print(f"  Max tokens: 1000")
            
            response = await adapter.complete(request)
            
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "grounded": grounded,
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
                result["finish_reason"] = response.metadata.get("finish_reason", "")
                result["retry_attempted"] = response.metadata.get("retry_attempted", False)
                result["retry_successful"] = response.metadata.get("retry_successful", False)
                result["retry_reason"] = response.metadata.get("retry_reason", "")
                result["als_sha256"] = response.metadata.get("als_sha256", "")[:16] + "..." if response.metadata.get("als_sha256") else ""
            
            results.append(result)
            
            print(f"\n  ✅ Success: {response.success}")
            print(f"  Content length: {result['content_length']} chars")
            print(f"  Latency: {response.latency_ms}ms")
            
            if result.get('retry_attempted'):
                print(f"  Retry: {result.get('retry_reason', 'Unknown reason')}")
                print(f"  Retry successful: {result.get('retry_successful', False)}")
            
            if grounded and result.get('grounded_effective'):
                print(f"  Tool calls: {result.get('tool_calls', 0)}")
            
            # Show first 200 chars of response
            preview = result['content'][:200] + "..." if len(result['content']) > 200 else result['content']
            print(f"\n  Response preview: {preview}")
            
        except Exception as e:
            result = {
                "config": config_name,
                "vendor": vendor_name,
                "country": country,
                "grounded": grounded,
                "success": False,
                "error": str(e),
                "content": "",
                "content_length": 0
            }
            results.append(result)
            print(f"  ❌ Error: {e}")
        
        await asyncio.sleep(2)  # Rate limiting
    
    # Generate markdown report
    markdown = f"""# VAT Rate Test Results

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Prompt**: "{prompt}"

## Summary

- Total Tests: {len(results)}
- Successful: {sum(1 for r in results if r.get('success', False))}
- Failed: {sum(1 for r in results if not r.get('success', False))}

## Results by Configuration

"""
    
    for result in results:
        markdown += f"""### {result['config']}

**Status**: {'✅ Success' if result.get('success') else '❌ Failed'}
**Latency**: {result.get('latency_ms', 'N/A')}ms
**Content Length**: {result['content_length']} chars
"""
        
        if result.get('grounded') and result.get('metadata'):
            metadata = result['metadata']
            markdown += f"**Grounded Effective**: {metadata.get('grounded_effective', 'N/A')}\n"
            markdown += f"**Tool Calls**: {metadata.get('tool_call_count', 0)}\n"
        
        if result.get('metadata', {}).get('retry_attempted'):
            markdown += f"**Retry Attempted**: Yes\n"
        
        if result.get('usage'):
            usage = result['usage']
            markdown += f"**Tokens**: Total={usage.get('total_tokens', 'N/A')}, "
            markdown += f"Prompt={usage.get('prompt_tokens', 'N/A')}, "
            markdown += f"Completion={usage.get('completion_tokens', 'N/A')}\n"
        
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
        has_no_vat = "no VAT" in r['content'].lower() or "no value-added" in r['content'].lower()
        has_sales_tax = "sales tax" in r['content'].lower()
        markdown += f"- **{r['config']}**: "
        markdown += f"{'✅' if has_no_vat else '❌'} No VAT mentioned, "
        markdown += f"{'✅' if has_sales_tax else '❌'} Sales tax mentioned\n"
    
    markdown += """
### DE Responses (Expected: 19% VAT/Mehrwertsteuer)
"""
    
    de_results = [r for r in results if r['country'] == 'DE' and r.get('success')]
    for r in de_results:
        has_19 = "19%" in r['content'] or "19 %" in r['content']
        has_mwst = "mehrwertsteuer" in r['content'].lower() or "mwst" in r['content'].lower()
        has_vat = "vat" in r['content'].lower() or "value-added" in r['content'].lower()
        markdown += f"- **{r['config']}**: "
        markdown += f"{'✅' if has_19 else '❌'} 19% mentioned, "
        markdown += f"{'✅' if (has_mwst or has_vat) else '❌'} VAT/MwSt mentioned\n"
    
    markdown += f"""

---

*Test completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""
    
    # Save to file
    filename = f"VAT_SIMPLE_MATRIX_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w') as f:
        f.write(markdown)
    
    print(f"\n✅ Results saved to {filename}")
    
    # Also copy to Downloads
    import shutil
    downloads_path = "/mnt/c/Users/leedr/Downloads/" + filename
    shutil.copy(filename, downloads_path)
    print(f"✅ Copied to {downloads_path}")
    
    return filename

if __name__ == "__main__":
    filename = asyncio.run(test_vat_simple())
    print(f"\nResults file: {filename}")