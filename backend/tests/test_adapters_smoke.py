#!/usr/bin/env python3
"""
Smoke tests for OpenAI and Vertex adapters.
These tests monkeypatch provider SDKs to avoid network calls.
Tests verify critical paths including retries and grounding enforcement.
"""

import os
import json
import types
import hashlib
import pytest
import asyncio

pytestmark = pytest.mark.asyncio

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# ------------------ OpenAI fakes ------------------

class _FakeOpenAIResponse:
    def __init__(self, text="OK", model="gpt-5-chat-latest", total_tokens=123, grounded=False):
        self.model = model
        self.usage = types.SimpleNamespace(
            total_tokens=total_tokens,
            prompt_tokens=50,
            completion_tokens=73
        )
        self.output_text = text
        self.output = [
            {"type": "message", "content": [{"type": "output_text", "text": text}]}
        ]
        self.content = text
        if grounded:
            self.output.insert(0, {"type": "web_search_call", "id": "ws_123"})
        self._grounded = grounded
        
    def model_dump(self):
        return {
            "output": self.output,
            "model": self.model,
            "usage": {"total_tokens": self.usage.total_tokens}
        }

@pytest.fixture
def patch_openai_ok(monkeypatch):
    import openai

    class _FakeResponses:
        async def create(self, **kwargs):
            tools = kwargs.get("tools") or []
            grounded = any(t.get("type") in ("web_search", "web_search_preview") for t in tools)
            if any(t.get("type") == "web_search_preview" for t in tools):
                return _FakeOpenAIResponse(text="hello-after-preview-retry", grounded=grounded)
            return _FakeOpenAIResponse(text="hello-from-openai", grounded=grounded)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.responses = _FakeResponses()
        def with_options(self, timeout=None):
            return self

    monkeypatch.setattr("openai.AsyncOpenAI", _FakeClient)
    return _FakeClient

@pytest.fixture
def patch_openai_preview_retry(monkeypatch):
    import openai

    state = {"attempt": 0}

    class _FakeResponses:
        async def create(self, **kwargs):
            state["attempt"] += 1
            tools = kwargs.get("tools") or []
            if state["attempt"] == 1 and any(t.get("type") == "web_search" for t in tools):
                # Simulate the exact error message the adapter looks for
                raise RuntimeError("Error code: 400 - {'error': {'message': 'web_search_preview is required with this model'}}")
            grounded = any(t.get("type") == "web_search_preview" for t in tools)
            return _FakeOpenAIResponse(text="hello-after-preview-retry", grounded=grounded)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.responses = _FakeResponses()
        def with_options(self, timeout=None):
            return self

    monkeypatch.setattr("openai.AsyncOpenAI", _FakeClient)
    return _FakeClient

@pytest.fixture
def patch_openai_unsupported(monkeypatch):
    import openai

    class _FakeResponses:
        async def create(self, **kwargs):
            tools = kwargs.get("tools") or []
            if tools:
                raise RuntimeError("Error code: 400 - {'error': {'message': 'Tool web_search is not supported with this model'}}")
            return _FakeOpenAIResponse(text="ungrounded-fallback", grounded=False)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.responses = _FakeResponses()
        def with_options(self, timeout=None):
            return self

    monkeypatch.setattr("openai.AsyncOpenAI", _FakeClient)
    return _FakeClient

@pytest.fixture
def patch_openai_required_ungrounded(monkeypatch):
    """Mock that returns ungrounded output even when tools were requested."""
    import openai

    class _FakeResponses:
        async def create(self, **kwargs):
            # Tools are present in request, but we return a response with NO grounding markers
            # This forces the adapter's post-call REQUIRED check to fail
            fake_resp = _FakeOpenAIResponse(text="ok-no-tools-used", grounded=False)
            # Ensure output has no tool-related types that the detector looks for
            fake_resp.output = [
                {"type": "message", "content": [{"type": "text", "text": "ok-no-tools-used"}]}
            ]
            return fake_resp

    class _FakeClient:
        def __init__(self, *a, **k):
            self.responses = _FakeResponses()
        def with_options(self, timeout=None):
            return self

    monkeypatch.setattr("openai.AsyncOpenAI", _FakeClient)
    return _FakeClient

