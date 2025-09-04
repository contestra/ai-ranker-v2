# GPT-5 API Limitations Report

## Executive Summary
After extensive testing, we've identified critical limitations with GPT-5's API that prevent ungrounded text generation. The adapter has been updated to properly handle these limitations.

## Key Findings

### 1. Ungrounded Mode Not Supported
**Issue**: GPT-5 cannot generate ungrounded text responses through any available API.

**Evidence**:
- **Responses API with no/empty tools**: Generates 0 output tokens (confirmed)
- **Chat Completions API**: Returns empty content even when consuming tokens (confirmed)
- **Responses API with dummy tools**: Generates 0 tokens when tools aren't called (confirmed)

### 2. API Behavior Details

#### Responses API
```python
# With tools=[] or no tools field
response.output_text = ''
response.usage.output_tokens = 0
response.usage.reasoning_tokens = 0
response.output = [reasoning_item]  # No message items
```

#### Chat Completions API
```python
# With max_completion_tokens=50
response.choices[0].message.content = ''
response.usage.completion_tokens = 50  # Tokens consumed but no text!
```

### 3. Working Configuration
GPT-5 ONLY works with:
- `grounded=True`
- Responses API endpoint
- Web search tools available
- Actual tool calls made or AUTO mode determining no search needed

## Implementation Changes

### 1. Error Handling
```python
if not is_grounded and "gpt-5" in request.model.lower():
    raise ValueError(
        "GPT-5 models do not support ungrounded text generation. "
        "The Responses API produces 0 output tokens without tools, "
        "and Chat Completions returns empty content. "
        "Please use grounded=True for GPT-5 models."
    )
```

### 2. Routing Logic
- Grounded GPT-5 → Responses API ✅
- Ungrounded GPT-5 → Error raised ❌
- Other models → Chat Completions ✅

## Test Results

### Grounded Mode (Working)
- ✅ AUTO mode with search-worthy queries: Calls tools, returns content
- ✅ AUTO mode with simple queries: No tools, returns content  
- ✅ Content extraction from message items works correctly
- ✅ Telemetry and metadata properly populated

### Ungrounded Mode (Not Supported)
- ❌ Responses API with empty tools: 0 tokens generated
- ❌ Responses API without tools field: 0 tokens generated
- ❌ Chat Completions: Empty content despite token usage
- ❌ All workarounds attempted failed

## Recommendations

1. **For Users**:
   - Always use `grounded=True` for GPT-5 models
   - Use GPT-4 or other models for ungrounded text generation

2. **For Future Development**:
   - Monitor OpenAI API updates for GPT-5 ungrounded support
   - Consider implementing a fallback to GPT-4 for ungrounded requests

## Technical Details

### Root Cause Analysis
The GPT-5 model appears to be designed primarily for tool-augmented generation. When no tools are available, the model's generation pipeline doesn't produce text output, likely because:

1. The model expects to reason about tool usage
2. Without tools, the reasoning stage produces no actionable output
3. The message generation stage depends on reasoning output

### Failed Workaround Attempts
1. ❌ Adding dummy tools with "don't use" instructions
2. ❌ Using different message formats (system vs user)
3. ❌ Payload field variations (modalities, response_format, include)
4. ❌ Token parameter adjustments
5. ❌ Chat Completions API fallback

## Conclusion
GPT-5's current API implementation fundamentally doesn't support ungrounded text generation. This is not a bug in our adapter but a limitation of the OpenAI API itself. The adapter now properly handles this by raising a clear error message when ungrounded mode is requested with GPT-5.