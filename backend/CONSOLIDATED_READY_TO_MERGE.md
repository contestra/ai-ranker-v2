# Ready-to-Merge Checklist - Consolidated Final Gate

*This is the single authoritative checklist. All other documents are referenced within.*

## Core Requirements ✓

### Orchestrator (ALS) - [Details: ALS_ARCHITECTURE_ANALYSIS.md]
- [ ] Applied once in the orchestrator (search for `_apply_als` in `complete()`)
- [ ] Message order is **system → ALS → user**
- [ ] ALS NFC length ≤ **350** or **fail-closed** (`ALS_BLOCK_TOO_LONG`)
- [ ] Persist complete provenance:
  - [ ] `als_block_text`
  - [ ] `als_block_sha256`
  - [ ] `als_variant_id`
  - [ ] `seed_key_id`

### OpenAI Adapter - [Details: ADAPTER_REVIEW_FIXES.md]
- [ ] Uses **normalized** model in actual call (search for `model_name` usage)
- [ ] Adds `response_api="responses_http"` to metadata/telemetry
- [ ] Synthesis fallback includes harvested search evidence
- [ ] Split metrics for `web_grounded` vs `any_tool`
- [ ] Temperature rule uses normalized `model_name` not raw `request.model`

### Vertex Adapter - [Details: ADAPTER_REVIEW_FIXES.md]
- [ ] **No hard-pin**: pass through requested model if in **config allowlist**
- [ ] Two-step reshape: Step-2 has **no tools** and records attestation:
  - [ ] `step2_tools_invoked=false`
  - [ ] `step2_source_ref` recorded
- [ ] Use unified metric name `tool_call_count` (remove all `grounding_count`)
- [ ] Set `response_api="vertex_genai"` consistently

### Telemetry Row (One Per Run) - [Details: PR_DEFINITION_OF_DONE.md]
- [ ] Core fields: `vendor`, `model`, `latency_ms`, tokens, `success`
- [ ] ALS fields: `als_present`, `als_block_sha256`, `als_variant_id`, `seed_key_id`
- [ ] Grounding fields: `grounding_mode_requested`, `grounded_effective`, `tool_call_count`, `why_not_grounded`
- [ ] API fields: `response_api`, `provider_api_version`, `region`
- [ ] Proxy normalization: `vantage_policy_before/after` when changed

---

## Unified Environment Variables

```bash
# Model Allowlists
ALLOWED_VERTEX_MODELS=publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash
ALLOWED_OPENAI_MODELS=gpt-5,gpt-5-chat-latest

# ALS Configuration
ALS_MAX_CHARS=350
ENFORCE_ALS_LIMIT=true

# OpenAI Configuration
OPENAI_API_KEY=<key>
OPENAI_MAX_WEB_SEARCHES=2
OPENAI_TPM_LIMIT=150000
OPENAI_RPM_LIMIT=10000
OPENAI_DEFAULT_MAX_OUTPUT_TOKENS=6000
OPENAI_MAX_OUTPUT_TOKENS_CAP=6000

# Vertex Configuration
VERTEX_PROJECT_ID=<project>
VERTEX_LOCATION=<region>

# Timeouts
LLM_TIMEOUT_UN=60
LLM_TIMEOUT_GR=120

# Features
DISABLE_PROXIES=true
LOG_PROVIDER_PAYLOADS=true  # For debugging
```

---

## Standardized API Values

### response_api Field Values:
- **OpenAI**: `"responses_http"`
- **Vertex**: `"vertex_genai"`

### provider_api_version Values:
- **OpenAI**: `"openai:responses-v1"`
- **Vertex**: `"vertex:genai-v1"`

---

## Implementation Priority - [Full Details: FINAL_PUNCH_LIST.md]

### P0 - Critical Blockers (Must fix first)
1. Remove Vertex model hard-pin in orchestrator (search for `MODEL_NOT_ALLOWED` check)
2. Remove `GEMINI_MODEL` constant in vertex_adapter.py

### P1 - Required for Spec
3. Fix ALS detection (replace string check with `als_applied` flag)
4. Enforce 350 NFC limit with fail-closed
5. Add complete provenance fields

### P2 - Telemetry & Polish
6. Complete telemetry emission with all fields
7. Fix OpenAI temperature rule and add response_api
8. Unify Vertex metrics to tool_call_count

---

## Minimal Smoke Test Suite

*Run all through **orchestrator/HTTP** path, NOT direct adapter calls*

### Test Matrix - [Full Details: PR_FINAL_BUNDLE.md]

| Test | Expected Result |
|------|-----------------|
| UNGROUNDED (ALS-only) - OpenAI | Payload shows system→ALS→user; telemetry has ALS fields; `tool_call_count=0` |
| GROUNDED-AUTO - OpenAI | May have `tool_call_count=0`; `grounded_effective` reflects reality; `response_api="responses_http"` |
| GROUNDED-REQUIRED - OpenAI | If no search → fail-closed with `why_not_grounded` |
| UNGROUNDED (ALS-only) - Vertex pinned | ALS present; model respected or error (no rewrite); `response_api="vertex_genai"` |
| GROUNDED-REQUIRED - Vertex | Step-1 has grounding metadata; Step-2 no tools; attestation persisted |
| ALS Length Guard | Force >350 NFC → error `ALS_BLOCK_TOO_LONG`, no truncation |

