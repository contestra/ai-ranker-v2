# End-to-End Longevity Test Report

**Generated:** 2025-09-01T15:11:02.697899  
**Test Prompt:** "today is 31st August, 2025 - tell me the top longevity news of August"

## Executive Summary

- **Total Tests:** 12
- **Successful:** 0 (0.0%)
- **Failed:** 12 (100.0%)
- **Average Latency:** 0ms
- **Grounding Success Rate:** 0.0%
- **Tests with Citations:** 0 (0.0%)
- **Average Citations (when present):** 0.0

## Detailed Results by Configuration

### OpenAI Results (6 tests)

| Configuration | Status | Latency | Citations | Grounding | Response API | Model |
|--------------|--------|---------|-----------|-----------|--------------|-------|
| openai_gpt_5_US_grounded_ALS_AUTO | ❌ | 0ms | 0 (0+0) | ❌ | N/A | gpt-5 |
| openai_gpt_5_US_grounded_noALS_AUTO | ❌ | 0ms | 0 (0+0) | ❌ | N/A | gpt-5 |
| openai_gpt_5_DE_grounded_ALS_AUTO | ❌ | 0ms | 0 (0+0) | ❌ | N/A | gpt-5 |
| openai_gpt_5_US_grounded_ALS_REQUIRED | ❌ | 0ms | 0 (0+0) | ❌ | N/A | gpt-5 |
| openai_gpt_5_chat_latest_US_ungrounded_ALS | ❌ | 0ms | 0 (0+0) | N/A | N/A | gpt-5-chat-latest |
| openai_gpt_5_chat_latest_US_ungrounded_noALS | ❌ | 0ms | 0 (0+0) | N/A | N/A | gpt-5-chat-latest |


### Vertex/Gemini Results (6 tests)

| Configuration | Status | Latency | Citations | Grounding | Response API | Tool Calls |
|--------------|--------|---------|-----------|-----------|--------------|------------|
| vertex_gemini_2.5_pro_US_grounded_ALS_AUTO | ❌ | 0ms | 0 (0+0) | ❌ | N/A | 0 |
| vertex_gemini_2.5_pro_US_grounded_noALS_AUTO | ❌ | 0ms | 0 (0+0) | ❌ | N/A | 0 |
| vertex_gemini_2.5_pro_DE_grounded_ALS_AUTO | ❌ | 0ms | 0 (0+0) | ❌ | N/A | 0 |
| vertex_gemini_2.5_pro_US_grounded_ALS_REQUIRED | ❌ | 0ms | 0 (0+0) | ❌ | N/A | 0 |
| vertex_gemini_2.5_pro_US_ungrounded_ALS | ❌ | 0ms | 0 (0+0) | N/A | N/A | 0 |
| vertex_gemini_2.5_pro_US_ungrounded_noALS | ❌ | 0ms | 0 (0+0) | N/A | N/A | 0 |


## Grounding Mode Analysis

### AUTO Mode Performance
- Tests: 6
- Grounded Successfully: 0 (0.0%)
- Average Citations: 0.0


### REQUIRED Mode Performance
- Tests: 2
- Grounded Successfully: 0 (0.0%)


## Telemetry Contract Verification

### Response API Labels

**Openai:**
- None: 4 tests

**Vertex:**
- None: 4 tests


## Feature Flags & A/B Testing

### Active Feature Flags


## Errors and Failures

### openai_gpt_5_US_grounded_ALS_AUTO
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### openai_gpt_5_US_grounded_noALS_AUTO
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### openai_gpt_5_DE_grounded_ALS_AUTO
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### openai_gpt_5_US_grounded_ALS_REQUIRED
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### openai_gpt_5_chat_latest_US_ungrounded_ALS
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### openai_gpt_5_chat_latest_US_ungrounded_noALS
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### vertex_gemini_2.5_pro_US_grounded_ALS_AUTO
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### vertex_gemini_2.5_pro_US_grounded_noALS_AUTO
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### vertex_gemini_2.5_pro_DE_grounded_ALS_AUTO
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### vertex_gemini_2.5_pro_US_grounded_ALS_REQUIRED
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### vertex_gemini_2.5_pro_US_ungrounded_ALS
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'

### vertex_gemini_2.5_pro_US_ungrounded_noALS
**Error:** 'UnifiedLLMAdapter' object has no attribute 'execute'



## Raw Test Data

<details>
<summary>Click to expand JSON data</summary>

