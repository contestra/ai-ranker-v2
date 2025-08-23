# Troubleshooting Guide

## Common Issues and Solutions

### Authentication Issues

#### ADC Not Working
**Error**: `google.auth.exceptions.DefaultCredentialsError: Could not automatically determine credentials`

**Solution**:
```bash
# Run authentication interactively
gcloud auth application-default login --no-launch-browser

# Set quota project
gcloud auth application-default set-quota-project contestra-ai

# Verify
gcloud auth application-default print-access-token
```

#### PKCE Verification Code Issues
**Error**: `Error: Invalid verification code` when piping codes to gcloud

**Solution**: Never pipe or echo verification codes. Always authenticate interactively:
```bash
# WRONG
echo "4/0AVMBsJj..." | gcloud auth application-default login

# CORRECT
gcloud auth application-default login --no-launch-browser
# Then manually copy/paste the verification code
```

#### Service Account Key Creation Blocked
**Error**: `Request violates constraint constraints/iam.disableServiceAccountKeyCreation`

**Solution**: Your organization blocks SA key creation. Use ADC instead:
1. Use Application Default Credentials for local development
2. Don't set `GOOGLE_APPLICATION_CREDENTIALS` in `.env.local`
3. Authenticate with your user account (must have Owner role)

### Vertex AI Issues

#### 404 Model Not Found
**Error**: `404 Not Found` when calling Vertex AI

**Common Causes**:
1. Wrong model format
2. Wrong region
3. Model not available in region

**Solution**:
```python
# Use short model names
model = "gemini-2.5-pro"  # CORRECT
model = "publishers/google/models/gemini-2.5-pro"  # WRONG for SDK

# Verify region matches
VERTEX_LOCATION=europe-west4  # Must match your project's region
```

#### Empty Response with Valid Tokens
**Symptoms**: 
- API returns 200 OK
- Usage shows tokens consumed
- But `content` field is empty

**Causes**:
1. Response extraction not handling SDK format
2. Model hit MAX_TOKENS during thinking
3. Safety filtering

**Solution**:
1. Check the adapter has proper extraction helpers:
   - `_extract_vertex_text()`
   - `_extract_vertex_usage()`
   - `_extract_finish_info()`

2. Increase `max_tokens` for Gemini 2.5:
   ```json
   {
     "max_tokens": 1000  // Minimum for Gemini 2.5 Pro
   }
   ```

#### MAX_TOKENS Error
**Error**: `Response candidate content has no parts (and thus no text)`

**Cause**: Gemini 2.5 Pro uses ~375-400 "thinking tokens" internally

**Solution**: Always set `max_tokens` to 1000+ for Gemini models:
```python
"max_tokens": 1000  # Simple prompts
"max_tokens": 2000  # Complex prompts
```

### Database Issues

#### Connection Refused
**Error**: `connection to server at "ep-empty-frog.eu-central-1.aws.neon.tech" failed`

**Solutions**:
1. Check DATABASE_URL in `.env`
2. Verify SSL is required: `?ssl=require` or `?sslmode=require`
3. Check Neon dashboard for service status
4. Verify connection pooler endpoint is used

#### Schema Not Found
**Error**: `relation "templates" does not exist`

**Solution**:
```bash
# Run schema creation
cd backend
psql $DATABASE_URL -f create_schema.sql

# Or using the script
./setup_db.sh
```

### Environment Issues

#### Wrong Credentials in Production
**Error**: `ENFORCE_VERTEX_WIF=true expects an 'external_account' credentials JSON`

**Cause**: Using local `.env.local` in production

**Solution**:
1. Use `.env.production` for deployment
2. Set `ENFORCE_VERTEX_WIF=true` in production
3. Provide WIF credentials via `WIF_CREDENTIALS_JSON` secret

#### Missing Environment Variables
**Error**: `GOOGLE_CLOUD_PROJECT missing`

