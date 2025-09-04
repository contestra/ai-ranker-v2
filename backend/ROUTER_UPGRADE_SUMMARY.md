# Router Upgrade Summary

## Overview
Successfully upgraded the UnifiedLLMAdapter router with capability gating for reasoning/thinking parameters, thin circuit-breaker mechanism, and pacing controls.

## Implemented Features

### 1. Capability Registry
- Added `_capabilities_for(vendor, model)` method to determine model capabilities
- Returns flags for:
  - `supports_reasoning_effort`: OpenAI reasoning models (GPT-5, o-series)
  - `supports_reasoning_summary`: OpenAI reasoning models
  - `supports_thinking_budget`: Gemini 2.5 thinking models
  - `include_thoughts_allowed`: Gemini 2.5 thinking models

### 2. Parameter Gating
- Automatically drops unsupported parameters based on capability matrix
- **OpenAI**: Drops `reasoning_effort` and `reasoning_summary` for non-reasoning models (e.g., gpt-4o)
- **Gemini/Vertex**: Drops `thinking_budget` and `include_thoughts` for non-thinking models
- Sets telemetry flags when parameters are dropped

### 3. Circuit Breaker (Thin Implementation)
- Per `vendor:model` circuit breaker state
- Opens after N consecutive transient failures (configurable via `CB_FAILURE_THRESHOLD`)
- Cool-down period (configurable via `CB_COOLDOWN_SECONDS`)
- States: closed → open → half-open → closed
- Transient errors identified:
  - OpenAI: RateLimitError, 429, 5xx errors
  - Google: ServiceUnavailable, TooManyRequests, 503, 429, 500

### 4. Router Pacing
- Respects `Retry-After` headers from rate limit errors
- Maintains `next_allowed_at` map per `vendor:model`
- Fails fast if request comes before allowed time
- Supports OpenAI-specific headers (x-ratelimit-reset-*)

### 5. Enhanced Telemetry
New fields added to telemetry:
- `reasoning_effort`: Value if sent
- `reasoning_summary_requested`: Boolean
- `thinking_budget`: Value if sent
- `include_thoughts`: Boolean
- `reasoning_hint_dropped`: Boolean
- `thinking_hint_dropped`: Boolean
- `circuit_breaker_status`: Current breaker state
- `circuit_breaker_open_count`: Monotonic counter
- `router_pacing_delay`: Boolean if pacing blocked request

## Configuration
Environment variables:
- `CB_FAILURE_THRESHOLD`: Number of failures before opening (default: 3)
- `CB_COOLDOWN_SECONDS`: Cool-down period in seconds (default: 60)

## Testing
Created comprehensive tests in `test_router_capabilities.py` covering:
1. OpenAI capability gating (GPT-4o vs GPT-5)
2. Gemini/Vertex thinking parameter gating
3. Circuit breaker transitions
4. Router pacing with Retry-After
5. Telemetry field verification
6. No prompt mutation guarantee

Integration test in `test_router_integration.py` validates end-to-end flow.

## Key Design Principles

### No Silent Mutations
- User messages are never modified
- Only parameter blocks are dropped (with telemetry)

### SDK Delegation
- Router doesn't retry - SDKs handle retries
- Router only decides whether to call now

### Fail-Fast
- Circuit breaker blocks requests immediately when open
- Pacing blocks requests if too early

### Transparency
- All gating decisions recorded in telemetry
- No silent dropping - always stamped

## Files Modified
1. `/app/llm/unified_llm_adapter.py` - Main router implementation
2. `/test_router_capabilities.py` - Comprehensive unit tests
3. `/test_router_integration.py` - Integration tests

## Migration Notes
- No breaking changes to public interface
- Existing code continues to work
- New telemetry fields are additive

## Next Steps
- Monitor circuit breaker effectiveness in production
- Consider adding metrics/dashboards for:
  - Circuit breaker open events
  - Parameter dropping frequency
  - Pacing delays
- Extend capability matrix as new models are released