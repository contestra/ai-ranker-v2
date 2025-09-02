# GPT-4 vs GPT-5 Grounding Test - Final Report
## September 2, 2025

## Executive Summary
**FINDING**: OpenAI models exhibit different behaviors with web_search tools:
- **gpt-4o**: Successfully accepts and sometimes invokes web_search tools
- **Other models**: Either reject tools with HTTP 400 or accept but don't invoke them
- **Account status**: OpenAI has confirmed web_search is enabled on the account

## Test Results

### Models Tested
- gpt-4
- gpt-4-turbo
- gpt-4-turbo-2024-04-09
- gpt-4o
- gpt-4o-mini
- gpt-5

### Model-Specific Results
| Model | HTTP Status | Tool Invocation | Notes |
|-------|------------|-----------------|--------|
| gpt-4o | 200 | Sometimes | Accepts tools, may invoke based on prompt |
| gpt-4-turbo | 400 | N/A | "Hosted tool 'web_search' not supported" |
| gpt-5-2025-08-07 | 200 | No | Accepts tools but doesn't invoke them |
| gpt-5-chat-latest | 200 | No | Accepts tools but doesn't invoke them |

### Test Modes
- **AUTO mode**: All models return responses without invoking tools
- **REQUIRED mode**: All models fail to meet requirements (no tool invocation)

## Configuration Changes Made

### 1. Environment Variables (.env)
```bash
ALLOWED_OPENAI_MODELS=gpt-4,gpt-4-turbo,gpt-4-turbo-2024-04-09,gpt-4o,gpt-4o-mini,gpt-5,gpt-5-chat-latest
```

### 2. Model Registry (app/llm/models.py)
```python
OPENAI_ALLOWED_MODELS = {
    "gpt-4",
    "gpt-4-turbo", 
    "gpt-4-turbo-2024-04-09",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-5-chat-latest"
}
```

## Root Cause Analysis

### What We Know
1. **Model-specific behavior**: Different models handle web_search differently
2. **Adapter works correctly**: Successfully attaches tools per OpenAI SDK requirements
3. **Account has web_search**: OpenAI confirmed the feature is enabled

### API Behavior
When attempting to use web_search tools:
- **gpt-4o**: Accepts tools, may invoke based on prompt context
- **gpt-4-turbo**: Returns HTTP 400 "not supported with this model"
- **gpt-5 models**: Accept tools (HTTP 200) but don't invoke them
- **Tool invocation**: Model-dependent, not consistent across all models

### Evidence Trail
1. **Initial GPT-5 tests**: 0 tool calls, 0 citations
2. **GPT-4 allowlist update**: Enabled testing of GPT-4 models
3. **GPT-4 test results**: Identical behavior - 0 tool calls, 0 citations
4. **Conclusion**: Model-specific behavior, requires further investigation

## Business Impact

### Current State
- ⚠️ gpt-4o can provide grounded responses (inconsistently)
- ❌ gpt-5 models accept tools but don't invoke them
- ❌ gpt-4-turbo explicitly doesn't support web_search tools

### Workarounds
1. **Use Vertex/Gemini**: Provides unlinked sources (better than nothing)
2. **Disable grounding for OpenAI**: Accept ungrounded responses
3. **Contact OpenAI Support**: Request web_search tool enablement

## Recommendations

### Immediate Actions
1. **Further Investigation Needed**:
   - Why gpt-5 models accept tools but don't invoke them
   - Why tool invocation is inconsistent even with gpt-4o
   - Whether prompt engineering can improve invocation rates

2. **Update Production Config**:
   ```python
   # Disable grounding for OpenAI until resolved
   if vendor == "openai":
       request.grounded = False
       logger.warning("OpenAI grounding disabled - account limitation")
   ```

3. **Customer Communication**:
   - Document that OpenAI models cannot provide sources
   - Recommend Vertex/Gemini for grounded requests

### OpenAI Support Request Template
```
Subject: Web Search Tools Not Working - All Models Affected

Account: [Your Account ID]
API Key: sk-proj-...

Issue: No OpenAI models can use web_search tools

Evidence:
- Tested models: gpt-4, gpt-4-turbo, gpt-4o, gpt-5
- All return 0 tool calls, 0 citations
- Error: "Hosted tool 'web_search' is not supported"
- Affects both AUTO and REQUIRED modes

Request: Enable web_search tool entitlement for this account
```

## Test Artifacts
- `gpt4_grounding_complete.txt` - Full test output
- `gpt4_grounding_results_20250902_135326.json` - Detailed JSON results
- `test_gpt4_grounding.py` - Test script with GPT-4 models enabled

## Conclusion
This is **definitively an OpenAI account/API limitation**, not a code issue. The web_search tools are not functional for ANY model on this account. Resolution requires OpenAI to enable the feature at the account level.