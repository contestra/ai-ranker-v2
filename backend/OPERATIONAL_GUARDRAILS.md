# Operational Guardrails - AI Ranker V2

## Critical Production Settings

### 1. Finalize Pass Configuration
- **Token Count**: ALWAYS 6000 tokens (6k)
- **Streaming**: ALWAYS enabled
- **When Applied**: Especially critical when grounded runs return tool-only outputs
- **Rationale**: Ensures consistent output quality and prevents truncation

### 2. Rate Limiting & Concurrency

#### OpenAI (gpt-5)
- **Max Concurrency**: 3 requests maximum
- **Request Stagger**: 15 seconds minimum between requests
- **Token Limit**: 30,000 TPM (tokens per minute)
- **Implementation**:
  ```python
  OPENAI_DELAY = 15  # seconds
  MAX_CONCURRENT_OPENAI = 3
  ```
- **429 Error Handling**: Implement exponential backoff starting at 15s

#### Vertex (gemini-2.5-pro)
- **Max Concurrency**: 4 requests (as per documentation)
- **Request Stagger**: 5 seconds recommended
- **No hard TPM limit** but respect concurrency limits

### 3. Authentication Configuration

#### Development Environment (WSL/Local)
- **Method**: ADC (Application Default Credentials)
- **Setup Command**:
  ```bash
  gcloud auth application-default login
  ```
- **Verification**:
  - Check `/health/auth` endpoint
  - Should transition: `error` → `ok` or `warn`
  - Expected mode: "ADC-UserCredentials"
- **Token Refresh**: Automatic via gcloud SDK

#### Production Environment
- **Method**: WIF (Workload Identity Federation)
- **Configuration**: Via environment variables
- **Health Check**: `/health/auth` should show:
  - Mode: "WIF-ImpersonatedSA" or "WIF-ExternalAccount"
  - Status: "healthy"
- **DO NOT**: Use service account keys in production

### 4. Model-Specific Settings

#### OpenAI gpt-5
- **Temperature**: Force-set to 1.0 (cannot be overridden)
- **Text Verbosity**: "medium" (via special parameters)
- **Max Tokens**: 6000 standard
- **Grounding**: Supported but limited tool calls

#### Vertex gemini-2.5-pro
- **Temperature**: 0.3 recommended
- **Min Tokens**: 500+ (accounts for thinking tokens)
- **Max Tokens**: 6000 standard
- **Grounding**: Full support with multiple tool calls

### 5. ALS (Ambient Location System) Rules
- **NEVER modify** `ALS_SYSTEM_PROMPT` - it's mission-critical
- **Message Order**: System → ALS block → User prompt (strict)
- **ALS Block Role**: Always "user" message, never "system"
- **Character Limit**: 350 characters maximum for ALS block

### 6. Proxy Configuration

#### Proxy Modes
- **direct**: Default, no proxy
- **backbone**: Stable IP for >2000 token responses
- **rotating**: Dynamic IPs for geographic diversity

#### When to Use Proxy
- `VantagePolicy.PROXY_ONLY`: Proxy without ALS
- `VantagePolicy.ALS_PLUS_PROXY`: Both proxy and ALS
- **Country Code Required**: When using proxy modes

### 7. Health Monitoring Endpoints

#### Critical Health Checks
1. `/health/auth` - Authentication status
2. `/health/proxy` - Proxy connectivity
3. `/health/llm` - LLM adapter status

#### Expected States
- **Healthy**: All green, ready for production
- **Warning**: Functional but needs attention (e.g., token expiry <1hr)
- **Error**: Non-functional, immediate action required

### 8. Error Handling Priorities

1. **Auth Errors**: Surface immediately, no silent fallbacks
2. **Rate Limits**: Implement backoff, queue requests
3. **Timeouts**: 
   - Ungrounded: 60s
   - Grounded: 120s (up to 240s for complex)
4. **Vendor Errors**: Log full context, return structured error

### 9. Telemetry & Monitoring

#### Required Metrics
- Request latency (p50, p95, p99)
- Token usage per vendor
- Error rates by type
- Geographic hit rates (for ALS/proxy)
- Auth token expiry time

#### Prometheus Metrics
- `contestra_llm_request_duration_seconds`
- `contestra_llm_tokens_used_total`
- `contestra_auth_token_seconds_remaining`
- `contestra_llm_errors_total`

### 10. Deployment Checklist

#### Before Production
- [ ] Verify WIF authentication configured
- [ ] Set rate limiting parameters
- [ ] Configure Prometheus exporters
- [ ] Test all health endpoints
- [ ] Verify 6k finalize pass setting
- [ ] Test geographic differentiation
- [ ] Confirm proxy routing works

#### During Operation
- Monitor 429 error rates
- Track token usage vs limits
- Watch auth token expiry
- Check geographic accuracy
- Review grounding effectiveness

### 11. Emergency Procedures

#### High 429 Rate
1. Reduce concurrency to 2
2. Increase stagger to 20-30s
3. Implement request queue
4. Consider backup vendor

#### Auth Failure
1. Check `/health/auth` endpoint
2. Verify environment variables
3. For dev: Re-run `gcloud auth application-default login`
4. For prod: Check WIF configuration

#### Proxy Issues
1. Test with `VantagePolicy.ALS_ONLY` (no proxy)
2. Check proxy service status
3. Verify country codes
4. Fall back to direct mode if critical

---

## Quick Reference

### Environment Variables
```bash
# Timeouts
LLM_TIMEOUT_UN=60
LLM_TIMEOUT_GR=120

# OpenAI
OPENAI_API_KEY=sk-...

# Vertex (Production)
GOOGLE_CLOUD_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4

# Development only
unset GOOGLE_APPLICATION_CREDENTIALS  # Use ADC instead
```

### Common Commands
```bash
# Check auth (development)
gcloud auth application-default login
curl http://localhost:8000/health/auth

# Monitor rates
curl http://localhost:8000/metrics | grep contestra_llm

# Test geographic differentiation
./scripts/smoke_openai.sh
./scripts/smoke_vertex.sh
```

---

*Last Updated: August 27, 2025*
*Version: 2.0 - Post-grounding implementation*