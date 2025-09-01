# Environment Setup Guide

## Important Note About Environment Configuration

The AI Ranker V2 system uses **explicit environment variable injection** rather than `.env` file discovery. This is a deliberate design choice for Phase-0 to ensure proper secret management in production.

## Required Environment Variables

### OpenAI Configuration
```bash
# Required for OpenAI adapter
export OPENAI_API_KEY="sk-..."

# Optional: Override default model
export OPENAI_MODEL="gpt-5"  # Default for grounded
export OPENAI_UNGROUNDED_MODEL="gpt-5-chat-latest"  # Default for ungrounded
```

### Vertex AI Configuration
```bash
# Required: Project and location
export GOOGLE_CLOUD_PROJECT="your-project-id"
export VERTEX_LOCATION="us-central1"  # or "europe-west4"

# Authentication (choose one):
# Option 1: Application Default Credentials (recommended)
gcloud auth application-default login

# Option 2: Service account key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

### Database Configuration (Neon)
```bash
# Primary database URL
export DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require"

# Alternative: Separate Neon URL
export NEON_DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require"
```

### Timeout Configuration
```bash
# Optional: Override default timeouts (seconds)
export LLM_TIMEOUT_UN="60"   # Ungrounded timeout (default: 60s)
export LLM_TIMEOUT_GR="120"  # Grounded timeout (default: 120s)
```

### Feature Flags
```bash
# Optional: Override feature flag defaults
export CITATION_EXTRACTOR_V2="1.0"  # 100% rollout
export TEXT_HARVEST_AUTO_ONLY="1.0"  # Enable text harvest
export ENFORCE_RESOLVER_BUDGETS="1.0"  # Enable budget limits
```

## Common Issues and Solutions

### Issue: "API keys missing" errors in tests
**Solution:** The adapters are working correctly - they fail-fast when auth is missing. Set the required environment variables above.

### Issue: Claude keeps checking for `.env` files
**Explanation:** This is Claude's default troubleshooting behavior, not part of the system design. In production, secrets are injected via:
- CI/CD secret stores (GitHub Actions secrets)
- Platform secret management (Fly.io secrets, K8s secrets)
- Neon connection pooling with managed auth

### Issue: "GROUNDING_NOT_SUPPORTED" for gpt-5-chat-latest
**Expected:** This model doesn't support web_search tools. The system correctly routes:
- Grounded requests → `gpt-5` (supports web_search)
- Ungrounded requests → `gpt-5-chat-latest` (cheaper, faster)

## Testing Environment Setup

### Local Development
```bash
# 1. Set all required variables
export OPENAI_API_KEY="sk-..."
export GOOGLE_CLOUD_PROJECT="your-project"
export VERTEX_LOCATION="us-central1"
export DATABASE_URL="postgresql://..."

# 2. Authenticate with Google Cloud
gcloud auth application-default login

# 3. Run tests
venv/bin/python test_e2e_longevity_comprehensive.py
```

### CI Environment
```yaml
# GitHub Actions example
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  GOOGLE_CLOUD_PROJECT: ${{ secrets.GCP_PROJECT }}
  VERTEX_LOCATION: us-central1
  DATABASE_URL: ${{ secrets.NEON_DATABASE_URL }}
```

### Production Deployment
```bash
# Fly.io example
fly secrets set OPENAI_API_KEY="sk-..."
fly secrets set GOOGLE_CLOUD_PROJECT="your-project"
fly secrets set VERTEX_LOCATION="us-central1"
fly secrets set DATABASE_URL="postgresql://..."
```

## Verification Commands

### Check Environment
```bash
# Verify all required variables are set
echo "OpenAI: ${OPENAI_API_KEY:0:10}..."
echo "GCP Project: $GOOGLE_CLOUD_PROJECT"
echo "Vertex Location: $VERTEX_LOCATION"
echo "Database: ${DATABASE_URL%%@*}@..."
```

### Test Authentication
```bash
# Test OpenAI
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | jq .

# Test Vertex (via ADC)
gcloud auth application-default print-access-token

# Test Neon
psql "$DATABASE_URL" -c "SELECT 1"
```

### Run Contract Checks
```bash
# Verify telemetry contract after deployment
./scripts/check_telemetry_contracts.sh
```

## Security Best Practices

1. **Never commit secrets** to version control
2. **Use secret managers** in production (Vault, AWS Secrets Manager, etc.)
3. **Rotate keys regularly** and audit access
4. **Use least-privilege** service accounts for GCP
5. **Enable SSL/TLS** for all database connections (`sslmode=require`)

## Adapter Fail-Fast Behavior

The adapters enforce authentication at initialization:

- **OpenAI:** Checks for `OPENAI_API_KEY`, fails with remediation message
- **Vertex:** Checks for project/location and ADC, suggests `gcloud auth` command
- **Database:** Validates connection on startup, fails fast if unreachable

This fail-fast design ensures misconfigurations are caught early rather than failing at runtime during user requests.