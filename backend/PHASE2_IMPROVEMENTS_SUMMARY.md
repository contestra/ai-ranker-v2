# Phase 2 Adapter Improvements Summary
## September 1, 2025 - Evening Session 2

## Overview
Implemented all high-priority improvements recommended by ChatGPT's comprehensive review. The adapters now have better observability, more reliable citation extraction, and clearer diagnostics.

## Improvements Implemented

### 1. Tool Call Count Threading ✅
- **File**: `vertex_adapter.py`
- **Change**: Pass `tool_call_count` parameter through citation extraction pipeline
- **Impact**: More reliable detection of tool usage for unlinked emission
- **Code**: Updated `_select_and_extract_citations()` and `_extract_vertex_citations()` signatures

### 2. Refined Citation Status Reasons ✅
- **File**: `vertex_adapter.py`
- **New Codes**:
  - `provider_returned_empty_evidence` - When grounding_chunks array is empty
  - `citations_missing_despite_tool_calls` - When extraction issue suspected
- **Impact**: Better distinction between provider issues and code bugs

### 3. Enhanced Citations Audit ✅
- **File**: `vertex_adapter.py`
- **Change**: Added sample data collection in `_audit_grounding_metadata()`
- **Includes**:
  - First 2 items from non-empty arrays (sanitized)
  - Structure flags for grounding_chunks (has_web, has_uri)
  - Truncated web_search_queries (50 chars max)
- **Impact**: Better debugging information without PII exposure

### 4. Grounded Evidence Unavailable Flag ✅
- **File**: `unified_llm_adapter.py`
- **New Flag**: `grounded_evidence_unavailable`
- **Condition**: Set when `grounded_effective=true` but `anchored_citations_count=0`
- **Impact**: Improved alerting and analytics for AUTO mode

### 5. Current/Past Query Testing ✅
- **File**: `test_citation_validation_current.py`
- **Queries**: 7 real-world queries about 2024 events
- **Results**: Vertex returns 5-10 unlinked sources for current events
- **Finding**: Citation extraction works; Gemini provides unlinked sources only

## Test Results Summary

### With Future Query (August 2025)
- **OpenAI**: 0 citations (no web_search support)
- **Vertex**: 0 citations (empty grounding_chunks for future date)
- **Status**: `provider_returned_empty_evidence`

### With Current/Past Queries (2024 events)
- **OpenAI**: 0 citations (no web_search support)
- **Vertex**: 5-10 citations per query (all unlinked sources)
- **Status**: Working correctly, but no anchored citations

## Key Findings

1. **Citation extraction is working correctly** - The V2 extractor properly handles Gemini responses
2. **Gemini returns unlinked sources only** - No anchored spans in citations
3. **Tool call detection improved** - Threading tool_call_count ensures reliable detection
4. **Better diagnostics** - New status reasons and audit data help identify issues

## Production Recommendations

1. **Keep `CITATION_EXTRACTOR_EMIT_UNLINKED=false` in production** - REQUIRED mode should require anchored citations
2. **Enable in QA/staging for testing** - Helps validate extraction logic
3. **Monitor `grounded_evidence_unavailable` flag** - Useful for dashboards
4. **Use current/past queries for testing** - Future queries may return empty evidence

## Files Modified
- `app/llm/adapters/vertex_adapter.py` - Threading, status reasons, audit
- `app/llm/unified_llm_adapter.py` - Evidence unavailable flag
- `ADAPTER_FIXES_250901.md` - Documentation updates
- `test_citation_validation_current.py` - New test suite

## Metrics to Monitor
- `grounded_evidence_unavailable` - When grounding works but no anchored citations
- `citations_status_reason` - Distinguishes provider vs extraction issues
- `anchored_citations_count` vs `unlinked_sources_count` - Citation quality
- `tool_call_count` - Grounding tool invocation rate

## Next Steps
1. Deploy to staging for validation
2. Monitor telemetry for citation patterns
3. Consider enabling unlinked emission in QA
4. Investigate Gemini's lack of anchored citations with Google