```json
{
  "timestamp": "2025-09-01T15:11:02.697899",
  "prompt": "today is 31st August, 2025 - tell me the top longevity news of August",
  "total_tests": 12,
  "results": [
    {
      "config_name": "openai_gpt_5_US_grounded_ALS_AUTO",
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "US",
        "grounded": true,
        "als": true,
        "mode": "AUTO"
      },
      "latency_ms": 0.0016689300537109375,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "AUTO",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gpt-5",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "openai_gpt_5_US_grounded_noALS_AUTO",
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "US",
        "grounded": true,
        "als": false,
        "mode": "AUTO"
      },
      "latency_ms": 0.003337860107421875,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "AUTO",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gpt-5",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "openai_gpt_5_DE_grounded_ALS_AUTO",
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "DE",
        "grounded": true,
        "als": true,
        "mode": "AUTO"
      },
      "latency_ms": 0.0035762786865234375,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "AUTO",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gpt-5",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "openai_gpt_5_US_grounded_ALS_REQUIRED",
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "US",
        "grounded": true,
        "als": true,
        "mode": "REQUIRED"
      },
      "latency_ms": 0.0045299530029296875,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "REQUIRED",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gpt-5",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "openai_gpt_5_chat_latest_US_ungrounded_ALS",
      "config": {
        "vendor": "openai",
        "model": "gpt-5-chat-latest",
        "country": "US",
        "grounded": false,
        "als": true,
        "mode": null
      },
      "latency_ms": 0.007152557373046875,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": false,
        "effective": false,
        "mode": null,
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gpt-5-chat-latest",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "openai_gpt_5_chat_latest_US_ungrounded_noALS",
      "config": {
        "vendor": "openai",
        "model": "gpt-5-chat-latest",
        "country": "US",
        "grounded": false,
        "als": false,
        "mode": null
      },
      "latency_ms": 0.00476837158203125,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": false,
        "effective": false,
        "mode": null,
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gpt-5-chat-latest",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "vertex_gemini_2.5_pro_US_grounded_ALS_AUTO",
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": true,
        "als": true,
        "mode": "AUTO"
      },
      "latency_ms": 0.0030994415283203125,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "AUTO",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gemini-2.5-pro",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "vertex_gemini_2.5_pro_US_grounded_noALS_AUTO",
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": true,
        "als": false,
        "mode": "AUTO"
      },
      "latency_ms": 0.003337860107421875,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "AUTO",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gemini-2.5-pro",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "vertex_gemini_2.5_pro_DE_grounded_ALS_AUTO",
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "DE",
        "grounded": true,
        "als": true,
        "mode": "AUTO"
      },
      "latency_ms": 0.0057220458984375,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "AUTO",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gemini-2.5-pro",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "vertex_gemini_2.5_pro_US_grounded_ALS_REQUIRED",
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": true,
        "als": true,
        "mode": "REQUIRED"
      },
      "latency_ms": 0.0035762786865234375,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": true,
        "effective": false,
        "mode": "REQUIRED",
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gemini-2.5-pro",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "vertex_gemini_2.5_pro_US_ungrounded_ALS",
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": false,
        "als": true,
        "mode": null
      },
      "latency_ms": 0.0035762786865234375,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": false,
        "effective": false,
        "mode": null,
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gemini-2.5-pro",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    },
    {
      "config_name": "vertex_gemini_2.5_pro_US_ungrounded_noALS",
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": false,
        "als": false,
        "mode": null
      },
      "latency_ms": 0.0040531158447265625,
      "success": false,
      "error": "'UnifiedLLMAdapter' object has no attribute 'execute'",
      "response_length": 0,
      "citations": {
        "total": 0,
        "anchored": 0,
        "unlinked": 0
      },
      "grounding": {
        "requested": false,
        "effective": false,
        "mode": null,
        "why_not_grounded": null,
        "response_api": null
      },
      "model": {
        "requested": "gemini-2.5-pro",
        "adjusted": false,
        "original": null
      },
      "tool_calls": 0,
      "feature_flags": {},
      "runtime_flags": {}
    }
  ]
}
```

</details>

## Test Matrix Configuration

The following configurations were tested:

1. **openai/gpt-5** - Country: US, Grounded: True, ALS: True, Mode: AUTO
2. **openai/gpt-5** - Country: US, Grounded: True, ALS: False, Mode: AUTO
3. **openai/gpt-5** - Country: DE, Grounded: True, ALS: True, Mode: AUTO
4. **openai/gpt-5** - Country: US, Grounded: True, ALS: True, Mode: REQUIRED
5. **openai/gpt-5-chat-latest** - Country: US, Grounded: False, ALS: True
6. **openai/gpt-5-chat-latest** - Country: US, Grounded: False, ALS: False
7. **vertex/gemini-2.5-pro** - Country: US, Grounded: True, ALS: True, Mode: AUTO
8. **vertex/gemini-2.5-pro** - Country: US, Grounded: True, ALS: False, Mode: AUTO
9. **vertex/gemini-2.5-pro** - Country: DE, Grounded: True, ALS: True, Mode: AUTO
10. **vertex/gemini-2.5-pro** - Country: US, Grounded: True, ALS: True, Mode: REQUIRED
11. **vertex/gemini-2.5-pro** - Country: US, Grounded: False, ALS: True
12. **vertex/gemini-2.5-pro** - Country: US, Grounded: False, ALS: False


## Conclusions

### Key Findings

1. **Citation Extraction:** ⚠️ No citations found - requires investigation
2. **Grounding Effectiveness:** 0.0% success rate for grounded requests
3. **Model Routing:** 0/4 OpenAI grounded requests correctly routed
4. **Telemetry Contract:** ✅ All grounded calls have response_api


### Recommendations

- Investigate 12 test failures
- Improve grounding success rate (currently 0.0%)
- Review citation extraction (average 0.0 is low)


---
*Generated by E2E Longevity Test Suite*
