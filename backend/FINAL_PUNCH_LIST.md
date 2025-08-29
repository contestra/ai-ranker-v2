# Final Punch-List: ALS + Pins + Telemetry Fixes

## Fix ALS & Pins at the Orchestrator

**File:** `unified_llm_adapter.py`

### 1. Stop the Brittle "[Context:" Check; Use Internal Flag
**Current Issue:** Gates ALS with string-prefix heuristic
**Location:** `complete()` method, lines 66-71
**Fix:**
- Replace with request-scoped boolean (e.g., `req.meta["als_applied"]=True`)
- Set inside `_apply_als()` so it's applied **once**, regardless of phrasing
- Keep ALS in orchestrator only (not BatchRunner)
- Aligns with spec's "apply ALS once, pre-routing"

### 2. Insert ALS as Distinct Block, Enforce ≤350 NFC Chars
**Current Issue:** Prepends text to first user message, no 350 limit enforcement
**Location:** `_apply_als()` method, lines 168-210
**Fix:**
- Build ALS as its own block
- Normalize to NFC
- Count characters
- Throw specific `ALS_BLOCK_TOO_LONG` error if >350
- **No truncation** (immutability requirement)
- Keep message order: **system → ALS → user**
- Persist: `als_block_text`, `als_block_sha256`, `als_variant_id`, `seed_key_id`

### 3. Persist ALS Provenance; Don't Just Stash Raw Text
**Current Issue:** Only stores `als_block` and `als_country` in `request.metadata`
**Location:** Lines 204-208
**Required Fields:**
```python
{
    'als_block_text': als_block_nfc,
    'als_block_sha256': hashlib.sha256(als_block_nfc.encode()).hexdigest(),
    'als_variant_id': variant_id,
    'seed_key_id': seed_key_id,
    'als_country': country_code,
    'als_nfc_length': len(als_block_nfc)
}
```

### 4. Un-Hard-Pin Vertex in the Router
**Current Issue:** Rejects anything except `"publishers/google/models/gemini-2.5-pro"`
**Location:** Lines 88-94
**Fix:**
- Remove hard gate
- Normalize → validate against **config allowlist**
- Pass through requested model or fail fast with remediation
- No silent rewrites (Adapter PRD requirement)

### 5. Telemetry: Include ALS + Grounding + Response_API
**Current Issue:** `_emit_telemetry()` writes thin row
**Location:** Lines 212-249
**Add (as columns or JSON `meta`):**

#### ALS Fields:
- `als_present`
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
- `als_country` (optional)
- `als_nfc_length` (optional)

#### Grounding Fields:
- `grounding_mode_requested`
- `grounded_effective`
- `tool_call_count`
- `why_not_grounded`
- `response_api`

#### Proxy Normalization:
- `vantage_policy_before/after` when `DISABLE_PROXIES` flips policy

---

## Vertex Adapter: Respect Pins + Unify Metrics

**File:** `vertex_adapter.py`

