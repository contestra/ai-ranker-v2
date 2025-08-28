#!/usr/bin/env python3
"""
Test grounding-specific fixes from ChatGPT review
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"
os.environ["OPENAI_MAX_WEB_SEARCHES"] = "4"  # Test configurability

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_grounding_fixes():
    """Test grounding with all the fixes applied"""
    adapter = UnifiedLLMAdapter()
    
    # Test 1: Basic grounding with web search
    print("\n=== TEST 1: Basic Grounding ===")
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is the current weather in San Francisco? Be specific."}],
        temperature=0,
        max_tokens=200,
        grounded=True
    )
    
    try:
        response = await adapter.complete(request)
        print(f"✅ Grounding successful!")
        print(f"Response: {response.content[:200]}...")
        
        # Check metadata for new signals
        meta = response.metadata
        print(f"\n📊 Metadata Analysis:")
        print(f"  - grounded_effective: {meta.get('grounded_effective', 'N/A')}")
        print(f"  - web_grounded: {meta.get('web_grounded', 'N/A')}")
        print(f"  - tool_call_count: {meta.get('tool_call_count', 'N/A')}")
        print(f"  - web_search_count: {meta.get('web_search_count', 'N/A')}")
        print(f"  - auto_trimmed: {meta.get('auto_trimmed', False)}")
        print(f"  - proxies_enabled: {meta.get('proxies_enabled', 'N/A')}")
        
        # Verify metadata preservation
        if 'proxies_enabled' in meta:
            print("✅ Metadata preservation verified (proxies_enabled present)")
        else:
            print("❌ Metadata preservation issue")
            
        # Verify grounding signal separation
        if 'web_grounded' in meta and 'grounded_effective' in meta:
            print("✅ Grounding signal separation verified")
        else:
            print("❌ Grounding signals not properly separated")
            
    except Exception as e:
        print(f"❌ Grounding test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Test synthesis fallback (if no message after tools)
    print("\n=== TEST 2: Synthesis Fallback Test ===")
    print("(This test may not trigger synthesis fallback in normal conditions)")
    
    # Test 3: Verify search limit configuration
    print("\n=== TEST 3: Search Limit Configuration ===")
    print(f"Max web searches configured: {os.getenv('OPENAI_MAX_WEB_SEARCHES', '2')}")
    
    # Test another grounding request to see if limit is respected
    request2 = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "Compare the current weather in New York, London, Tokyo, and Sydney. Give temperatures for each."}],
        temperature=0,
        max_tokens=300,
        grounded=True
    )
    
    try:
        response2 = await adapter.complete(request2)
        print(f"✅ Multi-location grounding successful!")
        
        meta2 = response2.metadata
        web_searches = meta2.get('web_search_count', 0)
        print(f"Web searches performed: {web_searches}")
        
        if web_searches <= 4:  # Our configured limit
            print(f"✅ Search limit respected ({web_searches} <= 4)")
        else:
            print(f"⚠️ Search limit may have been exceeded ({web_searches} > 4)")
            
    except Exception as e:
        print(f"❌ Multi-location test failed: {e}")
    
    print("\n" + "="*60)
    print("🎉 Grounding tests completed!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_grounding_fixes())