# Phase-0 Vertex SDK Migration Plan

## Goal
Remove all use of the legacy Vertex SDK (google.cloud.aiplatform / vertexai.generative_models) and make google-genai the single client for Gemini/Vertex calls (ungrounded + grounded).

## Required Changes

### 1. Imports
- **Delete** all imports of `google.cloud.aiplatform` and `vertexai.generative_models`
- **Ensure** only this form remains in the Vertex adapter:
  ```python
  from google import genai
  from google.genai.types import HttpOptions, GenerateContentConfig, Tool, GoogleSearch
  ```

### 2. Client Initialization
- **Hard-require** `genai.Client(vertexai=True, project=..., location=..., http_options=HttpOptions(api_version="v1"))`
- **Remove** any conditional logic that falls back to legacy SDK
- If genai is unavailable or misconfigured → **raise a hard error** at startup. No silent fallback.

### 3. Methods
- **Keep only** `_step1_grounded_genai(...)` and `_step2_reshape_json_genai(...)`
- **Delete** `_step1_grounded_sdk` / `_step2_reshape_json_sdk` or any "classic SDK" branches
- **Ensure** grounded runs use two-step:
  - Step 1: Gemini + GoogleSearch()
  - Step 2: JSON reshape with tools=[], attestation fields (step2_tools_invoked=false, step2_source_ref=sha256(step1_text))

### 4. Modes
- Map Contestra `AUTO` → API `"AUTO"`
- Map Contestra `REQUIRED` → API `"ANY"` (since "REQUIRED" is invalid)
- Post-hoc enforcement still required: if REQUIRED but no grounding evidence → fail closed

### 5. Telemetry
- **Always emit** `response_api="vertex_genai"` and `provider_api_version="vertex:genai-v1"`
- **Preserve** modelVersion and attestation fields in metadata

### 6. Config / CI Guards
- **Delete** any env flags related to legacy fallback (ALLOW_GEMINI_DIRECT, etc.)
- **Add** a CI import-guard: fail build if vertexai classic imports reappear

### 7. Docs / Comments
- **Update** adapter docstrings and inline comments to state:
  - "This adapter uses only the google-genai client. Legacy Vertex SDK has been removed per PRD-Adapter-Layer-V1 (Phase-0)."

## Acceptance Criteria

- ✅ No code paths reference legacy Vertex SDK
- ✅ All Gemini calls (ungrounded + grounded) go through google-genai
- ✅ Two-step reshape with attestation is enforced
- ✅ CI fails if vertexai classic imports are reintroduced
- ✅ Unit tests:
  - Auth failure raises clear remediation ("Run: gcloud auth application-default login")
  - Grounded REQUIRED without evidence fails closed
  - Ungrounded runs still succeed

## Implementation Steps

1. **Analyze current implementation** - Understand existing code structure
2. **Remove legacy SDK imports and code paths** - Clean up all vertexai references
3. **Update client initialization** - Hard-require genai.Client
4. **Clean up methods** - Keep only genai versions
5. **Update mode mapping** - AUTO/REQUIRED handling
6. **Update telemetry and attestation** - Ensure proper metadata
7. **Remove legacy config/env flags** - Clean up environment variables
8. **Create CI import guard** - Prevent reintroduction
9. **Update documentation** - Clear comments about migration
10. **Verify tests pass** - Ensure everything works

## Risk Mitigation

- **Backup original file** before making changes
- **Test thoroughly** with mock and integration tests
- **Clear error messages** for authentication failures
- **CI guards** to prevent regression
- **Documentation** for future maintainers

## Success Metrics

- Zero legacy SDK imports in codebase
- All tests passing with google-genai only
- CI guard actively preventing reintroduction
- Clear documentation of changes
- No degradation in functionality