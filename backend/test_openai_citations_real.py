#!/usr/bin/env python3
"""Test OpenAI citation extraction with real API."""

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

# Enable two-step for testing
os.environ["OPENAI_GROUNDED_TWO_STEP"] = "true"


async def test_real_api():
    """Test citation extraction with real OpenAI API."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*80)
    print("OPENAI CITATION EXTRACTION - REAL API TEST")
    print("="*80 + "\n")
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{
            "role": "user",
            "content": "What were the top 3 technology breakthroughs in October 2024?"
        }],
        grounded=True,
        max_tokens=2000,
        temperature=0.7
    )
    
    print("🚀 Executing grounded request...")
    start = datetime.now()
    response = await adapter.complete(request)
    elapsed = (datetime.now() - start).total_seconds()
    
    print(f"\n✅ Success: {response.success}")
    print(f"⏱️  Time: {elapsed:.2f}s")
    print(f"📝 Content length: {len(response.content) if response.content else 0} chars")
    
    if response.content:
        print(f"\n📄 Content preview:\n{'-'*60}")
        print(response.content[:500] + "..." if len(response.content) > 500 else response.content)
        print('-'*60)
    else:
        print("❌ Empty content")
    
    # Check metadata
    if hasattr(response, 'metadata') and response.metadata:
        print(f"\n📊 Metadata:")
        print(f"  - Tool calls: {response.metadata.get('tool_call_count', 0)}")
        print(f"  - Provoker used: {response.metadata.get('provoker_retry_used', False)}")
        print(f"  - Synthesis used: {response.metadata.get('synthesis_step_used', False)}")
        print(f"  - Citation count: {response.metadata.get('citation_count', 0)}")
        print(f"  - Anchored: {response.metadata.get('anchored_citations_count', 0)}")
        print(f"  - Unlinked: {response.metadata.get('unlinked_sources_count', 0)}")
        
        if response.metadata.get('synthesis_step_used'):
            print(f"  - Synthesis evidence: {response.metadata.get('synthesis_evidence_count', 0)}")
    
    # Check citations
    if hasattr(response, 'citations') and response.citations:
        print(f"\n📚 Citations found: {len(response.citations)}")
        for i, cite in enumerate(response.citations[:5], 1):
            print(f"\n  [{i}] {cite.get('title', 'No title')[:80]}")
            print(f"      URL: {cite['url']}")
            print(f"      Domain: {cite.get('domain', 'unknown')}")
            print(f"      Type: {cite.get('source_type', 'unknown')}")
    else:
        print("\n📚 No citations extracted")
    
    # Save full response for inspection
    output = {
        "request": {
            "model": request.model,
            "grounded": request.grounded,
            "max_tokens": request.max_tokens
        },
        "response": {
            "success": response.success,
            "content_length": len(response.content) if response.content else 0,
            "content": response.content,
            "citations": response.citations if hasattr(response, 'citations') else [],
            "metadata": response.metadata if hasattr(response, 'metadata') else {}
        },
        "elapsed_seconds": elapsed
    }
    
    filename = f"openai_citations_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n💾 Full response saved to: {filename}")
    
    return response


if __name__ == "__main__":
    asyncio.run(test_real_api())