**Solution**: Ensure all required variables are set:
```bash
# Required for Vertex
GOOGLE_CLOUD_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4

# Required for OpenAI
OPENAI_API_KEY=sk-proj-xxx

# Required for database
DATABASE_URL=postgresql+asyncpg://...
```

### API Issues

#### Template Not Found
**Error**: `404 Template not found`

**Causes**:
1. Template ID doesn't exist
2. Organization mismatch

**Solution**:
```bash
# List templates for org
curl -H "X-Organization-Id: test-org" \
  http://localhost:8000/v1/templates

# Use correct template ID from response
```

#### Vendor Routing Failures
**Error**: `No adapter found for provider: xyz`

**Solution**: Check provider/vendor values:
- Valid providers: `openai`, `vertex`, `anthropic`
- Case sensitive
- No silent fallbacks - must be exact match

### Testing Issues

#### Smoke Tests Failing
**Error**: Smoke tests return unexpected results

**Solution**:
1. Verify backend is running: `curl http://localhost:8000/health`
2. Check preflight: `curl http://localhost:8000/preflight/vertex`
3. Review logs: `docker logs ai-ranker-backend`
4. Ensure environment variables are loaded

#### pytest Import Errors
**Error**: `ModuleNotFoundError: No module named 'app'`

**Solution**:
```bash
cd backend
export PYTHONPATH=$PWD:$PYTHONPATH
pytest tests/
```

### Performance Issues

#### Slow Vertex AI Responses
**Symptoms**: 3-5 second latency

**Cause**: Normal for Gemini 2.5 Pro with thinking tokens

**Mitigations**:
1. Use connection pooling
2. Implement caching for repeated prompts
3. Consider async execution
4. Use smaller models for simple tasks

#### Token Limit Exceeded
**Error**: Token count exceeds model limit

**Solution**:
1. Reduce prompt size
2. Use prompt compression techniques
3. Split into multiple calls
4. Use a model with higher limits

## Debugging Tips

### Enable Detailed Logging
```python
# In app/main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Credential Type
```bash
curl http://localhost:8000/preflight/vertex
```

Expected for ADC:
```json
{
  "credential_type": "Credentials",
  "principal": null
}
```

Expected for WIF:
```json
{
  "credential_type": "ExternalAccountCredentials",
  "principal": "service-account@project.iam.gserviceaccount.com"
}
```

### Test Vertex Directly
```bash
TOKEN=$(gcloud auth application-default print-access-token)
curl -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://europe-west4-aiplatform.googleapis.com/v1/projects/contestra-ai/locations/europe-west4/publishers/google/models/gemini-2.5-pro:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Say PING"}]}]}'
```

### Monitor Background Tasks
```bash
# If using background bash
./bashes  # List running shells
./bash-output <shell-id>  # Check output
```

## Getting Help

### Resources
- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Google Auth Documentation](https://google-auth.readthedocs.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Neon Documentation](https://neon.tech/docs)

### Support Channels
- GitHub Issues: Report bugs and feature requests
- Internal Slack: #ai-ranker-support
- Email: ai-ranker-support@contestra.com

### Logs Location
- Backend logs: `backend/logs/`
- System logs: `/var/log/`
- Docker logs: `docker logs ai-ranker-backend`

## Quick Fixes Checklist

- [ ] ADC authenticated? `gcloud auth application-default login`
- [ ] Quota project set? `gcloud auth application-default set-quota-project`
- [ ] Environment file correct? `.env.local` for local, `.env.production` for prod
- [ ] Backend running? `curl http://localhost:8000/health`
- [ ] Database connected? `./test_db.sh`
- [ ] Vertex preflight OK? `curl http://localhost:8000/preflight/vertex`
- [ ] Model name normalized? Use `gemini-2.5-pro` not full path
- [ ] Max tokens sufficient? Use 1000+ for Gemini 2.5
- [ ] Region correct? Must be `europe-west4`

Last Updated: 2025-08-23