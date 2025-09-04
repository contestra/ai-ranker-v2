#!/usr/bin/env python3
"""Simple test of all adapters with DE ALS context."""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set required environment variables
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["LLM_TIMEOUT_GR"] = "120"
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
os.environ["VERTEX_PROJECT"] = os.getenv("VERTEX_PROJECT", "")


async def test_adapter(vendor: str, model: str, grounded: bool):
    """Test a single adapter."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter_name = f"{vendor}/{model}"
    print(f"\n{'='*80}")
    print(f"Testing: {adapter_name} - {'GROUNDED' if grounded else 'UNGROUNDED'}")
    print('='*80)
    
    try:
        # Initialize adapter
        adapter = UnifiedLLMAdapter()
        
        # Create basic request
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Provide informative responses about health and wellness."
                },
                {
                    "role": "user",
                    "content": "Tell me about the primary health and wellness news during August 2025. Focus on major developments."
                }
            ],
            grounded=grounded,
            max_tokens=500,
            temperature=0.7,
            als_context={
                "country_code": "DE",
                "locale": "de-DE"
            }
        )
        
        # Add metadata after creation
        request.metadata = {
            "als_country": "DE",
            "capabilities": {
                "supports_reasoning_effort": True,
                "supports_thinking_budget": True
            }
        }
        
        if grounded:
            request.meta = {"grounding_mode": "AUTO"}
        
        # Execute request
        start = datetime.now()
        response = await adapter.complete(request)
        elapsed = (datetime.now() - start).total_seconds()
        
        # Process response
        print(f"\n✅ Success in {elapsed:.2f}s")
        
        # Show content
        content = response.content if hasattr(response, 'content') else ""
        print(f"\n📝 Response ({len(content)} chars):")
        print("-" * 40)
        print(content[:500] + "..." if len(content) > 500 else content)
        print("-" * 40)
        
        # Show citations if grounded
        if grounded and hasattr(response, 'citations') and response.citations:
            print(f"\n📚 Citations: {len(response.citations)}")
            metadata = response.metadata if hasattr(response, 'metadata') else {}
            print(f"  Anchored: {metadata.get('anchored_citations_count', 0)}")
            print(f"  Unlinked: {metadata.get('unlinked_sources_count', 0)}")
            
            for i, cite in enumerate(response.citations[:3], 1):
                if 'url' in cite:
                    print(f"\n  {i}. {cite.get('title', 'No title')[:60]}")
                    print(f"     {cite['url'][:80]}")
                    print(f"     Type: {cite.get('source_type', 'unknown')}")
        elif grounded:
            print("\n📚 No citations found (grounding may not have triggered)")
        
        return {
            "adapter": adapter_name,
            "grounded": grounded,
            "success": True,
            "elapsed": elapsed,
            "content_length": len(content),
            "content": content,
            "citations": response.citations if hasattr(response, 'citations') else [],
            "metadata": response.metadata if hasattr(response, 'metadata') else {}
        }
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)[:200]}")
        return {
            "adapter": adapter_name,
            "grounded": grounded,
            "success": False,
            "error": str(e)
        }


async def main():
    """Run all tests."""
    print("\n" + "#"*80)
    print("# ADAPTER TESTS WITH DE ALS")
    print("# " + datetime.now().isoformat())
    print("#"*80)
    
    tests = [
        # OpenAI
        ("openai", "gpt-5-2025-08-07", False),
        ("openai", "gpt-5-2025-08-07", True),
        
        # Gemini Direct
        ("gemini_direct", "gemini-2.5-pro", False),
        ("gemini_direct", "gemini-2.5-pro", True),
        
        # Vertex
        ("vertex", "gemini-2.5-pro", False),
        ("vertex", "gemini-2.5-pro", True),
    ]
    
    results = []
    for vendor, model, grounded in tests:
        result = await test_adapter(vendor, model, grounded)
        results.append(result)
        await asyncio.sleep(2)  # Pause between tests
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON results
    json_file = f"test_results_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Markdown report
    report_file = f"test_report_{timestamp}.md"
    with open(report_file, 'w') as f:
        f.write(f"# Adapter Test Report\n")
        f.write(f"**Date:** {datetime.now().isoformat()}\n")
        f.write(f"**ALS:** DE (Germany)\n\n")
        
        f.write("## Summary\n\n")
        f.write("| Adapter | Mode | Status | Time | Citations |\n")
        f.write("|---------|------|--------|------|----------|\n")
        
        for r in results:
            status = "✅" if r.get('success') else "❌"
            mode = "Grounded" if r['grounded'] else "Ungrounded"
            time = f"{r.get('elapsed', 0):.2f}s" if r.get('success') else "N/A"
            citations = ""
            if r.get('citations'):
                meta = r.get('metadata', {})
                a = meta.get('anchored_citations_count', 0)
                u = meta.get('unlinked_sources_count', 0)
                citations = f"{len(r['citations'])} (A:{a}/U:{u})"
            elif r['grounded'] and r.get('success'):
                citations = "None"
            else:
                citations = "-"
            
            f.write(f"| {r['adapter']} | {mode} | {status} | {time} | {citations} |\n")
        
        f.write("\n## Detailed Results\n\n")
        
        for r in results:
            f.write(f"### {r['adapter']} - {'Grounded' if r['grounded'] else 'Ungrounded'}\n\n")
            
            if r.get('success'):
                f.write(f"**Success:** Yes\n")
                f.write(f"**Time:** {r['elapsed']:.2f} seconds\n")
                f.write(f"**Content Length:** {r['content_length']} chars\n\n")
                
                if r.get('citations'):
                    f.write("**Citations:**\n\n")
                    for cite in r['citations'][:5]:
                        if 'url' in cite:
                            f.write(f"- [{cite.get('title', 'No title')}]({cite['url']})\n")
                            f.write(f"  - Type: {cite.get('source_type', 'unknown')}\n")
                            f.write(f"  - Domain: {cite.get('domain', 'unknown')}\n\n")
                
                f.write("**Response Preview:**\n\n```\n")
                f.write(r['content'][:1000])
                if len(r['content']) > 1000:
                    f.write("\n...(truncated)")
                f.write("\n```\n\n")
            else:
                f.write(f"**Success:** No\n")
                f.write(f"**Error:** {r.get('error', 'Unknown')[:500]}\n\n")
            
            f.write("---\n\n")
    
    print(f"\n{'#'*80}")
    print("# SUMMARY")
    print(f"{'#'*80}\n")
    
    for r in results:
        status = "✅" if r.get('success') else "❌"
        mode = "GROUNDED" if r['grounded'] else "UNGROUNDED"
        print(f"{status} {r['adapter']:20} {mode:11} {r.get('elapsed', 0):.2f}s")
    
    print(f"\n📁 Results: {json_file}")
    print(f"📄 Report: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())