# PR Final Bundle - Complete Implementation Guide

## 1) PR Description (Copy-Paste Ready)

**Title:** Respect pinned models, finalize ALS provenance, unify telemetry keys

**Summary**

- Orchestrator applies ALS once (system → ALS → user); stores `als_block_text/sha256/variant/seed_key_id`; hard-limits ALS to **≤350 NFC** (fail-closed)
- OpenAI adapter: normalized model used; adds `response_api="responses_http"`; keeps evidence-aware synthesis fallback; split metrics for web grounding vs any tool
- Vertex adapter: removes hard-pin; validates requested model against allowlist; passes through or fails with remediation; uses unified `tool_call_count` metric; two-step attestation preserved

**Why**

- Meets immutability & provenance requirements (ALS determinism + run capture)
- Meets adapter PRD: no silent rewrites, single orchestrator entry, normalized telemetry

**User-visible behavior**

- UNGROUNDED (ALS-only) now reliably shows locale signals and records ALS provenance per run
- GROUNDED-REQUIRED fails closed if no search evidence; GROUNDED-AUTO logs zero tool calls without failing

---

## 2) Acceptance Checklist (Reviewers Tick)

- [ ] **ALS applied once in orchestrator**; provider payload order is `system → ALS → user`
- [ ] **ALS length rule enforced:** ALS >350 NFC → `ALS_BLOCK_TOO_LONG` (no truncation). Fields persisted: `als_block_text`, `als_block_sha256`, `als_variant_id`, `seed_key_id`
- [ ] **OpenAI telemetry:** adds `response_api="responses_http"`, captures `grounded_effective`, `tool_call_count`, `why_not_grounded`
- [ ] **Vertex respects model pins:** requested/pinned model passes through or errors with remediation—no silent rewrite to 2.5-pro
- [ ] **Vertex two-step attestation:** Step-2 has **no tools**; `step2_tools_invoked=false`; `step2_source_ref = sha256(step1_text)` is stored
- [ ] **Telemetry completeness:** one row per call includes ALS + grounding fields (or in `meta` JSON), tokens, latency, and `response_api`

---

## 3) Remediation Text Snippets (Use Verbatim in Errors)

### Vertex Model Not Allowed
```
Model not allowed for Vertex.
Requested: <MODEL_ID>
Allowed: <LIST or LINK TO CONFIG>
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
  gcloud config set project <PROJECT_ID>
Ensure roles:
  roles/aiplatform.user
  roles/serviceusage.serviceUsageConsumer
Then retry the request.
```

### ALS Too Long
```
ALS_BLOCK_TOO_LONG: Ambient Location Signals exceed 350 NFC characters.
Shorten the ALS template; we do not truncate automatically (immutability requirement).
```

---

## 4) Telemetry Fields (Ensure These Flow from Adapters → Orchestrator Row)

### Core Fields
- `vendor`
- `model`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `success`
- `error_code`
- `response_api`

### ALS Fields
- `als_present` (bool)
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
- `als_country` (optional)
- `als_nfc_length` (optional)

### Grounding Fields
- `grounding_mode_requested` (`UNGROUNDED|PREFERRED|REQUIRED`)
- `grounded_effective` (bool)
- `tool_call_count` (int)
- `why_not_grounded` (string)

### Gemini Attestation (When Used)
- `step2_tools_invoked` (must be false)
- `step2_source_ref`

*Note: If schema is fixed and columns are tight, drop the above under a `meta` JSON, but keep names exactly to match dashboards.*

---

## 5) Tiny To-Dos Per File (So Nothing Slips)

