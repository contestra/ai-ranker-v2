#!/usr/bin/env python3
"""
Test suite for Vertex FFC (Forced Function Calling) implementation.
Tests single-call strategy with GoogleSearch and SchemaFunction.
"""
import os
import sys
import json
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.types import LLMRequest, LLMResponse
from app.llm.adapters.vertex_adapter import VertexAdapter
from app.llm.errors import GroundingRequiredFailedError


@pytest.fixture
def vertex_adapter():
    """Create Vertex adapter instance."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client') as mock_client:
            mock_client.return_value = Mock()
            return VertexAdapter()


def test_message_shape_validation():
    """Test that exactly 2 messages are required (system + user)."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client'):
            adapter = VertexAdapter()
            
            # Test with multiple user messages - should fail
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "First question"},
                    {"role": "user", "content": "Second question"}  # Violation!
                ]
            )
            
            with pytest.raises(ValueError) as exc_info:
                system_content, user_content = adapter._build_two_messages(request)
            
            assert "Multiple user messages not allowed" in str(exc_info.value)
            
            # Test with assistant message - should fail
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "Question"},
                    {"role": "assistant", "content": "Answer"}  # Violation!
                ]
            )
            
            with pytest.raises(ValueError) as exc_info:
                system_content, user_content = adapter._build_two_messages(request)
            
            assert "Assistant messages not allowed" in str(exc_info.value)
            
            # Test with exactly 2 messages - should succeed
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "What's the weather?"}
                ]
            )
            
            system_content, user_content = adapter._build_two_messages(request)
            assert system_content == "You are helpful"
            assert user_content == "What's the weather?"
    
    print("✅ Message shape validation works correctly")


def test_als_constraints():
    """Test ALS block constraints (≤350 chars, system-side only)."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client'):
            adapter = VertexAdapter()
            
            # Test ALS within limit
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "System instruction"},
                    {"role": "user", "content": "User question"}
                ]
            )
            
            als_block = "Location: London, UK. Time: 2025-09-02 15:00:00"  # < 350 chars
            system_content, user_content = adapter._build_two_messages(request, als_block)
            
            # ALS should be appended to system
            assert "System instruction" in system_content
            assert als_block in system_content
            # User content unchanged
            assert user_content == "User question"
            
            # Test ALS exceeds limit
            als_block = "X" * 351  # > 350 chars
            with pytest.raises(ValueError) as exc_info:
                system_content, user_content = adapter._build_two_messages(request, als_block)
            
            assert "ALS block exceeds 350 chars" in str(exc_info.value)
    
    print("✅ ALS constraints enforced correctly")


def test_user_prompt_unchanged():
    """Test that user prompt remains byte-for-byte identical."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client'):
            adapter = VertexAdapter()
            
            # Test with special characters and formatting
            original_user_text = "Test with special chars: 你好 🚀 \n\t  spaces  "
            
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "System"},
                    {"role": "user", "content": original_user_text}
                ]
            )
            
            system_content, user_content = adapter._build_two_messages(request)
            
            # User content must be identical
            assert user_content == original_user_text
            assert len(user_content) == len(original_user_text)
            assert user_content.encode() == original_user_text.encode()
    
    print("✅ User prompt remains unchanged (byte-for-byte)")


@pytest.mark.asyncio
async def test_required_mode_enforcement():
    """Test REQUIRED mode fails closed when no grounding evidence."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client'):
            adapter = VertexAdapter()
            
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "System"},
                    {"role": "user", "content": "What's the latest news?"}
                ],
                grounded=True,
                meta={"grounding_mode": "REQUIRED"}
            )
            
            # Mock GenerativeModel
            with patch('google.genai.GenerativeModel') as mock_model_class:
                mock_model = Mock()
                mock_model_class.return_value = mock_model
                
                # Mock response without grounding evidence
                mock_response = Mock()
                mock_response.candidates = [Mock()]
                mock_response.candidates[0].content = Mock()
                mock_response.candidates[0].content.parts = [Mock(text="Some response")]
                # No grounding_metadata = no evidence
                
                mock_model.generate_content = Mock(return_value=mock_response)
                
                # Should raise GroundingRequiredFailedError
                with pytest.raises(GroundingRequiredFailedError) as exc_info:
                    await adapter.complete(request)
                
                error_msg = str(exc_info.value)
                assert "REQUIRED grounding mode" in error_msg
                assert "no grounding evidence found" in error_msg
    
    print("✅ REQUIRED mode enforced correctly (fail-closed)")


@pytest.mark.asyncio
async def test_auto_mode_returns_ungrounded():
    """Test AUTO mode returns response even without grounding."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client'):
            adapter = VertexAdapter()
            
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "System"},
                    {"role": "user", "content": "Hello"}
                ],
                grounded=True,
                meta={"grounding_mode": "AUTO"}
            )
            
            # Mock GenerativeModel
            with patch('google.genai.GenerativeModel') as mock_model_class:
                mock_model = Mock()
                mock_model_class.return_value = mock_model
                
                # Mock response without grounding
                mock_response = Mock()
                mock_response.candidates = [Mock()]
                mock_response.candidates[0].content = Mock()
                mock_response.candidates[0].content.parts = [Mock(text="Hello there!")]
                
                mock_model.generate_content = Mock(return_value=mock_response)
                
                # Should succeed even without grounding
                response = await adapter.complete(request)
                
                assert response.text == "Hello there!"
                assert response.metadata["grounded_effective"] == False
                assert response.metadata["why_not_grounded"] == "No GoogleSearch usage detected"
                assert response.metadata["grounding_mode_requested"] == "AUTO"
    
    print("✅ AUTO mode works without grounding")


