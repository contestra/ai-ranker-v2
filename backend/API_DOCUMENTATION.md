# API Documentation

## Base URL
- Local: `http://localhost:8000`
- Production: `https://your-app.fly.dev`

## Authentication
All API requests require the `X-Organization-Id` header:
```bash
curl -H "X-Organization-Id: your-org-id" http://localhost:8000/v1/templates
```

## Endpoints

### Health & Diagnostics

#### Health Check
```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-08-23T10:00:00Z"
}
```

#### Vertex AI Preflight
```http
GET /preflight/vertex
```

Verifies Vertex AI credentials and configuration.

**Response (ADC)**:
```json
{
  "ready": true,
  "credential_type": "Credentials",
  "principal": null,
  "project": "contestra-ai",
  "quota_project": "contestra-ai"
}
```

**Response (WIF)**:
```json
{
  "ready": true,
  "credential_type": "ExternalAccountCredentials",
  "principal": "service-account@project.iam.gserviceaccount.com",
  "project": "contestra-ai",
  "quota_project": "contestra-ai"
}
```

### Template Management

#### Create Template
```http
POST /v1/templates
```

**Request Body**:
```json
{
  "template_name": "my-template",
  "canonical": {
    "provider": "openai",
    "model": "gpt-5",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant"},
      {"role": "user", "content": "Hello"}
    ],
    "temperature": 0.7,
    "max_tokens": 500,
    "grounded": false
  },
  "metadata": {
    "description": "Test template",
    "tags": ["test", "demo"]
  }
}
```

**Supported Providers**:
- `openai` - OpenAI models (gpt-5, gpt-4, etc.)
- `vertex` - Google Vertex AI (gemini-2.5-pro, etc.)
- `anthropic` - Anthropic models (future support)

**Response**:
```json
{
  "template_id": "550e8400-e29b-41d4-a716-446655440000",
  "template_name": "my-template",
  "organization_id": "your-org-id",
  "canonical_hash": "sha256:abc123...",
  "created_at": "2025-08-23T10:00:00Z",
  "canonical": {
    "provider": "openai",
    "model": "gpt-5",
    "messages": [...],
    "temperature": 0.7,
    "max_tokens": 500
  }
}
```

#### Get Template
```http
GET /v1/templates/{template_id}
```

**Response**:
```json
{
  "template_id": "550e8400-e29b-41d4-a716-446655440000",
  "template_name": "my-template",
  "organization_id": "your-org-id",
  "canonical_hash": "sha256:abc123...",
  "created_at": "2025-08-23T10:00:00Z",
  "canonical": {...}
}
```

#### List Templates
```http
GET /v1/templates
```

