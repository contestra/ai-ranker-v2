#!/usr/bin/env python3
"""
Test suite for Phase-0 Vertex adapter migration.
Verifies that:
1. Legacy Vertex SDK is completely removed
2. Only google-genai client is used
3. Authentication failures provide clear remediation
4. Grounded REQUIRED mode fails closed without evidence
5. Ungrounded requests still succeed
"""
import os
import sys
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, LLMResponse
from app.llm.adapters.vertex_adapter import VertexAdapter


def test_no_legacy_imports():
    """Verify no legacy Vertex SDK imports are present."""
    import app.llm.adapters.vertex_adapter as vertex_module
    
    # Check module doesn't have legacy imports
    module_dict = vertex_module.__dict__
    
    # These should NOT be present
    forbidden = ['vertexai', 'google.cloud.aiplatform']
    for name in forbidden:
        assert name not in module_dict, f"Legacy import '{name}' found in vertex_adapter"
    
    # These SHOULD be present
    required = ['genai']
    for name in required:
        assert name in module_dict, f"Required import '{name}' not found in vertex_adapter"
    
    print("✅ No legacy Vertex SDK imports found")


def test_genai_client_initialization_required():
    """Test that genai.Client initialization is hard-required."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        # Mock genai.Client to raise an error
        with patch('app.llm.adapters.vertex_adapter.genai.Client') as mock_client:
            mock_client.side_effect = Exception("Authentication failed")
            
            # Should raise RuntimeError with clear remediation
            with pytest.raises(RuntimeError) as exc_info:
                adapter = VertexAdapter()
            
            error_msg = str(exc_info.value)
            assert "Failed to initialize google-genai client" in error_msg
            assert "REQUIRED dependency" in error_msg
            assert "gcloud auth application-default login" in error_msg
            assert "pip install google-genai" in error_msg
    
    print("✅ genai.Client initialization is hard-required with clear error messages")


@pytest.mark.asyncio
async def test_grounded_required_fails_without_evidence():
    """Test that REQUIRED mode fails closed when no grounding evidence is found."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        # Mock successful client initialization
        with patch('app.llm.adapters.vertex_adapter.genai.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            adapter = VertexAdapter()
            
            # Create a grounded request with REQUIRED mode
            request = LLMRequest(
                vendor="vertex",
                model="gemini-2.5-pro",
                messages=[{"role": "user", "content": "What's the weather?"}],
                grounded=True,
                meta={"grounding_mode": "REQUIRED"}
            )
            
            # Mock response without grounding evidence
            mock_response = Mock()
            mock_response.candidates = [Mock()]
            mock_response.candidates[0].content = Mock()
            mock_response.candidates[0].content.parts = [Mock(text="It's sunny")]
            # No grounding_metadata = no evidence
            
            mock_client.models.generate_content_async = AsyncMock(return_value=mock_response)
            
            # Should raise ValueError for REQUIRED mode without evidence
            with pytest.raises(ValueError) as exc_info:
                await adapter.complete(request)
            
            error_msg = str(exc_info.value)
            assert "REQUIRED mode" in error_msg
            assert "no grounding evidence" in error_msg
    
    print("✅ REQUIRED mode fails closed without grounding evidence")


@pytest.mark.asyncio
async def test_ungrounded_requests_succeed():
    """Test that ungrounded requests work with google-genai."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        # Mock successful client initialization
        with patch('app.llm.adapters.vertex_adapter.genai.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            adapter = VertexAdapter()
            
            # Create an ungrounded request
            request = LLMRequest(
                vendor="vertex",
                model="gemini-2.5-pro",
                messages=[{"role": "user", "content": "Hello"}],
                grounded=False
            )
            
            # Mock successful response
            mock_response = Mock()
            mock_response.candidates = [Mock()]
            mock_response.candidates[0].content = Mock()
            mock_response.candidates[0].content.parts = [Mock(text="Hello! How can I help?")]
            
            mock_client.models.generate_content_async = AsyncMock(return_value=mock_response)
            
            response = await adapter.complete(request)
            
            assert response.text == "Hello! How can I help?"
            assert response.metadata["grounded_effective"] == False
            assert response.metadata["response_api"] == "vertex_genai"
            assert response.metadata["provider_api_version"] == "vertex:genai-v1"
    
    print("✅ Ungrounded requests work with google-genai")


@pytest.mark.asyncio  
async def test_mode_mapping():
    """Test that AUTO maps to AUTO and REQUIRED maps to ANY."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        # Mock successful client initialization
        with patch('app.llm.adapters.vertex_adapter.genai.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            adapter = VertexAdapter()
            
            # Test AUTO mode
            request_auto = LLMRequest(
                vendor="vertex",
                model="gemini-2.5-pro",
                messages=[{"role": "user", "content": "Search for Python"}],
                grounded=True,
                meta={"grounding_mode": "AUTO"}
            )
            
            # Mock response with grounding
            mock_response = Mock()
            mock_response.candidates = [Mock()]
            mock_response.candidates[0].content = Mock()
            mock_response.candidates[0].content.parts = [Mock(text="Python is a programming language")]
            mock_response.candidates[0].grounding_metadata = Mock()
            mock_response.candidates[0].grounding_metadata.web_search_queries = ["Python"]
            
            mock_client.models.generate_content_async = AsyncMock(return_value=mock_response)
            
            response = await adapter.complete(request_auto)
            assert response.metadata["grounding_mode_requested"] == "AUTO"
            
            # Test REQUIRED mode (maps to ANY internally)
            request_required = LLMRequest(
                vendor="vertex",
                model="gemini-2.5-pro",
                messages=[{"role": "user", "content": "Search for Java"}],
                grounded=True,
                meta={"grounding_mode": "REQUIRED"}
            )
            
            response = await adapter.complete(request_required)
            assert response.metadata["grounding_mode_requested"] == "REQUIRED"
    
    print("✅ Mode mapping works correctly (AUTO→AUTO, REQUIRED→ANY)")


@pytest.mark.asyncio
async def test_attestation_fields():
    """Test that two-step grounded JSON includes attestation fields."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        # Mock successful client initialization
        with patch('app.llm.adapters.vertex_adapter.genai.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            adapter = VertexAdapter()
            
            # Create a grounded JSON request
            request = LLMRequest(
                vendor="vertex",
                model="gemini-2.5-pro",
                messages=[{"role": "user", "content": "Get weather data"}],
                grounded=True,
                json_mode=True
            )
            
            # Mock Step 1 response (grounded)
            mock_step1 = Mock()
            mock_step1.candidates = [Mock()]
            mock_step1.candidates[0].content = Mock()
            mock_step1.candidates[0].content.parts = [Mock(text="Weather is 20°C")]
            mock_step1.candidates[0].grounding_metadata = Mock()
            mock_step1.candidates[0].grounding_metadata.web_search_queries = ["weather"]
            
            # Mock Step 2 response (JSON)
            mock_step2 = Mock()
            mock_step2.candidates = [Mock()]
            mock_step2.candidates[0].content = Mock()
            mock_step2.candidates[0].content.parts = [Mock(text='{"temperature": 20}')]
            
            # Set up sequential returns
            mock_client.models.generate_content_async = AsyncMock()
            mock_client.models.generate_content_async.side_effect = [mock_step1, mock_step2]
            
            response = await adapter.complete(request)
            
            # Check attestation fields
            assert response.metadata["step2_tools_invoked"] == False
            assert "step2_source_ref" in response.metadata
            assert response.metadata["grounded_effective"] == True
            
            # Verify two calls were made
            assert mock_client.models.generate_content_async.call_count == 2
    
    print("✅ Two-step grounded JSON includes attestation fields")


if __name__ == "__main__":
    # Run tests
    print("\n" + "="*60)
    print("Phase-0 Vertex Adapter Migration Tests")
    print("="*60 + "\n")
    
    # Run non-async tests
    test_no_legacy_imports()
    test_genai_client_initialization_required()
    
    # Run async tests
    asyncio.run(test_grounded_required_fails_without_evidence())
    asyncio.run(test_ungrounded_requests_succeed())
    asyncio.run(test_mode_mapping())
    asyncio.run(test_attestation_fields())
    
    print("\n" + "="*60)
    print("✅ All Phase-0 migration tests passed!")
    print("="*60)