@pytest.mark.asyncio
async def test_single_call_only():
    """Test that only a single API call is made (no two-step)."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client'):
            adapter = VertexAdapter()
            
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "System"},
                    {"role": "user", "content": "Search for Python news"}
                ],
                grounded=True,
                json_mode=True,  # Would trigger two-step in old implementation
                meta={"grounding_mode": "AUTO"}
            )
            
            # Mock GenerativeModel
            with patch('google.genai.GenerativeModel') as mock_model_class:
                mock_model = Mock()
                mock_model_class.return_value = mock_model
                
                # Mock response with function call
                mock_response = Mock()
                mock_response.candidates = [Mock()]
                mock_response.candidates[0].content = Mock()
                mock_response.candidates[0].content.parts = [Mock()]
                mock_response.candidates[0].content.parts[0].function_call = Mock()
                mock_response.candidates[0].content.parts[0].function_call.name = "format_response"
                mock_response.candidates[0].content.parts[0].function_call.args = {
                    "response": "Python news content",
                    "data": {}
                }
                
                mock_model.generate_content = Mock(return_value=mock_response)
                
                response = await adapter.complete(request)
                
                # Verify only one call was made
                assert mock_model.generate_content.call_count == 1
                
                # Verify response is from function call
                parsed = json.loads(response.text)
                assert parsed["response"] == "Python news content"
                assert response.metadata["final_function_called"] == "format_response"
                assert response.metadata["schema_args_valid"] == True
    
    print("✅ Single call only (no two-step)")


@pytest.mark.asyncio
async def test_telemetry_fields():
    """Test that correct telemetry fields are emitted."""
    with patch.dict(os.environ, {"VERTEX_PROJECT": "test-project"}):
        with patch('app.llm.adapters.vertex_adapter.genai.Client'):
            adapter = VertexAdapter()
            
            request = LLMRequest(
                vendor="vertex",
                model="publishers/google/models/gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": "System"},
                    {"role": "user", "content": "Question"}
                ],
                grounded=True
            )
            
            # Mock GenerativeModel
            with patch('google.genai.GenerativeModel') as mock_model_class:
                mock_model = Mock()
                mock_model_class.return_value = mock_model
                
                # Mock response with grounding
                mock_response = Mock()
                mock_response.candidates = [Mock()]
                mock_response.candidates[0].content = Mock()
                mock_response.candidates[0].content.parts = [Mock(text="Answer")]
                mock_response.candidates[0].grounding_metadata = Mock()
                mock_response.candidates[0].grounding_metadata.web_search_queries = ["query1"]
                
                mock_model.generate_content = Mock(return_value=mock_response)
                
                response = await adapter.complete(request)
                
                # Check required telemetry fields
                assert "grounding_attempted" in response.metadata
                assert "grounded_effective" in response.metadata
                assert "tool_call_count" in response.metadata
                assert "final_function_called" in response.metadata
                assert "schema_args_valid" in response.metadata
                assert "why_not_grounded" in response.metadata
                assert "response_api" in response.metadata
                assert "provider_api_version" in response.metadata
                
                # Check values
                assert response.metadata["response_api"] == "vertex_genai"
                assert response.metadata["provider_api_version"] == "vertex:genai-v1"
                assert response.metadata["grounding_attempted"] == True
                
                # Verify NO two-step fields
                assert "step2_tools_invoked" not in response.metadata
                assert "step2_source_ref" not in response.metadata
    
    print("✅ Telemetry fields correct (no two-step fields)")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Vertex FFC Implementation Tests")
    print("="*60 + "\n")
    
    # Run synchronous tests
    test_message_shape_validation()
    test_als_constraints()
    test_user_prompt_unchanged()
    
    # Run async tests
    asyncio.run(test_required_mode_enforcement())
    asyncio.run(test_auto_mode_returns_ungrounded())
    asyncio.run(test_single_call_only())
    asyncio.run(test_telemetry_fields())
    
    print("\n" + "="*60)
    print("✅ All Vertex FFC tests passed!")
    print("="*60)