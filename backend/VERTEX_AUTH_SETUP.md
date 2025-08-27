# Vertex AI Authentication Setup - Complete Guide

## ✅ Current Status: WORKING with ADC

The Vertex AI integration is **fully operational** using Application Default Credentials (ADC) for local development and Workload Identity Federation (WIF) for production.

## Authentication Methods

### Local Development: ADC (Application Default Credentials)
- **Status**: ✅ Working
- **Method**: User account authentication via `gcloud auth application-default login`
- **User**: l@contestra.com (Owner role)
- **Note**: Service Account keys are blocked by organization policy `constraints/iam.disableServiceAccountKeyCreation`

### Production: WIF (Workload Identity Federation)
- **Status**: Ready for deployment
- **Method**: External account credentials via WIF
- **Configuration**: Set via `WIF_CREDENTIALS_JSON` environment variable

## Setup Instructions

### Local Development Setup (ADC)

#### 1. Clean Slate
```bash
unset GOOGLE_APPLICATION_CREDENTIALS
gcloud auth application-default revoke -q || true
rm -f ~/.config/gcloud/application_default_credentials.json

export PROJECT_ID="contestra-ai"
gcloud config set project "$PROJECT_ID"
gcloud config set ai/region europe-west4 || true
```

#### 2. Authenticate with ADC
```bash
gcloud auth application-default login --no-launch-browser
# Open the URL in browser, sign in, paste verification code back
```

#### 3. Set Quota Project
```bash
gcloud auth application-default set-quota-project "$PROJECT_ID"
```

#### 4. Verify Setup
```bash
# Check ADC file exists
test -f ~/.config/gcloud/application_default_credentials.json && echo "ADC file OK"

# Test access token
gcloud auth application-default print-access-token | head -c 16 && echo "...token works"
```

#### 5. Environment Configuration
The `.env.local` file is configured for ADC:
```env
# ADC mode: do NOT set GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_CLOUD_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4
ENFORCE_VERTEX_WIF=false
```

### Production Setup (Fly.io with WIF)

#### 1. Set WIF Credentials
```bash
fly secrets set WIF_CREDENTIALS_JSON="$(cat /path/to/external_account.json)"
```

#### 2. Deploy with Production Config
The `.env.production` file:
```env
GOOGLE_APPLICATION_CREDENTIALS=/etc/gcloud/wif-credentials.json
GOOGLE_CLOUD_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4
ENFORCE_VERTEX_WIF=true
```

#### 3. Runtime WIF Materialization
The `entrypoint.sh` script automatically:
- Writes WIF credentials to `/etc/gcloud/wif-credentials.json`
- Sets proper file permissions (0640)
- Starts the application

## Verification Endpoints

### Health Endpoints
`/health/auth` returns auth mode (WIF-ImpersonatedSA / ADC-User / etc.), principal, project/quota, and token expiry (>24h warn). `/health/proxy` labels egress as direct/backbone/rotating and shows masked proxy env + RTTs.

### Preflight Check
```bash
curl http://localhost:8000/preflight/vertex
```

**Expected Response (ADC)**:
```json
{
  "ready": true,
  "credential_type": "Credentials",
  "principal": null,
  "project": "contestra-ai",
  "quota_project": "contestra-ai"
}
```

**Expected Response (WIF)**:
```json
{
  "ready": true,
  "credential_type": "ExternalAccountCredentials",
  "principal": "service-account@project.iam.gserviceaccount.com",
  "project": "contestra-ai",
  "quota_project": "contestra-ai"
}
```

### Direct Vertex API Test
```bash
TOKEN="$(gcloud auth application-default print-access-token)"
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://europe-west4-aiplatform.googleapis.com/v1/projects/contestra-ai/locations/europe-west4/publishers/google/models/gemini-2.5-pro:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Say PING"}]}]}'
```

## Key Implementation Details

### Model Normalization
The adapter includes `_normalize_model_id()` to handle various model formats:
- Strips `publishers/google/models/` prefix
- Accepts short form (e.g., `gemini-2.5-pro`)
- Handles full resource paths

### Robust Text Extraction
`_extract_vertex_text()` handles:
- SDK convenience `.text` attribute
- Standard `candidates[0].content.parts[*].text` structure
- Proto/dict fallbacks for different SDK versions

### Usage Metadata Extraction
`_extract_vertex_usage()` supports:
- Current SDK object attributes
- Dict-like metadata
- Proto message conversion
- Legacy `tokenMetadata` format

### Finish Info & Safety
`_extract_finish_info()` provides:
- Finish reasons (STOP, MAX_TOKENS, SAFETY, etc.)
- Safety block detection
- Block reason details

## Important Notes

