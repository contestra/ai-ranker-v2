# OpenAI Adapter Resiliency Implementation - COMPLETE

## PR Description

**OpenAI adapter now has production-grade resiliency: retries with jitter, circuit breaker, clean failure semantics. Strict REQUIRED grounding preserved; no prompt/model mutation; immutability verified via hashes. Telemetry unified with Google adapters for easy cross-vendor monitoring.**

## Non-Negotiables ✅

1. **No prompt mutation** - Messages are never modified
2. **Pinned model only** - No auto-downgrade or swaps
3. **Two-phase grounded policy** - REQUIRED fails if web tool not invoked OR citations not produced
4. **No "unlinked" relaxation for OpenAI** - Strict anchored citations required

## Implementation Details

### 1. Resiliency for 5xx + Network Errors (Tier A)
✅ **Retry Policy**:
- **Triggers**: 502/503/504, timeouts, socket resets
- **Attempts**: 4 total (1 initial + 3 retries)
- **Backoff**: 0.5s → 1s → 2s → 4s with full jitter (up to 50%)
- **Request tracking**: Stable `request_id` for idempotency
- **Network errors**: Connection/socket errors trigger retry

### 2. Circuit Breaker (Tier B)
✅ **Per-model circuit breaker**:
- **Opens after**: 5 consecutive 5xx errors
- **Hold duration**: Random 60-120 seconds
- **States**: closed → open → half-open
- **Fail fast**: Returns `service_unavailable_upstream` when open
- **Scope**: Per model (e.g., `openai:gpt-5-2025-08-07`)

### 3. 429 Rate Limit Handling
✅ **Special handling for rate limits**:
- **Respect Retry-After**: Extracts from headers or error object
- **Integration**: Works with existing TPM/RPM limiter
- **Persistent quota**: After 10 consecutive 429s, exits with `rate_limited_quota`
- **No infinite retry**: Clean failure after quota exhaustion
- **No prompt mutation**: Never simplifies queries to reduce tokens

### 4. Grounding & Citations (Strict REQUIRED)
✅ **Two-phase enforcement**:
- **Tool negotiation**: Runtime selection of web_search variant
- **tool_choice**: Set to "auto" (router enforces post-hoc)
- **Invocation detection**: Positively detects web tool execution
- **Citation extraction**: Parses `url_citation` annotations
- **REQUIRED rule**: 
  - If web tool not invoked → `REQUIRED_GROUNDING_MISSING` error
  - If no anchored citations → `REQUIRED_GROUNDING_MISSING` error
  - Success only with anchored citations → `required_pass_reason="anchored_openai"`

### 5. Citation Normalization
✅ **Standard shape**:
```python
# Annotations (inline spans)
annotations = [
    {
        "start": 100,
        "end": 200,
        "text": "According to recent research...",
        "sources": [
            {
                "url": "https://example.com/article",
                "title": "Research Article",
                "domain": "example.com"
            }
        ]
    }
]

# Citations (deduplicated list)  
citations = [
    {
        "url": "https://example.com/article",
        "resolved_url": "https://example.com/article",
        "title": "Research Article",
        "domain": "example.com",
        "source_type": "annotation",
        "count": 3
    }
]
```

### 6. Streaming Robustness
✅ **Transport error handling**:
- Stream drops (socket reset) trigger full retry
- No partial chunk stitching
- Immutability maintained across retries

### 7. Telemetry (Parity with Google)
✅ **Comprehensive metrics**:
```python
metadata = {
    # Availability
    "request_id": "req_1234567890_5678",
    "retry_count": 2,
    "backoff_ms_last": 2500,
    "upstream_status": 503,
    "upstream_error": "HTTP_503",
    "circuit_state": "closed",
    "breaker_open_reason": "5_consecutive_5xx",  # When opened
    
    # Grounding
    "tool_call_count": 1,
    "anchored_citations_count": 5,
    "url_citations_count": 5,
    "required_pass_reason": "anchored_openai",  # Or REQUIRED_GROUNDING_MISSING
    
    # Immutability
    "messages_hash": "a3f5b8c9d2e1f4a6",  # SHA256 first 16 chars
    "model_identity": "gpt-5-2025-08-07",
    
    # Rate limiting
    "error_type": "rate_limited_quota",  # When persistent 429
}
```

## Acceptance Tests

### Test A: 5xx Retry Success ✅
- Forces 503 on attempt 1
- Succeeds on attempt 2
- Verifies retry_count >= 1
- Confirms backoff applied

### Test B: Circuit Breaker ✅
- Forces 5+ consecutive 503s
- Verifies breaker opens
- Subsequent calls fail fast
- Validates `service_unavailable_upstream`

### Test C: 429 Handling ✅
- Simulates 429 with Retry-After
- Verifies backoff respected
- Eventually succeeds
- Persistent 429 → `rate_limited_quota`

### Test D: Strict REQUIRED ✅
- Response without web tool → fails
- Web tool but no citations → fails
- Only passes with anchored citations
- Returns clear `REQUIRED_GROUNDING_MISSING`

### Test E: Immutability ✅
- Hashes messages before/after
- Model ID remains identical
- Any mutation fails test
- Verifies via SHA256 hash

### Test F: Persistent 429 ✅
- Continuous 429 responses
- Eventually exits with quota error
- No infinite retries
- Clean failure semantics

## Audit Line Format
```
AUDIT vendor=openai model={model} attempts={n} circuit={open|closed} 
      status={status_code} tool_calls={n} citations={n} 
      reason={anchored_openai|REQUIRED_GROUNDING_MISSING|rate_limited_quota}
```

## Environment Variables

### Existing (Preserved)
- `OPENAI_API_KEY`: API key for OpenAI
- `OPENAI_TPM_LIMIT`: Tokens per minute limit (default: 30000)
- `OPENAI_MAX_CONCURRENCY`: Max concurrent calls (default: 3)

### New (Added)
- `OPENAI_RETRY_MAX_ATTEMPTS`: Max retry attempts (default: 4)
- `OPENAI_BACKOFF_BASE_SECONDS`: Base backoff in seconds (default: 0.5)

## What We Do NOT Do

❌ **No prompt mutation** - Never simplify or rewrite messages
❌ **No model downgrade** - Never swap to different models
❌ **No relaxation for OpenAI** - REQUIRED always requires anchored citations
❌ **No infinite retries** - Clean failure after max attempts
❌ **No vendor failover** - Unless explicitly same-behavior secondary (not implemented)

## Status: PRODUCTION READY

All components implemented and tested:
- ✅ Retry logic with exponential backoff
- ✅ Circuit breaker for 5xx errors
- ✅ 429 rate limit handling
- ✅ Strict REQUIRED grounding
- ✅ Streaming robustness
- ✅ Comprehensive telemetry
- ✅ Immutability verification
- ✅ Acceptance tests passing

The OpenAI adapter now has production-grade resiliency matching the Google adapters, with strict enforcement of grounding requirements and complete immutability guarantees.