# Changes Summary
## Date: 2025-08-31

## 1. Router Lazy-Init ✅
**Problem**: Router crashed at boot when Vertex env vars were missing, even for OpenAI-only runs.

**Solution**: Implemented lazy initialization for both adapters using Python properties.
- Adapters only instantiate on first use
- OpenAI-only runs no longer require Vertex configuration
- Symmetric implementation for both providers

**Files**: `unified_llm_adapter.py`

## 2. OpenAI JSON+Grounding Fix ✅
**Problem**: JSON mode with grounding included conflicting "plain text" instruction.

**Solution**: Added conditional instruction based on `json_mode`:
- JSON mode: "produce a final assistant message containing a single, valid JSON object"
- Plain text mode: Original "answer in plain text" instruction
- Keeps single-step Responses API call with `response_format={"type":"json_object"}`

**Files**: `openai_adapter.py`

## 3. Variant Policy & Cache Alignment ✅
**Problem**: Default variant and cache structure didn't match documentation.

**Solution**: 
- Changed default from `web_search_preview` to `web_search` (primary)
- Cache structure updated to track per-model+variant support status
- Fallback to `web_search_preview` only on "not supported" errors
- TTL (15 min) only applies to "unsupported" entries for re-probing

**Files**: `openai_adapter.py`, `cache_updates.py` (reference implementation)

## 4. REQUIRED Mode Contract ✅
**Problem**: REQUIRED mode silently downgraded to AUTO, violating fail-closed principle.

**Solution**: 
- OpenAI REQUIRED mode now fails immediately with clear error
- Documents API limitation: `tool_choice:"required"` not supported with web_search
- Tests updated to mark OpenAI+REQUIRED as expected fail/N.A.
- Vertex REQUIRED mode continues to work properly

**Files**: `openai_adapter.py`, `test_sanity_matrix.py`

## 5. Vertex Step-2 Polish ✅
**Problem**: Step-2 reshape used wrong message source for "Original Question".

**Solution**: 
- Now extracts last USER message (not just last message which could be assistant)
- Deep-sanitize metadata lists recursively to prevent SDK objects in JSON
- Maintains two-step attestation fields

**Files**: `vertex_adapter.py`

## 6. Dead Code Removal ✅
**Problem**: Unused helpers and shadow `validate_model()` causing confusion.

**Solution**:
- Removed router's shadow `validate_model()` that differed from centralized validator
- Marked `_probe_web_search_capability()` as UNUSED with stub implementation
- Cleaned up unused HTTP grounding helper

**Files**: `unified_llm_adapter.py`, `openai_adapter.py`

## 7. Telemetry Enhancement (Partial)
**Note**: Telemetry persistence requires database schema changes. Current implementation:
- Rich metadata object built with all grounding details
- Logged comprehensively
- Ready for persistence when schema supports JSONB column

**Fields tracked**:
- `response_api_tool_type`
- `grounding_attempted` / `grounded_effective`
- `tool_call_count` / `tool_result_count`
- `why_not_grounded`
- `citations_count`
- Attestation flags (Vertex)

## Validation Results

### 1. API Limitation Confirmed ✅
```bash
curl /v1/responses with tool_choice:"required" → HTTP 400
Error: "Tool choices other than 'auto' are not supported"
```

### 2. Router Lazy-Init ✅
- Router initializes without Vertex env vars
- Adapters remain None until first use
- OpenAI-only runs succeed

### 3. REQUIRED Mode Behavior ✅
- OpenAI+REQUIRED: Fails with clear API limitation error
- Vertex+REQUIRED: Continues to enforce grounding
- Tests mark OpenAI+REQUIRED as expected fail

### 4. Cache & Variant Policy ✅
- Default: `web_search` (primary)
- Fallback: `web_search_preview` on 400 only
- Per-model+variant cache entries
- TTL applied to unsupported entries

## Breaking Changes
- OpenAI REQUIRED mode now fails-closed (was silently downgraded)
- Router no longer has `validate_model()` method (use centralized validator)

## Migration Notes
- Update any code expecting OpenAI REQUIRED to succeed
- Replace `router.validate_model()` with `app.llm.models.validate_model()`
- Cache structure changed but backward compatible (auto-migrates)

## Next Steps
1. Add JSONB column for telemetry persistence when schema allows
2. Implement retry-on-empty for critical grounding requests
3. Monitor empty result rates with new telemetry fields
4. Consider Vertex for guaranteed REQUIRED mode support