### Proxy Routing (2025-08-27)
Vertex grounded runs use GenAI **without** client proxy (server-side search; use ALS for geography). If a proxy is required for Vertex ungrounded, the **SDK path** uses a **per-run env proxy** with backbone IPs (`VERTEX_PROXY_VIA_SDK=true`). Keep `NO_PROXY=metadata.google.internal,169.254.169.254,localhost,127.0.0.1`. OpenAI can use proxies directly; backbone for >2k tokens, streaming on.

### Gemini 2.5 Pro Characteristics
- **Uses "thinking tokens"**: ~375-400 tokens for internal reasoning
- **Recommended `max_tokens`**: 
  - Simple prompts: 500+
  - Complex prompts: 1000+
- **Latency**: 3-5 seconds typical with thinking

### Organization Constraints
- **Service Account Key Creation**: Blocked by policy
- **Solution**: Use ADC for local development
- **Alternative**: Request policy exception from org admin

## Operational Limits & Concurrency

OpenAI concurrency **3** (stagger 15s; 429 backoff); Vertex direct **4**; Vertex SDK+env-proxy **1** (singleflight). SLA caps: Vertex direct **480s**, proxied **300s**.

### Rate Limits
- **OpenAI**: 30k TPM, max 3 concurrent, 15s stagger between starts
- **Vertex**: 4 concurrent direct, 1 for SDK+proxy mode
- **Timeouts**: Read 240s, Total 300s (OpenAI); 480s direct, 300s proxied (Vertex)

## Troubleshooting

### Empty Output
- **Cause**: Insufficient `max_tokens` (thinking tokens consume budget)
- **Solution**: Increase to 500+ tokens minimum

### Empty Output (Grounded)
Trigger a **Finalize Pass** (no tools/web) with **`max_tokens = original` (6000)** and streaming; add `finalize_pass=true`, `finalize_reason`, `finalize_attempts=1` to metadata.

### 404 Errors
- **Cause**: Wrong model format or region
- **Solution**: Use short model ID (e.g., `gemini-2.5-pro`)

### Authentication Errors
- **ADC Not Set**: Run `gcloud auth application-default login`
- **Quota Issues**: Run `gcloud auth application-default set-quota-project`
- **WIF Issues**: Check `WIF_CREDENTIALS_JSON` secret in production

### MAX_TOKENS Error
- **Symptom**: "Response candidate content has no parts"
- **Cause**: Model hit token limit during thinking
- **Solution**: Increase `max_tokens` significantly (1000+)

## Security Best Practices

1. **Never commit credentials**:
   - `.env.local` is in `.gitignore`
   - SA keys directory excluded
   - WIF credentials as runtime secret only

2. **Environment separation**:
   - Local: ADC with user account
   - Production: WIF only, no keys

3. **Credential validation**:
   - `ENFORCE_VERTEX_WIF=true` in production
   - Preflight checks credential type
   - Fail-closed on wrong credential type

## Files Structure

```
backend/
├── app/
│   ├── google_creds.py        # Credential detection & validation
│   ├── deps_vertex.py         # Vertex initialization
│   ├── routers/
│   │   └── preflight.py       # Preflight endpoint
│   └── llm/
│       └── adapters/
│           └── vertex_adapter.py  # Vertex implementation with helpers
├── .env.local                  # Local ADC configuration
├── .env.production            # Production WIF configuration
├── entrypoint.sh              # Runtime WIF materialization
└── VERTEX_AUTH_SETUP.md       # This documentation
```

## Testing

### Run Smoke Tests
```bash
# Test preflight
bash scripts/smoke_vertex.sh

# Create and run test template
curl -X POST "http://localhost:8000/v1/templates" \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: test-org" \
  -d '{
    "template_name": "vertex-test",
    "canonical": {
      "provider": "vertex",
      "model": "gemini-2.5-pro",
      "messages": [{"role": "user", "content": "Say PING"}],
      "temperature": 0.1,
      "max_tokens": 1000
    }
  }'
```

## Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| ADC Authentication | ✅ Working | Using l@contestra.com |
| WIF Setup | ✅ Ready | Configured for production |
| Model Routing | ✅ Working | Proper normalization |
| Text Extraction | ✅ Working | Robust helper functions |
| Usage Tracking | ✅ Working | Handles all SDK versions |
| Error Handling | ✅ Working | Safety & finish detection |
| Preflight Endpoint | ✅ Working | Shows credential info |
| Smoke Tests | ✅ Passing | Both OpenAI and Vertex |
| Proxy Strategy | ✅ Working | Vertex via SDK env-proxy; GenAI direct |
| Rate-limits/SLA | ✅ Configured | OpenAI 3 concurrent, Vertex 4 direct/1 proxied |
| Health Monitoring | ✅ Active | Auth, proxy, and LLM health endpoints |

Last Updated: 2025-08-27
Status: **Production Ready**