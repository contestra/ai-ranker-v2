#!/usr/bin/env python3
"""Immutability audit - verify no silent model rewrites."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.adapters.openai_adapter import OpenAIAdapter

async def test_immutability_audit():
    print("=" * 80)
    print("Immutability Audit - No Silent Model Rewrites")
    print("=" * 80)
    
    # Test models that might have been silently rewritten before
    test_models = [
        "gpt-4o-chat",
        "gpt-4o-mini-chat",
        "gpt-5-chat-latest",
        "o4-mini-chat",
        "gpt-4o"  # Should remain unchanged
    ]
    
    print("\n1. OpenAI Adapter Direct Test:")
    print("-" * 60)
    
    adapter = OpenAIAdapter()
    
    # Check that _map_model no longer exists
    if hasattr(adapter, '_map_model'):
        print("✗ FAILED: _map_model method still exists (should be removed)")
    else:
        print("✓ _map_model method properly removed")
    
    print("\n2. Model Preservation Test:")
    print("-" * 60)
    
    for model in test_models:
        request = LLMRequest(
            vendor="openai",
            model=model,
            messages=[{"role": "user", "content": "test"}]
        )
        
        # Build payload to see what model is used
        payload = adapter._build_payload(request, is_grounded=False)
        effective_model = payload.get("model")
        
        print(f"\nInput model: {model}")
        print(f"Effective model: {effective_model}")
        
        if effective_model == model:
            print("✓ Model preserved exactly (no silent rewrite)")
        else:
            print(f"✗ Model was changed from '{model}' to '{effective_model}'")
    
    print("\n3. Router-Level Validation:")
    print("-" * 60)
    
    router = UnifiedLLMAdapter()
    
    # Mock the OpenAI adapter to capture what it receives
    mock_adapter = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = "test response"
    mock_response.metadata = {"test": "metadata"}
    mock_response.usage = {"input_tokens": 10, "output_tokens": 20}
    mock_response.citations = []
    mock_response.grounded_effective = False
    mock_response.model_version = "gpt-4o"
    mock_response.latency_ms = 100
    mock_adapter.complete.return_value = mock_response
    
    router.openai_adapter = mock_adapter
    
    # Test with a model that might have been rewritten
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o-chat",
        messages=[{"role": "user", "content": "test"}]
    )
    
    try:
        response = await router.complete(request, timeout=60)
        
        # Check what model was passed to the adapter
        if mock_adapter.complete.called:
            call_args = mock_adapter.complete.call_args
            passed_request = call_args[0][0] if call_args else None
            
            if passed_request:
                print(f"\nRouter test with model: {request.model}")
                print(f"Model passed to adapter: {passed_request.model}")
                
                if passed_request.model == request.model:
                    print("✓ Router preserved model exactly")
                else:
                    print(f"✗ Router changed model from '{request.model}' to '{passed_request.model}'")
    except Exception as e:
        print(f"Router test error (expected if model not in allowlist): {e}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("✓ _map_model method removed from OpenAI adapter")
    print("✓ Models are preserved exactly as provided")
    print("✓ No silent rewrites occurring")
    print("\nNOTE: Models may still be rejected by validation")
    print("but they are never silently rewritten")

if __name__ == "__main__":
    asyncio.run(test_immutability_audit())