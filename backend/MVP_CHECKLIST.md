# Citation Extraction MVP Checklist

## 🚦 Go/No-Go Gates for Production

### A) Before Production (MVP Requirements)

#### 1. ✅ Core Fixes (COMPLETE)
- [x] Ungrounded retry token budget fix
- [x] Candidate-level citation scanning
- [x] Index-driven union-of-views
- [x] Anchored vs unlinked separation
- [x] Text-harvest fallback (AUTO-only)
- [x] Forensics logging
- [x] OpenAI tool_result parsing
- [x] 20 tests passing
- [x] ADC auth fixed for Vertex (user-confirmed)

#### 2. ✅ Core Validation (COMPLETE)
**Verified:**
- [x] ADC auth working for Vertex (user-confirmed)
- [x] OpenAI fallback for unsupported tools working
- [x] Vertex citation extraction functional
- [x] Ungrounded responses produce non-empty output
- [x] Feature flags wired and tested
- [x] Resolver budgets enforced (max 8 URLs, 3s stopwatch)

#### 3. ✅ Feature Flags (COMPLETE)
**Implemented flags:**
```yaml
CITATION_EXTRACTOR_V2: 0.0  # Start at 0, then 0.05 → 0.50 → 1.00
CITATION_EXTRACTOR_ENABLE_LEGACY: true
UNGROUNDED_RETRY_POLICY: "aggressive"
TEXT_HARVEST_AUTO_ONLY: false  # Enable after validation
CITATIONS_EXTRACTOR_ENABLE: true  # Kill switch
MODEL_ADJUST_FOR_GROUNDING: true  # Route grounded to gpt-5
```
- [x] Flags wired and tested
- [x] Flag states emitted in response metadata
- [x] A/B selection with tenant_id/account_id bucketing
- [x] Rollback tested (flip to false)

#### 4. ⏳ Monitoring & Alerts
**Metrics per call:**
- [ ] `anchored_citations_count`
- [ ] `unlinked_sources_count`
- [ ] `citations_shape_set`
- [ ] `tool_call_count`
- [ ] `grounded_effective`
- [ ] `why_not_grounded`

**Alert thresholds:**
| Alert | Condition | Action |
|-------|-----------|--------|
| Citation failure | tools>0 & anchored==0 > 5% for 15min | Page |
| Extractor error | Any exception in 5min | Page |
| Latency | Grounded p95 > 30s for 15min | Warn |

#### 5. ⏳ Canary Rollout
**Traffic gates:**
- [ ] 5-10% (24-48h) → Check metrics
- [ ] 50% (24-48h) → Check metrics
- [ ] 100% GA

**Advance criteria:**
- Tools>0 & anchored==0 ≤ 2%
- Zero extractor errors
- p95 ≤ 25s, p50 ≤ 10s

#### 6. ✅ Resolver Budgets (COMPLETE)
- [x] Max 8 URLs per request
- [x] Max 2s resolve time  
- [x] 3s total stopwatch
- [x] Truncated marked as `source_type="redirect_only"`
- [x] Batch resolution with `resolve_citations_with_budget()`
- [x] Tests verify budget enforcement

---

## 📊 Decision Gates

### Canary → 50% Gate
✅ Proceed when ALL true for 24h:
- Tools>0 & anchored==0 ≤ 2%
- Zero extractor exceptions
- Grounded p95 ≤ 25s
- Grounded p50 ≤ 10s

### 50% → GA Gate
✅ Proceed when above holds for additional 24-48h

### Emergency Rollback
🚨 Rollback if ANY occur:
- Tools>0 & anchored==0 > 10%
- Extractor error rate > 1%
- p95 latency > 45s
- REQUIRED failure rate > 15%

---

## 🧪 Risk Validation Tests

Run these once before canary:

1. **Typed/dict union**: Typed candidates with None metadata → citations extracted
2. **Mixed sources**: Anchored counted, unlinked emitted but not counted
3. **Legacy only**: URLs present, REQUIRED fails
4. **AUTO harvest**: Only when tools>0 & anchored==0, never satisfies REQUIRED
5. **Redirect chains**: Stop at 8 URLs or 2s
6. **Two-step**: Gemini grounded+JSON maintains invariants

---

## 📈 Week 1 Post-Deploy (Nice-to-Have)

- [ ] Redirect cache (LRU, 10-15min TTL)
- [ ] Dashboard with shape distribution
- [ ] Shapes Gallery documentation
- [ ] A/B testing infrastructure

---

## 👥 Ownership

- **Team**: AI Ranker
- **On-call**: See PagerDuty
- **Slack**: #ai-ranker-alerts
- **Runbook**: CITATION_FIX_RUNBOOK.md

---

## ✅ Final Sign-Off

**Engineering Lead**: _______________  Date: _______________

**Product Owner**: _______________  Date: _______________

**SRE/Ops**: _______________  Date: _______________

---

*Last Updated: 2025-09-01*
*Status: Ready for MVP validation*