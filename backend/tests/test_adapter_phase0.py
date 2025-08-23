"""
Test suite for Phase-0 adapter implementation
Comprehensive tests for OpenAI and Vertex AI adapters
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from app.llm.types import LLMRequest, LLMResponse
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter


@pytest.fixture
def adapter():
    """Create unified adapter instance"""
    return UnifiedLLMAdapter()


@pytest.fixture
def openai_request():
    """Create sample OpenAI request with GPT-5 (primary model)"""
    return LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "What is the capital of France?"}
        ],
        temperature=0.0,
        grounded=False,
        json_mode=False
    )


@pytest.fixture
def vertex_request():
    """Create sample Vertex request"""
    return LLMRequest(
        vendor="vertex",
        model="gemini-1.5-pro",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "What is the capital of France?"}
        ],
        temperature=0.0,
        grounded=False,
        json_mode=False
    )


# ============= OPENAI TESTS =============

@pytest.mark.asyncio
async def test_openai_gpt5_standard_completion(adapter, openai_request):
    """Test OpenAI standard completion with GPT-5 (PRIMARY MODEL)"""
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="The capital of France is Paris."))],
            model="gpt-5-2024-11-01",
            system_fingerprint="fp_gpt5_e467b03e43",
            usage=Mock(prompt_tokens=25, completion_tokens=8, total_tokens=33)
        )
        
        response = await adapter.complete(openai_request)
        
        assert response.success
        assert response.content == "The capital of France is Paris."
        assert response.model_version == "gpt-5-2024-11-01"
        assert response.model_fingerprint == "fp_gpt5_e467b03e43"
        assert response.grounded_effective == False
        assert response.usage["prompt_tokens"] == 25
        assert response.usage["completion_tokens"] == 8
        assert response.usage["total_tokens"] == 33
        assert response.vendor == "openai"
        assert response.model == "gpt-5"
        
        # Verify correct API call
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "gpt-5"
        assert call_kwargs["temperature"] == 0.0
        assert len(call_kwargs["messages"]) == 2




@pytest.mark.asyncio
async def test_openai_with_grounding(adapter, openai_request):
    """Test OpenAI with grounding (Responses API simulation)"""
    openai_request.grounded = True
    openai_request.messages = [
        {"role": "user", "content": "What's the current weather in Paris?"}
    ]
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="Based on current data, Paris is experiencing partly cloudy weather with 18°C."))],
            model="gpt-4o-2024-08-06",
            system_fingerprint="fp_e467b03e43",
            usage=Mock(prompt_tokens=40, completion_tokens=20, total_tokens=60)
        )
        
        response = await adapter.complete(openai_request)
        
        assert response.success
        assert "18°C" in response.content
        assert response.grounded_effective == False  # Will be True when Responses API is available
        assert response.vendor == "openai"
        
        # Check that grounding system message was added
        call_kwargs = mock_create.call_args[1]
        messages = call_kwargs['messages']
        assert any("web search" in msg['content'] and "cite sources" in msg['content'].lower() 
                  for msg in messages if msg['role'] == 'system')


@pytest.mark.asyncio
async def test_openai_json_mode(adapter, openai_request):
    """Test OpenAI with JSON mode enabled"""
    openai_request.json_mode = True
    openai_request.messages = [
        {"role": "user", "content": "Return a JSON object with city: Paris and country: France"}
    ]
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content='{"city": "Paris", "country": "France"}'))],
            model="gpt-4o-2024-08-06",
            system_fingerprint="fp_e467b03e43",
            usage=Mock(prompt_tokens=20, completion_tokens=10, total_tokens=30)
        )
        
        response = await adapter.complete(openai_request)
        
        assert response.success
        assert response.content == '{"city": "Paris", "country": "France"}'
        
        # Verify JSON is valid
        parsed = json.loads(response.content)
        assert parsed["city"] == "Paris"
        assert parsed["country"] == "France"
        
        # Check response_format was set
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openai_system_fingerprint_extraction(adapter, openai_request):
    """Test OpenAI system_fingerprint is properly extracted"""
    fingerprints = [
        "fp_e467b03e43",
        "fp_a7daf7c51e",
        "fp_system_2024_08",
        None  # Test missing fingerprint
    ]
    
    for fingerprint in fingerprints:
        with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = Mock(
                choices=[Mock(message=Mock(content="Test response"))],
                model="gpt-4o-2024-08-06",
                system_fingerprint=fingerprint,
                usage=Mock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            )
            
            response = await adapter.complete(openai_request)
            
            assert response.success
            assert response.model_fingerprint == fingerprint
            assert response.model_version == "gpt-4o-2024-08-06"


@pytest.mark.asyncio
async def test_openai_with_als_context(adapter, openai_request):
    """Test OpenAI with ALS (Ambient Location Signals) context"""
    openai_request.als_context = {
        'locale': 'fr-FR',
        'seed_key_id': 'k3'
    }
    openai_request.template_id = "test_template_123"
    
    with patch.object(adapter.als_builder, 'build_als_block') as mock_als:
        mock_als.return_value = "[ALS: locale=fr-FR, seed=k3, template=test_template_123]"
        
        with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = Mock(
                choices=[Mock(message=Mock(content="Bonjour! Comment puis-je vous aider?"))],
                model="gpt-4o-2024-08-06",
                system_fingerprint="fp_e467b03e43",
                usage=Mock(prompt_tokens=50, completion_tokens=10, total_tokens=60)
            )
            
            response = await adapter.complete(openai_request)
            
            assert response.success
            
            # Verify ALS was built correctly
            mock_als.assert_called_once_with(
                locale='fr-FR',
                template_id="test_template_123",
                seed_key_id='k3'
            )
            
            # Check ALS was prepended to user message
            call_kwargs = mock_create.call_args[1]
            messages = call_kwargs['messages']
            user_msg = next(msg for msg in messages if msg['role'] == 'user')
            assert "[ALS:" in user_msg['content']
            assert "fr-FR" in user_msg['content']


@pytest.mark.asyncio
async def test_openai_with_seed(adapter, openai_request):
    """Test OpenAI with seed parameter for deterministic output"""
    openai_request.seed = 42
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="Deterministic response"))],
            model="gpt-4o-2024-08-06",
            system_fingerprint="fp_e467b03e43",
            usage=Mock(prompt_tokens=20, completion_tokens=5, total_tokens=25)
        )
        
        response = await adapter.complete(openai_request)
        
        assert response.success
        
        # Verify seed was passed
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs.get("seed") == 42


@pytest.mark.asyncio
async def test_openai_with_max_tokens(adapter, openai_request):
    """Test OpenAI with max_tokens limit"""
    openai_request.max_tokens = 100
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="Limited response"))],
            model="gpt-4o-2024-08-06",
            system_fingerprint="fp_e467b03e43",
            usage=Mock(prompt_tokens=20, completion_tokens=5, total_tokens=25)
        )
        
        response = await adapter.complete(openai_request)
        
        assert response.success
        
        # Verify max_tokens was passed
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs.get("max_tokens") == 100


# ============= VERTEX AI TESTS =============

@pytest.mark.asyncio
async def test_vertex_standard_completion(adapter, vertex_request):
    """Test Vertex AI standard completion with Gemini"""
    with patch('app.llm.adapters.vertex_adapter.generative_models.GenerativeModel') as MockModel:
        mock_instance = Mock()
        MockModel.return_value = mock_instance
        
        mock_response = Mock()
        mock_response.text = "The capital of France is Paris."
        mock_response.usage_metadata = Mock(
            prompt_token_count=25,
            candidates_token_count=8,
            total_token_count=33
        )
        mock_response.model_version = "gemini-1.5-pro-001"
        
        mock_instance.generate_content.return_value = mock_response
        
        response = await adapter.complete(vertex_request)
        
        assert response.success
        assert response.content == "The capital of France is Paris."
        assert response.model_version == "gemini-1.5-pro"
        assert response.model_fingerprint == "gemini-1.5-pro-001"
        assert response.grounded_effective == False
        assert response.usage["prompt_tokens"] == 25
        assert response.usage["completion_tokens"] == 8
        assert response.usage["total_tokens"] == 33
        assert response.vendor == "vertex"
        assert response.model == "gemini-1.5-pro"


@pytest.mark.asyncio
async def test_vertex_auth_failure():
    """Test Vertex AI fails with clear error when ADC not configured"""
    with patch('app.llm.adapters.vertex_adapter.google.auth.default') as mock_auth:
        from google.auth.exceptions import DefaultCredentialsError
        mock_auth.side_effect = DefaultCredentialsError("Could not automatically determine credentials")
        
        # Create adapter with failed auth
        vertex_adapter = VertexAdapter()
        
        request = LLMRequest(
            vendor="vertex",
            model="gemini-1.5-pro",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.0
        )
        
        response = await vertex_adapter.complete(request)
        
        assert not response.success
        assert response.error_type == "AuthenticationError"
        assert "gcloud auth application-default login" in response.error_message
        assert "GOOGLE_APPLICATION_CREDENTIALS" in response.error_message
        assert "Workload Identity Federation" in response.error_message


@pytest.mark.asyncio
async def test_vertex_no_direct_gemini_api():
    """Ensure NO Direct Gemini API fallback exists anywhere"""
    from app.llm.adapters import vertex_adapter
    
    # Check that Direct Gemini API is NOT imported
    assert not hasattr(vertex_adapter, 'genai')
    assert 'google.generativeai' not in str(vertex_adapter.__dict__)
    
    # Check source code doesn't contain Direct API imports
    import inspect
    source = inspect.getsource(vertex_adapter)
    assert 'import google.generativeai' not in source
    assert 'from google import generativeai' not in source
    assert 'GEMINI_API_KEY' not in source
    
    # Check settings don't have Direct API flags
    from app.core.config import get_settings
    settings = get_settings()
    assert not hasattr(settings, 'ALLOW_GEMINI_DIRECT')
    assert not hasattr(settings, 'GEMINI_API_KEY')


# ============= CROSS-PROVIDER TESTS =============

@pytest.mark.asyncio
async def test_cross_provider_same_prompt(adapter):
    """Test same prompt to both providers returns normalized response"""
    prompt_messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "What is 2+2?"}
    ]
    
    # OpenAI request
    openai_req = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=prompt_messages,
        temperature=0.0
    )
    
    # Vertex request
    vertex_req = LLMRequest(
        vendor="vertex",
        model="gemini-1.5-pro",
        messages=prompt_messages,
        temperature=0.0
    )
    
    # Mock OpenAI response
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
        mock_openai.return_value = Mock(
            choices=[Mock(message=Mock(content="4"))],
            model="gpt-4o-2024-08-06",
            system_fingerprint="fp_123",
            usage=Mock(prompt_tokens=20, completion_tokens=1, total_tokens=21)
        )
        
        openai_response = await adapter.complete(openai_req)
    
    # Mock Vertex response
    with patch('app.llm.adapters.vertex_adapter.generative_models.GenerativeModel') as MockModel:
        mock_instance = Mock()
        MockModel.return_value = mock_instance
        
        mock_response = Mock()
        mock_response.text = "4"
        mock_response.usage_metadata = Mock(
            prompt_token_count=20,
            candidates_token_count=1,
            total_token_count=21
        )
        mock_response.model_version = "gemini-1.5-pro-001"
        
        mock_instance.generate_content.return_value = mock_response
        
        vertex_response = await adapter.complete(vertex_req)
    
    # Both responses should have same structure
    assert openai_response.success == vertex_response.success
    assert openai_response.content == vertex_response.content == "4"
    assert isinstance(openai_response.usage, dict) and isinstance(vertex_response.usage, dict)
    assert "total_tokens" in openai_response.usage and "total_tokens" in vertex_response.usage
    assert openai_response.latency_ms > 0 and vertex_response.latency_ms > 0
    assert openai_response.vendor == "openai" and vertex_response.vendor == "vertex"


@pytest.mark.asyncio
async def test_cross_provider_telemetry(adapter):
    """Test telemetry is recorded for both providers"""
    from sqlalchemy.ext.asyncio import AsyncSession
    
    mock_session = AsyncMock(spec=AsyncSession)
    telemetry_records = []
    
    def capture_telemetry(record):
        telemetry_records.append(record)
    
    mock_session.add.side_effect = capture_telemetry
    
    # OpenAI call
    openai_req = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
        template_id="template_123",
        run_id="run_456"
    )
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
        mock_openai.return_value = Mock(
            choices=[Mock(message=Mock(content="Hi!"))],
            model="gpt-4o-2024-08-06",
            system_fingerprint="fp_123",
            usage=Mock(prompt_tokens=10, completion_tokens=2, total_tokens=12)
        )
        
        await adapter.complete(openai_req, session=mock_session)
    
    # Vertex call
    vertex_req = LLMRequest(
        vendor="vertex",
        model="gemini-1.5-pro",
        messages=[{"role": "user", "content": "Hello"}],
        template_id="template_789",
        run_id="run_012"
    )
    
    with patch('app.llm.adapters.vertex_adapter.generative_models.GenerativeModel') as MockModel:
        mock_instance = Mock()
        MockModel.return_value = mock_instance
        
        mock_response = Mock()
        mock_response.text = "Hi!"
        mock_response.usage_metadata = Mock(
            prompt_token_count=10,
            candidates_token_count=2,
            total_token_count=12
        )
        mock_response.model_version = "gemini-1.5-pro-001"
        
        mock_instance.generate_content.return_value = mock_response
        
        await adapter.complete(vertex_req, session=mock_session)
    
    # Check both telemetry records
    assert len(telemetry_records) == 2
    
    openai_telemetry = telemetry_records[0]
    assert openai_telemetry.vendor == "openai"
    assert openai_telemetry.model == "gpt-4o"
    assert openai_telemetry.template_id == "template_123"
    assert openai_telemetry.run_id == "run_456"
    assert openai_telemetry.total_tokens == 12
    assert openai_telemetry.success == True
    
    vertex_telemetry = telemetry_records[1]
    assert vertex_telemetry.vendor == "vertex"
    assert vertex_telemetry.model == "gemini-1.5-pro"
    assert vertex_telemetry.template_id == "template_789"
    assert vertex_telemetry.run_id == "run_012"
    assert vertex_telemetry.total_tokens == 12
    assert vertex_telemetry.success == True


@pytest.mark.asyncio
async def test_cross_provider_json_mode(adapter):
    """Test JSON mode works for both providers"""
    json_messages = [
        {"role": "user", "content": "Return JSON with field 'answer' set to 42"}
    ]
    
    # OpenAI JSON mode
    openai_req = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=json_messages,
        json_mode=True,
        temperature=0.0
    )
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_openai:
        mock_openai.return_value = Mock(
            choices=[Mock(message=Mock(content='{"answer": 42}'))],
            model="gpt-4o-2024-08-06",
            system_fingerprint="fp_123",
            usage=Mock(prompt_tokens=15, completion_tokens=5, total_tokens=20)
        )
        
        openai_response = await adapter.complete(openai_req)
        
        # Verify JSON mode was set
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs.get("response_format") == {"type": "json_object"}
    
    # Vertex JSON mode
    vertex_req = LLMRequest(
        vendor="vertex",
        model="gemini-1.5-pro",
        messages=json_messages,
        json_mode=True,
        temperature=0.0
    )
    
    with patch('app.llm.adapters.vertex_adapter.generative_models') as mock_gm:
        MockModel = Mock()
        mock_gm.GenerativeModel.return_value = MockModel
        
        # Mock GenerationConfig
        mock_gm.GenerationConfig = Mock
        
        mock_response = Mock()
        mock_response.text = '{"answer": 42}'
        mock_response.usage_metadata = Mock(
            prompt_token_count=15,
            candidates_token_count=5,
            total_token_count=20
        )
        
        MockModel.generate_content.return_value = mock_response
        
        vertex_response = await adapter.complete(vertex_req)
    
    # Both should return valid JSON
    openai_json = json.loads(openai_response.content)
    vertex_json = json.loads(vertex_response.content)
    
    assert openai_json["answer"] == 42
    assert vertex_json["answer"] == 42


# ============= GPT-5 PRIORITY TESTS =============

@pytest.mark.asyncio
async def test_gpt5_mandatory_parameters(adapter):
    """Test GPT-5 enforces mandatory parameters"""
    # Test 1: GPT-5 MUST use temperature=1.0 and max_completion_tokens
    gpt5_request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        temperature=0.0,  # This should be overridden to 1.0
        max_tokens=100    # This should become max_completion_tokens=100
    )
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="4"))],
            model="gpt-5-2024-11-01",
            system_fingerprint="fp_gpt5_calc",
            usage=Mock(prompt_tokens=10, completion_tokens=1, total_tokens=11)
        )
        
        response = await adapter.complete(gpt5_request)
        assert response.success
        
        # Verify GPT-5 mandatory parameters were applied
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["temperature"] == 1.0  # MUST be 1.0 for GPT-5
        assert call_kwargs["max_completion_tokens"] == 100  # Not max_tokens
        assert "max_tokens" not in call_kwargs  # max_tokens should be removed
    
    # Test 2: GPT-5 with default max_completion_tokens
    gpt5_default = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "List 5 longevity supplements"}],
        temperature=0.5  # Should be overridden
    )
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="1. NMN\n2. Resveratrol\n3. Quercetin\n4. Fisetin\n5. Spermidine"))],
            model="gpt-5-2024-11-01",
            system_fingerprint="fp_gpt5_longevity",
            usage=Mock(prompt_tokens=15, completion_tokens=20, total_tokens=35)
        )
        
        response = await adapter.complete(gpt5_default)
        assert response.success
        
        # Verify default max_completion_tokens of 4000
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["temperature"] == 1.0
        assert call_kwargs["max_completion_tokens"] == 4000  # Default for GPT-5
        assert "max_tokens" not in call_kwargs


@pytest.mark.asyncio
async def test_gpt5_complex_prompts(adapter):
    """Test GPT-5 with complex prompts requiring high token limits"""
    # Complex prompt that needs lots of tokens
    gpt5_complex = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "What are the most trusted longevity supplement brands?"}],
        max_tokens=6000  # Should become max_completion_tokens=6000
    )
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="Based on scientific research and consumer trust..."))],
            model="gpt-5-2024-11-01",
            system_fingerprint="fp_gpt5_complex",
            usage=Mock(prompt_tokens=50, completion_tokens=4500, total_tokens=4550)
        )
        
        response = await adapter.complete(gpt5_complex)
        assert response.success
        assert response.usage["completion_tokens"] == 4500  # High token usage for reasoning
        
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["max_completion_tokens"] == 6000


@pytest.mark.asyncio
async def test_gpt5_with_json_mode(adapter):
    """Test GPT-5 with JSON mode maintains mandatory parameters"""
    gpt5_json = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "Return JSON with status: ready"}],
        json_mode=True,
        temperature=0.0  # Should still be overridden to 1.0
    )
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content='{"status": "ready"}'))],
            model="gpt-5-2024-11-01",
            system_fingerprint="fp_gpt5_json",
            usage=Mock(prompt_tokens=15, completion_tokens=5, total_tokens=20)
        )
        
        response = await adapter.complete(gpt5_json)
        assert response.success
        assert json.loads(response.content)["status"] == "ready"
        
        # Verify GPT-5 parameters even with JSON mode
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["temperature"] == 1.0  # MUST be 1.0 for GPT-5
        assert call_kwargs["max_completion_tokens"] == 4000  # Default
        assert call_kwargs["response_format"] == {"type": "json_object"}  # JSON mode
        assert "max_tokens" not in call_kwargs


# ============= MODEL ROUTING TESTS =============

@pytest.mark.asyncio
async def test_model_routing_focused(adapter):
    """Test focused model routing - ONLY GPT-5 and Gemini"""
    # GPT-5 is the ONLY OpenAI model we support
    assert adapter.get_vendor_for_model("gpt-5") == "openai"
    assert adapter.validate_model("openai", "gpt-5")
    assert not adapter.validate_model("vertex", "gpt-5")
    
    # Legacy OpenAI models are NOT supported
    unsupported_openai = [
        "gpt-4o", "gpt-4", "gpt-3.5-turbo",
        "o1-preview", "o1-mini",
        "gpt-5-nano", "gpt-5-micro", "gpt-5-turbo"
    ]
    
    for model in unsupported_openai:
        assert adapter.get_vendor_for_model(model) is None
        assert not adapter.validate_model("openai", model)
    
    # Gemini models for Vertex
    gemini_models = [
        "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"
    ]
    
    for model in gemini_models:
        assert adapter.get_vendor_for_model(model) == "vertex"
        assert adapter.validate_model("vertex", model)
        assert not adapter.validate_model("openai", model)
    
    # Claude models are NOT supported (Vertex only supports Gemini)
    unsupported_vertex = [
        "claude-3-opus", "claude-3-sonnet", "claude-3-haiku"
    ]
    
    for model in unsupported_vertex:
        assert adapter.get_vendor_for_model(model) is None
        assert not adapter.validate_model("vertex", model)
    
    # Other unknown models
    unknown_models = ["llama-2", "mistral-7b", "unknown-model"]
    
    for model in unknown_models:
        assert adapter.get_vendor_for_model(model) is None
        assert not adapter.validate_model("openai", model)
        assert not adapter.validate_model("vertex", model)


# ============= ERROR HANDLING TESTS =============

@pytest.mark.asyncio
async def test_openai_error_handling(adapter, openai_request):
    """Test OpenAI error handling"""
    from openai import APIError
    
    with patch.object(adapter.openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = APIError("Rate limit exceeded", response=None, body=None)
        
        response = await adapter.complete(openai_request)
        
        assert not response.success
        assert response.error_type == "APIError"
        assert "Rate limit exceeded" in response.error_message
        assert response.content == ""
        assert response.vendor == "openai"
        assert response.model == "gpt-4o"


@pytest.mark.asyncio
async def test_invalid_vendor_error(adapter):
    """Test invalid vendor error handling"""
    request = LLMRequest(
        vendor="invalid_vendor",
        model="test-model",
        messages=[{"role": "user", "content": "Test"}]
    )
    
    response = await adapter.complete(request)
    
    assert not response.success
    assert response.error_type == "InvalidVendor"
    assert "Unknown vendor: invalid_vendor" in response.error_message
    assert response.content == ""
    assert response.latency_ms > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])