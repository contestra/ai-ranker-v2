# Citation Extraction System - Release Documentation

## 🎯 Overview
Comprehensive fix for citation extraction in Vertex/Gemini and OpenAI adapters, addressing critical issues that caused 0 citations despite multiple tool calls.

## 🔧 Core Fixes Implemented

### 1. **Vertex Citation Extraction** ✅
- **Problem**: Citations at wrong response hierarchy level, early-continue bug skipping dict views
- **Solution**: Index-driven union-of-views, candidate-level scanning, anchored vs unlinked separation
- **Files Modified**: 
  - `app/llm/adapters/vertex_adapter.py`
  - Added `_extract_vertex_citations()` with comprehensive extraction
  - Added `_extract_vertex_citations_legacy()` for A/B testing

### 2. **Ungrounded Retry Token Budget** ✅
- **Problem**: Retry attempts had fewer tokens than first attempt, causing empty responses
- **Solution**: Ensure `retry_max_tokens >= max(first_attempt*2, 3000, max_tokens_used)`
- **Impact**: Prevents empty responses on ungrounded retries

### 3. **OpenAI Model Routing** ✅
- **Problem**: `gpt-5-chat-latest` doesn't support web_search tools
- **Solution**: Route grounded→`gpt-5`, ungrounded→`gpt-5-chat-latest`
- **Configuration**: `MODEL_ADJUST_FOR_GROUNDING=true` (required in production)
- **Documentation**: `OPENAI_MODEL_ROUTING.md`

### 4. **Citation Resolution Budgets** ✅
- **Problem**: Unbounded citation resolution could cause timeouts
- **Solution**: Max 8 URLs, 3s stopwatch, graceful truncation
- **Implementation**: `app/llm/citations/resolver.py`
  - `resolve_citations_with_budget()` enforces limits
  - Marks truncated as `source_type="redirect_only"`

### 5. **Feature Flags & A/B Testing** ✅
- **Implemented Flags**:
  - `CITATION_EXTRACTOR_V2`: Gradual rollout (0.0 → 0.05 → 0.50 → 1.00)
  - `CITATION_EXTRACTOR_ENABLE_LEGACY`: Fallback toggle
  - `CITATIONS_EXTRACTOR_ENABLE`: Master kill switch
  - `TEXT_HARVEST_AUTO_ONLY`: Text extraction fallback
  - `MODEL_ADJUST_FOR_GROUNDING`: OpenAI routing control
- **A/B Selection**: Sticky bucketing via MD5(tenant_id/account_id)
- **Files**: `app/core/config.py`, `app/llm/unified_llm_adapter.py`

## 📋 Test Coverage

### Unit Tests (33 tests total)
- `tests/test_vertex_citations_parametrized.py` - 12 parametrized tests
- `tests/test_citations.py` - 13 unified tests
- `tests/test_resolver_budget.py` - 4 budget tests
- `tests/test_openai_model_routing.py` - 5 routing invariants
- All tests passing ✅

### Test Fixtures
- `fixture_1_direct_uris.json` - Direct URI pattern
- `fixture_2_v1_join.json` - citationMetadata→citedSources JOIN
- `fixture_3_legacy_attributions.json` - Legacy grounding pattern
- `fixture_4_candidate_level.json` - Candidate-level metadata
- `fixture_5_mixed_patterns.json` - Multiple patterns combined

## 🚀 Deployment Strategy

### Phase 1: Canary (5% traffic, 24-48h)
```yaml
CITATION_EXTRACTOR_V2: 0.05
CITATION_EXTRACTOR_ENABLE_LEGACY: true
MODEL_ADJUST_FOR_GROUNDING: true
```

### Phase 2: Rollout (50% traffic, 24-48h)
```yaml
CITATION_EXTRACTOR_V2: 0.50
```

### Phase 3: GA (100% traffic)
```yaml
CITATION_EXTRACTOR_V2: 1.00
```

## 📊 Monitoring & Alerts

### Key Metrics
- `anchored_citations_count` - Anchored citations per response
- `unlinked_sources_count` - Unlinked sources found
- `tool_call_count` - Number of tool calls made
- `grounded_effective` - Whether grounding actually occurred
- `citations_shape_set` - Citation patterns detected

### Alert Thresholds
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Tools>0 & anchored==0 | >2% | >5% | Page on-call |
| Extractor errors | Any | >1% | Page on-call |
| p95 latency | >25s | >45s | Investigate |
| REQUIRED failures | >5% | >10% | Rollback |

## 🔒 CI Invariants

### OpenAI Routing Invariant
```python
# Grounded MUST use gpt-5, ungrounded MUST use gpt-5-chat-latest
assert grounded_model == "gpt-5"
assert ungrounded_model == "gpt-5-chat-latest"
```

### Resolver Budget Invariant
```python
assert resolved_count <= 8
assert total_time_ms <= 3000
```

### GitHub Actions
- `.github/workflows/invariant-tests.yml` - Automated invariant checks

## 📁 File Structure

```
backend/
├── app/
│   ├── llm/
│   │   ├── adapters/
│   │   │   ├── openai_adapter.py (modified)
│   │   │   └── vertex_adapter.py (modified)
│   │   ├── citations/
│   │   │   ├── __init__.py (new)
│   │   │   ├── resolver.py (new)
│   │   │   ├── redirectors.py (new)
│   │   │   ├── http_resolver.py (new)
│   │   │   └── domains.py (new)
│   │   └── unified_llm_adapter.py (modified)
│   └── core/
│       └── config.py (modified)
├── tests/
│   ├── fixtures/ (new test fixtures)
│   ├── test_citations.py (new)
│   ├── test_resolver_budget.py (new)
│   ├── test_openai_model_routing.py (new)
│   └── test_vertex_citations_parametrized.py (new)
└── docs/
    ├── CITATION_FIX_RUNBOOK.md
    ├── MVP_CHECKLIST.md
    ├── OPENAI_MODEL_ROUTING.md
    └── CI_INVARIANTS.md
```

## ✅ MVP Checklist Status

- [x] Core fixes (ungrounded retry, citation scanning, etc.)
- [x] 20+ tests passing
- [x] ADC auth working (user-confirmed)
- [x] Feature flags wired with metadata emission
- [x] A/B selection with tenant_id bucketing
- [x] Resolver budgets implemented
- [x] OpenAI model routing documented
- [x] CI invariants created

## 🚨 Emergency Rollback

If issues arise:
1. Set `CITATION_EXTRACTOR_V2=0.00` immediately
2. Check logs for `candidate_citation_meta_preview`
3. File bug with response shape samples
4. Revert commit if structural issues found

## 👥 Ownership

- **Team**: AI Ranker
- **Slack**: #ai-ranker-alerts
- **On-call**: See PagerDuty schedule
- **Documentation**: This file and linked runbooks

## 🔗 Related Documentation

- [CITATION_FIX_RUNBOOK.md](./CITATION_FIX_RUNBOOK.md) - Detailed technical runbook
- [MVP_CHECKLIST.md](./MVP_CHECKLIST.md) - Go/no-go gates
- [OPENAI_MODEL_ROUTING.md](./OPENAI_MODEL_ROUTING.md) - Model routing strategy
- [CI_INVARIANTS.md](./CI_INVARIANTS.md) - Critical invariants for CI

---
*Last Updated: 2025-09-01*
*Version: 1.0.0*
*Status: Ready for Production Deployment*