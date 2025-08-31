#!/usr/bin/env python3
"""
Quick test to verify OpenAI and Vertex grounding fixes
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["ALLOW_PREVIEW_COMPAT"] = "false"
os.environ["OPENAI_READ_TIMEOUT_MS"] = "120000"
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_grounding_fixed():
    """Test that grounding now works for both OpenAI and Vertex"""
    
    adapter = UnifiedLLMAdapter()
    
    print("="*60)
    print("Testing OpenAI Grounding (Should now work!)")
    print("="*60)
    
    # Test OpenAI Preferred
    request = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[{'role': 'user', 'content': 'Tell me the latest news'}],
        grounded=True,
        temperature=0.7,
        max_tokens=1000
    )
    request.meta = {'grounding_mode': 'AUTO'}
    request.tool_choice = 'auto'
    
    try:
        print("\n1. OpenAI Grounded-Preferred mode...")
        response = await adapter.complete(request)
        
        print(f"   Success: {response.success}")
        print(f"   Grounded effective: {response.grounded_effective}")
        print(f"   Tool calls: {response.metadata.get('tool_call_count', 0) if response.metadata else 0}")
        print(f"   Citations: {response.metadata.get('citations_count', 0) if response.metadata else 0}")
        print(f"   Why not grounded: {response.metadata.get('why_not_grounded', 'N/A') if response.metadata else 'N/A'}")
        
        if response.grounded_effective:
            print("   ✅ OpenAI grounding is WORKING!")
        else:
            print("   ⚠️ OpenAI grounding still not effective")
            
        # Show response preview
        if response.content:
            preview = response.content[:200] + "..." if len(response.content) > 200 else response.content
            print(f"   Response: {preview}")
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("Testing Vertex Grounding (Citations check)")
    print("="*60)
    
    # Test Vertex Preferred
    request2 = LLMRequest(
        vendor='vertex',
        model='publishers/google/models/gemini-2.5-pro',
        messages=[{'role': 'user', 'content': 'Tell me the latest news'}],
        grounded=True,
        temperature=0.7,
        max_tokens=1000
    )
    request2.meta = {'grounding_mode': 'AUTO'}
    
    try:
        print("\n2. Vertex Grounded-Preferred mode...")
        response = await adapter.complete(request2)
        
        print(f"   Success: {response.success}")
        print(f"   Grounded effective: {response.grounded_effective}")
        print(f"   Tool calls: {response.metadata.get('tool_call_count', 0) if response.metadata else 0}")
        print(f"   Citations: {response.metadata.get('citations_count', 0) if response.metadata else 0}")
        
        if response.metadata and 'citations' in response.metadata:
            print(f"   ✅ Vertex citations extracted: {len(response.metadata['citations'])} citations")
            for i, cit in enumerate(response.metadata['citations'][:3], 1):
                print(f"      {i}. {cit.get('title', 'No title')[:60]}")
        else:
            print("   ⚠️ No citations extracted")
            
        # Show response preview
        if response.content:
            preview = response.content[:200] + "..." if len(response.content) > 200 else response.content
            print(f"   Response: {preview}")
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("Summary:")
    print("- OpenAI grounding should now attach web_search tools")
    print("- Vertex should extract and count citations")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_grounding_fixed())