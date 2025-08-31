#!/usr/bin/env python3
"""Quick test of authority scoring"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest
from app.llm.domain_authority import authority_scorer

async def test_authority():
    adapter = UnifiedLLMAdapter()
    
    # Test with Vertex (more likely to ground successfully)
    request = LLMRequest(
        messages=[{"role": "user", "content": "What are the latest Tesla stock news with URLs?"}],
        vendor="vertex",
        model="publishers/google/models/gemini-2.5-pro",
        grounded=True,
        meta={"grounding_mode": "REQUIRED"},
        max_tokens=300,
        template_id="test_authority",
        run_id="auth_001"
    )
    
    print("Testing authority scoring with Vertex REQUIRED mode...")
    
    try:
        response = await asyncio.wait_for(adapter.complete(request), timeout=60)
        
        if hasattr(response, 'metadata'):
            citations = response.metadata.get('citations', [])
            print(f"\nFound {len(citations)} citations")
            
            if citations:
                # Score the citations
                metrics = authority_scorer.score_citations(citations)
                
                print("\n=== AUTHORITY ANALYSIS ===")
                print(f"Total Citations: {metrics['total_citations']}")
                print(f"Authority Score: {metrics['authority_score']}/100")
                print(f"Tier-1 Sources: {metrics['tier_1_count']} ({metrics['tier_1_percentage']}%)")
                print(f"Premium (Tier 1+2): {metrics['premium_percentage']}%")
                if metrics['penalty_percentage'] > 0:
                    print(f"⚠️ Low-quality: {metrics['penalty_percentage']}%")
                
                print("\n=== DOMAIN BREAKDOWN ===")
                for item in metrics['tier_breakdown']:
                    tier_label = {1: "Tier-1", 2: "Tier-2", 3: "Tier-3", 4: "Penalty"}[item['tier']]
                    print(f"[{tier_label}] {item['domain']}")
                    
            else:
                print("No citations found (model may not have grounded)")
                
    except asyncio.TimeoutError:
        print("Request timed out")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_authority())