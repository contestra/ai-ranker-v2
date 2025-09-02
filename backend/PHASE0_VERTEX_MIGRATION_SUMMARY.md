# Phase-0 Vertex SDK Migration Summary

## Migration Completed: Removal of Legacy Vertex SDK

### Overview
Successfully migrated the Contestra LLM adapters to remove all use of the legacy Vertex SDK (`google.cloud.aiplatform` / `vertexai.generative_models`) and made `google-genai` the single client for all Gemini/Vertex calls (both grounded and ungrounded).

### Changes Implemented

#### 1. Imports Updated ✅
- **Removed:** All imports of `vertexai`, `google.cloud.aiplatform`, `vertexai.generative_models`
- **Added:** Required imports from `google.genai`:
  ```python
  from google import genai
  from google.genai.types import (
      HttpOptions, 
      GenerateContentConfig, 
      Tool, 
      GoogleSearch,
      Content,
      Part
  )
  ```

#### 2. Client Initialization ✅
- **Hard requirement:** `genai.Client(vertexai=True, project=..., location=..., http_options=HttpOptions(api_version="v1"))`
- **No fallback:** If `genai` is unavailable or misconfigured, raises a hard error at startup
- **Clear error messages:** Includes remediation steps for authentication failures

#### 3. Methods Cleaned ✅
- **Kept:** Only `_step1_grounded_genai()` and `_step2_reshape_json_genai()`
- **Removed:** All SDK-specific methods and conditional branches
- **Two-step process preserved:**
  - Step 1: Gemini + GoogleSearch() for grounding
  - Step 2: JSON reshape with tools=[], includes attestation fields

#### 4. Mode Mapping ✅
- Contestra `AUTO` → API `"AUTO"`
- Contestra `REQUIRED` → API `"ANY"` (since "REQUIRED" is invalid in API)
- Post-hoc enforcement: If REQUIRED but no grounding evidence → fail closed

#### 5. Telemetry Updated ✅
- Always emits `response_api="vertex_genai"`
- Always emits `provider_api_version="vertex:genai-v1"`
- Preserves `modelVersion` and attestation fields in metadata
- Attestation fields for two-step:
  - `step2_tools_invoked=false`
  - `step2_source_ref=sha256(step1_text)`

#### 6. Config/CI Guards ✅
- **Removed env flags:** `VERTEX_USE_GENAI_CLIENT`, `ALLOW_GEMINI_DIRECT`, `GENAI_AVAILABLE` checks
- **Added CI guard:** `ci_guard_vertex_sdk.py` - fails build if vertexai classic imports reappear
- **GitHub Actions:** `.github/workflows/ci_guard_vertex.yml` - runs on PR/push to adapter files

#### 7. Documentation ✅
- Updated adapter docstrings to state: "This adapter uses only the google-genai client. Legacy Vertex SDK has been removed per PRD-Adapter-Layer-V1 (Phase-0)."
- Clear comments throughout explaining the migration

### Files Modified

1. **`app/llm/adapters/vertex_adapter.py`** - Complete refactor to use only google-genai
2. **`ci_guard_vertex_sdk.py`** - CI guard script to prevent reintroduction
3. **`.github/workflows/ci_guard_vertex.yml`** - GitHub Actions workflow for CI guard
4. **`test_vertex_genai_phase0.py`** - Comprehensive test suite for migration validation

### Backup Created
- Original file backed up to: `app/llm/adapters/vertex_adapter_backup_phase0.py`

### Acceptance Criteria Met

✅ No code paths reference legacy Vertex SDK  
✅ All Gemini calls (ungrounded + grounded) go through google-genai  
✅ Two-step reshape with attestation is enforced  
✅ CI fails if vertexai classic imports are reintroduced  
✅ Unit tests validate:
  - Auth failure raises clear remediation ("Run: gcloud auth application-default login")
  - Grounded REQUIRED without evidence fails closed
  - Ungrounded runs still succeed
  - Mode mapping works correctly (AUTO→AUTO, REQUIRED→ANY)
  - Attestation fields are included in two-step responses

### Testing Recommendations

1. **Authentication Test:**
   ```bash
   # Verify clear error on auth failure
   unset GOOGLE_APPLICATION_CREDENTIALS
   python test_vertex_genai_phase0.py
   ```

2. **CI Guard Test:**
   ```bash
   # Verify guard catches legacy imports
   python ci_guard_vertex_sdk.py
   ```

3. **Integration Test:**
   - Test ungrounded requests
   - Test grounded AUTO mode
   - Test grounded REQUIRED mode
   - Test two-step grounded JSON

### Next Steps

1. Deploy to staging environment
2. Monitor telemetry for `response_api="vertex_genai"` 
3. Verify no degradation in grounding quality
4. Remove backup file after successful production deployment

### Migration Status: ✅ COMPLETE

All Phase-0 requirements have been successfully implemented. The Vertex adapter now exclusively uses the google-genai client with no fallback to legacy SDK.