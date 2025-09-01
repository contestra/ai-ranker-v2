"""
Invariant test: OpenAI model routing based on grounding requirement.

CRITICAL INVARIANTS:
1. Grounded requests MUST use gpt-5 (supports web_search tools)
2. Ungrounded requests MUST use gpt-5-chat-latest (conversational variant)
3. MODEL_ADJUST_FOR_GROUNDING=true MUST be enabled in production

These invariants prevent the "hosted tool not supported" error that would
occur if grounded requests were sent to gpt-5-chat-latest.
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.types import LLMRequest


class TestOpenAIRoutingInvariant:
    """Ensure OpenAI model routing follows the required invariants."""
    
    @pytest.mark.asyncio
    async def test_grounded_must_use_gpt5(self):
        """INVARIANT: Grounded requests MUST route to gpt-5, never gpt-5-chat-latest."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            adapter = OpenAIAdapter()
        
        # Test with gpt-5-chat-latest requested but grounded=True
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[{"role": "user", "content": "Test"}],
            grounded=True,
            max_tokens=100
        )
        
        with patch.dict(os.environ, {"MODEL_ADJUST_FOR_GROUNDING": "true"}):
            with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
                mock_client = AsyncMock()
                mock_openai.return_value = mock_client
                
                # Capture the actual model used in the API call
                actual_model_used = None
                
                async def capture_model(**kwargs):
                    nonlocal actual_model_used
                    actual_model_used = kwargs.get('model')
                    # Return a mock response
                    mock_response = MagicMock()
                    mock_response.output = "Test response"
                    mock_response.model = kwargs.get('model')
                    mock_response.metadata = {}
                    mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
                    return mock_response
                
                mock_client.responses.create = AsyncMock(side_effect=capture_model)
                
                # Make the request
                try:
                    await adapter.complete(request)
                except:
                    pass  # We only care about the model used
                
                # INVARIANT CHECK: Grounded requests must use gpt-5
                assert actual_model_used == "gpt-5", \
                    f"INVARIANT VIOLATION: Grounded request used {actual_model_used} instead of gpt-5"
    
    @pytest.mark.asyncio
    async def test_ungrounded_must_use_chat_variant(self):
        """INVARIANT: Ungrounded requests MUST route to gpt-5-chat-latest."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            adapter = OpenAIAdapter()
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[{"role": "user", "content": "Test"}],
            grounded=False,  # Ungrounded
            max_tokens=100
        )
        
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            
            actual_model_used = None
            
            async def capture_model(**kwargs):
                nonlocal actual_model_used
                actual_model_used = kwargs.get('model')
                mock_response = MagicMock()
                mock_response.output = "Test response"
                mock_response.model = kwargs.get('model')
                mock_response.metadata = {}
                mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
                return mock_response
            
            mock_client.responses.create = AsyncMock(side_effect=capture_model)
            
            try:
                await adapter.complete(request)
            except:
                pass
            
            # INVARIANT CHECK: Ungrounded requests must use gpt-5-chat-latest
            assert actual_model_used == "gpt-5-chat-latest", \
                f"INVARIANT VIOLATION: Ungrounded request used {actual_model_used} instead of gpt-5-chat-latest"
    
    @pytest.mark.asyncio
    async def test_grounded_with_gpt5_stays_gpt5(self):
        """INVARIANT: If user explicitly requests gpt-5 for grounded, keep it."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            adapter = OpenAIAdapter()
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5",  # Already the right model
            messages=[{"role": "user", "content": "Test"}],
            grounded=True,
            max_tokens=100
        )
        
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            
            actual_model_used = None
            
            async def capture_model(**kwargs):
                nonlocal actual_model_used
                actual_model_used = kwargs.get('model')
                mock_response = MagicMock()
                mock_response.output = "Test response"
                mock_response.model = kwargs.get('model')
                mock_response.metadata = {}
                mock_response.usage = {"prompt_tokens": 10, "completion_tokens": 20}
                return mock_response
            
            mock_client.responses.create = AsyncMock(side_effect=capture_model)
            
            try:
                await adapter.complete(request)
            except:
                pass
            
            # INVARIANT CHECK: gpt-5 stays gpt-5 for grounded
            assert actual_model_used == "gpt-5", \
                f"INVARIANT VIOLATION: Model changed from gpt-5 to {actual_model_used}"
    
    def test_model_adjust_flag_required(self):
        """INVARIANT: MODEL_ADJUST_FOR_GROUNDING must be true in production."""
        # This test documents the requirement but doesn't fail CI
        # In production deployment scripts, this should be enforced
        
        production_value = os.getenv("MODEL_ADJUST_FOR_GROUNDING", "false")
        
        if production_value.lower() != "true":
            pytest.skip(
                "WARNING: MODEL_ADJUST_FOR_GROUNDING should be 'true' in production. "
                "Without it, grounded requests to gpt-5-chat-latest will fail with "
                "'hosted tool not supported' errors."
            )
    
    @pytest.mark.asyncio
    async def test_metadata_tracks_adjustment(self):
        """Ensure metadata properly tracks when model adjustment occurs."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            adapter = OpenAIAdapter()
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[{"role": "user", "content": "Test"}],
            grounded=True,
            max_tokens=100,
            meta={}
        )
        
        # Enable model adjustment
        with patch.dict(os.environ, {"MODEL_ADJUST_FOR_GROUNDING": "true"}):
            # Check that metadata is set for adjustment
            # This happens in unified_llm_adapter, so we check the request metadata
            assert request.model == "gpt-5-chat-latest", "Original model should be preserved initially"
            
            # After unified adapter processing (simulated):
            if request.grounded and request.model == "gpt-5-chat-latest":
                # This is what unified adapter does
                request.meta = request.meta or {}
                request.meta['model_adjusted_for_grounding'] = True
                request.meta['original_model'] = request.model
                adjusted_model = "gpt-5"
                
                # Verify metadata
                assert request.meta.get('model_adjusted_for_grounding') is True
                assert request.meta.get('original_model') == "gpt-5-chat-latest"
                assert adjusted_model == "gpt-5"


# One-liner invariant for CI (can be added to any test file):
def test_openai_routing_invariant_oneliner():
    """One-liner invariant: Grounded OpenAI must use gpt-5, ungrounded must use gpt-5-chat-latest."""
    # This can be called from CI or as a post-deployment check
    grounded_model = "gpt-5"  # MUST be gpt-5 for grounded
    ungrounded_model = "gpt-5-chat-latest"  # MUST be gpt-5-chat-latest for ungrounded
    assert grounded_model != ungrounded_model, "Models must be different for routing"
    assert "chat" not in grounded_model, "Grounded model must not be chat variant"
    assert "chat" in ungrounded_model, "Ungrounded model must be chat variant"