### 6. Remove the Adapter-Level Hard-Pin
**Current Issue:** Hard-pins `GEMINI_MODEL = "...gemini-2.5-pro"` everywhere
**Locations:**
- Step-1 calls
- Step-2 calls
- GenAI calls
**Fix:**
- Replace with **validated request model** (normalized + allowlist)
- Pass it through
- If disallowed, error with remediation text (don't rewrite)
- **This is the main blocker**

### 7. Unify Metric Key: Use `tool_call_count` Everywhere
**Current Issue:** Stores `grounding_count` but logs `tool_call_count` causing inconsistencies
**Fix:**
- Standardize on `tool_call_count` for analytics parity with OpenAI
- Update all references

### 8. Keep Two-Step Attestation As Is
**Status:** ✅ Good - Step-2 enforces **no tools** and records attestation
**Action:** Ensure these flow to telemetry row via orchestrator:
- `step2_tools_invoked`
- `step2_source_ref`

---

## OpenAI Adapter: Small Polish

**File:** `openai_adapter.py`

### 9. Model Normalization at Call Site
**Status:** ✅ Good - passes normalized model (`model_name`) in params
**Action:** Keep this

### 10. Add `response_api="responses_http"` to Metadata
**Current Issue:** Missing explicit flag
**Fix:**
```python
metadata["response_api"] = "responses_http"
```
**Why:** Dashboards need to segment API paths cleanly
**Mirror:** Vertex sets `response_api="vertex_v1"`

### 11. Temperature Rule: Key Off Normalized Model or Tools-Present
**Current Issue:** Sets `temperature=1.0` only when `request.model == "gpt-5"`
**Problem:** Misses `"gpt-5-chat-latest"`
**Fix:**
- Key off **normalized** name, OR
- Simply apply if grounded/tools present

---

## What Was Verified (Concrete Evidence)

### Orchestrator Issues Found:
- Applies ALS via prepend to first user message ✓
- Only stores `als_block` + `als_country` (missing SHA256/variant/seed) ✗
- No 350-char guard ✗
- Uses **string prefix** to detect prior ALS ✗
- **Hard-pins** Vertex to 2.5-pro in router ✗

### Vertex Adapter Issues Found:
- Hard-pins to 2.5-pro for both `vertexai` and `google-genai` paths ✗
- Uses `grounding_count` vs `tool_call_count` inconsistently ✗

### OpenAI Adapter Status:
- Normalized model being used ✓
- Evidence-aware synthesis fallback present ✓
- `response_api` flag not clearly added ✗

---

## Quick Acceptance Checks (Run Through Orchestrator)

### 1. ALS Presence & Order (UNGROUNDED)
**Check:** Provider payload literally shows **system → ALS → user**
**Verify:** 
- Run row has `als_block_sha256/variant/seed_key_id`
- NFC length ≤350
- Else `ALS_BLOCK_TOO_LONG` error

### 2. Model Pins (Vertex)
**Test:** Template pinned to non-default 2.x model
**Expected:** Either:
- Runs with that exact ID, OR
- Errors with remediation
- **NO rewrite**

### 3. Grounded-Required Mode
**OpenAI:**
- Uses `tool_choice:"required"`
- Fail-closed if `tool_call_count==0`

**Vertex:**
- Requires grounding metadata
- Step-2 has **no tools**
- Attestation persisted

---

## Implementation Priority

### Critical (P0) - Block Merge
1. Vertex adapter: Remove hard-pin (Fix #6)
2. Orchestrator: Un-hard-pin Vertex (Fix #4)

### High (P1) - Required for Spec
3. Orchestrator: Fix ALS detection (Fix #1)
4. Orchestrator: Enforce 350 char limit (Fix #2)
5. Orchestrator: Persist provenance (Fix #3)

### Medium (P2) - Telemetry & Polish
6. Orchestrator: Complete telemetry (Fix #5)
7. Vertex: Unify metrics (Fix #7)
8. OpenAI: Add response_api (Fix #10)
9. OpenAI: Fix temperature rule (Fix #11)

---

## File-by-File Summary

### unified_llm_adapter.py (5 fixes)
- Fix #1: Replace string check with flag
- Fix #2: Enforce 350 NFC limit
- Fix #3: Complete provenance fields
- Fix #4: Remove Vertex hard-pin
- Fix #5: Add telemetry fields

### vertex_adapter.py (2 fixes)
- Fix #6: Remove model hard-pin
- Fix #7: Unify metric names

### openai_adapter.py (2 fixes)
- Fix #10: Add response_api
- Fix #11: Fix temperature rule

---

## Remediation Text Templates

### Model Not Allowed
```
Model not allowed: {model}
Allowed models: {allowlist}
To use this model:
1. Add to ALLOWED_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
```

### ALS Too Long
```
ALS_BLOCK_TOO_LONG: {length} chars exceeds 350 limit
No automatic truncation (immutability requirement)
Fix: Reduce ALS template configuration
```

---

## Success Metrics

### Immediate (Deploy + 1hr)
- ALS in 100% of applicable runs
- No model rewrites (0 occurrences)
- Complete telemetry rows

### Short-term (24hr)
- Model diversity as configured
- Grounding modes behave per spec
- ALS provenance queryable

### Long-term (7 days)
- ALS effectiveness measurable
- Cross-provider metrics aligned
- No performance regression

---

*Punch-List Created: August 29, 2025*
*Files to Modify: 3*
*Total Fixes: 11*
*Estimated Time: 90-120 minutes*