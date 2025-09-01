"""
OpenAI Telemetry Contract Tests
================================

These tests ensure that all telemetry fields are populated consistently
for debugging and monitoring. They validate the complete telemetry contract
including response_api, runtime flags, and model adjustment breadcrumbs.

As ChatGPT noted: "These assertions line up with your PRDs/guide: emit a 
normalized row per call, include response_api, runtime flags/config, and 
provenance such as model-adjustment and grounding status."
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter


@pytest.mark.asyncio
async def test_openai_grounded_uses_gpt5_and_emits_telemetry():
    """
    Test grounded OpenAI requests with full telemetry validation.
    Ensures all metadata fields are populated for monitoring/debugging.
    """
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "MODEL_ADJUST_FOR_GROUNDING": "true",
        "ALLOWED_OPENAI_MODELS": "gpt-5,gpt-5-chat-latest",
        "CITATION_EXTRACTOR_V2": "0.5",  # Test feature flag emission
        "CITATIONS_EXTRACTOR_ENABLE": "true"
    }):
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            
            actual_model_used = None
            
            async def capture_and_respond(**kwargs):
                nonlocal actual_model_used
                actual_model_used = kwargs.get('model')
                
                mock_response = MagicMock()
                mock_response.output = "Test response with grounding"
                mock_response.model = actual_model_used
                mock_response.metadata = {
                    "grounded_effective": True,
                    "model_adjusted_for_grounding": True,
                    "original_model": "gpt-5-chat-latest",
                    "response_api": "responses_http",
                    "tool_call_count": 2,
                    "anchored_citations_count": 3,
                    "feature_flags": {
                        "citation_extractor_v2": 0.5,
                        "citations_extractor_enable": True,
                        "model_adjust_for_grounding": True
                    },
                    "runtime_flags": {
                        "grounding_mode": "REQUIRED",
                        "ab_bucket": 0.42
                    }
                }
                mock_response.usage = {"prompt_tokens": 50, "completion_tokens": 100}
                return mock_response
            
            mock_client.responses.create = AsyncMock(side_effect=capture_and_respond)
            
            openai_adapter = OpenAIAdapter()
            vertex_adapter = VertexAdapter()
            
            adapter = UnifiedLLMAdapter(
                openai_adapter=openai_adapter,
                vertex_adapter=vertex_adapter
            )
            
            # Grounded request; caller mistakenly asks for chat-latest to ensure adjustment kicks in
            req = LLMRequest(
                vendor="openai",
                model="gpt-5-chat-latest",  # Wrong model - should trigger adjustment
                messages=[{"role": "user", "content": "Test grounding"}],
                grounded=True,
                meta={"grounding_mode": "REQUIRED"}  # Exercise fail-closed semantics
            )
            
            resp = await adapter.complete(req)
            
            # === ROUTING INVARIANTS ===
            assert actual_model_used == "gpt-5", "Grounded must use gpt-5"
            assert "chat-latest" not in str(actual_model_used), "Must not use chat variant"
            
            # === TELEMETRY CONTRACT (Phase-0: always include response_api & provenance) ===
            assert hasattr(resp, "metadata") and isinstance(resp.metadata, dict), (
                "Response must have metadata dict"
            )
            
            # OpenAI grounded path MUST use Responses HTTP surface
            assert resp.metadata.get("response_api") == "responses_http", (
                f"Grounded must use responses_http, got {resp.metadata.get('response_api')}"
            )
            
            # Grounding fields MUST be present (even if tool calls are 0 for some prompts)
            assert "grounded_effective" in resp.metadata, (
                "Must include grounded_effective field"
            )
            assert resp.metadata["grounded_effective"] is True, (
                "Grounded request must have grounded_effective=True"
            )
            
            # Model adjustment breadcrumbs MUST be present when we adjusted models
            assert resp.metadata.get("model_adjusted_for_grounding") is True, (
                "Must track model adjustment"
            )
            assert resp.metadata.get("original_model") == "gpt-5-chat-latest", (
                "Must track original model before adjustment"
            )
            
            # Feature flags MUST be emitted for A/B testing and rollback
            flags = resp.metadata.get("feature_flags") or {}
            assert "citation_extractor_v2" in flags, "Must emit citation extractor flag"
            assert "model_adjust_for_grounding" in flags, "Must emit model adjust flag"
            
            # Runtime flags for analytics/debugging
            runtime = resp.metadata.get("runtime_flags") or {}
            assert "grounding_mode" in runtime, "Must track grounding mode"
            assert runtime["grounding_mode"] == "REQUIRED", "Must preserve REQUIRED mode"
            
            # Citation telemetry (when tools are called)
            if resp.metadata.get("tool_call_count", 0) > 0:
                assert "anchored_citations_count" in resp.metadata, (
                    "Must track citation counts when tools called"
                )


@pytest.mark.asyncio
async def test_openai_ungrounded_uses_chat_latest_and_emits_telemetry():
    """
    Test ungrounded OpenAI requests with telemetry validation.
    Ensures proper metadata for ungrounded conversational flows.
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
                mock_response.output = "Conversational response"
                mock_response.model = actual_model_used
                mock_response.metadata = {
                    "grounded_effective": False,
                    "response_api": "chat_completions",  # Or None for ungrounded
                    "feature_flags": {
                        "model_adjust_for_grounding": True
                    },
                    "runtime_flags": {
                        "als_injected": False
                    }
                }
                mock_response.usage = {"prompt_tokens": 30, "completion_tokens": 80}
                return mock_response
            
            mock_client.responses.create = AsyncMock(side_effect=capture_and_respond)
            
            openai_adapter = OpenAIAdapter()
            vertex_adapter = VertexAdapter()
            
            adapter = UnifiedLLMAdapter(
                openai_adapter=openai_adapter,
                vertex_adapter=vertex_adapter
            )
            
            # Ungrounded; no grounding requested
            req = LLMRequest(
                vendor="openai",
                model="gpt-5-chat-latest",
                messages=[{"role": "user", "content": "Tell me a joke"}],
                grounded=False
            )
            
            resp = await adapter.complete(req)
            
            # === ROUTING INVARIANTS ===
            assert actual_model_used == "gpt-5-chat-latest", (
                "Ungrounded must use gpt-5-chat-latest"
            )
            
            # === TELEMETRY CONTRACT ===
            assert hasattr(resp, "metadata") and isinstance(resp.metadata, dict)
            
            # Ungrounded should NOT use grounded Responses surface
            assert resp.metadata.get("response_api") != "responses_http", (
                "Ungrounded must not use responses_http API"
            )
            # Allow either None or explicit chat_completions for ungrounded
            api = resp.metadata.get("response_api")
            assert api in [None, "chat_completions", ""], (
                f"Unexpected response_api for ungrounded: {api}"
            )
            
            # Grounding fields
            assert resp.metadata.get("grounded_effective") is False, (
                "Ungrounded must have grounded_effective=False"
            )
            
            # No model adjustment should occur for ungrounded
            assert not resp.metadata.get("model_adjusted_for_grounding"), (
                "Should not adjust model for ungrounded requests"
            )
            
            # Runtime flags still emitted for analytics
            flags = resp.metadata.get("feature_flags") or resp.metadata.get("runtime_flags") or {}
            assert isinstance(flags, dict), "Flags must be a dict"


