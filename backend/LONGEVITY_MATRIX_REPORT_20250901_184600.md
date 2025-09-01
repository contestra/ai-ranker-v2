# Longevity News Test Matrix Report

**Generated:** 2025-09-01T18:46:00.232529  
**Prompt:** "what was the top longevity and life-extension news during August, 2025"

## Executive Summary

- **Total Tests:** 16
- **Successful:** 16 (100.0%)
- **Failed:** 0 (0.0%)

## Results by Configuration

### OpenAI - United States (4 tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
| gpt-5 (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gpt-5 (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |
| gpt-5-chat-latest (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gpt-5-chat-latest (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |


### OpenAI - Germany (4 tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
| gpt-5 (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gpt-5 (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |
| gpt-5-chat-latest (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gpt-5-chat-latest (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |


### Vertex/Gemini - United States (4 tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
| gemini-2.5-pro (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gemini-2.5-pro (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |
| gemini-2.5-pro (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gemini-2.5-pro (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |


### Vertex/Gemini - Germany (4 tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
| gemini-2.5-pro (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gemini-2.5-pro (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |
| gemini-2.5-pro (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gemini-2.5-pro (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |


## Analysis

### Grounding Effectiveness
- Grounded requests: 8
- Actually grounded: 0 (0.0%)


### ALS Impact
- Average response with ALS: 0 chars
- Average response without ALS: 0 chars


### Citation Extraction
- Grounded tests with citations: 0


## Response Samples

### OpenAI US Grounded with ALS

```

```

### OpenAI DE Grounded with ALS

```

```

### Vertex US Grounded with ALS

```

```

### Vertex DE Grounded with ALS

```

```



## Raw Test Data

<details>
<summary>Click to expand JSON data</summary>

```json
{
  "timestamp": "2025-09-01T18:46:00.232529",
  "prompt": "what was the top longevity and life-extension news during August, 2025",
  "results": [
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "US",
        "grounded": true,
        "als": true
      },
      "config_name": "openai_gpt_5_US_grounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.2887248992919922
    },
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "US",
        "grounded": true,
        "als": false
      },
      "config_name": "openai_gpt_5_US_grounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.152587890625
    },
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5-chat-latest",
        "country": "US",
        "grounded": false,
        "als": true
      },
      "config_name": "openai_gpt_5_chat_latest_US_ungrounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.4558563232421875
    },
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5-chat-latest",
        "country": "US",
        "grounded": false,
        "als": false
      },
      "config_name": "openai_gpt_5_chat_latest_US_ungrounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.225067138671875
    },
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "DE",
        "grounded": true,
        "als": true
      },
      "config_name": "openai_gpt_5_DE_grounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.40340423583984375
    },
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5",
        "country": "DE",
        "grounded": true,
        "als": false
      },
      "config_name": "openai_gpt_5_DE_grounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.1475811004638672
    },
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5-chat-latest",
        "country": "DE",
        "grounded": false,
        "als": true
      },
      "config_name": "openai_gpt_5_chat_latest_DE_ungrounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.21004676818847656
    },
    {
      "config": {
        "vendor": "openai",
        "model": "gpt-5-chat-latest",
        "country": "DE",
        "grounded": false,
        "als": false
      },
      "config_name": "openai_gpt_5_chat_latest_DE_ungrounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.12946128845214844
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": true,
        "als": true
      },
      "config_name": "vertex_gemini_2_5_pro_US_grounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.22554397583007812
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": true,
        "als": false
      },
      "config_name": "vertex_gemini_2_5_pro_US_grounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.10442733764648438
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": false,
        "als": true
      },
      "config_name": "vertex_gemini_2_5_pro_US_ungrounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.21719932556152344
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "US",
        "grounded": false,
        "als": false
      },
      "config_name": "vertex_gemini_2_5_pro_US_ungrounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.12564659118652344
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "DE",
        "grounded": true,
        "als": true
      },
      "config_name": "vertex_gemini_2_5_pro_DE_grounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.1800060272216797
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "DE",
        "grounded": true,
        "als": false
      },
      "config_name": "vertex_gemini_2_5_pro_DE_grounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.11754035949707031
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "DE",
        "grounded": false,
        "als": true
      },
      "config_name": "vertex_gemini_2_5_pro_DE_ungrounded_ALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.18978118896484375
    },
    {
      "config": {
        "vendor": "vertex",
        "model": "gemini-2.5-pro",
        "country": "DE",
        "grounded": false,
        "als": false
      },
      "config_name": "vertex_gemini_2_5_pro_DE_ungrounded_noALS",
      "success": true,
      "error": null,
      "response_length": 0,
      "metadata": {
        "grounded_effective": false,
        "citations_count": 0,
        "anchored_citations": 0,
        "unlinked_sources": 0,
        "tool_calls": 0,
        "response_api": null,
        "model_adjusted": false,
        "original_model": null,
        "feature_flags": {},
        "runtime_flags": {},
        "why_not_grounded": null,
        "extraction_path": null
      },
      "usage": {},
      "latency_ms": 0.1289844512939453
    }
  ]
}
```

</details>

---
*Generated by Longevity News Test Matrix*
