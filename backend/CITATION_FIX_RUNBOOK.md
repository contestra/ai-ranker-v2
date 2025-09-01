# Citation Extraction Fix - Pre-GA Runbook

## Executive Summary
Fixed two critical issues in Vertex/Gemini citation extraction:
1. **Ungrounded retry regression**: Retry tokens were < first attempt, causing empty responses
2. **Missing citations**: Citations at candidate level and dict-only views were being skipped

## Fixes Implemented

### 1. Core Extraction Improvements
- ✅ **Index-driven union-of-views**: Process `max(len(typed_candidates), len(dict_candidates))`
- ✅ **Fixed early-continue bug**: Always consult dict view even when typed candidates have None metadata
- ✅ **Candidate-level scanning**: Check both `groundingMetadata` and `citationMetadata` at candidate level
- ✅ **Anchored vs unlinked tracking**: Separate tracking, always flush unlinked sources
- ✅ **Retry token fix**: Ensure `retry_max_tokens >= max(first_attempt*2, 3000, max_tokens_used)`, capped at 8192

### 2. Test Coverage
- 20 tests passing (8 original + 12 parametrized)
- 5 fixture files covering all citation formats
- Centralized test helpers for consistent mocking

## Ship-Readiness Checklist

### ✅ Completed
- [x] Index-driven extraction handles typed+dict views
- [x] Candidate-level citationMetadata scanning
- [x] Anchored vs unlinked source separation
- [x] Comprehensive test suite (20/20 passing)
- [x] Retry token budget fix

### ⏳ Pre-Deployment Validation
- [ ] **Two-step invariants**: Verify `two_step_used=true`, `step2_tools_invoked=false`, `step2_source_ref = sha256(step1_text)`
- [ ] **Ungrounded regression**: Confirm `retry_max_tokens ≥ first_attempt_max_tokens`
- [ ] **Anchored citations**: At least 1 anchored citation on grounded runs
- [ ] **Typed+dict union**: Test typed candidates with None metadata
- [ ] **OpenAI parity**: Verify REQUIRED fail-closes without hosted search

## Canary Deployment Plan

### Phase 1: 5% Traffic (24-48h)
```yaml
feature_flags:
  CITATION_EXTRACTOR_V2: 0.05  # Buckets [0, 0.05) get V2 (exactly 5%)
  TEXT_HARVEST_AUTO_ONLY: false  # AUTO-only when enabled
  UNGROUNDED_RETRY_POLICY: "aggressive"
  CITATIONS_EXTRACTOR_ENABLE: true  # Master switch
  CITATION_EXTRACTOR_ENABLE_LEGACY: true  # Allow fallback
```

**Flag Precedence:**
1. `CITATIONS_EXTRACTOR_ENABLE=false` → disables all extraction (emergency kill)
2. Otherwise, `CITATION_EXTRACTOR_V2` controls percentage (clamped to [0,1])
3. `CITATION_EXTRACTOR_ENABLE_LEGACY` controls fallback availability

**Monitor**:
- `anchored_citations_count ≥ 1` for >70% of grounded calls
- `tool_call_count>0 && anchored_citations_count==0` rate <2%
- p95 latency within 110% of baseline

### Phase 2: 50% Traffic (24-48h)
```yaml
feature_flags:
  CITATION_EXTRACTOR_V2: 0.50
```

### Phase 3: GA
```yaml
feature_flags:
  CITATION_EXTRACTOR_V2: 1.00
```

## A/B Bucketing Strategy

### Stable Key Selection
- **Primary**: `tenant_id` (stable across all requests from same tenant)
- **Fallback**: `account_id` (if no tenant_id available)
- **Optional**: `template_id` (for per-template canaries)
- **Never use**: `request_id` (changes per request, breaks stickiness)

### Boundary Rule
- Bucket **strictly less than** threshold routes to V2
- Example: `CITATION_EXTRACTOR_V2=0.05` means buckets [0, 0.05) get V2 (exactly 5%)
- Bucket value computed via MD5(stable_key) → float in [0, 1)

