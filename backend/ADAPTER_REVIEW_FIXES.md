# Adapter Review Fixes - OpenAI & Vertex

## Executive Summary

- **OpenAI adapter:** Earlier fixes landed successfully ✅ Minor P1 issues remain
- **Vertex adapter:** Still hard-pins to 2.5-pro ❗ Violates PRD's "respect pins / no silent rewrites"

---

# OpenAI Adapter (gpt-5 via Responses)

## What's Good ✔️

### Successfully Fixed from Earlier Review:
- **Normalized model is actually sent:** `model_name = normalize_model(...)` used in `params["model"]`
- **TPM limiter "credit"** and **grounded multiplier** implemented
- **Evidence-aware synthesis fallback:** Builds enhanced input with `extract_openai_search_evidence(...)`
- **Configurable search cap:** Via `OPENAI_MAX_WEB_SEARCHES`
- **Grounding signals split:** Records `grounded_effective`, `tool_call_count`, `web_grounded`, `web_search_count`

## Must-Fix Issues

### P1: Temperature Rule Targets Raw Name, Not Normalized
**Problem:** Temperature=1.0 only when `request.model == "gpt-5"`
**Impact:** Won't fire for `"gpt-5-chat-latest"` (the default)
**Location:** Line where temperature is set based on model
**Fix:**
```python
# WRONG
if request.model == "gpt-5":
    temperature = 1.0

# RIGHT
if model_name == "gpt-5":  # Use normalized name
    temperature = 1.0
# OR
if request.grounded and tools_present:
    temperature = 1.0
```

### P1: Response API Flag Missing
**Problem:** Missing `response_api` field for telemetry
**Impact:** Dashboards can't segment by API path
**Fix:**
```python
# Add to metadata
metadata["response_api"] = "responses_http"
```

## Nice-to-Have

### Schema-Based Strict JSON
**Recommendation:** Prefer schema-based strict JSON when schema provided
```python
# When schema available
text.format: json_schema
# Fallback to response_format if not
```

---

# Vertex Adapter (Gemini via Vertex)

## What's Good ✔️

### Successfully Implemented:
- **Two-step grounded→JSON:** Step-2 has no tools, includes attestation fields
- **google-genai v1 path:** Present with `tool_config` and GoogleSearch wiring
- **Grounding detection + REQUIRED enforcement:** Wired for both SDK shapes

## Must-Fix Issues

### P0: Respect Model Pins / No Silent Rewrites ❗
**Problem:** Hard-pins `GEMINI_MODEL = "publishers/google/models/gemini-2.5-pro"`
**Violation:** Ignores `req.model`, breaks PRD's "pass through pinned models or fail fast"
**Impact:** Can't use other Gemini models, breaks template pins

**Current Code (WRONG):**
```python
GEMINI_MODEL = "publishers/google/models/gemini-2.5-pro"
# Always uses GEMINI_MODEL, ignores req.model
```

**Required Fix:**
```python
# 1. Remove hard constant
# 2. Normalize and validate
normalized_model = normalize_model("vertex", req.model)
allowed_models = os.getenv("VERTEX_ALLOWED_MODELS", "...").split(",")

if normalized_model not in allowed_models:
    raise ValueError(
        f"MODEL_NOT_ALLOWED: {normalized_model} not in allowed set. "
        f"Allowed: {allowed_models}. "
        f"Update VERTEX_ALLOWED_MODELS env var to use this model."
    )

# 3. Pass through the validated model
model_to_use = normalized_model  # NOT a hard-coded constant
```

**Places to Fix:**
- `complete()` method where `GEMINI_MODEL` is used
- `_step1_grounded_genai()` 
- `_step2_reshape_json_genai()`

## Should-Fix Issues

### P1: Metric Key Alignment
**Problem:** OpenAI uses `tool_call_count`, Vertex uses `grounding_count`
**Impact:** Cross-provider analytics need if/else logic
**Fix:** 
```python
# Change in Vertex adapter
metadata["tool_call_count"] = grounding_count  # Align with OpenAI
# Keep grounding_count for backward compat if needed
```

## Nice-to-Have

