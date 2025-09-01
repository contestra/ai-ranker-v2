# Adapter Improvement Plan - Based on ChatGPT Review
## September 1, 2025

## Executive Summary
ChatGPT's review confirms our adapters are working correctly. The Vertex "0 citations" issue is due to provider data availability for future-dated queries, not a bug. This plan implements recommended improvements for better observability and graceful degradation.

## Key Findings from ChatGPT Review
1. ✅ **All 16 tests passed** - 100% success rate
2. ✅ **Routing & enforcement logic is sound** - REQUIRED fails closed as designed
3. ✅ **OpenAI behavior correct** - Gracefully handles unsupported web_search
4. ✅ **Vertex grounding works** - Provider returns empty evidence for future queries
5. ✅ **ALS handling solid** - Deterministic and properly guarded

## Improvement Categories

### A. Observability & Graceful Degradation

#### 1. Thread tool_call_count to Citation Extractor
**Problem**: Unlinked emission relies on detecting function_call parts which may miss some cases
**Solution**: Pass tool_call_count from step-1 into the extractor
**Implementation**:
- Modify `_select_and_extract_citations()` to accept `tool_call_count` parameter
- Use `tool_call_count > 0` as reliable "tools_called" signal
- Enable unlinked emission in QA when `CITATION_EXTRACTOR_EMIT_UNLINKED=true`
- Keep anchored-only threshold for REQUIRED mode

#### 2. Refine Citation Status Reasons
**Current**: `citations_missing_despite_tool_calls`
**New Codes**:
- `provider_returned_empty_evidence` - Provider gave no chunks/joins
- `extractor_processing_error` - Actual extraction bug
- `grounding_evidence_unavailable` - Tools called but no anchors

#### 3. Enhanced Citations Audit
**Current**: Logs keys when tools>0 & citations=0
**Enhancement**: Include 1-2 sample items from grounding arrays (non-PII)
**Fields to Sample**:
- First grounding_chunk title/URL (if any)
- First retrieval query
- Tool invocation summary

### B. Runtime Behavior Improvements

#### 4. Telemetry Flag for Evidence Unavailable
**When**: `grounded_effective=true` but `anchored_citations=0`
**Add Flag**: `grounded_evidence_unavailable=true`
**Purpose**: Better alerting/analytics in AUTO mode
**Note**: REQUIRED already fails-closed (keep as-is)

### C. Test Harness Improvements

#### 5. Use Current/Past Queries for Validation
**Problem**: Future queries (Aug 2025) don't exercise JOIN/anchoring paths
**Solution**: Create test suite with:
- **Positive cases**: Current events, recent news (should get citations)
- **Negative case**: Keep one future-dated prompt to catch edge conditions
**Example Queries**:
- "What happened in the 2024 US presidential election?"
- "Latest developments in COVID-19 research"
- "Recent breakthroughs in AI technology"

#### 6. QA Gate for Unlinked Emission
**Test**: Run same 16 configs with `CITATION_EXTRACTOR_EMIT_UNLINKED=true`
**Purpose**: Verify extractor can list unlinked sources when available
**Production**: Keep OFF (REQUIRED requires anchored only)

## Implementation Priority

### Phase 1 - Core Improvements (High Priority)
1. Thread tool_call_count to extractor
2. Add refined citation status reasons
3. Add grounded_evidence_unavailable flag

### Phase 2 - Observability (Medium Priority)
4. Enhance citations audit with samples
5. Create current/past query test suite

### Phase 3 - Testing (Low Priority)
6. Add QA gate tests for unlinked emission

## Code Changes Required

### vertex_adapter.py
```python
# In detect_vertex_grounding():
metadata['tool_call_count'] = tool_call_count

# In _select_and_extract_citations():
def _select_and_extract_citations(response, metadata, tool_call_count=0):
    # Use tool_call_count for reliable tools_called detection
    tools_called = tool_call_count > 0
```

### unified_llm_adapter.py
```python
# Add new telemetry flag
if metadata.get('grounded_effective') and not metadata.get('anchored_citations_count'):
    metadata['grounded_evidence_unavailable'] = True
    
# Refine status reasons
if tool_calls > 0 and not citations:
    metadata['citations_status_reason'] = 'provider_returned_empty_evidence'
```

### Test Updates
- Create `test_citation_validation_current.py` with real-world queries
- Add environment variable tests with `CITATION_EXTRACTOR_EMIT_UNLINKED=true`

## Success Metrics
1. **Citation extraction rate** for current/past queries > 0
2. **Clear distinction** in telemetry between provider issues vs bugs
3. **No REQUIRED mode false positives** (keep fail-closed)
4. **Improved debugging** with audit samples

## Notes from ChatGPT
- "Your adapters are behaving correctly"
- "The Vertex '0 citations' is an upstream data availability artifact"
- "Keep anchored-only for REQUIRED"
- "Shift positive citation tests to current/past topics"

## Next Steps
1. Implement Phase 1 improvements
2. Test with current event queries
3. Deploy with telemetry monitoring
4. Iterate based on production metrics