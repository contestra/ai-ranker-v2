# LLM Adapters

## Overview
This directory contains adapter implementations for various LLM providers. Each adapter handles:
- Request/response shape conversion
- Policy enforcement (e.g., grounding requirements)
- Telemetry and usage tracking
- Provider-specific quirks and workarounds

## OpenAI Adapter (Refactored)
The OpenAI adapter has been refactored to be lean and focused, delegating all transport concerns to the official SDK.

### Key Features
- **Responses API Only**: Uses OpenAI's Responses API exclusively (no Chat Completions)
- **SDK-Managed Transport**: Retries, backoff, rate limiting handled by SDK
- **Grounding Support**: AUTO and REQUIRED modes with web_search tool
- **Citation Extraction**: Properly extracts citations from web_search_call results
- **TextEnvelope Fallback**: Handles GPT-5 empty text quirk
- **Tool Negotiation**: Automatically falls back from web_search to web_search_preview
- **Respects Caller Limits**: Honors request.max_tokens, defaults to 6000 (grounded) or 1024 (ungrounded)

### Configuration
Environment variables:
- `OPENAI_API_KEY`: API key for authentication
- `OPENAI_MAX_RETRIES`: Max retry attempts (default: 5)
- `OPENAI_TIMEOUT_SECONDS`: Request timeout (default: 60)
- `OPENAI_GROUNDED_MAX_TOKENS`: Max tokens for grounded requests (default: 6000)

### Usage Example
```python
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.types import LLMRequest

adapter = OpenAIAdapter()

# Ungrounded request
request = LLMRequest(
    vendor="openai",
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is 2+2?"}],
    grounded=False,
    max_tokens=100
)

response = await adapter.complete(request)

# Grounded request with REQUIRED mode
request = LLMRequest(
    vendor="openai",
    model="gpt-5-2025-08-07",
    messages=[{"role": "user", "content": "What's the weather?"}],
    grounded=True,
    max_tokens=200,
    meta={"grounding_mode": "REQUIRED"}
)

response = await adapter.complete(request)
```

### Supported Models
- GPT-4 variants: gpt-4o, gpt-4o-mini
- GPT-5 variants: gpt-5-2025-08-07, gpt-5-mini-2025-08-07

### Architecture Principles
The adapter follows these principles:
1. **Lean**: Only implements what can't be delegated to SDK
2. **Focused**: Shape conversion, policy, telemetry only
3. **Protected**: CI guards prevent reintroduction of removed patterns

## Vertex Adapter
Handles Google Vertex AI models (Gemini family).

### Key Features
- **Snake-case Config**: Uses proper snake_case field names (max_output_tokens, system_instruction, top_p)
- **System Instruction**: Uses system_instruction field in config for clean prompt separation
- **FFC for Grounded+JSON**: Uses Forced Function Calling with schema-as-tool when both grounded and JSON are requested
- **SDK-Managed Transport**: All retries and backoff handled by the Google GenAI SDK

### Configuration
- `VERTEX_PROJECT`: Google Cloud project ID
- `VERTEX_LOCATION`: Region (default: europe-west4)  
- `VERTEX_MAX_OUTPUT_TOKENS`: Max output tokens (default: 8192)
- `VERTEX_GROUNDED_MAX_TOKENS`: Max tokens for grounded requests (default: 6000)

## Gemini Adapter  
Direct Gemini API integration.

### Key Features
- **Clean Prompts**: Uses system_instruction field instead of synthetic "System:" user messages
- **No Fake Turns**: No more "I understand..." model responses injected
- **FFC for Grounded+JSON**: Uses Forced Function Calling with schema-as-tool when both grounded and JSON are requested
- **SDK-Managed Transport**: All retries handled by the Google GenAI SDK

### Configuration
- `GEMINI_API_KEY`: API key for authentication
- `GEMINI_MAX_OUTPUT_TOKENS`: Max output tokens (default: 8192)
- `GEMINI_GROUNDED_MAX_TOKENS`: Max tokens for grounded requests (default: 6000)

## CI Protection
The `ci_adapter_guard.py` script runs in CI to prevent reintroduction of banned patterns:
- Custom HTTP clients
- Rate limiters
- Circuit breakers
- Health checks
- Streaming implementations
- Chat Completions code

Run locally: `python ci_adapter_guard.py`