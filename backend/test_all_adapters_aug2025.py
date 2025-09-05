#!/usr/bin/env python3
"""Test all adapters with August 2025 health news prompt."""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Set required environment variables
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["LLM_TIMEOUT_GR"] = "120"
os.environ["GEMINI_PRO_THINKING_BUDGET"] = "256"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_UNGROUNDED"] = "768"
os.environ["GEMINI_PRO_MAX_OUTPUT_TOKENS_GROUNDED"] = "1536"


async def test_adapter(vendor: str, model: str, grounded: bool):
    """Test a single adapter."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter_name = f"{vendor}/{model}"
    mode = "GROUNDED" if grounded else "UNGROUNDED"
    print(f"\n{'='*80}")
    print(f"Testing: {adapter_name} - {mode}")
    print('='*80)
    
    try:
        # Initialize adapter
        adapter = UnifiedLLMAdapter()
        
        # Create request with DE ALS context
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant providing information about health and wellness news."
                },
                {
                    "role": "user",
                    "content": "Tell me the primary health and wellness news during August 2025"
                }
            ],
            grounded=grounded,
            max_tokens=800 if grounded else 600,
            temperature=0.7,
            als_context={
                "country_code": "DE",
                "locale": "de-DE"
            }
        )
        
        # Add metadata for ALS
        request.metadata = {
            "als_country": "DE",
            "als_locale": "de-DE",
            "als_present": True
        }
        
        if grounded:
            request.meta = {"grounding_mode": "AUTO"}
        
        # Execute request
        start = datetime.now()
        response = await adapter.complete(request)
        elapsed = (datetime.now() - start).total_seconds()
        
        # Display results
        print(f"\n✅ Success: {response.success}")
        print(f"⏱️  Time: {elapsed:.2f}s")
        
        # Show content
        content = response.content if hasattr(response, 'content') else ""
        print(f"\n📝 Response ({len(content)} chars):")
        print("-" * 60)
        print(content if content else "[EMPTY RESPONSE]")
        print("-" * 60)
        
        # Show metadata
        if hasattr(response, 'metadata') and response.metadata:
            meta = response.metadata
            
            # Show usage if available
            if 'usage' in meta:
                usage = meta['usage']
                print(f"\n📊 Token Usage:")
                print(f"  - Thoughts: {usage.get('thoughts_token_count', 'N/A')}")
                print(f"  - Input: {usage.get('input_token_count', 'N/A')}")
                print(f"  - Output: {usage.get('output_token_count', 'N/A')}")
                print(f"  - Total: {usage.get('total_token_count', 'N/A')}")
            
            if 'finish_reason' in meta:
                print(f"  - Finish: {meta['finish_reason']}")
        
        # Show citations if grounded
        if grounded and hasattr(response, 'citations') and response.citations:
            print(f"\n📚 Citations Found: {len(response.citations)}")
            metadata = response.metadata if hasattr(response, 'metadata') else {}
            print(f"  - Anchored: {metadata.get('anchored_citations_count', 0)}")
            print(f"  - Unlinked: {metadata.get('unlinked_sources_count', 0)}")
            
            print("\n🔗 Citation URLs:")
            for i, cite in enumerate(response.citations, 1):
                if 'url' in cite:
                    title = cite.get('title', 'No title')[:80]
                    url = cite['url']
                    source_type = cite.get('source_type', 'unknown')
                    print(f"\n  [{i}] {title}")
                    print(f"      URL: {url}")
                    print(f"      Type: {source_type}")
                    if 'domain' in cite:
                        print(f"      Domain: {cite['domain']}")
        elif grounded:
            print("\n📚 No citations returned (grounding may not have triggered)")
        
        # Return detailed results
        return {
            "adapter": adapter_name,
            "mode": mode,
            "success": response.success,
            "elapsed": elapsed,
            "content_length": len(content),
            "content": content,
            "citations": response.citations if hasattr(response, 'citations') else [],
            "metadata": response.metadata if hasattr(response, 'metadata') else {},
            "grounded_effective": response.grounded_effective if hasattr(response, 'grounded_effective') else False
        }
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return {
            "adapter": adapter_name,
            "mode": mode,
            "success": False,
            "error": str(e)
        }


async def main():
    """Run all tests."""
    print("\n" + "#"*80)
    print("# ALL ADAPTERS TEST - AUGUST 2025 HEALTH NEWS")
    print("# ALS Context: DE (Germany)")
    print("# " + datetime.now().isoformat())
    print("#"*80)
    
    tests = [
        # OpenAI GPT-5
        ("openai", "gpt-5-2025-08-07", False),  # Ungrounded
        ("openai", "gpt-5-2025-08-07", True),   # Grounded
        
        # Gemini Direct 2.5 Pro
        ("gemini_direct", "gemini-2.5-pro", False),  # Ungrounded
        ("gemini_direct", "gemini-2.5-pro", True),   # Grounded
        
        # Vertex Gemini 2.5 Pro
        ("vertex", "gemini-2.5-pro", False),  # Ungrounded
        ("vertex", "gemini-2.5-pro", True),   # Grounded
    ]
    
    all_results = []
    for vendor, model, grounded in tests:
        result = await test_adapter(vendor, model, grounded)
        all_results.append(result)
        await asyncio.sleep(2)  # Brief pause between tests
    
    # Print summary
    print(f"\n{'#'*80}")
    print("# SUMMARY")
    print(f"{'#'*80}\n")
    
    print("| Adapter | Mode | Success | Time | Content | Citations |")
    print("|---------|------|---------|------|---------|-----------|")
    
    for r in all_results:
        status = "✅" if r.get('success') else "❌"
        time = f"{r.get('elapsed', 0):.1f}s" if r.get('success') else "N/A"
        content_len = r.get('content_length', 0)
        citations_list = r.get('citations')
        citations = len(citations_list) if citations_list else 0
        mode = r['mode'][:4]  # GROU or UNGR
        
        print(f"| {r['adapter']:25} | {mode} | {status:7} | {time:6} | {content_len:7} | {citations:9} |")
    
    print("\n" + "="*80)
    print("Test completed at", datetime.now().isoformat())


if __name__ == "__main__":
    asyncio.run(main())