# AI Ranker V2 - Complete System Documentation

## 📋 Table of Contents
1. [System Overview](#system-overview)
2. [Core Features](#core-features)
3. [Authentication](#authentication)
4. [Proxy System](#proxy-system)
5. [Health Monitoring](#health-monitoring)
6. [Testing](#testing)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)

## System Overview

**Version**: 2.7.0  
**Status**: Production Ready  
**Last Updated**: 2025-08-27

AI Ranker V2 is a prompt immutability testing platform with geographic A/B testing capabilities, supporting multiple LLM providers with advanced routing and monitoring.

### Architecture Components
- **FastAPI** backend with async support
- **Neon** PostgreSQL database
- **OpenAI** and **Vertex AI** adapters
- **Webshare.io** residential proxy integration
- **Health monitoring** endpoints
- **Rate limiting** and SLA protection

## Core Features

### 1. Geographic A/B Testing
Four vantage policies for experimental control:
- `NONE` - No ALS, no proxy
- `ALS_ONLY` - Ambient Location Signals via system messages
- `PROXY_ONLY` - Proxy routing without ALS
- `ALS_PLUS_PROXY` - Both ALS and proxy

### 2. Smart Proxy Routing
Automatic mode selection based on token count:
```python
if max_tokens > 2000:
    mode = "backbone"  # Stable IP for long responses
else:
    mode = "rotating"  # Dynamic IPs for short responses
```

### 3. Grounding Support
- **OpenAI**: Responses API with web_search tools + deterministic fallback chain
  - Provoker retry for empty responses (flag: `OPENAI_PROVOKER_ENABLED`)
  - Two-step synthesis fallback (flag: `OPENAI_GROUNDED_TWO_STEP`)
  - Strict REQUIRED mode: must have tool calls AND citations
- **Vertex**: GenAI SDK for grounded, SDK env proxy for ungrounded+proxy
- **Citations**: Normalized schema with deduplication
- Automatic fallback for empty grounded responses

### 4. Rate Limiting & SLA Protection
- **OpenAI**: Max 3 concurrent (30k TPM limit)
- **Vertex**: Max 4 concurrent
- **Stagger**: 15s between OpenAI calls
- **SLA timeout**: 480s hard limit

## Authentication

### Development (ADC)
```bash
# Clean slate
unset GOOGLE_APPLICATION_CREDENTIALS
gcloud auth application-default revoke -q || true
rm -f ~/.config/gcloud/application_default_credentials.json

# Configure
export PROJECT_ID="contestra-ai"
gcloud config set project "$PROJECT_ID"
gcloud config set ai/region europe-west4

# Authenticate
gcloud auth application-default login --no-launch-browser

# Set quota
gcloud auth application-default set-quota-project "$PROJECT_ID"

# Verify
gcloud auth application-default print-access-token | head -c 16
```

### Production (WIF)
- Uses Workload Identity Federation
- No service account keys (blocked by org policy)
- Configuration via `WIF_CREDENTIALS_JSON` env var

### Health Check
```bash
curl -s http://localhost:8000/health/auth | jq '.'
```

Expected response:
```json
{
  "status": "ok",
  "auth_mode": "ADC-User",  // or "WIF-ImpersonatedSA" in prod
  "principal": "user@domain.com",
  "seconds_remaining": 172800,
  "warn_threshold_hours": 48
}
```

## Proxy System

### Configuration
**Provider**: Webshare.io  
**Protocol**: HTTP CONNECT  
**Credentials**: Set in `.env`

### Username Format
- **Rotating**: `{username}-{country}-rotate`
- **Backbone**: `{username}-{country}-1`

### Health Check
```bash
curl -s http://localhost:8000/health/proxy | jq '.'
```

Expected response:
```json
{
  "status": "ok",
  "mode_guess": "direct",  // or "backbone"/"rotating" with proxy
  "first_ip": "77.111.26.72",
  "second_ip": "77.111.26.72",
  "match_stable": true
}
```

### Routing Decision Matrix
| Max Tokens | Proxy Mode | Timeouts | Use Case |
|------------|------------|----------|----------|
| ≤2000 | rotating | 60s/300s | Short responses |
| >2000 | backbone | 240s/300s | Long responses |
| 6000 | backbone | 240s/300s | Standard production |

## Health Monitoring

### Endpoints

#### `/health/auth` - Authentication Monitoring
- Reports authentication mode (WIF vs ADC vs SA)
- Shows token expiry and warns if <24h remaining
- Returns principal, project, quota project
- Status: ok/warn/error based on expiry threshold

#### `/health/proxy` - Proxy Connectivity
- Detects proxy mode: direct, backbone, rotating, or unknown
- Hits IP services twice to detect rotation
- Cross-checks with secondary service for validation
- Returns RTT metrics and stability assessment

#### `/health/llm` - End-to-End Validation
- Executes real LLM call (~50 tokens) to verify routing
- Validates vantage policy (NONE/ALS_ONLY/PROXY_ONLY/ALS_PLUS_PROXY)
- Returns same metadata as [LLM_ROUTE] logs
- Tracks usage, duration, and grounding effectiveness

### Alert Conditions

#### Critical (Page)
```yaml
- condition: health_auth_status == "error"
  action: page
  message: "Authentication failed"

- condition: health_proxy_failures > 3 in 10min
  action: page  
  message: "Proxy connectivity issues"
```

#### Warning
```yaml
- condition: health_auth_seconds_remaining < 14400  # 4h
  action: warn
  message: "Auth expiring soon"

- condition: health_proxy_mode == "rotating" AND tokens == 6000
  action: warn
  message: "Wrong proxy mode for long response"
```

### Dashboard Metrics
- **Auth**: status, mode, principal, seconds_remaining
- **Proxy**: mode_guess, RTT p95, error_count
- **LLM Health**: vendor, duration_ms, vantage_policy, usage
- **LLM Logs**: [LLM_ROUTE], [LLM_RESULT], [LLM_TIMEOUT]

## Testing

### Quick Test Scripts

#### Test Longevity Prompt (Geographic)
```python
# /tmp/test_all_scenarios_rate_limited.py
# Tests all combinations with rate limiting:
# - US/DE × ALS/ALS+Proxy × grounded/ungrounded
# - 6000 tokens always
# - 3 concurrent OpenAI, 4 concurrent Vertex
```

#### Test Auth
```bash
curl -s http://localhost:8000/health/auth | jq '.status'
```

#### Test Proxy
```bash
curl -s http://localhost:8000/health/proxy | jq '.mode_guess'
```

### Full Test Matrix
| Vendor | Country | Policy | Grounded | Expected Result |
|--------|---------|--------|----------|-----------------|
| OpenAI | US | ALS_ONLY | No | US brands |
| OpenAI | US | ALS_PLUS_PROXY | Yes | US brands + sources |
| OpenAI | DE | ALS_ONLY | No | EU brands |
| OpenAI | DE | ALS_PLUS_PROXY | Yes | EU brands + sources |
| Vertex | US | ALS_ONLY | No | US brands |
| Vertex | US | PROXY_ONLY | No | US IP brands |
| Vertex | DE | ALS_ONLY | Yes | EU brands + sources |

## Configuration

### Environment Variables (.env)
```bash
# Models (ONLY these)
OPENAI_MODEL=gpt-5
VERTEX_MODEL=gemini-2.5-pro

# Tokens (ALWAYS)
MAX_TOKENS=6000

# Google Cloud
GOOGLE_CLOUD_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4
GOOGLE_GENAI_USE_VERTEXAI=true

# Proxy (Webshare.io)
WEBSHARE_PROXY_HOST=proxy.webshare.io
WEBSHARE_PROXY_PORT=80
WEBSHARE_USERNAME=iuneqpvp
WEBSHARE_PASSWORD=kxn8btgwq1ai

# Health Monitoring
AUTH_EXPIRY_WARN_HOURS=48

# Rate Limits
OPENAI_MAX_CONCURRENCY=3
VERTEX_MAX_CONCURRENCY=4
STAGGER_DELAY_SECONDS=15
SLA_TIMEOUT_SECONDS=480

# OpenAI Grounding Features
OPENAI_PROVOKER_ENABLED=true          # Enable provoker retry
OPENAI_GROUNDED_TWO_STEP=false        # Enable two-step synthesis (set true in prod)
OPENAI_GROUNDED_MAX_EVIDENCE=5        # Max citations in evidence list
OPENAI_GROUNDED_MAX_TOKENS=6000       # Max tokens for grounded requests
```

### Critical Constants (Never Change)
```python
MAX_TOKENS = 6000  # Always
FINALIZE_MAX_TOKENS = 6000  # Same as original
OPENAI_MODEL = "gpt-5"  # Only
VERTEX_MODEL = "gemini-2.5-pro"  # Only
```

## Troubleshooting

### Common Issues

#### Empty OpenAI Grounded Responses
- **Cause**: Responses API returns tool calls but no final synthesis
- **Fix**: Three-stage fallback chain:
  1. Initial request with web_search tools
  2. Provoker retry (adds synthesis prompt)
  3. Two-step fallback (synthesis without tools using evidence list)
- **Enable in Production**: `export OPENAI_GROUNDED_TWO_STEP=true`
- **Telemetry**: Check `provoker_retry_used` and `synthesis_step_used` in metadata

#### Vertex Auth Failures
- **Error**: "Reauthentication is needed"
- **Fix**: Run ADC login steps (see Authentication section)

#### Rate Limit 429 Errors
- **Cause**: Exceeding 30k TPM for OpenAI
- **Fix**: Automatic retry with backoff, max 3 concurrent

#### Proxy Timeout on Long Responses
- **Cause**: Default 60s timeout too short for 6000 tokens
- **Fix**: Automatically uses 240s for backbone mode

#### Wrong Proxy Mode
- **Symptom**: IP changes mid-response
- **Fix**: Automatic backbone for >2000 tokens

### Debug Commands

```bash
# Check backend logs
tail -f backend.log | grep -E "ERROR|WARNING"

# Monitor LLM routing
tail -f backend.log | grep "\[LLM_ROUTE\]"

# Watch for timeouts
tail -f backend.log | grep "\[LLM_TIMEOUT\]"

# Check proxy environment
env | grep -E "PROXY|WEBSHARE"
```

## File Structure

```
backend/
├── app/
│   ├── llm/
│   │   ├── adapters/
│   │   │   ├── openai_adapter.py       # Proxy, grounding, synthesis
│   │   │   ├── vertex_adapter.py       # Dual path implementation
│   │   │   └── grounding_detection_helpers.py
│   │   └── types.py                    # VantagePolicy enum
│   ├── services/
│   │   └── proxy_service.py            # Webshare integration
│   └── routers/
│       ├── health_auth_endpoint.py     # Auth monitoring
│       ├── health_proxy_endpoint.py    # Proxy monitoring
│       └── health_llm_endpoint.py      # LLM end-to-end check
├── Documentation/
│   ├── SYSTEM_DOCUMENTATION.md         # This file
│   ├── ADAPTER_OPS_PLAYBOOK.md        # Operational guide
│   ├── HEALTH_MONITORING_SETUP.md     # Monitoring setup
│   ├── VERTEX_AUTH_SETUP.md           # Auth documentation
│   ├── PROXY_IMPLEMENTATION_PLAN.md   # Proxy details
│   └── IMPORTANT_MODELS.md            # Model constraints
└── Tests/
    ├── test_all_scenarios_6000.py
    └── test_all_scenarios_rate_limited.py
```

## API Endpoints

### Core Operations
- `POST /v1/templates` - Create template
- `POST /v1/templates/{id}/run` - Run template
- `POST /v1/templates/{id}/batch-run` - Batch execution

### Health & Monitoring
- `GET /health/auth` - Auth status
- `GET /health/proxy` - Proxy status  
- `GET /health/llm` - End-to-end LLM validation
- `GET /ops/openai-preflight` - OpenAI connectivity
- `GET /ops/vertex-preflight` - Vertex connectivity

### Preflight Checks
- `GET /preflight/vertex` - Vertex credentials info

## Performance Metrics

### Typical Response Times
- **OpenAI Direct**: 84-162s (6000 tokens)
- **OpenAI Proxy**: 51-123s (6000 tokens)
- **Vertex Direct**: 40-48s (US), 118-877s (DE)
- **Vertex Proxy**: 41-42s (US)

### Rate Limits
- **OpenAI**: 30k TPM (≈4 concurrent @ 6000 tokens)
- **Vertex**: No hard limit, 4 concurrent recommended

## Security Notes

- Never log proxy credentials (use masked URIs)
- ADC tokens not exposed in health checks
- WIF credentials stored as runtime secrets only
- All secrets in `.env` (gitignored)

## Support & References

- **Auth Issues**: See `VERTEX_AUTH_SETUP.md`
- **Proxy Config**: See `ADAPTER_OPS_PLAYBOOK.md`
- **Monitoring**: See `HEALTH_MONITORING_SETUP.md`
- **Rate Limits**: See `IMPORTANT_MODELS.md`

---
**Version**: 2.7.0  
**Status**: Production Ready  
**Updated**: 2025-08-27