#!/usr/bin/env python3
"""
Full matrix test: VAT rate across all configurations
"""
import asyncio
import os
import sys
import json
from datetime import datetime
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_vat_matrix():
    """Test VAT rate question across all configurations"""
    
    adapter = UnifiedLLMAdapter()
    prompt = "What is the VAT rate?"
    
    # Test configurations
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
        print(f"\nTesting: {config_name}...")
        
        # Set up request
        vendor = "openai" if vendor_name == "OpenAI" else "vertex"
        model = "gpt-5" if vendor == "openai" else "publishers/google/models/gemini-2.5-pro"
        locale = f"en-{country}"
        
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000,
            grounded=grounded,
            als_context={'country_code': country, 'locale': locale}
        )
        
        try:
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
                result["als_sha256"] = response.metadata.get("als_sha256", "")[:16] + "..." if response.metadata.get("als_sha256") else ""
            
            results.append(result)
            print(f"  ✅ Success: {response.success}, Length: {result['content_length']}")
            
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
        
        await asyncio.sleep(1)  # Rate limiting
    
    # Generate markdown report
    markdown = f"""# VAT Rate Test - Full Matrix Results

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Prompt**: "{prompt}"

## Summary

Total Tests: {len(results)}
Successful: {sum(1 for r in results if r.get('success', False))}
Failed: {sum(1 for r in results if not r.get('success', False))}

## Detailed Results

"""
    
    for result in results:
        markdown += f"""### {result['config']}

**Status**: {'✅ Success' if result.get('success') else '❌ Failed'}
**Latency**: {result.get('latency_ms', 'N/A')}ms
**Content Length**: {result['content_length']} chars
"""
        
        if result.get('grounded') is not None:
            markdown += f"**Grounded Effective**: {result.get('grounded_effective', 'N/A')}\n"
            markdown += f"**Tool Calls**: {result.get('tool_calls', 0)}\n"
        
        if result.get('retry_attempted'):
            markdown += f"**Retry Attempted**: Yes\n"
        
        if result.get('als_sha256'):
            markdown += f"**ALS SHA256**: {result['als_sha256']}\n"
        
        if result.get('usage'):
            usage = result['usage']
            markdown += f"**Tokens**: {usage.get('total_tokens', 'N/A')} "
            markdown += f"(prompt: {usage.get('prompt_tokens', 'N/A')}, "
            markdown += f"completion: {usage.get('completion_tokens', 'N/A')})\n"
        
        markdown += f"""
**Full Response**:
```
{result.get('content', result.get('error', 'No content'))}
```

---

"""
    
    # Add analysis section
    markdown += """## Analysis

### Regional Awareness

**US Responses**: Should mention no VAT, sales tax instead
**DE Responses**: Should mention 19% German VAT (Mehrwertsteuer)

### Grounding Effectiveness

"""
    
    for vendor in ["OpenAI", "Vertex"]:
        grounded_results = [r for r in results if r['vendor'] == vendor and r.get('grounded')]
        if grounded_results:
            effective = sum(1 for r in grounded_results if r.get('grounded_effective'))
            markdown += f"**{vendor}**: {effective}/{len(grounded_results)} grounded requests were effective\n"
    
    markdown += f"""

### Token Limits

"""
    
    for result in results:
        if result.get('retry_attempted'):
            markdown += f"- **{result['config']}**: Required retry due to token limits\n"
    
    markdown += f"""

---

*Test completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""
    
    # Save to file
    filename = f"VAT_MATRIX_RESULTS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w') as f:
        f.write(markdown)
    
    print(f"\n✅ Results saved to {filename}")
    return filename

if __name__ == "__main__":
    filename = asyncio.run(test_vat_matrix())
    print(f"\nResults file: {filename}")