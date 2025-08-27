# Rate Limiting Implementation Summary

## Status: ✅ IMPLEMENTED

ChatGPT's rate limiting guardrails have been successfully implemented in the AI Ranker V2 backend.

## What Was Added

### 1. Configuration (Environment Variables)
```bash
OPENAI_MAX_CONCURRENCY=3
OPENAI_STAGGER_SECONDS=15
OPENAI_TPM_LIMIT=30000
OPENAI_TPM_HEADROOM=0.15
OPENAI_EST_TOKENS_PER_RUN=7000
OPENAI_RETRY_MAX_ATTEMPTS=5
OPENAI_BACKOFF_BASE_SECONDS=2
FINALIZE_LOWERS_CONCURRENCY=true
```

### 2. Core Features Implemented

#### A. Concurrency Control (`batch_runner.py`)
- **Semaphore**: Limits OpenAI to max 3 concurrent requests
- **Dynamic tracking**: Active concurrency exposed via Prometheus metric
- **Finalize mode**: Can drop to 2 concurrent when handling finalize passes

#### B. Request Staggering (`batch_runner.py`)
- **15-second stagger**: Enforced between OpenAI request launches
- **Jitter**: ±20% (capped at 3s) to prevent thundering herd
- **Slot scheduling**: Tracks next available launch slot

#### C. Token Budget Management (`batch_runner.py`)
- **TPM tracking**: Monitors token usage per minute
- **Headroom**: Keeps 15% buffer (25.5k effective limit of 30k)
- **Window-based**: Resets every minute
- **Deferral**: Delays requests when approaching limit

#### D. 429 Retry Logic (`openai_adapter.py`)
- **Exponential backoff**: 2s → 4s → 8s → 16s → 32s
- **Max 5 attempts**: Configurable via environment
- **Honors Retry-After**: If header present, uses that value
- **Rate limit exhaustion**: Returns structured error after max attempts

### 3. Telemetry & Monitoring

#### New Prometheus Metrics:
- `contestra_openai_active_concurrency` - Current in-flight requests
- `contestra_openai_next_slot_epoch` - Next launch slot timestamp
- `contestra_openai_stagger_delays_total` - Count of stagger delays
- `contestra_openai_tpm_window_deferrals_total` - TPM budget deferrals
- `contestra_llm_rate_limit_events_total` - 429 events by vendor

### 4. Files Modified
- `app/core/config.py` - Added rate limiting configuration
- `app/prometheus_metrics.py` - Added new metrics and helpers
- `app/services/batch_runner.py` - Implemented concurrency/stagger/TPM logic
- `app/llm/adapters/openai_adapter.py` - Added 429 retry/backoff logic
- `app/api/routes/templates.py` - Added preflight TPM guard for batch endpoint
- `.env` - Added configuration variables

### 5. API Preflight Guard
The batch endpoint (`/templates/{template_id}/batch-run`) now includes a preflight check that:
- Calculates projected token usage: `openai_runs * est_tokens_per_run`
- Compares against per-minute budget: `tpm_limit * (1 - headroom)`
- Returns `503 BATCH_RATE_LIMITED` if batch would exceed limit
- Provides detailed error with suggested wait time
- Prevents starting batches that would immediately hit rate limits

## Testing & Verification

### Quick Smoke Test
```bash
# Check metrics endpoint
curl -s http://localhost:8000/metrics | grep contestra_openai

# Expected metrics:
# - contestra_openai_active_concurrency (should be 0 when idle)
# - contestra_openai_next_slot_epoch
# - contestra_openai_stagger_delays_total
# - contestra_openai_tpm_window_deferrals_total
```

### Batch Test Checklist
1. **Start a batch with 10 OpenAI runs**
   - Should never exceed 3 concurrent
   - Launches should be ~15s apart (check logs)
   - Metrics should update in real-time

2. **Force 429 errors** (lower TPM limit locally)
   - Should see successful retries with backoff
   - `contestra_llm_rate_limit_events_total` should increment
   - After 5 attempts, should get `OPENAI_RATE_LIMIT_EXHAUSTED` error

3. **Monitor TPM window**
   - Requests should defer when approaching 25.5k tokens/minute
   - `contestra_openai_tpm_window_deferrals_total` should increment

## Production Readiness

### ✅ Completed:
- Rate limiting logic prevents 429 errors proactively
- Retry logic handles 429s gracefully when they occur
- Metrics provide full observability
- Configuration is externalized via environment variables
- 6000 token finalize pass is maintained

### ⚠️ Notes:
- Currently in-process only (single instance)
- For multi-instance deployment, would need Redis-backed coordination
- TPM estimates are conservative (7k per run default)

## Operational Guidelines

1. **Monitor key metrics**:
   - Keep `contestra_openai_active_concurrency` ≤ 3
   - Watch `contestra_llm_rate_limit_events_total` for spikes
   - Track `contestra_openai_tpm_window_deferrals_total` for capacity issues

2. **Tuning parameters**:
   - Increase `OPENAI_STAGGER_SECONDS` if still hitting 429s
   - Adjust `OPENAI_EST_TOKENS_PER_RUN` based on actual usage
   - Increase `OPENAI_TPM_HEADROOM` for more conservative limits

3. **Incident response**:
   - High 429 rate: Increase stagger to 20-30s
   - Consistent deferrals: Review token estimates
   - Timeouts: Check if requests are queuing too long

---

**Implementation Date**: August 27, 2025
**Implemented By**: Claude with guidance from ChatGPT's surgical diffs
**Status**: Production Ready (single-instance mode)