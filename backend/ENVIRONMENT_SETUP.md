# Environment Configuration Guide

## CRITICAL: Environment Separation

This application uses **different authentication methods** for local development and production:

- **Local Development**: Application Default Credentials (ADC) via user account
- **Production (Fly.io)**: Workload Identity Federation (WIF) - secure, no keys

## Local Development Setup with ADC

### ✅ Current Status: WORKING
- **Method**: Application Default Credentials (ADC) 
- **User**: l@contestra.com (Owner role)
- **Note**: Service Account keys are blocked by organization policy

### 1. Clean Slate Setup
```bash
# Remove any old credentials
unset GOOGLE_APPLICATION_CREDENTIALS
gcloud auth application-default revoke -q || true
rm -f ~/.config/gcloud/application_default_credentials.json

# Set project
export PROJECT_ID="contestra-ai"
gcloud config set project "$PROJECT_ID"
gcloud config set ai/region europe-west4 || true
```

### 2. Authenticate with ADC
```bash
# Run this interactively in terminal (not via script)
gcloud auth application-default login --no-launch-browser

# Follow the prompts:
# 1. Copy the URL to browser
# 2. Sign in with l@contestra.com
# 3. Paste verification code back
```

### 3. Set Quota Project
```bash
gcloud auth application-default set-quota-project "$PROJECT_ID"
```

### 4. Verify Setup
```bash
# Check ADC file exists
test -f ~/.config/gcloud/application_default_credentials.json && echo "ADC file OK"

# Test access token
gcloud auth application-default print-access-token | head -c 16 && echo "...token works"
```

### 5. Environment Configuration
The `.env.local` file is configured for ADC:
```env
# ADC mode: do NOT set GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_CLOUD_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4
ENFORCE_VERTEX_WIF=false
```

### 6. Start Backend
```bash
cd backend
cp .env.local .env  # Use local configuration
./start_backend.sh
```

## Production Setup (Fly.io with WIF)

### 1. Use `.env.production` for Deployment
```env
GOOGLE_APPLICATION_CREDENTIALS=/etc/gcloud/wif-credentials.json
GOOGLE_CLOUD_PROJECT=contestra-ai  
VERTEX_LOCATION=europe-west4
ENFORCE_VERTEX_WIF=true
```

### 2. Set WIF Credentials
```bash
# Set the WIF credentials as Fly.io secret
fly secrets set WIF_CREDENTIALS_JSON="$(cat /path/to/external_account.json)"
```

### 3. Deploy with Production Config
```bash
# Set other secrets in Fly.io (one-time)
fly secrets set OPENAI_API_KEY=sk-proj-xxx
fly secrets set DATABASE_URL=postgresql://...
fly secrets set SECRET_KEY=your-secret-key

# Deploy (uses .env.production and entrypoint.sh)
fly deploy
```

The `entrypoint.sh` script automatically materializes WIF credentials at runtime.

## Security Rules

### NEVER DO THIS:
- ❌ Don't commit `.env.local` 
- ❌ Don't commit any credential files
- ❌ Don't use Service Account keys (blocked by org policy)
- ❌ Don't set `GOOGLE_APPLICATION_CREDENTIALS` in local ADC mode
- ❌ Don't use ADC in production

### ALWAYS DO THIS:
- ✅ Use ADC for local development
- ✅ Use WIF for production (Fly.io)
- ✅ Set `ENFORCE_VERTEX_WIF=true` in production
- ✅ Use Fly.io secrets for sensitive values
- ✅ Verify `.gitignore` includes all credential patterns

## How the Code Handles Both Modes

The Vertex adapter enforces credential policies:

```python
# In vertex_adapter.py
def _enforce_credential_policy(self):
    if os.getenv("ENFORCE_VERTEX_WIF", "false").lower() == "true":
        # Production mode: Require WIF (external_account)
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not cred_path:
            raise RuntimeError("ENFORCE_VERTEX_WIF=true but GOOGLE_APPLICATION_CREDENTIALS not set")
        with open(cred_path) as f:
            cfg = json.load(f)
        if cfg.get("type") != "external_account":
            raise RuntimeError("ENFORCE_VERTEX_WIF=true expects 'external_account' credentials")
    # Else: Local mode - uses ADC via google.auth.default()
```

## Verification Endpoints

### Preflight Check
```bash
# Local (should show ADC/Credentials)
curl http://localhost:8000/preflight/vertex

# Production (should show WIF/ExternalAccountCredentials)
curl https://your-app.fly.dev/preflight/vertex
```

**Expected Local Response (ADC)**:
```json
{
  "ready": true,
  "credential_type": "Credentials",
  "principal": null,
  "project": "contestra-ai",
  "quota_project": "contestra-ai"
}
```

**Expected Production Response (WIF)**:
```json
{
  "ready": true,
  "credential_type": "ExternalAccountCredentials",
  "principal": "service-account@project.iam.gserviceaccount.com",
  "project": "contestra-ai",
  "quota_project": "contestra-ai"
}
```

## Troubleshooting

### ADC Issues
- **"No credentials" error**: Run `gcloud auth application-default login`
- **"Quota project" error**: Run `gcloud auth application-default set-quota-project`
- **PKCE errors**: Don't pipe/echo codes - authenticate interactively

### Model/API Issues
- **404 errors**: Wrong model format or region - use short form like `gemini-2.5-pro`
- **Empty responses**: Increase `max_tokens` to 1000+ (Gemini 2.5 uses thinking tokens)
- **MAX_TOKENS error**: Model hit limit during thinking - increase significantly

### Production Issues
- **"WIF required" error**: Using wrong env file - use `.env.production`
- **"External account not found"**: Check `WIF_CREDENTIALS_JSON` secret in Fly.io
- **Authentication fails**: Verify WIF is materialized to `/etc/gcloud/wif-credentials.json`

## Organization Constraints

This project operates under the following org policy:
- **`constraints/iam.disableServiceAccountKeyCreation`**: Service Account key creation is blocked
- **Solution**: Use ADC for local development instead of Service Account keys
- **Alternative**: Request policy exception from organization admin if SA keys are required

## Key Differences from Standard Setup

1. **No Service Account Keys**: Organization policy prevents SA key creation
2. **ADC for Local Dev**: Using user account authentication instead of service accounts
3. **Mandatory WIF for Production**: Enhanced security with no key files
4. **Robust Helpers**: Special functions to handle various SDK response formats
5. **Model Normalization**: Handles both short and full model ID formats

Last Updated: 2025-08-23
Status: **Production Ready with ADC**