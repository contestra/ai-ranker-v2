# Contestra Prompt Lab — V2 API (Phase‑0)

**Date:** 2025-08-22

## Auth
Include your tenant/org header on all calls:
```
X-Organization-Id: <org-id>
```

---

## Health
`GET /health` → `200 OK`

---

## Templates

### Create template
`POST /v1/templates`

Body (example):
```json
{
  "name": "Longevity Q&A",
  "messages": [
    { "role": "system", "content": "You are a precise assistant." },
    { "role": "user", "content": "Say hello" }
  ],
  "vendor": "openai",
  "model": "gpt-5"
}
```

Response:
```json
{
  "template_id": "UUID",
  "template_sha256": "hex-64",
  "name": "Longevity Q&A",
  "messages": [ ... ],
  "vendor": "openai",
  "model": "gpt-5"
}
```

### Get template
`GET /v1/templates/{id}` → 200 with template record.

### Run template
`POST /v1/templates/{id}/run`

Body:
```json
{
  "strict_json": false,   // or "json_mode" for backwards-compat
  "max_tokens": 512,
  "grounded": false,
  "inputs": {}
}
```

Response (normalized):
```json
{
  "provider": "openai|vertex",
  "model": "gpt-5-YYYY-MM-DD|gemini-1.5-pro",
  "content": "string (may be empty if model returned none)",
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 },
  "latency_ms": 0,
  "model_version": "string",
  "model_fingerprint": "string|null",
  "meta": {
    "response_format": { "type": "json_object" },
    "max_output_tokens_requested": 512,
    "max_output_tokens_effective": 512,
    "retry_mode": "none|responses_retry1|responses_retry2|chat_fallback",
    "reasoning_only_detected": false,
    "had_text_after_retry": true
  }
}
```

Errors:
- `400 MODEL_NOT_ALLOWED`
- `404 Template not found`
- `424 OPENAI_CALL_FAILED` / Vertex auth issues
- `500 internal_error` (JSON envelope)

---

## Ops

### OpenAI preflight
`GET /ops/openai-preflight` →
```json
{ "ready": true, "errors": [], "model_allowlist": ["gpt-5"], "probe_tokens": 16 }
```

### Vertex preflight
`GET /ops/vertex-preflight` →
```json
{ "ready": true, "errors": [], "project": "…", "location": "us-central1" }
```

---

## Notes
- Phase‑0 avoids Celery/Redis; endpoints are synchronous with timeouts.
- Template immutability uses canonical JSON → SHA‑256 (see PRD v2.7).

