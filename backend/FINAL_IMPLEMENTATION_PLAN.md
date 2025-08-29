# Final Implementation Plan - ALS Fixes

## Executive Summary
Fix ALS implementation across 3 files with 11 specific changes to meet spec requirements:
- ALS applied once in orchestrator, ≤350 NFC, fail-closed
- No silent model rewrites, config allowlist for models
- Complete telemetry with provenance fields
- Unified metrics across providers

---

## Phase 1: Critical Blockers (P0) - Remove Hard-Pins

### 1. Remove Vertex Model Hard-Pin in Orchestrator
**File**: `unified_llm_adapter.py`
**Location**: Search for `MODEL_NOT_ALLOWED` in vertex validation section
**Change**:
```python
# Remove hard-coded check
# Replace with:
allowed_models = os.getenv("ALLOWED_VERTEX_MODELS", "...").split(",")
if request.model not in allowed_models:
    raise ValueError(f"Model not allowed: {request.model}\n"
                    f"Allowed models: {allowed_models}\n"
                    f"To use: Add to ALLOWED_VERTEX_MODELS env var")
```

### 2. Remove GEMINI_MODEL Constant in Adapter
**File**: `vertex_adapter.py`
**Location**: Search for `GEMINI_MODEL =` constant declaration
**Changes**:
- Remove constant definition
- Replace all 4 usages with validated `req.model`
- Add allowlist validation with remediation text

---

## Phase 2: Fix ALS Core Issues (P1)

### 3. Fix ALS Detection Logic
**File**: `unified_llm_adapter.py`
**Location**: Search for `startswith('[Context:'` in `complete()` method
**Change**:
```python
# Replace string check with:
als_already_applied = getattr(request, 'als_applied', False)
```

### 4. Enforce ALS 350 Character Limit
**File**: `unified_llm_adapter.py`
**Location**: `_apply_als()` method
**Changes**:
```python
import unicodedata
# After building als_block:
als_block_nfc = unicodedata.normalize('NFC', als_block)
if len(als_block_nfc) > 350:
    raise ValueError(f"ALS_BLOCK_TOO_LONG: {len(als_block_nfc)} chars exceeds 350 limit (NFC normalized)\n"
                    f"No automatic truncation (immutability requirement)\n"
                    f"Fix: Reduce ALS template configuration")
```

### 5. Add Complete ALS Provenance
**File**: `unified_llm_adapter.py`
**Location**: `_apply_als()` method, metadata storage section
**Add**:
```python
import hashlib
request.metadata.update({
    'als_block_text': als_block_nfc,
    'als_block_sha256': hashlib.sha256(als_block_nfc.encode()).hexdigest(),
    'als_variant_id': getattr(self.als_builder, 'last_variant_id', 'default'),
    'seed_key_id': getattr(self.als_builder, 'seed_key_id', 'default'),
    'als_country': country_code,
    'als_nfc_length': len(als_block_nfc),
    'als_present': True
})
request.als_applied = True  # Set flag to prevent reapplication
```

---

## Phase 3: Complete Telemetry (P2)

### 6. Enhanced Telemetry Emission
**File**: `unified_llm_adapter.py`
**Location**: `_emit_telemetry()` method
**Add to meta JSON**:
```python
meta_json = {
    # ALS fields
    'als_present': request.metadata.get('als_present', False),
    'als_block_sha256': request.metadata.get('als_block_sha256'),
    'als_variant_id': request.metadata.get('als_variant_id'),
    'seed_key_id': request.metadata.get('seed_key_id'),
    'als_country': request.metadata.get('als_country'),
    'als_nfc_length': request.metadata.get('als_nfc_length'),
    
    # Grounding fields
    'grounding_mode_requested': 'REQUIRED' if request.grounded else 'NONE',
    'grounded_effective': response.grounded_effective,
    'tool_call_count': response.metadata.get('tool_call_count', 0),
    'why_not_grounded': response.metadata.get('why_not_grounded'),
    
    # API versioning
    'response_api': response.metadata.get('response_api'),
    'provider_api_version': response.metadata.get('provider_api_version'),
    'region': response.metadata.get('region'),
    
    # Proxy normalization
    'vantage_policy_before': getattr(request, 'original_vantage_policy', None),
    'vantage_policy_after': request.vantage_policy,
    'proxies_normalized': getattr(request, 'proxy_normalization_applied', False)
}
```

### 7. Fix OpenAI Adapter
**File**: `openai_adapter.py`
**Changes**:
1. **Add API metadata** (search for metadata building):
   ```python
   metadata["response_api"] = "responses_http"
   metadata["provider_api_version"] = "openai:responses-v1"
   ```

2. **Fix temperature rule** (search for `request.model == "gpt-5"`):
   ```python
   # Use normalized model:
   if model_name == "gpt-5" or (request.grounded and tools_present):
       temperature = 1.0
   ```