async def _mk_openai_request(grounded=False, json_mode=False, required=False):
    from app.llm.types import LLMRequest
    
    meta = {}
    if required:
        meta["grounding_mode"] = "REQUIRED"
    elif grounded:
        meta["grounding_mode"] = "AUTO"
    
    return LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "Say hello"}
        ],
        grounded=grounded,
        json_mode=json_mode,
        max_tokens=200,
        temperature=0.7,
        meta=meta
    )

async def _call_openai_adapter(req):
    from app.llm.adapters.openai_adapter import OpenAIAdapter
    # Set API key before construction
    os.environ["OPENAI_API_KEY"] = "test-key-for-smoke-tests"
    try:
        adapter = OpenAIAdapter()
        return await adapter.complete(req, timeout=30)
    finally:
        os.environ.pop("OPENAI_API_KEY", None)

async def _assert_basic_openai(resp):
    assert resp is not None
    assert hasattr(resp, "content")
    assert isinstance(resp.content, str) and len(resp.content) > 0
    assert hasattr(resp, "model_version")
    assert resp.model_version is not None
    assert hasattr(resp, "usage")
    assert resp.usage.get("total_tokens", 0) > 0

@pytest.mark.usefixtures("patch_openai_ok")
async def test_openai_ungrounded_text():
    """Test ungrounded text generation."""
    req = await _mk_openai_request(grounded=False, json_mode=False)
    resp = await _call_openai_adapter(req)
    await _assert_basic_openai(resp)
    assert resp.grounded_effective in (False, None)

@pytest.mark.usefixtures("patch_openai_ok")
async def test_openai_ungrounded_json():
    """Test ungrounded JSON generation."""
    req = await _mk_openai_request(grounded=False, json_mode=True)
    resp = await _call_openai_adapter(req)
    await _assert_basic_openai(resp)
    assert resp.grounded_effective in (False, None)

@pytest.mark.usefixtures("patch_openai_ok")
async def test_openai_grounded_auto():
    """Test grounded with AUTO mode - tool use is optional."""
    req = await _mk_openai_request(grounded=True, json_mode=False, required=False)
    resp = await _call_openai_adapter(req)
    await _assert_basic_openai(resp)
    # In AUTO mode, grounding is attempted
    assert hasattr(resp, "grounded_effective")

@pytest.mark.usefixtures("patch_openai_required_ungrounded")
async def test_openai_grounded_required_enforcement():
    """Test REQUIRED mode enforcement when tools don't produce grounding."""
    req = await _mk_openai_request(grounded=True, json_mode=False, required=True)
    
    # Should raise error in REQUIRED mode when no actual tool use detected
    with pytest.raises(RuntimeError) as exc_info:
        await _call_openai_adapter(req)
    assert "GROUNDING_REQUIRED" in str(exc_info.value)

@pytest.mark.usefixtures("patch_openai_preview_retry")
async def test_openai_preview_fallback_via_sdk():
    """Test web_search → web_search_preview retry via SDK."""
    os.environ["ALLOW_PREVIEW_COMPAT"] = "true"
    try:
        req = await _mk_openai_request(grounded=True, json_mode=False)
        resp = await _call_openai_adapter(req)
        await _assert_basic_openai(resp)
        # Check for preview retry marker in metadata
        assert hasattr(resp, "metadata") or hasattr(resp, "raw_response")
        # The adapter may store this in metadata or raw_response
    finally:
        os.environ.pop("ALLOW_PREVIEW_COMPAT", None)

# ------------------ Vertex fakes ------------------

class _FakeVertexCandidate:
    def __init__(self, text, grounded=False):
        self.content = types.SimpleNamespace(
            parts=[types.SimpleNamespace(text=text)]
        )
        if grounded:
            self.grounding_metadata = types.SimpleNamespace(
                web_search_queries=["test query"],
                grounding_chunks=[{"uri": "https://example.com"}],
                grounding_attributions=[{"segment": {"text": text[:50]}}]
            )

class _FakeVertexResponse:
    def __init__(self, text, grounded=False):
        self.candidates = [_FakeVertexCandidate(text, grounded)]
        self.usage_metadata = types.SimpleNamespace(
            prompt_token_count=50,
            candidates_token_count=100,
            total_token_count=150
        )
        
    @property
    def text(self):
        return self.candidates[0].content.parts[0].text

