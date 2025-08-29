# PR: Restore Spec-Correct ALS + Respect Model Pins + Telemetry

## A) Orchestrator: ALS Application & Provenance

### 1. Apply ALS Unconditionally in Orchestrator (Not BatchRunner)
**File**: `unified_llm_adapter.py`
**Current Issue**: String prefix check `"[Context:"` is fragile
**Fix**: Replace with internal flag `als_applied=True` set by `_apply_als()`
**Location**: Lines 66-75 where `als_already_applied` is computed

### 2. Stop Mutating In-Place Without Provenance
**Current**: Prepends text to first user message, stores only `als_block` and `als_country`
**Required Fields**:
- NFC length check ≤350
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
**Message Order**: system → ALS → user (provenance must record ALS separately)

### 3. Enforce 350-char NFC Rule & Fail-Closed
**Location**: Within `_apply_als()` method
**Action**: 
- Enforce ≤350 NFC chars for ALS
- Raise specific error `ALS_BLOCK_TOO_LONG` instead of truncating
- Capture `als_block_sha256`

### 4. Persist ALS Provenance
**Location**: `_emit_telemetry()` method
**Add to telemetry row or meta JSON blob**:
- `als_present`
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
- `als_country`
- `grounding_mode_requested`
- `tool_call_count`
- `why_not_grounded`
- `response_api`

### 5. Record Proxy Normalization
**Issue**: Normalize `vantage_policy` to `ALS_ONLY` when `DISABLE_PROXIES` but don't emit change
**Fix**: Include in telemetry:
- `vantage_policy_before/after` or
- `proxies_normalized: true`

## B) Orchestrator: Model/Vendor Handling (No Silent Pins)

### 6. Vendor Inference After Robust Normalization
**Issue**: `get_vendor_for_model()` misses `"gpt-5-chat-latest"` and full Vertex publisher IDs
**Problem**: Vendor inference happens BEFORE normalization
**Fix Options**:
- (a) Normalize first then infer, or
- (b) Expand inference to cover actual IDs used

### 7. Remove Hard "Only gemini-2.5-pro" Gate
**Location**: `complete()` method, "Hard guardrails for allowed models" block
**Current**: Forces only allowed Vertex model, raises `MODEL_NOT_ALLOWED`
**Violation**: PRD states "respect pins; no silent rewrites"
**Fix**: 
- Validate against configurable allowlist
- Pass through requested model if allowed
- Fail with remediation text if not allowed

## C) OpenAI Adapter: Minor Alignment for ALS & Evidence

### 8. Ensure ALS Survives Message Splitting
**Location**: Message splitting into `instructions` and `user_input`
**Check**: Confirm ALS-enriched block is in `user_input` and not dropped
**Action**: Sanity-check only if already working

### 9. Grounded Synthesis Fallback: Keep Evidence-Aware
**Current**: Synthesis triggers when tools ran but no final message
**Required**: Evidence bundle (queries/URLs/snippets) from Step-1 injected into synthesis
**Implementation**: Use logged URL citation counts and shape summaries to build bundle

### 10. Normalize Model Usage at Call Site
**Location**: In adapter where `params["model"]` is built
**Fix**: Use normalized `model_name` not raw `request.model`

## D) Vertex Adapter: Respect Pins & Surface Fingerprints

### 11. Stop Hard-Pinning Inside Adapter
**Location**: `VertexAdapter.complete()` 
**Current**: Sets `model_id = GEMINI_MODEL`, logs "Using hard-pinned model"
**Fix**: 
- Pass through `req.model` (validated against allowlist)
- Or fail fast with remediation if not allowed

### 12. Keep Two-Step Policy; Expose modelVersion/Fingerprint
**Current**: Already extracts `modelVersion`
**Action**: Verify it flows back to telemetry via metadata

### 13. ALS Position in Vertex Content Builder
**Location**: `_build_content_with_als()` method
**Current**: Passes `als_block=None`, relies on orchestrator to prefix ALS
**Check**: Ensure ALS is in `req.messages` after orchestrator step

## E) Telemetry & Run-Record Parity

### 14. Emit Grounding Facts Consistently
**Add to telemetry per run**:
- `grounded_effective`
- `tool_call_count`
- `why_not_grounded`
**Note**: Already logged in adapter metadata, surface in orchestrator's `_emit_telemetry()`

### 15. Add response_api to Telemetry
**Current**: Set in adapters (`vertex_v1`, OpenAI Responses)
**Action**: Include in record for dashboard segmentation

---

# Quick Acceptance Checks (Run After PR)

## 1. Payload Spot-Check (UNGROUNDED Lane)
**Action**: Dump actual provider payload
**Expected Order**:
1. System message
2. ALS block (≤350 NFC)
3. User content
**Validation**: If ALS isn't literally present, wiring is wrong

## 2. DB/Telemetry Row Check
**Verify latest rows include**:
- `als_present=true`
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
- `grounding_mode_requested`
- `grounded_effective`
- `tool_call_count`
- `response_api`
- `vantage_policy_before/after` (when proxies disabled)

## 3. Model Pin Test
**Test**: Create template pinned to different Vertex build
**Expected**: Either:
- (a) Run with exact ID, or
- (b) Fail-fast with clear remediation
**NOT**: Silent coercion to 2.5-pro

## 4. Mode Separation Test
**Modes**:
- UNGROUNDED (ALS-only)
- GROUNDED-AUTO
- GROUNDED-REQUIRED

**Requirements**:
- Produce distinct, measurable outputs
- GROUNDED-REQUIRED fails closed if no tool use:
  - OpenAI: `tool_choice:"required"`
  - Vertex: Non-empty grounding metadata

---

# Tiny Diff-Sized To-Dos (Fast Execution)

## Immediate Actions:
1. **Replace prefix check** for ALS with internal boolean flag and provenance write in `_apply_als()`
   - Add NFC length check + SHA256 + IDs

2. **Extend `_emit_telemetry()`** to include ALS + grounding meta
   - Include proxy normalization flags

3. **In `complete()`**, remove hard "only gemini-2.5-pro" constraint
   - Validate against configurable allowlist
   - Pass through `request.model`

4. **In `VertexAdapter.complete()`**, stop overwriting `req.model` with `GEMINI_MODEL`
   - Use validated request model

5. **Sanity-check** OpenAI message splitting so ALS block persists into `user_input`
   - Keep synthesis fallback evidence-aware

---

# Definition of Done

## Core Requirements Met:
- [ ] ALS applied unconditionally in orchestrator (not BatchRunner)
- [ ] ALS provenance captured (sha256, variant_id, seed_key_id)
- [ ] 350 NFC char limit enforced with fail-closed behavior
- [ ] Model pins respected (no silent rewrites)
- [ ] Telemetry includes all required fields

## Acceptance Tests Pass:
- [ ] Payload contains ALS in correct position
- [ ] Database rows have complete ALS metadata
- [ ] Model pin test shows proper validation/failure
- [ ] Three grounding modes behave distinctly

## No Regressions:
- [ ] Existing tests pass
- [ ] Rate limiting still functions
- [ ] Grounding detection accurate
- [ ] Token estimation correct

## Documentation Updated:
- [ ] PR description includes acceptance criteria
- [ ] Environment variables documented
- [ ] Migration notes if schema changes

---

*PR Checklist Created: August 29, 2025*
*Estimated Implementation: 45-60 minutes*
*Review Required: Yes*