### REQUIRED Mode Semantics
- Even with fallback to legacy, REQUIRED **fail-closes** unless anchored citations found
- Legacy URLs without anchors do NOT satisfy REQUIRED
- Step-2 JSON reshape remains unaffected (tools-off, attestation unchanged)

## Telemetry & Monitoring

### Metrics to Track
```python
metadata = {
    # Core counts
    "anchored_citations_count": int,
    "unlinked_sources_count": int,
    
    # Shape distribution
    "citations_shape_set": ["direct_uris", "v1_join", "legacy_attributions"],
    
    # Failure analysis
    "why_not_grounded": str,  # When AUTO proceeds without anchors
    
    # View audit (when tools>0 & anchored==0)
    "typed_candidates_count": int,
    "dict_candidates_count": int,
    "candidate_citation_meta_preview": dict  # Size-capped to 1KB
}
```

### Alert Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| Anchored rate (grounded calls) | <70% | <50% |
| Tools>0 & anchored==0 rate | >2% | >5% |
| p95 latency increase | >10% | >25% |
| REQUIRED failure rate | >5% | >10% |

## Edge Case Testing

### Before GA (15-min manual tests)
1. **Volume test**: 50-100 citedSources + 30 citations
2. **Redirect chains**: 3-4 hop redirectors, verify resolver caps
3. **URL normalization**: Non-HTTP URIs, fragments, tracking params
4. **Mismatched lengths**: `len(typed)=1, len(dict)=3`
5. **Legacy-only**: URLs present, REQUIRED fails without anchors

## Policy Definitions

### REQUIRED Mode
- **Pass**: ≥1 anchored citation (direct URI or JOINed sourceId→citedSource)
- **Fail**: Only unlinked/legacy/text-harvest sources found
- **Behavior**: Fail-closed, no text harvest allowed

### AUTO Mode
- **Pass**: Any evidence (anchored, unlinked, or text-harvest)
- **Fallback**: May proceed without citations, populate `why_not_grounded`
- **Behavior**: Best-effort, text harvest allowed as last resort

## Quick Troubleshooting

### "tools>0 but citations=0"
1. Check `candidate_citation_meta_preview` in logs
2. Verify dict view: `dict_candidates_count > 0`?
3. Check metadata location: candidate-level vs grounding-level
4. Verify field names: camelCase vs snake_case

### "Typed candidates blocking dict view"
- Symptom: `typed_candidates_count > 0`, citations = 0
- Fix: Already implemented - index-driven iteration processes both views

### "Unlinked sources not appearing"
- Symptom: citedSources present but not in output
- Fix: Already implemented - always flush unlinked sources

## Code Locations

- **Main extractor**: `/app/llm/adapters/vertex_adapter.py::_extract_vertex_citations()`
- **Retry logic**: `/app/llm/adapters/vertex_adapter.py` lines 1564-1570
- **Tests**: `/tests/test_vertex_citations*.py`
- **Fixtures**: `/tests/fixtures/fixture*.json`

## Rollback Plan

If issues arise:
1. Set `CITATION_EXTRACTOR_V2=0.00` immediately
2. Check logs for `candidate_citation_meta_preview`
3. File bug with response shape samples
4. Revert commit if structural issues found

## Post-GA Roadmap

1. **Week 1-2**: Monitor telemetry, tune alert thresholds
2. **Week 3-4**: Enable text harvest for AUTO mode
3. **Month 2**: Sunset legacy paths if <0.5% usage
4. **Month 3**: Add resolver cache with LRU + short TTL

## FAQ

**Q: Why separate anchored vs unlinked?**
A: REQUIRED mode must have concrete evidence (anchored). Unlinked sources are supplementary.

**Q: When does text harvest run?**
A: Only in AUTO mode, never in REQUIRED. Must be explicitly enabled via flag.

**Q: What if typed and dict candidates have different lengths?**
A: We process `max(len(typed), len(dict))` indices, no data lost.

**Q: How are duplicates handled?**
A: URL normalization + deduplication map. First occurrence wins for title/snippet.

## Contact

- **Owner**: AI Ranker Team
- **Slack**: #ai-ranker-alerts
- **Oncall**: See PagerDuty schedule

---
*Last Updated: 2025-09-01*
*Version: 1.0.0*