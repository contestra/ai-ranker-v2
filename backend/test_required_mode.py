#!/usr/bin/env python3
"""
Test Required mode fail-close behavior with pre-flight probe
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

async def test_required_mode():
    """Test that Required mode fails immediately when grounding unsupported"""
    
    adapter = UnifiedLLMAdapter()
    
    print("Testing OpenAI Grounded-Required mode...")
    print("="*60)
    
    request = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[{'role': 'user', 'content': 'What is the VAT rate?'}],
        grounded=True,
        temperature=0.7,
        max_tokens=1000,
        als_context={'country_code': 'US', 'locale': 'en-US'}
    )
    request.meta = {'grounding_mode': 'REQUIRED'}
    request.tool_choice = 'required'
    
    try:
        print("Attempting grounded request with REQUIRED mode...")
        response = await adapter.complete(request)
        
        # If we get here, check if it actually grounded
        print(f"\n⚠️ UNEXPECTED: Request succeeded!")
        print(f"Success: {response.success}")
        print(f"Content length: {len(response.content) if response.content else 0}")
        print(f"Grounded effective: {response.grounded_effective}")
        print(f"Tool calls: {response.metadata.get('tool_call_count', 0) if response.metadata else 0}")
        print(f"Why not grounded: {response.metadata.get('why_not_grounded', 'N/A') if response.metadata else 'N/A'}")
        
        if not response.grounded_effective:
            print("\n❌ PROBLEM: Required mode should have failed but returned ungrounded content!")
    
    except RuntimeError as e:
        error_msg = str(e)
        if "GROUNDING_NOT_SUPPORTED" in error_msg:
            print(f"\n✅ CORRECT: Required mode failed as expected!")
            print(f"Error: {error_msg}")
        elif "GROUNDING_REQUIRED_ERROR" in error_msg:
            print(f"\n✅ CORRECT: Required mode enforcement triggered!")
            print(f"Error: {error_msg}")
        else:
            print(f"\n❓ Unexpected error: {error_msg}")
    
    except Exception as e:
        print(f"\n❌ Unexpected error type: {type(e).__name__}: {e}")
    
    print("\n" + "="*60)
    print("Testing OpenAI Grounded-Preferred mode for comparison...")
    print("="*60)
    
    # Now test Preferred mode to show it proceeds ungrounded
    request2 = LLMRequest(
        vendor='openai',
        model='gpt-5',
        messages=[{'role': 'user', 'content': 'What is the VAT rate?'}],
        grounded=True,
        temperature=0.7,
        max_tokens=1000,
        als_context={'country_code': 'US', 'locale': 'en-US'}
    )
    request2.meta = {'grounding_mode': 'AUTO'}
    request2.tool_choice = 'auto'
    
    try:
        print("Attempting grounded request with PREFERRED/AUTO mode...")
        response = await adapter.complete(request2)
        
        print(f"\n✅ Preferred mode succeeded (as expected)")
        print(f"Content length: {len(response.content) if response.content else 0}")
        print(f"Grounded effective: {response.grounded_effective}")
        print(f"Tool calls: {response.metadata.get('tool_call_count', 0) if response.metadata else 0}")
        print(f"Why not grounded: {response.metadata.get('why_not_grounded', 'N/A') if response.metadata else 'N/A'}")
        print(f"Grounding not supported: {response.metadata.get('grounding_not_supported', False) if response.metadata else False}")
        
        # Show first 200 chars of response
        if response.content:
            preview = response.content[:200] + "..." if len(response.content) > 200 else response.content
            print(f"\nResponse preview: {preview}")
    
    except Exception as e:
        print(f"\n❌ Unexpected error in Preferred mode: {e}")

if __name__ == "__main__":
    asyncio.run(test_required_mode())