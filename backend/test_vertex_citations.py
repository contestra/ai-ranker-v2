#!/usr/bin/env python3
"""Quick test for Vertex citation extraction with grounding_chunks/supports"""
import asyncio
import json
import logging
import sys
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_vertex_citations():
    """Test Vertex grounding to see if citations are captured"""
    print("\n" + "="*60)
    print("VERTEX CITATION EXTRACTION TEST")
    print("="*60)
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        messages=[
            {"role": "user", "content": "What are the latest features of Google's Gemini AI models in 2024?"}
        ],
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",
        grounded=True,
        json_mode=False,
        max_tokens=300,
        meta={"grounding_mode": "AUTO"},
        template_id="test_vertex_citations",
        run_id="citation_test_001"
    )
    
    try:
        print("\nSending grounded request to Vertex...")
        response = await adapter.complete(request)
        
        print(f"\n✓ Response received")
        print(f"  Success: {response.success}")
        print(f"  Grounded Effective: {response.grounded_effective}")
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            tool_count = meta.get('tool_call_count', 0)
            citations = meta.get('citations', [])
            
            print(f"  Tool Call Count: {tool_count}")
            print(f"  Citations Count: {len(citations)}")
            
            if citations:
                print(f"\n  ✅ CITATIONS CAPTURED! Found {len(citations)} citations:")
                for i, cit in enumerate(citations[:5], 1):  # Show first 5
                    print(f"\n  Citation {i}:")
                    print(f"    URL: {cit.get('url', 'N/A')}")
                    print(f"    Title: {cit.get('title', 'N/A')}")
                    snippet = cit.get('snippet', '')
                    if snippet:
                        print(f"    Snippet: {snippet[:100]}...")
            else:
                print(f"\n  ⚠️ NO CITATIONS FOUND")
                
                # Check forensic audit
                audit = meta.get('citations_audit', {})
                if audit:
                    print("\n  FORENSIC AUDIT DATA:")
                    print(f"    Candidates: {audit.get('candidates', 0)}")
                    print(f"    Keys found: {audit.get('grounding_metadata_keys', [])}")
                    
                    example = audit.get('example', {})
                    if example:
                        print(f"    Example structure:")
                        print(json.dumps(example, indent=6)[:500])
                
                # Check why_not_grounded
                why_not = meta.get('why_not_grounded')
                if why_not:
                    print(f"\n  Why not grounded: {why_not}")
        
        print(f"\n  Response preview: {response.content[:150]}...")
        
        return response
        
    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        logger.exception("Test failed")
        return None

async def main():
    result = await test_vertex_citations()
    
    if result and hasattr(result, 'metadata'):
        citations = result.metadata.get('citations', [])
        if citations:
            print("\n" + "="*60)
            print("SUCCESS: Citations are now being captured!")
            print(f"Found {len(citations)} citations from grounding_chunks/supports")
            print("="*60)
        else:
            print("\n" + "="*60)
            print("ATTENTION: Citations still not captured")
            print("Check the forensic audit data above for SDK structure")
            print("="*60)

if __name__ == "__main__":
    asyncio.run(main())