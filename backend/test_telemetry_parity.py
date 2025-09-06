#!/usr/bin/env python3
"""Test telemetry parity between OpenAI and Google adapters."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_telemetry_parity():
    adapter = UnifiedLLMAdapter()
    
    print("=" * 80)
    print("Testing Telemetry Parity Between Adapters")
    print("=" * 80)
    
    test_cases = [
        {
            "name": "OpenAI GPT-4o",
            "vendor": "openai",
            "model": "gpt-4o",
            "grounded": False
        },
        {
            "name": "Vertex Gemini 2.5 Pro",
            "vendor": "vertex",
            "model": "gemini-2.5-pro",
            "grounded": False
        },
        {
            "name": "Gemini Direct 2.5 Pro",
            "vendor": "gemini_direct",
            "model": "gemini-2.5-pro",
            "grounded": False
        }
    ]
    
    prompt = "What is 2+2? Answer in one word."
    
    for test in test_cases:
        print(f"\n{test['name']}")
        print("-" * 60)
        
        request = LLMRequest(
            vendor=test['vendor'],
            model=test['model'],
            messages=[{"role": "user", "content": prompt}],
            grounded=test['grounded'],
            max_tokens=50,
            temperature=0.0
        )
        
        try:
            response = await adapter.complete(request, session=None)
            
            print(f"✅ Success: {response.success}")
            print(f"Content: {response.content[:50] if response.content else '(empty)'}")
            
            # Check telemetry fields
            print(f"\n📊 Telemetry Fields:")
            
            # Usage (should be on response directly)
            if response.usage:
                print(f"  Usage (response level):")
                print(f"    - prompt_tokens: {response.usage.get('prompt_tokens', 'N/A')}")
                print(f"    - completion_tokens: {response.usage.get('completion_tokens', 'N/A')}")
                print(f"    - total_tokens: {response.usage.get('total_tokens', 'N/A')}")
                if 'reasoning_tokens' in response.usage:
                    print(f"    - reasoning_tokens: {response.usage['reasoning_tokens']}")
            else:
                print(f"  ⚠️ Usage missing on response")
            
            # Metadata fields
            if response.metadata:
                print(f"\n  Metadata fields:")
                
                # Finish reason (new for OpenAI, existing for Google)
                finish_reason = response.metadata.get('finish_reason', 'N/A')
                print(f"    - finish_reason: {finish_reason}")
                
                # Usage in metadata (for backup/consistency)
                if 'usage' in response.metadata:
                    print(f"    - usage (in metadata): ✅ Present")
                else:
                    print(f"    - usage (in metadata): ❌ Not present")
                
                # Common telemetry fields
                print(f"    - latency_ms: {response.metadata.get('latency_ms', 'N/A')}")
                print(f"    - response_api: {response.metadata.get('response_api', 'N/A')}")
                print(f"    - web_tool_type: {response.metadata.get('web_tool_type', 'N/A')}")
                print(f"    - tool_call_count: {response.metadata.get('tool_call_count', 0)}")
                
                # Check telemetry parity
                required_fields = ['finish_reason', 'latency_ms', 'response_api']
                missing_fields = [f for f in required_fields if f not in response.metadata]
                
                if missing_fields:
                    print(f"\n  ⚠️ Missing required telemetry fields: {missing_fields}")
                else:
                    print(f"\n  ✓ All required telemetry fields present")
            else:
                print(f"  ⚠️ No metadata on response")
                
        except Exception as e:
            print(f"❌ Error: {str(e)[:200]}")
    
    print("\n" + "=" * 80)
    print("Telemetry Parity Summary")
    print("=" * 80)
    print("All adapters should have:")
    print("  1. response.usage with prompt/completion/total tokens")
    print("  2. metadata.finish_reason for completion status")
    print("  3. metadata.latency_ms for performance tracking")
    print("  4. metadata.response_api to identify the API used")

if __name__ == "__main__":
    asyncio.run(test_telemetry_parity())