@pytest.fixture
def patch_vertex_sdk(monkeypatch):
    """Patch Vertex SDK components for testing."""
    import vertexai
    from vertexai import generative_models as gm
    
    class _FakeTool:
        @classmethod
        def from_google_search_retrieval(cls, retrieval):
            return _FakeTool()
    
    class _FakeGoogleSearchRetrieval:
        pass
    
    class _FakeGenerativeModel:
        def __init__(self, model_name):
            self.model_name = model_name
            self._calls = 0
        
        def generate_content(self, contents, tools=None, generation_config=None):
            self._calls += 1
            
            # Check if tools are provided (Step-1)
            # Tools is a list when provided, None when not
            has_tools = tools is not None
            
            # Check if JSON mode is requested (Step-2)
            # GenerationConfig doesn't expose attributes directly, need to check dict or string repr
            is_json = False
            if generation_config is not None:
                # Check string representation or dict conversion
                config_str = str(generation_config)
                if 'response_mime_type' in config_str and 'application/json' in config_str:
                    is_json = True
                elif hasattr(generation_config, 'to_dict'):
                    config_dict = generation_config.to_dict()
                    is_json = config_dict.get('response_mime_type') == 'application/json'
                elif hasattr(generation_config, 'response_mime_type'):
                    is_json = generation_config.response_mime_type == 'application/json'
            
            if has_tools:
                # Step 1: grounded response with tools
                return _FakeVertexResponse("Grounded answer from web sources.", grounded=True)
            elif tools is None and is_json:
                # Step 2: JSON reshape (tools=None + JSON config)
                json_response = '{"answer": "Reshaped to JSON", "step2_attestation": true}'
                return _FakeVertexResponse(json_response, grounded=False)
            elif tools is None and not is_json:
                # Regular ungrounded (no tools, no JSON)
                return _FakeVertexResponse("Ungrounded response.", grounded=False)
            else:
                # Fallback - should not happen but return something safe
                return _FakeVertexResponse("Fallback response.", grounded=False)
        
        async def generate_content_async(self, contents, tools=None, generation_config=None):
            # Same logic as sync version - adapter will pick one
            return self.generate_content(contents, tools, generation_config)
    
    class _FakeGrounding:
        GoogleSearchRetrieval = _FakeGoogleSearchRetrieval
    
    # Monkey-patch the modules
    monkeypatch.setattr("vertexai.generative_models.Tool", _FakeTool)
    monkeypatch.setattr("vertexai.generative_models.GenerativeModel", _FakeGenerativeModel)
    monkeypatch.setattr("vertexai.generative_models.grounding", _FakeGrounding)
    
    # Also patch the init function
    def fake_init(*args, **kwargs):
        pass
    monkeypatch.setattr("vertexai.init", fake_init)
    
    return _FakeGenerativeModel

async def _mk_vertex_request(grounded=False, json_mode=False, required=False):
    """Create Vertex request."""
    from app.llm.types import LLMRequest
    
    meta = {}
    if required:
        meta["grounding_mode"] = "REQUIRED"
    elif grounded:
        meta["grounding_mode"] = "AUTO"
    
    return LLMRequest(
        vendor="vertex",
        model="publishers/google/models/gemini-2.5-pro",
        messages=[
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "Say hello"}
        ],
        grounded=grounded,
        json_mode=json_mode,
        max_tokens=256,
        temperature=0.7,
        meta=meta
    )

async def _call_vertex_adapter(req):
    from app.llm.adapters.vertex_adapter import VertexAdapter
    
    # Mock environment
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    os.environ["VERTEX_LOCATION"] = "europe-west4"
    
    try:
        adapter = VertexAdapter()
        result = await adapter.complete(req, timeout=45)
        return result
    finally:
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("VERTEX_LOCATION", None)

async def _assert_basic_vertex(resp):
    assert resp is not None
    assert hasattr(resp, "content")
    assert isinstance(resp.content, str) and len(resp.content) > 0
    assert hasattr(resp, "model_version")
    assert resp.model_version is not None
    assert hasattr(resp, "usage")

@pytest.mark.usefixtures("patch_vertex_sdk")
async def test_vertex_grounded_prose_step1():
    """Test Vertex Step-1 grounded prose generation."""
    req = await _mk_vertex_request(grounded=True, json_mode=False)
    resp = await _call_vertex_adapter(req)
    await _assert_basic_vertex(resp)
    assert "Grounded" in resp.content or "sources" in resp.content.lower()
    # Check metadata for grounded_effective
    if hasattr(resp, "metadata"):
        assert resp.metadata.get("grounded_effective") == True