### ALS Content Builder
**Note:** `_build_content_with_als(...)` supports ALS but passes `als_block=None`
**Status:** OK if orchestrator already inserted ALS into messages
**Requirement:** Orchestrator must guarantee `system → ALS → user` order

---

# Cross-Cutting Fixes

## 1. Telemetry Completeness

### OpenAI Needs:
```python
metadata["response_api"] = "responses_http"
# Keep existing:
# - grounded_effective
# - tool_call_count  
# - why_not_grounded (when REQUIRED fails)
```

### Vertex Needs:
```python
metadata["response_api"] = "vertex_v1"  # or "vertex_genai"
metadata["tool_call_count"] = grounding_count  # Align naming
metadata["model_version"] = response.model_version  # Already pulled
```

## 2. ALS Ownership Check
- ✅ Adapters don't inject ALS (correct)
- Orchestrator must apply ALS once
- Must persist: `als_block_text/sha256/variant/seed_key_id`

---

# Tiny PR Checklist

## OpenAI Adapter Fixes

### 1. Fix Temperature Rule
**File:** `openai_adapter.py`
**Find:** Temperature setting based on `request.model`
**Change:** Use `model_name` (normalized) or check for tools
```python
# Option 1: Use normalized model
if model_name == "gpt-5" or (request.grounded and tools_present):
    temperature = 1.0

# Option 2: Guard with env var
if os.getenv("OPENAI_GROUNDED_TEMP_OVERRIDE", "true") == "true":
    if request.grounded and tools_present:
        temperature = 1.0
```

### 2. Add Response API Flag
**Location:** Metadata building section
**Add:**
```python
metadata["response_api"] = "responses_http"
```

## Vertex Adapter Fixes

### 1. Remove Hard-Pin (P0)
**File:** `vertex_adapter.py`
**Remove:** `GEMINI_MODEL` constant usage
**Replace with:**
1. Accept `req.model` (normalized)
2. Validate against `VERTEX_ALLOWED_MODELS`
3. Pass through if valid
4. Raise with remediation if invalid

**Touch these methods:**
- `complete()`
- `_step1_grounded_genai()`
- `_step2_reshape_json_genai()`

### 2. Align Metric Names (P1)
**Find:** `grounding_count`
**Replace with:** `tool_call_count`
**Keep:** Any derived counts needed

---

# Quick Acceptance Checks

## Run All Via Orchestrator Path

### 1. OpenAI Grounded REQUIRED
**Test:** Request with grounded=REQUIRED
**Expected:**
- Returns `tool_call_count > 0` if supported
- Else fails closed with `why_not_grounded`
- Telemetry shows `response_api="responses_http"`

### 2. Vertex Pinned Model
**Test:** Template pinned to non-default model (e.g., gemini-2.0-flash)
**Expected:**
- Runs with that exact ID, OR
- Fails fast without rewriting
- NO silent rewrite to 2.5-pro

### 3. ALS Presence
**Test:** Any request with ALS context
**Expected:**
- Provider payload shows `system → ALS → user`
- Run record contains ALS provenance fields
- ALS is NFC ≤350 chars

---

# Implementation Priority

## Critical (P0) - Do First
1. **Vertex:** Remove model hard-pin (blocks template functionality)

## High (P1) - Do Second  
2. **OpenAI:** Fix temperature rule to use normalized model
3. **OpenAI:** Add response_api flag
4. **Vertex:** Align metric names

## Nice-to-Have - Do if Time
5. **OpenAI:** Schema-based strict JSON
6. **Both:** Verify ALS flow from orchestrator

---

# Environment Variables

```bash
# Add these for configuration
VERTEX_ALLOWED_MODELS=publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash
OPENAI_GROUNDED_TEMP_OVERRIDE=true
```

---

# Summary

## OpenAI Status: ✅ 95% Complete
- All major fixes from earlier review landed
- Just need temperature rule fix and response_api flag

## Vertex Status: ⚠️ 70% Complete  
- Two-step policy works well
- **BLOCKER:** Still hard-pins model (P0 violation)
- Need metric alignment

## Next Steps:
1. Fix Vertex model hard-pin immediately
2. Add missing telemetry fields
3. Run acceptance checks through orchestrator

---

*Review Date: August 29, 2025*
*Estimated Fix Time: 30-45 minutes*
*Backward Compatible: Yes*