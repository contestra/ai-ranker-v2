#!/usr/bin/env python3
"""
Quick test to verify citation extraction fixes.
"""

import asyncio
import json
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_vertex_citations():
    """Test Vertex with grounding to see if citations are extracted."""
    print("\n" + "="*60)
    print("TESTING VERTEX CITATION EXTRACTION")
    print("="*60)
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        model="gemini-2.5-pro",
        messages=[
            {"role": "user", "content": "What are the latest AI developments in 2024?"}
        ],
        grounded=True,
        max_tokens=500,
        temperature=0.7
    )
    
    # Add grounding mode
    request.meta = {"grounding_mode": "AUTO"}
    
    try:
        response = await adapter.complete(request)
        
        print(f"✓ Success: {response.success}")
        print(f"✓ Grounded Effective: {response.grounded_effective}")
        print(f"✓ Tool Calls: {response.metadata.get('tool_call_count', 0) if response.metadata else 0}")
        print(f"✓ Response Length: {len(response.content) if response.content else 0}")
        
        # Check for citations
        if response.metadata and 'citations' in response.metadata:
            citations = response.metadata['citations']
            print(f"✅ Citations count: {len(citations)}")
            
            if citations:
                print("\nFirst 3 citations:")
                for i, cit in enumerate(citations[:3], 1):
                    print(f"{i}. Domain: {cit.get('source_domain', 'N/A')}")
                    print(f"   URL: {cit.get('url', '')[:80]}...")
                    print(f"   Title: {cit.get('title', '')[:60]}...")
        else:
            print("❌ No citations in metadata")
            
            # Check why_not_grounded
            if response.metadata and 'why_not_grounded' in response.metadata:
                print(f"⚠ Why not grounded: {response.metadata['why_not_grounded']}")
            
            # Check audit if present
            if response.metadata and 'citations_audit' in response.metadata:
                audit = response.metadata['citations_audit']
                print(f"\nCitation audit:")
                print(f"  Grounding metadata keys: {audit.get('grounding_metadata_keys', [])[:10]}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

async def test_gemini_ungrounded():
    """Test ungrounded Gemini to see if it works now."""
    print("\n" + "="*60)
    print("TESTING GEMINI UNGROUNDED")
    print("="*60)
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        model="gemini-2.5-pro",
        messages=[
            {"role": "user", "content": "Tell me about recent longevity research breakthroughs"}
        ],
        grounded=False,
        max_tokens=500,
        temperature=0.7
    )
    
    try:
        response = await adapter.complete(request)
        
        print(f"✓ Success: {response.success}")
        print(f"✓ Response Length: {len(response.content) if response.content else 0}")
        
        if response.content:
            print(f"✅ Response preview: {response.content[:200]}...")
        else:
            print("❌ Empty response")
            
            # Check metadata for retry info
            if response.metadata:
                if 'retry_attempted' in response.metadata:
                    print(f"⚠ Retry attempted: {response.metadata['retry_attempted']}")
                if 'retry_reason' in response.metadata:
                    print(f"⚠ Retry reason: {response.metadata['retry_reason']}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    """Run both tests."""
    await test_vertex_citations()
    await test_gemini_ungrounded()

if __name__ == "__main__":
    asyncio.run(main())