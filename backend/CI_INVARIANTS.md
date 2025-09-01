# CI Invariants - Critical Rules That Must Never Break

## OpenAI Model Routing Invariant

**Rule**: OpenAI requests MUST be routed based on grounding requirement:
- **Grounded → `gpt-5`** (supports web_search tools)
- **Ungrounded → `gpt-5-chat-latest`** (conversational variant)

**Why**: `gpt-5-chat-latest` does NOT support hosted web_search tools. If grounded requests are sent to it, they will fail with "hosted tool not supported" errors.

### One-Liner Test
```python
# Add to any test file or CI script:
assert grounded_model == "gpt-5" and ungrounded_model == "gpt-5-chat-latest"
```

### Full Test Suite
```bash
pytest tests/test_openai_routing_invariant.py
```

### Required Environment
```bash
export MODEL_ADJUST_FOR_GROUNDING=true  # MUST be true in production
```

## Vertex Citation Extraction Invariant

**Rule**: When Vertex/Gemini returns tool calls, citations MUST be extracted.

**Test**:
```python
if tool_call_count > 0:
    assert anchored_citations_count > 0 or unlinked_sources_count > 0
```

## Resolver Budget Invariant

**Rule**: Citation resolution MUST respect budgets:
- Max 8 URLs per request
- Max 3 seconds total resolution time

**Test**:
```python
assert resolved_count <= 8
assert total_time_ms <= 3000
```

## Feature Flag Invariant

**Rule**: Kill switch MUST override all other flags:
```python
if not CITATIONS_EXTRACTOR_ENABLE:
    assert no_extraction_attempted
```

## ALS Propagation Invariant

**Rule**: ALS context MUST propagate through async calls:
```python
assert als_context_before == als_context_after
```

---

## CI Integration

Add to `.github/workflows/ci.yml`:
```yaml
- name: Run invariant tests
  run: |
    export MODEL_ADJUST_FOR_GROUNDING=true
    pytest tests/test_openai_routing_invariant.py
    pytest tests/test_resolver_budget.py
```

## Monitoring

These invariants should also be monitored in production:
- Alert if grounded requests use wrong model
- Alert if tool calls produce no citations
- Alert if resolver exceeds budgets

---
*Last Updated: 2025-09-01*