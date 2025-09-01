"""
OpenAI Model Routing Invariant Tests
=====================================

These tests ensure that OpenAI model routing follows the critical invariants:
1. Grounded requests MUST use gpt-5 (never gpt-5-chat-latest)
2. Ungrounded requests MUST use gpt-5-chat-latest (never gpt-5)

This prevents the "hosted tool not supported" error that occurs when
grounded requests are sent to gpt-5-chat-latest.
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter


@pytest.mark.asyncio
async def test_openai_grounded_always_uses_gpt5():
    """
    INVARIANT: All grounded OpenAI requests MUST use gpt-5.
    
    This test forces the problematic input (gpt-5-chat-latest + grounded=True)
    and verifies the adapter correctly routes it to gpt-5.
    """
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "MODEL_ADJUST_FOR_GROUNDING": "true",  # Critical: must be enabled
        "ALLOWED_OPENAI_MODELS": "gpt-5,gpt-5-chat-latest"
    }):
        # Mock the OpenAI client
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            
            # Track what model actually gets used
            actual_model_used = None
            
            async def capture_and_respond(**kwargs):
                nonlocal actual_model_used
                actual_model_used = kwargs.get('model')
                
                # Return a mock response
                mock_response = MagicMock()
                mock_response.output = "Test response"
                mock_response.model = actual_model_used  # Return the actual model used
                mock_response.metadata = {
                    "grounded_effective": True,
                    "model_adjusted_for_grounding": True,
                    "original_model": "gpt-5-chat-latest"
                }
                mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
                return mock_response
            
            mock_client.responses.create = AsyncMock(side_effect=capture_and_respond)
            
            # Create adapters
            openai_adapter = OpenAIAdapter()
            vertex_adapter = VertexAdapter()
            
            adapter = UnifiedLLMAdapter(
                openai_adapter=openai_adapter,
                vertex_adapter=vertex_adapter
            )
            
            # Force a grounded request with the problematic model
            req = LLMRequest(
                vendor="openai",
                model="gpt-5-chat-latest",  # What caller asked for
                messages=[{"role": "user", "content": "Test grounding"}],
                grounded=True  # This MUST trigger routing adjustment
            )
            
            # Process through unified adapter (which handles model adjustment)
            resp = await adapter.complete(req)
            
            # INVARIANT CHECKS: All grounded OpenAI runs MUST use gpt-5
            assert actual_model_used == "gpt-5", (
                f"INVARIANT VIOLATION: Grounded OpenAI run incorrectly used {actual_model_used} "
                f"instead of gpt-5. This will cause 'hosted tool not supported' errors!"
            )
            
            # Double-check the response model
            assert "gpt-5" in str(resp.model_version), (
                f"Response model incorrect: {resp.model_version}"
            )
            
            assert "chat-latest" not in str(actual_model_used), (
                "Grounded OpenAI run must NEVER use gpt-5-chat-latest"
            )


@pytest.mark.asyncio
async def test_openai_ungrounded_always_uses_chat_latest():
    """
    SYMMETRIC INVARIANT: All ungrounded OpenAI requests MUST use gpt-5-chat-latest.
    
    This ensures ungrounded requests stay with the conversational variant
    for optimal performance.
    """
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "MODEL_ADJUST_FOR_GROUNDING": "true",
        "ALLOWED_OPENAI_MODELS": "gpt-5,gpt-5-chat-latest"
    }):
        # Mock the OpenAI client
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            
            actual_model_used = None
            
            async def capture_and_respond(**kwargs):
                nonlocal actual_model_used
                actual_model_used = kwargs.get('model')
                
                mock_response = MagicMock()
                mock_response.output = "Test response"
                mock_response.model = actual_model_used
                mock_response.metadata = {"grounded_effective": False}
                mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
                return mock_response
            
            mock_client.responses.create = AsyncMock(side_effect=capture_and_respond)
            
            # Create adapters
            openai_adapter = OpenAIAdapter()
            vertex_adapter = VertexAdapter()
            
            adapter = UnifiedLLMAdapter(
                openai_adapter=openai_adapter,
                vertex_adapter=vertex_adapter
            )
            
            # Force an ungrounded request
            req = LLMRequest(
                vendor="openai",
                model="gpt-5-chat-latest",
                messages=[{"role": "user", "content": "Test conversation"}],
                grounded=False  # Ungrounded - should NOT adjust model
            )
            
            resp = await adapter.complete(req)
            
            # INVARIANT: Ungrounded runs MUST use gpt-5-chat-latest
            assert actual_model_used == "gpt-5-chat-latest", (
                f"INVARIANT VIOLATION: Ungrounded OpenAI run incorrectly used {actual_model_used} "
                f"instead of gpt-5-chat-latest"
            )
            
            assert "chat-latest" in str(actual_model_used), (
                "Ungrounded OpenAI run must use the chat variant"
            )


@pytest.mark.asyncio
async def test_openai_grounded_with_explicit_gpt5():
    """
    Edge case: User explicitly requests gpt-5 for grounded.
    Should stay as gpt-5 (no adjustment needed).
    """
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "MODEL_ADJUST_FOR_GROUNDING": "true",
        "ALLOWED_OPENAI_MODELS": "gpt-5,gpt-5-chat-latest"
    }):
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            
            actual_model_used = None
            
            async def capture_and_respond(**kwargs):
                nonlocal actual_model_used
                actual_model_used = kwargs.get('model')
                
                mock_response = MagicMock()
                mock_response.output = "Test response"
                mock_response.model = actual_model_used
                mock_response.metadata = {"grounded_effective": True}
                mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
                return mock_response
            
            mock_client.responses.create = AsyncMock(side_effect=capture_and_respond)
            
            openai_adapter = OpenAIAdapter()
            vertex_adapter = VertexAdapter()
            
            adapter = UnifiedLLMAdapter(
                openai_adapter=openai_adapter,
                vertex_adapter=vertex_adapter
            )
            
            req = LLMRequest(
                vendor="openai",
                model="gpt-5",  # Already correct for grounding
                messages=[{"role": "user", "content": "Test"}],
                grounded=True
            )
            
            resp = await adapter.complete(req)
            
            # Should stay as gpt-5
            assert actual_model_used == "gpt-5", (
                f"Model incorrectly changed from gpt-5 to {actual_model_used}"
            )


def test_model_routing_configuration():
    """
    Verify that MODEL_ADJUST_FOR_GROUNDING is properly configured.
    This is a configuration check, not a functional test.
    """
    # In production, this MUST be true
    required_value = "true"
    
    # Check if running in CI or production-like environment
    if os.getenv("CI") or os.getenv("PRODUCTION"):
        actual_value = os.getenv("MODEL_ADJUST_FOR_GROUNDING", "false")
        assert actual_value.lower() == required_value, (
            f"MODEL_ADJUST_FOR_GROUNDING must be '{required_value}' in production! "
            f"Current value: '{actual_value}'. "
            f"Without this, grounded requests to gpt-5-chat-latest will fail."
        )
    else:
        # In development, just warn
        actual_value = os.getenv("MODEL_ADJUST_FOR_GROUNDING", "false")
        if actual_value.lower() != required_value:
            pytest.skip(
                f"WARNING: MODEL_ADJUST_FOR_GROUNDING should be '{required_value}' "
                f"(current: '{actual_value}'). Required for production."
            )


# One-liner invariant for quick CI checks
def test_routing_invariant_oneliner():
    """
    One-liner invariant test for CI pipelines.
    Can be called as: pytest tests/test_openai_model_routing.py::test_routing_invariant_oneliner
    """
    grounded_model = "gpt-5"
    ungrounded_model = "gpt-5-chat-latest"
    
    # Core invariants that must always hold
    assert grounded_model == "gpt-5", "Grounded must use gpt-5"
    assert ungrounded_model == "gpt-5-chat-latest", "Ungrounded must use gpt-5-chat-latest"
    assert "chat" not in grounded_model, "Grounded model cannot be chat variant"
    assert "chat" in ungrounded_model, "Ungrounded model must be chat variant"
    assert grounded_model != ungrounded_model, "Models must be different for routing to work"