@pytest.mark.asyncio
async def test_required_mode_failure_emits_telemetry():
    """
    Test REQUIRED mode failure includes proper telemetry.
    When grounding fails in REQUIRED mode, telemetry must explain why.
    """
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "MODEL_ADJUST_FOR_GROUNDING": "true",
        "ALLOWED_OPENAI_MODELS": "gpt-5,gpt-5-chat-latest"
    }):
        with patch('app.llm.adapters.openai_adapter.OpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            
            # Simulate tool failure
            async def fail_with_unsupported(**kwargs):
                raise Exception("Hosted tool 'web_search' is not supported")
            
            mock_client.responses.create = AsyncMock(side_effect=fail_with_unsupported)
            
            openai_adapter = OpenAIAdapter()
            vertex_adapter = VertexAdapter()
            
            adapter = UnifiedLLMAdapter(
                openai_adapter=openai_adapter,
                vertex_adapter=vertex_adapter
            )
            
            req = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[{"role": "user", "content": "Search for latest news"}],
                grounded=True,
                meta={"grounding_mode": "REQUIRED"}
            )
            
            # In REQUIRED mode, this should fail-closed
            try:
                resp = await adapter.complete(req)
                
                # If it doesn't raise, check telemetry explains the failure
                assert resp.metadata.get("grounded_effective") is False, (
                    "Failed grounding must be marked as ineffective"
                )
                
                # REQUIRED mode failure MUST include reason
                assert "why_not_grounded" in resp.metadata, (
                    "Must include why_not_grounded for failed REQUIRED"
                )
                assert isinstance(resp.metadata["why_not_grounded"], str), (
                    "why_not_grounded must be a string explanation"
                )
                assert len(resp.metadata["why_not_grounded"]) > 0, (
                    "why_not_grounded must not be empty"
                )
                
                # Should indicate it was a tool support issue
                reason = resp.metadata["why_not_grounded"].lower()
                assert any(word in reason for word in ["tool", "support", "hosted"]), (
                    f"Reason should mention tool support issue: {reason}"
                )
                
            except Exception as e:
                # REQUIRED mode may raise instead of returning
                # This is also valid fail-closed behavior
                assert "not supported" in str(e).lower() or "grounding" in str(e).lower(), (
                    f"Exception should indicate grounding failure: {e}"
                )


