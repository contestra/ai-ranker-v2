# Ready-to-Merge Checklist (Final)

## Core Requirements ✓

### Orchestrator (ALS)
- [ ] Applied once in the orchestrator
- [ ] Message order is **system → ALS → user**
- [ ] ALS NFC length ≤ **350** or **fail-closed** (`ALS_BLOCK_TOO_LONG`)
- [ ] Persist `als_block_text/sha256/variant/seed_key_id`

### OpenAI Adapter
- [ ] Uses **normalized** model in the actual call
- [ ] Adds `response_api="responses_http"` to metadata/telemetry
- [ ] Synthesis fallback includes harvested search evidence
- [ ] Split metrics for `web_grounded` vs `any_tool`

### Vertex Adapter
- [ ] **No hard-pin**: pass through requested model if in **config allowlist**, otherwise error with remediation (don't rewrite)
- [ ] Two-step reshape: Step-2 has **no tools** and records attestation
  - [ ] `step2_tools_invoked=false`
  - [ ] `step2_source_ref` recorded
- [ ] Use unified metric name `tool_call_count`

### Telemetry Row (One Per Run)
Includes:
- [ ] ALS fields: `als_present`, `als_block_sha256`, `als_variant_id`, `seed_key_id`
- [ ] Grounding fields: `grounding_mode_requested`, `grounded_effective`, `tool_call_count`, `why_not_grounded`, `response_api`
- [ ] Core metrics: tokens, latency

---

## Minimal Smoke Test Suite
*Run all through **orchestrator/HTTP** path, NOT direct adapter calls*

### Test 1: UNGROUNDED (ALS-only) — OpenAI
**Expected:**
- Payload visibly shows **system → ALS → user**
- Telemetry has ALS fields
- `tool_call_count=0`

**Command:**
```bash
curl -X POST /api/llm/complete \
  -d '{"vendor":"openai","model":"gpt-5","grounded":false,"als_context":{"country_code":"US"}}'
```

### Test 2: GROUNDED-AUTO — OpenAI
**Expected:**
- May return `tool_call_count=0`
- Logs/row show `grounded_effective=false`
- `response_api="responses_http"`

**Command:**
```bash
curl -X POST /api/llm/complete \
  -d '{"vendor":"openai","model":"gpt-5","grounded":true,"grounding_mode":"AUTO"}'
```

### Test 3: GROUNDED-REQUIRED — OpenAI
**Expected:**
- If no search calls occur → **fail-closed** with `why_not_grounded`

**Command:**
```bash
curl -X POST /api/llm/complete \
  -d '{"vendor":"openai","model":"gpt-5","grounded":true,"grounding_mode":"REQUIRED"}'
```

### Test 4: UNGROUNDED (ALS-only) — Vertex (Pin to Non-Default)
**Expected:**
- Runs with exact ID **OR** errors with "Model not allowed" remediation
- Never silently rewrites

**Command:**
```bash
curl -X POST /api/llm/complete \
  -d '{"vendor":"vertex","model":"publishers/google/models/gemini-2.0-flash","grounded":false}'
```

### Test 5: GROUNDED-REQUIRED — Vertex
**Expected:**
- Step-1 shows grounding metadata
- Step-2 has **no tools**
- Attestation fields persisted

**Command:**
```bash
curl -X POST /api/llm/complete \
  -d '{"vendor":"vertex","model":"gemini-2.5-pro","grounded":true,"grounding_mode":"REQUIRED"}'
```

### Test 6: ALS Length Guard
**Expected:**
- Force ALS >350 NFC chars → **error** `ALS_BLOCK_TOO_LONG`
- No truncation

**Command:**
```python
# Test script
als_context = {
    "country_code": "US",
    "override_text": "x" * 351  # Force oversized ALS
}
# Should fail with ALS_BLOCK_TOO_LONG
```

---

## Stock Remediation Texts

### Vertex Model Not Allowed
```
Model not allowed for Vertex.
Requested: {model_id}
Allowed: {allowed_list}
How to proceed:
  1) Use one of the allowed models, OR
  2) Update the allowlist in config and redeploy.
Note: We do not silently rewrite models (per Adapter PRD).
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

### ALS Too Long
```
ALS_BLOCK_TOO_LONG: Ambient Location Signals exceed 350 NFC characters.
Current: {actual_length} chars
Maximum: 350 chars
Shorten the ALS template; we do not truncate automatically (immutability requirement).
```

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

### 3. Verify Grounding Modes
```sql
SELECT
    meta->>'grounding_mode_requested' as mode,
    meta->>'grounded_effective' as effective,
    AVG(CAST(meta->>'tool_call_count' AS INT)) as avg_tools
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2;
```

### 4. Check Response APIs
```sql
SELECT
    vendor,
    meta->>'response_api' as api,
    COUNT(*) as count
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2;
```

---

## Pre-Merge Verification

### Code Review Checklist
- [ ] No hard-coded model names in adapters
- [ ] ALS applied only in orchestrator
- [ ] All error messages include remediation
- [ ] Telemetry fields consistent across adapters

### Test Results
- [ ] All 6 smoke tests pass
- [ ] Database queries show expected data
- [ ] No regressions in existing tests

### Documentation
- [ ] PR description accurate
- [ ] Environment variables documented
- [ ] Remediation texts in place

---

## Post-Merge Monitoring

### First Hour
- Monitor error rates for `ALS_BLOCK_TOO_LONG`
- Check model distribution matches expectations
- Verify ALS presence >95% of runs

### First Day
- Review grounding effectiveness metrics
- Check for any silent model rewrites (should be 0)
- Validate telemetry completeness

### First Week
- Analyze ALS impact on responses
- Review model pin respect rate
- Check cross-provider metric consistency

---

## Rollback Plan

If issues detected:
```bash
# Revert commits
git revert {commit_hash}

# Or use previous Docker image
kubectl set image deployment/ai-ranker ai-ranker={previous_image}

# Monitor recovery
watch 'kubectl get pods | grep ai-ranker'
```

---

## Success Criteria

### Immediate (Within 1 Hour)
- [ ] No increase in error rate
- [ ] ALS present in >95% of applicable runs
- [ ] Model pins respected (no silent rewrites)

### Short-term (Within 24 Hours)
- [ ] Telemetry dashboard shows complete data
- [ ] Cross-provider metrics aligned
- [ ] Grounding modes behave as specified

### Long-term (Within 1 Week)
- [ ] ALS effectiveness measurable
- [ ] Model diversity as expected
- [ ] No performance degradation

---

*Checklist Created: August 29, 2025*
*Status: Ready for Final Review*
*Merge Window: After all checks pass*