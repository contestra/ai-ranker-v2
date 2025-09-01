# Longevity News Test Matrix Report

**Generated:** 2025-09-01T18:45:02.116926  
**Prompt:** "what was the top longevity and life-extension news during August, 2025"

## Executive Summary

- **Total Tests:** 16
- **Successful:** 16 (100.0%)
- **Failed:** 0 (0.0%)

## Results by Configuration

### OpenAI - United States (4 tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
| gpt-5 (G:Yes) | ✅ | 1ms | 0 | ❌ | 0 | ✅ |
| gpt-5 (G:Yes) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |
| gpt-5-chat-latest (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ✅ |
| gpt-5-chat-latest (G:No) | ✅ | 0ms | 0 | ❌ | 0 | ❌ |


### OpenAI - Germany (4 tests)

| Config | Status | Latency | Response Length | Grounded Effective | Citations | ALS |
|--------|--------|---------|-----------------|-------------------|-----------|-----|
| gpt-5 (G:Yes) | ✅ | 9ms | 0 | ❌ | 0 | ✅ |
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
  "timestamp": "2025-09-01T18:45:02.116926",
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
      "latency_ms": 1.489877700805664
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
      "latency_ms": 0.23674964904785156
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
      "latency_ms": 0.19097328186035156
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
      "latency_ms": 0.12564659118652344
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
      "latency_ms": 8.772850036621094
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
      "latency_ms": 0.17213821411132812
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
      "latency_ms": 0.2872943878173828
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
      "latency_ms": 0.11444091796875
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
      "latency_ms": 0.23555755615234375
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
      "latency_ms": 0.12278556823730469
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
      "latency_ms": 0.179290771484375
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
      "latency_ms": 0.12612342834472656
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
      "latency_ms": 0.26869773864746094
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
      "latency_ms": 0.0972747802734375
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
      "latency_ms": 0.18668174743652344
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
      "latency_ms": 0.12111663818359375
    }
  ]
}
```

</details>

---
*Generated by Longevity News Test Matrix*
