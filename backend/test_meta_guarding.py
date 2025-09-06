#!/usr/bin/env python3
"""Test that OpenAI adapter handles missing meta field gracefully"""

import asyncio
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest, ALSContext
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.services.als.als_builder import ALSBuilder


@dataclass
class MinimalRequest:
    """Request without meta field to test guarding"""
    vendor: str
    model: str
    messages: List[Dict]
    grounded: bool
    temperature: float
    als_context: Optional[ALSContext] = None
    max_tokens: Optional[int] = None
    metadata: Optional[Dict] = None
    # Intentionally no meta field


async def test_without_meta():
    """Test OpenAI adapter with request that has no meta field"""
    adapter = OpenAIAdapter()
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block('DE')
    
    # Create request without meta field
    request = MinimalRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        grounded=False,
        temperature=0.5,
        als_context=ALSContext(
            country_code='DE',
            locale='de-DE',
            als_block=als_block,
            als_variant_id='de_v1'
        )
    )
    
    print("Testing OpenAI adapter WITHOUT meta field...")
    
    try:
        # This should not throw AttributeError
        result = await asyncio.wait_for(adapter.complete(request, timeout=30), timeout=35)
        print(f"✅ Success: {result.success}")
        print(f"Content: {result.content[:100] if result.content else 'None'}")
        print(f"No AttributeError - meta guarding working!")
        return True
    except AttributeError as e:
        print(f"❌ AttributeError: {e}")
        print("Meta guarding FAILED - request.meta access not protected")
        return False
    except Exception as e:
        print(f"❌ Other error: {e}")
        return False


async def test_with_meta():
    """Test OpenAI adapter with normal request that has meta field"""
    adapter = OpenAIAdapter()
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block('DE')
    
    # Create normal request with meta field
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        grounded=False,
        temperature=0.5,
        als_context=ALSContext(
            country_code='DE',
            locale='de-DE',
            als_block=als_block,
            als_variant_id='de_v1'
        ),
        meta={"reasoning_effort": "minimal"}  # Include meta with reasoning hint
    )
    
    print("\nTesting OpenAI adapter WITH meta field...")
    
    try:
        result = await asyncio.wait_for(adapter.complete(request, timeout=30), timeout=35)
        print(f"✅ Success: {result.success}")
        print(f"Content: {result.content[:100] if result.content else 'None'}")
        
        # Check if reasoning hint was processed
        if result.metadata and "reasoning_effort_applied" in result.metadata:
            print(f"Reasoning effort applied: {result.metadata['reasoning_effort_applied']}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_grounded_without_meta():
    """Test grounded mode without meta field"""
    adapter = OpenAIAdapter()
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block('DE')
    
    # Create grounded request without meta field
    request = MinimalRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        grounded=True,  # Grounded mode
        temperature=0.5,
        als_context=ALSContext(
            country_code='DE',
            locale='de-DE',
            als_block=als_block,
            als_variant_id='de_v1'
        )
    )
    
    print("\nTesting OpenAI adapter GROUNDED mode WITHOUT meta field...")
    
    try:
        result = await asyncio.wait_for(adapter.complete(request, timeout=60), timeout=65)
        print(f"✅ Success: {result.success}")
        print(f"Content: {result.content[:100] if result.content else 'None'}")
        print(f"Citations: {len(result.citations) if result.citations else 0}")
        print(f"No AttributeError - meta guarding working in grounded mode!")
        return True
    except AttributeError as e:
        print(f"❌ AttributeError: {e}")
        print("Meta guarding FAILED in grounded mode")
        return False
    except Exception as e:
        print(f"❌ Other error: {e}")
        return False


async def main():
    """Run all meta guarding tests"""
    print("="*60)
    print("META GUARDING TESTS FOR OPENAI ADAPTER")
    print("="*60)
    
    results = []
    
    # Test 1: Without meta field
    results.append(await test_without_meta())
    
    # Test 2: With meta field
    results.append(await test_with_meta())
    
    # Test 3: Grounded without meta
    results.append(await test_grounded_without_meta())
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Test without meta: {'✅ PASS' if results[0] else '❌ FAIL'}")
    print(f"Test with meta: {'✅ PASS' if results[1] else '❌ FAIL'}")
    print(f"Test grounded without meta: {'✅ PASS' if results[2] else '❌ FAIL'}")
    
    all_passed = all(results)
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)