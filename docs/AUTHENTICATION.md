# AI Ranker V2 - Authentication Configuration

## Overview

AI Ranker V2 uses different authentication methods for local development vs production deployment:

- **Local Development**: Google Cloud ADC (Application Default Credentials)
- **Production (Fly.io)**: Workload Identity Federation (WIF) with Fly.io OIDC

## Production WIF Setup (Complete)

### Current Production Configuration
- ✅ **Service Account**: `vertex-runner@contestra-ai.iam.gserviceaccount.com`
- ✅ **Workload Identity Pool**: `flyio-pool`
- ✅ **Project**: `contestra-ai` (857244965511)
- ✅ **Region**: `europe-west4`
- ✅ **Fly.io OIDC Provider**: Configured with `/.fly/api` endpoint

### WIF Configuration Files
The WIF configuration is stored in:
```
backend/config/external_account.json
```

This file contains the complete Workload Identity Federation setup that allows Fly.io deployments to authenticate with Google Cloud using OIDC tokens.

## Auth Strategy

- **Local development:** **ADC** (Application Default Credentials)
  - `gcloud auth application-default login`
  - `.env`: `GOOGLE_CLOUD_PROJECT=contestra-ai`, `GOOGLE_CLOUD_REGION=europe-west4`, `ENFORCE_VERTEX_WIF=false`
  - Do **not** set `GOOGLE_APPLICATION_CREDENTIALS` locally (forces ADC).

- **Production (Fly.io):** **WIF** (external_account)
  - Store `external_account.json` as a Fly secret (base64).
  - At boot, write to `/app/config/gcp_external_account.json` and set `GOOGLE_APPLICATION_CREDENTIALS` to that path.
  - `.env`: `ENFORCE_VERTEX_WIF=true` (app will verify the JSON is `type: external_account`).

- **No silent fallbacks:**
  - If `vendor="vertex"` and credentials are missing/invalid, return an explicit 401/403/500.
  - Never route to OpenAI due to auth exceptions.

## Local Development Setup

### Setting Up ADC Locally

1. **Authenticate with Google Cloud**:
   ```bash
   gcloud auth application-default login
   gcloud config set project contestra-ai
   ```

2. **Verify Authentication**:
   ```bash
   gcloud auth list
   # Should show your account as active
   ```

3. **Environment Variables for Local Development**:
   ```bash
   # Add to backend/.env
   GOOGLE_CLOUD_PROJECT=contestra-ai
   GOOGLE_CLOUD_REGION=europe-west4
   ENFORCE_VERTEX_WIF=false  # Use ADC locally instead of WIF
   ```

### Testing Vertex AI Locally

After setting up ADC, test Vertex AI integration:

```bash
# Test Vertex preflight
curl -sS http://localhost:8000/ops/vertex-preflight | python3 -m json.tool

# Test Vertex template run
curl -X POST "http://localhost:8000/v1/templates/{vertex-template-id}/run" \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: test-org" \
  -d '{"max_tokens": 128}'
```

## Production Deployment

### Environment Variables for Production
```bash
GOOGLE_CLOUD_PROJECT=contestra-ai
GOOGLE_CLOUD_REGION=europe-west4
ENFORCE_VERTEX_WIF=true  # Use WIF in production
GOOGLE_APPLICATION_CREDENTIALS=/app/config/external_account.json
```

### WIF Configuration Copy
For V2 production deployment, copy the existing WIF config:
```bash
cp /path/to/existing/external_account.json ~/ai-ranker-v2/backend/config/
```

## Service Account Permissions

The `vertex-runner@contestra-ai.iam.gserviceaccount.com` service account has the following roles:
- **Vertex AI User**: For accessing Gemini models
- **AI Platform User**: For model inference
- **Project Viewer**: For basic project access

## Troubleshooting

### Common Local Issues
1. **"Default credentials not found"**:
   ```bash
   gcloud auth application-default login
   ```

2. **Wrong project selected**:
   ```bash
   gcloud config set project contestra-ai
   ```

3. **Insufficient permissions**:
   - Verify your Google account has access to the `contestra-ai` project
   - Contact admin for project access if needed

### Common Production Issues
1. **WIF token expired**:
   - Fly.io handles token refresh automatically
   - Check Fly.io deployment logs for authentication errors

2. **Missing external_account.json**:
   - Ensure the WIF config file is deployed with the application
   - Verify the `GOOGLE_APPLICATION_CREDENTIALS` path is correct

## Security Notes

- **Never commit** `external_account.json` or ADC credentials to version control
- **Use environment variables** for all authentication configuration
- **Rotate service account keys** if any are compromised
- **Monitor access logs** for unusual Vertex AI usage patterns

## Testing Authentication

### Local Development Test
```bash
# Should return ready: true
curl -sS http://localhost:8000/ops/vertex-preflight

# Should route to Vertex (not OpenAI)
curl -X POST http://localhost:8000/v1/templates/{vertex-template}/run \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: test-org" \
  -d '{}'
```

### Production Test
Same commands as local, but should work with WIF authentication automatically.

## Migration Notes

When deploying V2 to production:
1. Copy existing WIF configuration from V1
2. Update environment variables for V2 structure
3. Test both OpenAI and Vertex routing
4. Verify telemetry shows correct vendor attribution

---

**Last Updated**: August 2025  
**Status**: ADC setup for local development, WIF ready for production