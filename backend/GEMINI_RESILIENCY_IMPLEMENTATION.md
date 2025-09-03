# Gemini Resiliency Implementation - COMPLETE

## PR Description

**Implemented resiliency for Gemini 2.5 Pro that preserves immutability: retries → circuit breaker → optional vendor failover (Direct→Vertex) with the same model and no prompt mutation.**

**Grounding remains single-call FFC; anchored citations are emitted when supports exist, otherwise Option-A unlinked evidence is allowed for Google vendors in REQUIRED.**

**Dev/staging/prod stay aligned; no silent downgrades or "smart" prompt edits.**

## Implementation Details

### 1. Retry Logic (Tier A)
✅ **Both adapters** (gemini_adapter.py & vertex_adapter.py):
- **Attempts**: 4 total (1 initial + 3 retries)
- **Backoff**: Exponential with jitter
  - Base delays: 0.5s → 1s → 2s → 4s
  - Jitter: Up to 50% random addition
- **Request tracking**: Stable `request_id` for idempotency
- **503 detection**: Checks for "503" or "UNAVAILABLE" in error string

### 2. Circuit Breaker (Tier B)
✅ **Per vendor+model combination**:
- **Opens after**: 5 consecutive 503 errors within any timeframe
- **Hold duration**: Random 60-120 seconds
- **States**: closed → open → half-open → closed
- **Fail fast**: When open, immediately returns `service_unavailable_upstream`
- **Reset**: On successful call or after hold duration expires

### 3. Optional Vendor Failover (Tier C)
✅ **Flag-gated failover**:
- **Environment variable**: `GEMINI_DIRECT_FAILOVER_TO_VERTEX=true`
- **Trigger**: Only when circuit breaker is open for gemini_direct
- **Behavior**: 
  - Attempts same request on Vertex with identical model
  - No prompt mutation
  - Records `vendor_path: ["gemini_direct", "vertex"]`
- **Telemetry**: `failover_from`, `failover_to`, `failover_reason="503_circuit_open"`

### 4. Immutability Guarantees
✅ **Strictly enforced**:
- **No prompt mutation**: Original messages preserved exactly
- **No model substitution**: gemini-2.5-pro remains gemini-2.5-pro
- **No flash downgrade**: Automatic blocking of flash models
- **Hash verification**: Can verify prompt hash before/after

### 5. Telemetry Added
✅ **Comprehensive metrics**:
```python
metadata = {
    "request_id": "req_1234567890_5678",
    "retry_count": 2,
    "backoff_ms_last": 2500,
    "circuit_state": "closed",
    "breaker_open_reason": "5_consecutive_503s",  # When opened
    "upstream_status": 503,
    "upstream_error": "UNAVAILABLE",
    "vendor_path": ["gemini_direct", "vertex"],  # When failover
    "failover_from": "gemini_direct",
    "failover_to": "vertex", 
    "failover_reason": "503_circuit_open",
    "error_type": "service_unavailable_upstream"  # When all retries fail
}
```

## What We Do NOT Do

❌ **No "autonomous query simplification"** - Prompts are never modified
❌ **No model substitution** - No silent downgrade to flash
❌ **No multi-turn reduction** - Contract remains two-message
❌ **No prompt rewriting** - ALS stays in place, messages unchanged

## Acceptance Tests

### Test A: Retry Success ✅
- Simulates 503 on first call
- Verifies retry with backoff
- Confirms eventual success
- Validates `retry_count >= 1`

### Test B: Circuit Breaker ✅
- Forces 5+ consecutive 503s
- Verifies breaker opens
- Confirms fail-fast behavior
- Validates `circuit_state="open"`

### Test C: Vendor Failover ✅
- Opens breaker for gemini_direct
- Enables failover flag
- Verifies request routes to vertex
- Validates `vendor_path` tracking

### Test D: Immutability ✅
- Hashes prompt before/after
- Verifies model unchanged
- Confirms no prompt mutation
- Validates across retries

## Audit Line Format
```
AUDIT vendor={gemini_direct|vertex} model={gemini-2.5-pro} 
      attempts={n} breaker={open|closed} failover={true|false} 
      tool_calls={n} chunks={n} supports={n} 
      anchored={n} unlinked={n} coverage_pct={n} 
      reason={anchored_google|unlinked_google|...}
```

## Configuration

### Environment Variables
- `GEMINI_DIRECT_FAILOVER_TO_VERTEX`: Enable failover (default: false)
- `USE_GEMINI_DIRECT`: Route Gemini models via Direct API (default: false)

### Production Settings
- **Model**: ONLY gemini-2.5-pro
- **Retries**: 4 attempts with exponential backoff
- **Circuit breaker**: 5 failures to open, 60-120s hold
- **Failover**: Disabled by default (enable via env var)

## Status: PRODUCTION READY

All components implemented and tested:
- ✅ Retry logic with exponential backoff
- ✅ Circuit breaker pattern
- ✅ Optional vendor failover
- ✅ Full telemetry
- ✅ Immutability preserved
- ✅ Acceptance tests passing

The implementation handles 503 errors gracefully while maintaining strict immutability and model consistency requirements.