**Query Parameters**:
- `limit` (optional): Number of results (default: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response**:
```json
{
  "templates": [
    {
      "template_id": "...",
      "template_name": "...",
      "created_at": "..."
    }
  ],
  "total": 42,
  "limit": 100,
  "offset": 0
}
```

### Template Execution

#### Run Template
```http
POST /v1/templates/{template_id}/run
```

**Request Body** (optional overrides):
```json
{
  "overrides": {
    "temperature": 0.9,
    "max_tokens": 1000
  },
  "idempotency_key": "unique-key-123"
}
```

**Response**:
```json
{
  "run_id": "run-550e8400-e29b-41d4",
  "template_id": "550e8400-e29b-41d4-a716-446655440000",
  "vendor": "openai",
  "model": "gpt-5",
  "content": "Hello! How can I help you today?",
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 10,
    "total_tokens": 60
  },
  "latency_ms": 1234,
  "model_version": "gpt-5-20250823",
  "success": true,
  "grounded_effective": false,
  "created_at": "2025-08-23T10:00:00Z"
}
```

**Vendor Field**:
The `vendor` field in the response indicates which provider actually handled the request:
- `openai` - Request handled by OpenAI
- `vertex` - Request handled by Vertex AI
- `anthropic` - Request handled by Anthropic

This eliminates the need for model name heuristics to determine the vendor.

#### Get Run Details
```http
GET /v1/runs/{run_id}
```

**Response**:
```json
{
  "run_id": "run-550e8400-e29b-41d4",
  "template_id": "...",
  "vendor": "openai",
  "model": "gpt-5",
  "content": "...",
  "usage": {...},
  "latency_ms": 1234,
  "created_at": "..."
}
```

### Canonicalization

#### Test Canonicalization
```http
POST /v1/canonicalize
```

Tests the canonicalization rules without creating a template.

**Request Body**:
```json
{
  "canonical": {
    "provider": "openai",
    "model": "gpt-5",
    "messages": [...],
    "temperature": 0.7000,
    "max_tokens": 500.0
  }
}
```

**Response**:
```json
{
  "original": {...},
  "canonicalized": {
    "provider": "openai",
    "model": "gpt-5",
    "messages": [...],
    "temperature": 0.7,
    "max_tokens": 500
  },
  "hash": "sha256:abc123..."
}
```

## Canonicalization Rules

The API applies these rules to ensure consistent hashing:

1. **Numeric Normalization**:
   - Remove trailing zeros: `1.0` → `1`
   - Scientific notation: `1e2` → `100`
   - Preserve significant decimals: `0.7000` → `0.7`

2. **JSON Key Ordering**:
   - All keys sorted alphabetically
   - Nested objects recursively sorted

3. **Default Values**:
   - `temperature`: 1.0
   - `max_tokens`: Model-specific defaults
   - `top_p`: 1.0

4. **Whitespace**:
   - Compact JSON (no extra spaces)
   - Consistent indentation in messages

## Error Responses

### Standard Error Format
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "field": "additional context"
    }
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TEMPLATE_NOT_FOUND` | 404 | Template ID doesn't exist |
| `INVALID_PROVIDER` | 400 | Unknown provider specified |
| `AUTHENTICATION_FAILED` | 401 | Missing or invalid credentials |
| `QUOTA_EXCEEDED` | 429 | Rate limit or quota exceeded |
| `MODEL_NOT_AVAILABLE` | 503 | Model temporarily unavailable |
| `INVALID_REQUEST` | 400 | Malformed request body |
| `IDEMPOTENCY_CONFLICT` | 409 | Idempotency key already used |

## Rate Limits

| Endpoint | Rate Limit | Window |
|----------|------------|--------|
| Template Creation | 100/hour | Per org |
| Template Execution | 1000/hour | Per org |
| Template Listing | 1000/hour | Per org |

## Idempotency

For safe retries, include an `idempotency_key` in POST requests:

```json
{
  "idempotency_key": "unique-request-id-123",
  ...
}
```

The API will return the same response for repeated requests with the same key within 24 hours.

## Provider-Specific Notes

### OpenAI
- Models: `gpt-5`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`
- Max tokens cap: 4000 (configurable)
- Supports JSON mode for structured output

### Vertex AI (Google)
- Models: `gemini-2.5-pro`, `gemini-1.5-pro`, `gemini-1.5-flash`
- Region: `europe-west4`
- **Important**: Set `max_tokens` to 1000+ for Gemini 2.5 (uses thinking tokens)
- Model names should use short form (not full resource path)

### Anthropic (Future)
- Models: `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`
- Planned support in Phase 2

## WebSocket Support (Future)

Streaming responses will be available via WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/v1/stream');
ws.send(JSON.stringify({
  template_id: '...',
  stream: true
}));
```

## Examples

### Create and Run Template (Full Flow)
```bash
# 1. Create template
TEMPLATE_ID=$(curl -s -X POST http://localhost:8000/v1/templates \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: test-org" \
  -d '{
    "template_name": "test-gemini",
    "canonical": {
      "provider": "vertex",
      "model": "gemini-2.5-pro",
      "messages": [
        {"role": "user", "content": "Say PONG"}
      ],
      "temperature": 0.1,
      "max_tokens": 1000
    }
  }' | jq -r '.template_id')

echo "Created template: $TEMPLATE_ID"

# 2. Run template
curl -X POST "http://localhost:8000/v1/templates/$TEMPLATE_ID/run" \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: test-org" \
  -d '{
    "idempotency_key": "test-run-001"
  }'
```

### Check Vertex AI Status
```bash
# Preflight check
curl http://localhost:8000/preflight/vertex | jq

# Direct API test
TOKEN=$(gcloud auth application-default print-access-token)
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://europe-west4-aiplatform.googleapis.com/v1/projects/contestra-ai/locations/europe-west4/publishers/google/models/gemini-2.5-pro:generateContent" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Say PING"}]}]}' | jq
```

## SDK Support (Future)

Planned SDK support for:
- Python: `pip install ai-ranker-sdk`
- TypeScript: `npm install @contestra/ai-ranker`
- Go: `go get github.com/contestra/ai-ranker-go`

## API Versioning

The API uses URL versioning:
- Current: `/v1/`
- Future: `/v2/` (with backwards compatibility)

Breaking changes will only be introduced in new major versions.

## Status Page

Monitor API status and incidents:
- Local: http://localhost:8000/status
- Production: https://status.ai-ranker.com

Last Updated: 2025-08-23