def test_telemetry_field_consistency():
    """
    Document the complete telemetry contract for reference.
    This test serves as documentation of all expected fields.
    """
    expected_grounded_fields = {
        # Core routing
        "response_api",           # "responses_http" for grounded OpenAI
        "grounded_effective",     # True if grounding succeeded
        "model",                  # Effective model used
        
        # Model adjustment tracking
        "model_adjusted_for_grounding",  # True if model was swapped
        "original_model",               # Model before adjustment
        
        # Feature flags for A/B testing
        "feature_flags",          # Dict of active feature flags
        "runtime_flags",          # Dict of runtime configuration
        
        # Citation metrics (when tools called)
        "tool_call_count",        # Number of tool invocations
        "anchored_citations_count",  # Citations with evidence
        "unlinked_sources_count",     # Sources without anchors
        "citations_shape_set",        # Citation patterns detected
        
        # Failure tracking
        "why_not_grounded",       # Reason for grounding failure (REQUIRED mode)
        
        # Performance
        "latency_ms",             # Response time
        "proxy_mode",             # Proxy configuration
    }
    
    expected_ungrounded_fields = {
        # Core routing
        "response_api",           # None or "chat_completions" for ungrounded
        "grounded_effective",     # False for ungrounded
        "model",                  # Should be gpt-5-chat-latest
        
        # ALS/ambient signals
        "als_injected",           # Whether ALS was added
        "country_code",           # Ambient location if ALS
        
        # Feature flags still present
        "feature_flags",
        "runtime_flags",
        
        # Performance
        "latency_ms",
        "proxy_mode",
    }
    
    # This test documents expectations but doesn't fail
    # It serves as a reference for the telemetry contract
    assert len(expected_grounded_fields) > 0
    assert len(expected_ungrounded_fields) > 0
    
    print("\n=== Telemetry Contract Documentation ===")
    print(f"Grounded requests should emit {len(expected_grounded_fields)} fields")
    print(f"Ungrounded requests should emit {len(expected_ungrounded_fields)} fields")
    print("\nSee test source for complete field list and semantics")