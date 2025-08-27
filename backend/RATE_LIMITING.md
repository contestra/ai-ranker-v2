# Rate Limiting Implementation

## Overview
Comprehensive rate limiting system for OpenAI API calls with multiple layers of protection to prevent 429 errors.

## Components

### 1. Batch Runner (`app/services/batch_runner.py`)
- **Concurrency Control**: Semaphore limits to 3 concurrent OpenAI requests
- **Request Stagger**: 15-second delay between request starts (with jitter)
- **TPM Tracking**: Monitors tokens per minute with sliding window
- **Configuration**: Environment variables control all parameters

### 2. OpenAI Adapter (`app/llm/adapters/openai_adapter.py`)
- **429 Retry Logic**: Exponential backoff (2→4→8→16→32 seconds)
- **Retry-After Header**: Honors server-specified retry delays
- **Jittered Backoff**: Adds randomness to prevent thundering herd
- **Max Attempts**: Configurable retry limit (default: 5)

### 3. API Preflight Guard (`app/api/routes/templates.py`)
- **Budget Check**: Rejects batches that would exceed TPM limit
- **503 Response**: Returns Service Unavailable with Retry-After header
- **Early Validation**: Prevents overload before batch execution starts

### 4. Prometheus Metrics (`app/core/prometheus_metrics.py`)
- **Concurrency Gauge**: `openai_concurrent_requests`
- **Slot Usage**: `openai_slots_in_use`
- **TPM Usage**: `openai_tpm_current`
- **Rate Limit Events**: `openai_rate_limit_hits_total`

## Configuration

Environment variables in `.env`:

```bash
# Concurrency Control
OPENAI_MAX_CONCURRENCY=3         # Max simultaneous requests
OPENAI_STAGGER_SECONDS=15        # Delay between request starts

# TPM Management
OPENAI_TPM_LIMIT=30000           # OpenAI tier limit
OPENAI_TPM_HEADROOM=0.15        # Reserve 15% headroom
OPENAI_EST_TOKENS_PER_RUN=7000  # Estimated tokens per request

# Retry Configuration  
OPENAI_RETRY_MAX_ATTEMPTS=5     # Max retry attempts on 429
OPENAI_BACKOFF_BASE_SECONDS=2   # Base backoff duration
```

## How It Works

### Request Flow
1. **API Check**: Batch endpoint validates projected TPM usage
2. **Semaphore Gate**: Limits concurrent requests to 3
3. **Stagger Delay**: Waits 15s (±jitter) between starts
4. **TPM Window**: Tracks minute-based token usage
5. **429 Handling**: Automatic retry with exponential backoff

### Protection Layers
- **Layer 1**: API rejects excessive batches (503 + Retry-After)
- **Layer 2**: Semaphore prevents concurrent overload
- **Layer 3**: Stagger spreads requests over time
- **Layer 4**: TPM tracking prevents minute-based limits
- **Layer 5**: Retry logic handles any 429s that occur

## Testing

Run comprehensive test:
```bash
python /tmp/test_rate_limit_comprehensive.py
```

Test scenarios:
1. Concurrent limit enforcement (max 3)
2. Stagger timing verification (15s gaps)
3. TPM tracking and limits
4. 429 retry with backoff
5. API preflight guard

## Monitoring

Check Prometheus metrics:
```bash
curl http://localhost:8000/metrics | grep openai
```

Key metrics:
- `openai_concurrent_requests`: Current active requests
- `openai_tpm_current`: Current TPM usage
- `openai_rate_limit_hits_total`: Count of 429 errors

## Known Issues

Current implementation has partial enforcement:
- Concurrency limiting needs stricter semaphore enforcement
- Stagger timing requires better async coordination
- TPM tracking window needs sliding implementation

## Future Improvements

1. **Sliding TPM Window**: Replace fixed minute with rolling window
2. **Dynamic Backoff**: Adjust retry based on error patterns  
3. **Predictive Throttling**: Slow down before hitting limits
4. **Multi-Model Support**: Different limits per model tier
5. **Circuit Breaker**: Temporary disable after repeated failures