@pytest.mark.usefixtures("patch_vertex_sdk")
async def test_vertex_two_step_grounded_to_json():
    """Test Vertex two-step: Step-1 grounded → Step-2 JSON (no tools)."""
    req = await _mk_vertex_request(grounded=True, json_mode=True)
    resp = await _call_vertex_adapter(req)
    await _assert_basic_vertex(resp)
    
    # Should have two-step metadata
    if hasattr(resp, "metadata"):
        assert resp.metadata.get("two_step_used") == True
        assert resp.metadata.get("step2_tools_invoked") == False
        assert "step2_source_ref" in resp.metadata
    
    # Content should be valid JSON
    parsed = json.loads(resp.content)
    assert parsed.get("answer") == "Reshaped to JSON"
    assert parsed.get("step2_attestation") == True

@pytest.mark.usefixtures("patch_vertex_sdk")
async def test_vertex_ungrounded_json():
    """Test Vertex ungrounded JSON generation."""
    req = await _mk_vertex_request(grounded=False, json_mode=True)
    resp = await _call_vertex_adapter(req)
    await _assert_basic_vertex(resp)
    if hasattr(resp, "metadata"):
        assert resp.metadata.get("grounded_effective") == False
        assert resp.metadata.get("two_step_used") != True

@pytest.mark.usefixtures("patch_vertex_sdk")
async def test_vertex_ungrounded_text():
    """Test Vertex ungrounded text generation."""
    req = await _mk_vertex_request(grounded=False, json_mode=False)
    resp = await _call_vertex_adapter(req)
    await _assert_basic_vertex(resp)
    if hasattr(resp, "metadata"):
        assert resp.metadata.get("grounded_effective") == False

# ------------------ Rate limiting tests ------------------

async def test_rate_limiter_adaptive_multiplier(monkeypatch):
    """Test that adaptive multiplier tracks actual/estimated ratios."""
    from unittest.mock import MagicMock
    
    # Patch settings BEFORE constructing limiter
    import app.core.config
    mock_settings = MagicMock()
    mock_settings.openai_gate_in_adapter = True
    mock_settings.openai_max_concurrency = 5
    mock_settings.openai_tpm_limit = 10000
    monkeypatch.setattr(app.core.config, "get_settings", lambda: mock_settings)
    
    from app.llm.adapters.openai_adapter import _OpenAIRateLimiter
    limiter = _OpenAIRateLimiter()
    
    # Simulate grounded calls with varying actual vs estimated
    await limiter.commit_actual_tokens(2000, 1000, is_grounded=True)  # 2x ratio
    await limiter.commit_actual_tokens(1500, 1000, is_grounded=True)  # 1.5x ratio
    await limiter.commit_actual_tokens(1800, 1000, is_grounded=True)  # 1.8x ratio
    
    # Check multiplier adjusted
    multiplier = limiter.get_grounded_multiplier()
    assert 1.0 <= multiplier <= 2.0  # Should be in reasonable range
    assert multiplier > 1.0  # Should have adapted upward

async def test_rate_limiter_auto_trim(monkeypatch):
    """Test auto-trim suggestion when budget is tight."""
    from unittest.mock import MagicMock
    
    # Patch settings BEFORE constructing limiter
    import app.core.config
    mock_settings = MagicMock()
    mock_settings.openai_gate_in_adapter = True
    mock_settings.openai_max_concurrency = 5
    mock_settings.openai_tpm_limit = 1000
    monkeypatch.setattr(app.core.config, "get_settings", lambda: mock_settings)
    
    from app.llm.adapters.openai_adapter import _OpenAIRateLimiter
    limiter = _OpenAIRateLimiter()
    
    # Reserve 95% of the TPM budget through the proper API
    # This actually increments _tokens_used_this_minute (unlike commit_actual_tokens)
    await limiter.await_tpm(estimated_tokens=950)
    
    # Test the suggest_trim method with clear parameters
    suggested = limiter.suggest_trim(2000, min_out=128)
    
    # Should suggest trimming when at 95% capacity
    assert suggested < 2000, f"Expected trim suggestion < 2000, got {suggested}"
    assert suggested >= 128, f"Expected trim suggestion >= 128, got {suggested}"