---

## Verification Queries

### 1. Verify ALS Applied
```sql
SELECT 
    COUNT(*) as total,
    COUNT(meta->>'als_block_sha256') as with_als,
    COUNT(meta->>'als_block_sha256') * 100.0 / COUNT(*) as als_percentage
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour';
```

### 2. Check Model Distribution
```sql
SELECT 
    vendor,
    model,
    COUNT(*) as count
FROM llm_telemetry  
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY vendor, model
ORDER BY count DESC;
```

### 3. Verify Response API and Region (NEW)
```sql
SELECT
    meta->>'response_api' as api,
    meta->>'region' as region,
    meta->>'provider_api_version' as version,
    COUNT(*) as count
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2, 3
ORDER BY count DESC;
```

### 4. Check Grounding Effectiveness
```sql
SELECT
    meta->>'grounding_mode_requested' as mode,
    meta->>'grounded_effective' as effective,
    AVG(CAST(meta->>'tool_call_count' AS INT)) as avg_tools
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2;
```

### 5. Verify No Silent Region Rewrites (NEW)
```sql
-- Should show consistent regions per vendor
SELECT
    vendor,
    meta->>'region' as region,
    COUNT(DISTINCT model) as models,
    COUNT(*) as requests
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY vendor, region
ORDER BY vendor, requests DESC;
```

---

## Remediation Text Templates

### Model Not Allowed
```
Model not allowed: {model}
Allowed models: {allowlist}
To use this model:
1. Add to ALLOWED_VERTEX_MODELS or ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
```

### ALS Too Long
```
ALS_BLOCK_TOO_LONG: {length} chars exceeds 350 limit (NFC normalized)
No automatic truncation (immutability requirement)
Fix: Reduce ALS template configuration
```

### Vertex Auth Missing
```
Vertex authentication failed.
Run:
  gcloud auth application-default login
  gcloud config set project {project_id}
Ensure roles:
  roles/aiplatform.user
  roles/serviceusage.serviceUsageConsumer
Then retry the request.
```

---

## Code Change Locations (Search Tokens)

### unified_llm_adapter.py
- **ALS detection**: Search for `startswith('[Context:'` → replace with flag
- **Model hard-pin**: Search for `MODEL_NOT_ALLOWED` in vertex section
- **_apply_als method**: Add NFC check, SHA256, provenance fields
- **_emit_telemetry**: Add complete metadata fields

### vertex_adapter.py
- **Hard-pin removal**: Search for `GEMINI_MODEL =` constant
- **Metric unification**: Search for `grounding_count` → replace with `tool_call_count`
- **Response API**: Add `metadata["response_api"] = "vertex_genai"`

### openai_adapter.py
- **Temperature fix**: Search for `request.model == "gpt-5"` → use `model_name`
- **Response API**: Add `metadata["response_api"] = "responses_http"`

---

## Pre-Merge Verification

### Code Review
- [ ] No hard-coded model names in adapters
- [ ] ALS applied only in orchestrator
- [ ] All error messages include remediation
- [ ] Telemetry fields consistent across adapters
- [ ] response_api and provider_api_version set correctly

### Test Results
- [ ] All 6 smoke tests pass
- [ ] Database queries show expected data
- [ ] No regressions in existing tests
- [ ] Region/version verification shows no rewrites

### Documentation
- [ ] PR description accurate (use PR_FINAL_BUNDLE.md)
- [ ] Environment variables documented
- [ ] Remediation texts in place

---

## Post-Merge Monitoring

### First Hour
- Monitor error rates for `ALS_BLOCK_TOO_LONG`
- Check model distribution matches expectations
- Verify ALS presence >95% of runs
- Confirm response_api and region fields populated

### First Day
- Review grounding effectiveness metrics
- Check for any silent model/region rewrites (should be 0)
- Validate telemetry completeness
- Verify provider_api_version consistency

---

## Success Criteria

### Immediate (Within 1 Hour)
- [ ] No increase in error rate
- [ ] ALS present in >95% of applicable runs
- [ ] Model pins respected (no silent rewrites)
- [ ] Region consistency maintained

### Short-term (Within 24 Hours)
- [ ] Telemetry dashboard shows complete data including new fields
- [ ] Cross-provider metrics aligned (tool_call_count)
- [ ] Grounding modes behave as specified
- [ ] API versioning tracked correctly

---

## Related Documents

- **Architecture Analysis**: ALS_ARCHITECTURE_ANALYSIS.md
- **Implementation Details**: FINAL_PUNCH_LIST.md
- **PR Description**: PR_FINAL_BUNDLE.md
- **Adapter Specifics**: ADAPTER_REVIEW_FIXES.md

---

*Checklist Consolidated: August 29, 2025*
*Single Source of Truth for Merge Gate*
*All duplicates referenced but not repeated*