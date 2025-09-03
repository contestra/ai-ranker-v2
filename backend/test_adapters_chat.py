#!/usr/bin/env python3
"""
Test adapters with simple chat (no grounding).
"""
import asyncio
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

def get_timestamp() -> str:
    """Get current ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()

async def test_openai_chat():
    """Test OpenAI with simple chat."""
    print("\n" + "="*80)
    print("TESTING OPENAI ADAPTER - CHAT MODE")
    print("="*80)
    
    # Try to use fixed adapter
    try:
        from app.llm.adapters.openai_adapter_fixed import OpenAIAdapter
    except ImportError:
        from app.llm.adapters.openai_adapter import OpenAIAdapter
    
    from app.llm.types import LLMRequest
    
    adapter = OpenAIAdapter()
    
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[
            {"role": "user", "content": "What is the capital of France? Answer in one word."}
        ],
        grounded=False,
        max_tokens=10
    )
    
    timeout_sec = int(os.getenv("CHAT_TEST_TIMEOUT_SEC", "45"))
    
    try:
        start_time = time.monotonic()
        print(f"[{get_timestamp()}] Calling OpenAI adapter... (grounding=OFF, json=OFF)", flush=True)
        
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=30),
            timeout=timeout_sec
        )
        
        duration_ms = int((time.monotonic() - start_time) * 1000)
        print(f"[{get_timestamp()}] OpenAI adapter returned. duration={duration_ms}ms", flush=True)
        print(f"✅ Response: {response.content}")
        return True
        
    except asyncio.TimeoutError:
        print(f"[{get_timestamp()}] OpenAI adapter TIMED OUT after {timeout_sec}s", flush=True)
        return False
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)[:200]}")
        return False

async def test_gemini_chat():
    """Test Gemini with simple chat."""
    print("\n" + "="*80)
    print("TESTING GEMINI ADAPTER - CHAT MODE")
    print("="*80)
    
    from app.llm.adapters.gemini_adapter import GeminiAdapter
    from app.llm.types import LLMRequest
    
    adapter = GeminiAdapter()
    
    request = LLMRequest(
        vendor="gemini_direct",
        model="gemini-2.5-pro",
        messages=[
            {"role": "user", "content": "What is the capital of France? Answer in one word."}
        ],
        grounded=False,
        max_tokens=10
    )
    
    timeout_sec = int(os.getenv("CHAT_TEST_TIMEOUT_SEC", "45"))
    
    try:
        start_time = time.monotonic()
        print(f"[{get_timestamp()}] Calling Gemini adapter... (grounding=OFF, json=OFF)", flush=True)
        
        response = await asyncio.wait_for(
            adapter.complete(request, timeout=30),
            timeout=timeout_sec
        )
        
        duration_ms = int((time.monotonic() - start_time) * 1000)
        print(f"[{get_timestamp()}] Gemini adapter returned. duration={duration_ms}ms", flush=True)
        print(f"✅ Response: {response.content}")
        return True
        
    except asyncio.TimeoutError:
        print(f"[{get_timestamp()}] Gemini adapter TIMED OUT after {timeout_sec}s", flush=True)
        return False
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)[:200]}")
        return False

async def main():
    print("="*80)
    print("CHAT MODE TEST (NO GROUNDING)")
    print("="*80)
    
    # Print ALS settings
    print(f"\n📋 Environment:")
    print(f"  • ALS_COUNTRY_CODE: {os.getenv('ALS_COUNTRY_CODE', 'DE (default)')}")
    print(f"  • ALS_LOCALE: {os.getenv('ALS_LOCALE', 'de-DE (default)')}")
    print(f"  • ALS_TZ: {os.getenv('ALS_TZ', 'Europe/Berlin (default)')}")
    print(f"  • Chat test timeout: {os.getenv('CHAT_TEST_TIMEOUT_SEC', '45')}s")
    
    # Test both
    openai_ok = await test_openai_chat()
    gemini_ok = await test_gemini_chat()
    
    print("\n" + "="*80)
    print("RESULTS:")
    print(f"OpenAI: {'✅ PASSED' if openai_ok else '❌ FAILED/TIMED_OUT'}")
    print(f"Gemini: {'✅ PASSED' if gemini_ok else '❌ FAILED/TIMED_OUT'}")
    print("="*80)
    
    # Exit code
    exit_code = 0 if (openai_ok and gemini_ok) else 1
    print(f"\nExit code: {exit_code}")
    return exit_code

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))