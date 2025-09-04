#!/usr/bin/env python3
"""Test all adapters through the router with DE ALS context."""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest


async def test_adapter(adapter_name: str, vendor: str, model: str, grounded: bool, als_context: Dict) -> Dict[str, Any]:
    """Test a single adapter configuration."""
    print(f"\n{'='*80}")
    print(f"Testing {adapter_name} - {'GROUNDED' if grounded else 'UNGROUNDED'}")
    print(f"Model: {model}")
    print(f"ALS: {als_context['country_code']}")
    print('='*80)
    
    try:
        # Initialize the router
        router = UnifiedLLMAdapter()
        
        # Create the request
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful health and wellness expert. Provide accurate information."
                },
                {
                    "role": "user", 
                    "content": "Tell me the primary health and wellness news during August 2025"
                }
            ],
            grounded=grounded,
            max_tokens=1000,
            temperature=0.7,
            als_context=als_context
        )
        
        # Add metadata and meta after creation
        request.metadata = {
            "als_country": als_context["country_code"],
            "capabilities": {
                "supports_reasoning_effort": True,  # For GPT-5
                "supports_thinking_budget": True    # For Gemini
            }
        }
        
        if grounded:
            request.meta = {"grounding_mode": "AUTO"}
        
        # Make the request
        start_time = datetime.now()
        response = await router.complete(request)
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Prepare result
        result = {
            "adapter": adapter_name,
            "vendor": vendor,
            "model": model,
            "grounded": grounded,
            "als_context": als_context,
            "success": response.success if hasattr(response, 'success') else True,
            "elapsed_seconds": elapsed,
            "content": response.content if hasattr(response, 'content') else "",
            "citations": response.citations if hasattr(response, 'citations') else [],
            "metadata": response.metadata if hasattr(response, 'metadata') else {},
            "usage": response.usage if hasattr(response, 'usage') else {},
            "grounded_effective": response.grounded_effective if hasattr(response, 'grounded_effective') else False
        }
        
        # Print key information
        print(f"\n✅ SUCCESS - Response received in {elapsed:.2f}s")
        print(f"\nContent Length: {len(result['content'])} chars")
        print(f"Grounded Effective: {result['grounded_effective']}")
        
        if result['citations']:
            print(f"\n📚 Citations Found: {len(result['citations'])}")
            print(f"  - Anchored: {result['metadata'].get('anchored_citations_count', 0)}")
            print(f"  - Unlinked: {result['metadata'].get('unlinked_sources_count', 0)}")
            for i, citation in enumerate(result['citations'][:5], 1):
                if 'url' in citation:
                    print(f"  {i}. {citation.get('title', 'No title')[:60]}...")
                    print(f"     URL: {citation['url'][:80]}...")
                    print(f"     Type: {citation.get('source_type', 'unknown')}")
        else:
            print("\n📚 No citations (ungrounded or no results)")
            
        # Print first 500 chars of content
        print(f"\n📝 Response Preview:")
        print("-" * 40)
        print(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])
        print("-" * 40)
        
        return result
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return {
            "adapter": adapter_name,
            "vendor": vendor,
            "model": model,
            "grounded": grounded,
            "als_context": als_context,
            "success": False,
            "error": str(e),
            "elapsed_seconds": 0
        }


async def main():
    """Run all tests."""
    
    # DE ALS context
    als_context = {
        "country_code": "DE",
        "locale": "de-DE",
        "detected_location": "Berlin, Germany"
    }
    
    # Test configurations
    tests = [
        # OpenAI tests
        ("OpenAI/GPT-5", "openai", "gpt-5-2025-08-07", False),  # Ungrounded
        ("OpenAI/GPT-5", "openai", "gpt-5-2025-08-07", True),   # Grounded
        
        # Gemini Direct tests  
        ("Gemini Direct", "gemini_direct", "gemini-2.5-pro", False),  # Ungrounded
        ("Gemini Direct", "gemini_direct", "gemini-2.5-pro", True),   # Grounded
        
        # Vertex tests
        ("Vertex/Gemini", "vertex", "gemini-2.5-pro", False),  # Ungrounded
        ("Vertex/Gemini", "vertex", "gemini-2.5-pro", True),   # Grounded
    ]
    
    all_results = []
    
    print(f"\n{'#'*80}")
    print(f"# TESTING ALL ADAPTERS WITH DE ALS CONTEXT")
    print(f"# Time: {datetime.now().isoformat()}")
    print(f"# Prompt: 'Tell me the primary health and wellness news during August 2025'")
    print(f"{'#'*80}")
    
    for adapter_name, vendor, model, grounded in tests:
        result = await test_adapter(adapter_name, vendor, model, grounded, als_context)
        all_results.append(result)
        await asyncio.sleep(2)  # Brief pause between tests
    
    # Write results to file
    output_file = f"test_results_all_adapters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'#'*80}")
    print(f"# SUMMARY")
    print(f"{'#'*80}")
    
    for result in all_results:
        status = "✅" if result.get('success') else "❌"
        grounding = "GROUNDED" if result['grounded'] else "UNGROUNDED"
        citations_info = ""
        if result.get('citations'):
            anchored = result.get('metadata', {}).get('anchored_citations_count', 0)
            unlinked = result.get('metadata', {}).get('unlinked_sources_count', 0)
            citations_info = f" | Citations: {len(result['citations'])} (A:{anchored}/U:{unlinked})"
        
        print(f"{status} {result['adapter']:15} {grounding:11} | {result.get('elapsed_seconds', 0):.2f}s{citations_info}")
    
    print(f"\n📁 Full results saved to: {output_file}")
    
    # Also create a human-readable report
    report_file = f"test_report_all_adapters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# Adapter Test Report - {datetime.now().isoformat()}\n\n")
        f.write(f"**ALS Context:** DE (Germany)\n")
        f.write(f"**Prompt:** Tell me the primary health and wellness news during August 2025\n\n")
        
        for result in all_results:
            f.write(f"\n## {result['adapter']} - {'GROUNDED' if result['grounded'] else 'UNGROUNDED'}\n\n")
            f.write(f"- **Model:** {result['model']}\n")
            f.write(f"- **Success:** {'✅ Yes' if result.get('success') else '❌ No'}\n")
            f.write(f"- **Time:** {result.get('elapsed_seconds', 0):.2f} seconds\n")
            f.write(f"- **Grounded Effective:** {result.get('grounded_effective', False)}\n")
            
            if result.get('error'):
                f.write(f"- **Error:** {result['error']}\n")
            
            if result.get('citations'):
                f.write(f"\n### Citations ({len(result['citations'])} total)\n")
                f.write(f"- Anchored: {result.get('metadata', {}).get('anchored_citations_count', 0)}\n")
                f.write(f"- Unlinked: {result.get('metadata', {}).get('unlinked_sources_count', 0)}\n\n")
                
                for i, citation in enumerate(result['citations'][:10], 1):
                    if 'url' in citation:
                        f.write(f"{i}. **{citation.get('title', 'No title')}**\n")
                        f.write(f"   - URL: {citation['url']}\n")
                        f.write(f"   - Type: {citation.get('source_type', 'unknown')}\n")
                        f.write(f"   - Domain: {citation.get('domain', 'unknown')}\n\n")
            
            f.write(f"\n### Response Content\n\n")
            f.write(f"```\n{result.get('content', 'No content')[:2000]}\n")
            if len(result.get('content', '')) > 2000:
                f.write(f"\n... (truncated, full length: {len(result['content'])} chars)\n")
            f.write(f"```\n\n")
            f.write(f"---\n")
    
    print(f"📄 Human-readable report saved to: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())