### OpenAI Adapter
- [ ] Set `metadata["response_api"]="responses_http"`
- [ ] Key any temperature special-case off the **normalized** `model_name` (or simply "tools present → 1.0" if that's your policy)

### Vertex Adapter
- [ ] Remove all uses of constant hard-pin; accept `req.model` (normalized), validate against `VERTEX_ALLOWED_MODELS`, then pass through; else raise with the remediation text above
- [ ] Emit `tool_call_count` (not `grounding_count`) for cross-provider parity

### Orchestrator (`unified_llm_adapter.py`)
- [ ] `_apply_als` sets `req.meta["als_applied"]=True` and never relies on a string prefix check
- [ ] Enforce ALS NFC ≤350; compute SHA-256; set `als_block_text/sha256/variant/seed_key_id`
- [ ] Write ALS + grounding fields into the telemetry row (direct columns or `meta`)
- [ ] Remove any BatchRunner ALS insertion; orchestrator is the single source of ALS

---

## 6) Minimal Smoke Test Matrix (Through the **PUBLIC** Path)

| Lane | Provider/Model | Expect |
|------|---------------|--------|
| UNGROUNDED (ALS-only) | OpenAI gpt-5-chat-latest | Payload shows system→ALS→user; telemetry has ALS fields; `tool_call_count=0` |
| GROUNDED-AUTO | OpenAI gpt-5-chat-latest | May have `tool_call_count=0`; `grounded_effective` reflects reality; `response_api="responses_http"` |
| GROUNDED-REQUIRED | OpenAI gpt-5-chat-latest | If no web search → fail-closed with `why_not_grounded` |
| UNGROUNDED (ALS-only) | Vertex <pinned 2.x variant> | ALS present; no tools; model respected or explicit error (no rewrite) |
| GROUNDED-REQUIRED | Vertex <pinned 2.x variant> | Step-1 shows grounding metadata; Step-2 no tools; attestation fields persisted |

---

## Implementation Order

### Phase 1: Critical Fixes (P0)
1. **Vertex adapter:** Remove model hard-pin (15 min)
2. **Orchestrator:** Fix ALS detection and provenance (20 min)

### Phase 2: Required Fixes (P1)
3. **OpenAI adapter:** Add response_api, fix temperature (10 min)
4. **Vertex adapter:** Align metric names (5 min)
5. **Orchestrator:** Complete telemetry fields (15 min)

### Phase 3: Validation
6. Run smoke test matrix (15 min)
7. Verify database rows (5 min)

**Total Estimated Time:** 85 minutes

---

## Code Locations Quick Reference

### unified_llm_adapter.py
- **ALS detection:** Lines 66-71
- **ALS application:** Lines 168-210
- **Model validation:** Lines 88-101
- **Telemetry emission:** Lines 212-249

### openai_adapter.py
- **Temperature setting:** Search for `temperature` assignment
- **Metadata building:** Search for `metadata` dict creation
- **Response API:** Add to metadata section

### vertex_adapter.py
- **GEMINI_MODEL constant:** Remove all references
- **Model usage:** `complete()`, `_step1_grounded_genai()`, `_step2_reshape_json_genai()`
- **Metric names:** Search for `grounding_count`

---

## Environment Variables

```bash
# Required
VERTEX_ALLOWED_MODELS=publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash
OPENAI_API_KEY=<key>
VERTEX_PROJECT_ID=<project>
VERTEX_LOCATION=<region>

# Optional
ALS_MAX_CHARS=350
ENFORCE_ALS_LIMIT=true
LOG_PROVIDER_PAYLOADS=true  # For debugging
```

---

## Git Commit Message

```
fix: Respect model pins, finalize ALS provenance, unify telemetry

- ALS applied once in orchestrator with ≤350 NFC enforcement
- Add complete ALS provenance fields (sha256, variant_id, seed_key_id)
- Remove Vertex hard-pin to respect template model selection
- Add response_api field to all adapters
- Unify metric names (tool_call_count across providers)
- Fix temperature rule to use normalized model name

Fixes: ALS bypass in tests, model pin violations, incomplete telemetry
Meets: Immutability PRD, Adapter PRD requirements
```

---

## Post-Deployment Verification

### 1. Check ALS Application
```sql
SELECT 
    meta->>'als_block_sha256' as hash,
    meta->>'als_variant_id' as variant,
    COUNT(*) as count
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2;
```

### 2. Verify Model Diversity
```sql
SELECT 
    vendor,
    model,
    COUNT(*) as requests
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

### 3. Check Grounding Effectiveness
```sql
SELECT 
    meta->>'grounding_mode_requested' as mode,
    meta->>'grounded_effective' as effective,
    COUNT(*) as count
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2;
```

---

## Definition of Done

### Code Complete
- [ ] All P0 fixes implemented
- [ ] All P1 fixes implemented
- [ ] No regressions in existing tests

### Testing Complete
- [ ] Smoke test matrix passes
- [ ] Database contains expected fields
- [ ] Provider payloads show correct ALS placement

### Documentation Complete
- [ ] PR description accurate
- [ ] Environment variables documented
- [ ] Remediation text in place

### Review Complete
- [ ] Code review approved
- [ ] Acceptance checklist verified
- [ ] No silent model rewrites confirmed

---

*Bundle Created: August 29, 2025*
*Ready for Implementation: Yes*
*Backward Compatible: Yes*