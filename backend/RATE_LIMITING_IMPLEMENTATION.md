# Rate Limiting Implementation Summary

## Status: ✅ FULLY UPDATED (August 28, 2025)

ChatGPT's enhanced token-based rate limiting has been fully implemented with sliding window, debt tracking, and proper concurrency control.

## What Was Added

### 1. Configuration (Environment Variables)
```bash
OPENAI_MAX_CONCURRENCY=1        # Set to 1 for sequential execution
OPENAI_STAGGER_SECONDS=15       # Deprecated - using token-based control
OPENAI_TPM_LIMIT=30000          # 30,000 tokens per minute limit
OPENAI_TPM_HEADROOM=0.15        # 15% reserved headroom
OPENAI_EST_TOKENS_PER_RUN=7000  # Default estimate (now dynamic)
OPENAI_RETRY_MAX_ATTEMPTS=5     # Max retry attempts on 429
OPENAI_BACKOFF_BASE_SECONDS=2   # Base for exponential backoff
OPENAI_GATE_IN_ADAPTER=true     # Enable adapter-level rate limiting
OPENAI_GATE_IN_BATCH=false      # Disable batch-level (legacy)
```

### 2. Core Features Implemented (ENHANCED)

#### A. Token-Based Rate Limiting (`openai_adapter.py` - `_OpenAIRateLimiter`)
- **Sliding Window**: 60-second window tracking actual token usage
- **Dynamic Estimation**: Per-request calculation based on input + output tokens
- **Debt Tracking**: Accumulates underestimation for next window
- **Smart Sleep**: Calculates exact sleep time to next window

#### B. Token Estimation (Pre-call)
- **Input Tokens**: `char_count / 4 + 100` (buffer for structure)
- **Output Tokens**: From `request.max_tokens` (6000 for tests)
- **Safety Margin**: 20% overhead on total estimate
- **Grounded Overhead**: Additional 15% for search/reasoning

#### C. Debt Management (Post-call)
- **Actual Usage**: Extracted from `response.usage.total_tokens`
- **Debt Calculation**: `max(0, actual - estimated)`
- **Carry Forward**: Debt added to next window's initial usage
- **429 Penalty**: 1000 token debt added on rate limit errors

#### D. Enhanced 429 Handling (`openai_adapter.py`)
- **Integrated with Rate Limiter**: Uses `_RL.handle_429(retry_after)`
- **Smart Backoff**: Honors `Retry-After` header if present
- **Exponential with Jitter**: `min(30, 2^n) + random(-1, 1)` seconds
- **Debt Penalty**: Adds 1000 tokens to debt on 429
- **Structured Errors**: Returns `OPENAI_RATE_LIMIT_EXHAUSTED` after max attempts

### 3. Telemetry & Monitoring

#### New Prometheus Metrics:
- `contestra_openai_active_concurrency` - Current in-flight requests
- `contestra_openai_next_slot_epoch` - Next launch slot timestamp
- `contestra_openai_stagger_delays_total` - Count of stagger delays
- `contestra_openai_tpm_window_deferrals_total` - TPM budget deferrals
- `contestra_llm_rate_limit_events_total` - 429 events by vendor

### 4. Files Modified (Latest Updates)
- `app/core/config.py` - Added token-based rate limiting configuration
- `app/prometheus_metrics.py` - Added metrics for monitoring
- `app/services/batch_runner.py` - Batch-level gating (now disabled by default)
- `app/llm/adapters/openai_adapter.py` - **MAJOR UPDATE**: Complete rewrite of `_OpenAIRateLimiter` class
  - New sliding window implementation
  - Dynamic token estimation per request
  - Debt tracking and management
  - Integrated 429 handling
- `app/api/routes/templates.py` - Preflight TPM guard for batch endpoint
- `.env` - Updated configuration variables

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

## Latest Updates (August 28, 2025)

### Key Improvements from ChatGPT's Final Guidance:

1. **Token-Based Rate Limiting**: Complete rewrite to track actual tokens, not request count
2. **Dynamic Token Estimation**: Per-request calculation with safety margins
3. **Sliding Window**: Proper 60-second window with debt carry-over
4. **Smart 429 Handling**: Integrated with rate limiter, proper backoff
5. **Proxy Preflight Checks**: 3-second HEAD requests to prevent hangs
6. **Token Usage Logging**: All successful calls now log full usage metrics

### Test Matrix Configuration:
- **32 Tests Total**: 12 scenarios × 2 models (OpenAI GPT-5, Vertex Gemini 2.5 Pro)
- **Max Tokens**: 6000 for ALL tests (do not reduce)
- **Execution**: Sequential (OPENAI_MAX_CONCURRENCY=1)
- **Vantage Policies**: NONE, ALS_ONLY, PROXY_ONLY, ALS_PLUS_PROXY
- **Grounding**: Both grounded and ungrounded variants

### Known Issues Resolved:
- ✅ 429 errors despite rate limiting - Fixed with token-based tracking
- ✅ Proxy timeouts - Fixed with preflight checks and HTTP/1.1
- ✅ FunctionTool warnings - Clean tool arrays for OpenAI
- ✅ Empty responses - Proper extraction paths and error classification

**Initial Implementation**: August 27, 2025
**Major Update**: August 28, 2025
**Implemented By**: Claude with guidance from ChatGPT
**Status**: Production Ready with Token-Based Rate Limiting