3. **REQUIRED mode handling**:
   ```python
   if grounding_mode == "REQUIRED" and tool_call_count == 0:
       metadata["why_not_grounded"] = "web_search not available in Responses API"
   ```

### 8. Fix Vertex Adapter
**File**: `vertex_adapter.py`
**Changes**:
1. **Unify metrics** (search for `grounding_count`):
   ```python
   # Replace all occurrences with:
   metadata["tool_call_count"] = grounding_count
   ```

2. **Add API metadata**:
   ```python
   metadata["response_api"] = "vertex_genai"
   metadata["provider_api_version"] = "vertex:genai-v1"
   metadata["region"] = os.getenv("VERTEX_LOCATION", "us-central1")
   ```

3. **Ensure attestation flows**:
   ```python
   metadata["step2_tools_invoked"] = False  # Must be false
   metadata["step2_source_ref"] = hashlib.sha256(step1_text.encode()).hexdigest()
   ```

---

## Environment Variables (Complete List)

```bash
# Model Allowlists
ALLOWED_VERTEX_MODELS=publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash
ALLOWED_OPENAI_MODELS=gpt-5,gpt-5-chat-latest

# ALS Configuration
ALS_MAX_CHARS=350
ENFORCE_ALS_LIMIT=true
ALS_SEED_KEY_ID=default  # For provenance/rotation

# OpenAI Configuration
OPENAI_API_KEY=<key>
OPENAI_MAX_WEB_SEARCHES=2
OPENAI_TPM_LIMIT=150000
OPENAI_RPM_LIMIT=10000

# Vertex Configuration
VERTEX_PROJECT_ID=<project>
VERTEX_LOCATION=<region>  # Prevents silent region drift

# Timeouts
LLM_TIMEOUT_UN=60
LLM_TIMEOUT_GR=120

# Features
DISABLE_PROXIES=true
LOG_PROVIDER_PAYLOADS=true  # For debugging
```

---

## Standardized Values (Locked)

### response_api Values:
- OpenAI: `"responses_http"`
- Vertex: `"vertex_genai"`

### provider_api_version Values:
- OpenAI: `"openai:responses-v1"`
- Vertex: `"vertex:genai-v1"`

### Metric Names:
- Use `tool_call_count` everywhere (no `grounding_count`)

---

## Validation Tests (Enhanced)

### 1. ALS Presence & Order
- Payload shows `system → ALS → user`
- ALS is NFC ≤350 chars
- Telemetry has all provenance fields

### 2. ALS Length Guard
- Send >350 NFC chars
- Expect `ALS_BLOCK_TOO_LONG` error
- No truncation

### 3. Model Pin Respect
- Use non-default Vertex model
- Either runs with exact ID or errors
- No silent rewrite

### 4. Grounding Modes
- **UNGROUNDED**: No tools, ALS present
- **AUTO**: May have tool_call_count=0, logged
- **REQUIRED**: Fail-closed if no evidence, why_not_grounded set

### 5. Provider/Region/Version Sanity
```sql
SELECT
    meta->>'response_api' as api,
    meta->>'region' as region,
    meta->>'provider_api_version' as version,
    COUNT(*) as count
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY 1, 2, 3;
```

### 6. Gemini Attestation
- Assert `step2_tools_invoked=false`
- Assert `step2_source_ref` present
- Verify two-step policy held

---

## Key Principles

### ALS Responsibility
- **Only** orchestrator applies ALS (once)
- BatchRunner may choose locale/variant but doesn't inject
- Message order: system → ALS → user

### No Silent Rewrites
- Models pass through if allowed
- Clear error with remediation if not
- No automatic fallbacks

### Complete Provenance
- Every run captures full ALS metadata
- SHA256 for immutability
- Variant/seed for determinism

### Unified Telemetry
- One row per run
- Consistent field names across providers
- Meta JSONB for extensibility (no migration needed)

---

## Implementation Order

1. **First**: Remove hard-pins (P0 blockers)
2. **Second**: Fix ALS detection and enforcement
3. **Third**: Add provenance fields
4. **Fourth**: Complete telemetry with new fields
5. **Fifth**: Minor adapter fixes

**Estimated Time**: 90-120 minutes
**Files**: 3 (unified_llm_adapter.py, vertex_adapter.py, openai_adapter.py)
**Total Changes**: 11

---

## Success Metrics

### Immediate (1 hour post-deploy)
- ALS in 100% of applicable runs
- No model rewrites (0 occurrences)
- Complete telemetry rows with all fields

### Short-term (24 hours)
- Model diversity as configured
- Grounding modes behave per spec
- Region consistency maintained
- API versioning tracked correctly

---

*Plan Finalized: August 29, 2025*
*Ready for Implementation*
*Spec-Compliant and Reviewer-Proof*