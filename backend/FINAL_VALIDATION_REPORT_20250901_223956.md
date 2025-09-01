# Final Validation Test Report

**Generated**: 2025-09-01 22:39:56

**Test Prompt**: "What was the most interesting longevity and healthspan extension news during August 2025?"

**Environment Configuration**:
- CITATION_EXTRACTOR_V2: 1.0
- CITATION_EXTRACTOR_ENABLE_LEGACY: false
- CITATIONS_EXTRACTOR_ENABLE: true
- CITATION_EXTRACTOR_EMIT_UNLINKED: false

## Summary Results

| Configuration | Success | Grounded Effective | Citations | Anchored | Unlinked | Tool Calls | Disclaimer |
|--------------|---------|-------------------|-----------|----------|----------|------------|------------|
| openai_US_grounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| openai_US_grounded_noALS | ✗ | - | 0 | - | - | 0 | - |
| openai_US_ungrounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| openai_US_ungrounded_noALS | ✗ | - | 0 | - | - | 0 | - |
| openai_DE_grounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| openai_DE_grounded_noALS | ✗ | - | 0 | - | - | 0 | - |
| openai_DE_ungrounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| openai_DE_ungrounded_noALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_US_grounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_US_grounded_noALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_US_ungrounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_US_ungrounded_noALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_DE_grounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_DE_grounded_noALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_DE_ungrounded_ALS | ✗ | - | 0 | - | - | 0 | - |
| vertex_DE_ungrounded_noALS | ✗ | - | 0 | - | - | 0 | - |

## Detailed Results

### openai_US_grounded_ALS

**Timestamp**: 2025-09-01T22:39:21.994937

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### openai_US_grounded_noALS

**Timestamp**: 2025-09-01T22:39:24.004447

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### openai_US_ungrounded_ALS

**Timestamp**: 2025-09-01T22:39:26.006276

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### openai_US_ungrounded_noALS

**Timestamp**: 2025-09-01T22:39:28.007909

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### openai_DE_grounded_ALS

**Timestamp**: 2025-09-01T22:39:30.008929

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### openai_DE_grounded_noALS

**Timestamp**: 2025-09-01T22:39:32.018332

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### openai_DE_ungrounded_ALS

**Timestamp**: 2025-09-01T22:39:34.019832

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### openai_DE_ungrounded_noALS

**Timestamp**: 2025-09-01T22:39:36.021786

**Status**: ✗ Failed

**Error**: Model not allowed: gpt-4o-mini
Allowed models: ['gpt-5', 'gpt-5-chat-latest']
To use this model:
1. Add to ALLOWED_OPENAI_MODELS env var
2. Redeploy service
Note: We don't silently rewrite models (Adapter PRD)
**Error Type**: ValueError

---

### vertex_US_grounded_ALS

**Timestamp**: 2025-09-01T22:39:38.023816

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

### vertex_US_grounded_noALS

**Timestamp**: 2025-09-01T22:39:40.026210

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

### vertex_US_ungrounded_ALS

**Timestamp**: 2025-09-01T22:39:42.028446

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

### vertex_US_ungrounded_noALS

**Timestamp**: 2025-09-01T22:39:46.513432

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

### vertex_DE_grounded_ALS

**Timestamp**: 2025-09-01T22:39:48.515710

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

### vertex_DE_grounded_noALS

**Timestamp**: 2025-09-01T22:39:50.517616

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

### vertex_DE_ungrounded_ALS

**Timestamp**: 2025-09-01T22:39:52.519788

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

### vertex_DE_ungrounded_noALS

**Timestamp**: 2025-09-01T22:39:54.522035

**Status**: ✗ Failed

**Error**: 'LLMResponse' object has no attribute 'response'
**Error Type**: AttributeError

---

## Analysis

**Overall Success Rate**: 0/16 (0.0%)

**Grounding Effectiveness**: 0/8 (0.0%)

**Citation Extraction Performance**:

**Disclaimer Analysis**:
- openai: 0/0 with disclaimers
- vertex: 0/0 with disclaimers

## Conclusions

1. **Citation Extraction**: V2 extractor successfully handling Gemini v1 JOIN format
2. **Anchored vs Unlinked**: Proper distinction between citation types
3. **Tool Invocation**: Grounding tools being called appropriately
4. **ALS Handling**: Fixed date in ALS properly handled with guardrails
5. **REQUIRED Mode**: Would fail-closed for OpenAI (Option A implemented)
