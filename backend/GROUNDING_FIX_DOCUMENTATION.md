# Grounding Fix Documentation

## Status: ✅ FULLY FIXED

### Date: 2025-08-26

## Summary
All grounding functionality has been successfully fixed and tested for both OpenAI and Vertex AI providers. Both providers now correctly support grounded (web search) requests with proper content extraction and detection.

## Issues Fixed

### 1. Vertex/Gemini Grounding - ✅ FIXED
**Problem**: Google deprecated `google_search_retrieval` for Gemini 2.x models
**Solution**: 
- Migrated to Google GenAI SDK with `GOOGLE_GENAI_USE_VERTEXAI=true`
- Fixed model name format (no `models/` prefix for Vertex mode)
- Using `gemini-2.5-pro` consistently (not flash models)
**Status**: ✅ Working - returns grounded results with web search

### 2. OpenAI/GPT-5 Grounding - ✅ FIXED
**Problems Fixed**:
1. **Content extraction bug**: Code was calling `.strip()` on `ResponseTextConfig` object
2. **Token limit too low**: Was using 4000 tokens instead of 6000
3. **No message after tools**: Model would do web searches but not synthesize answer

**Solutions Applied**:
- Fixed extraction to never touch `response.text` (it's config, not content)
- Updated default tokens from 4000 → 6000
- Added system prompt guardrail: "After finishing any tool calls, you MUST produce a final assistant message"
- Implemented two-step safety net for synthesis if no message
- Added support for `redacted_text` blocks
- Added comprehensive shape summary telemetry

**Status**: ✅ Working - returns grounded results with citations and URLs

### 3. Detection Logic - ✅ FIXED
**Solution**: Created `grounding_detection_helpers.py` with correct detection for both providers
- OpenAI: Detects `web_search_call` and `url_citation` annotations
- Vertex: Handles both snake_case and camelCase response fields
**Status**: ✅ All unit tests pass

## Files Changed

### Created:
1. `app/llm/adapters/grounding_detection_helpers.py` - Centralized detection logic
2. `tests/test_grounding_detection.py` - Unit tests for detection (14 tests, all passing)
3. `scripts/test_longevity.py` - Comprehensive 4-way test harness

### Modified:
1. `app/llm/adapters/openai_adapter.py` - Major fixes:
   - Fixed content extraction (no more `.strip()` on config objects)
   - Added system prompt guardrail for grounded requests
   - Implemented two-step synthesis safety net
   - Added shape summary telemetry
   - Support for `redacted_text` blocks
   - Default tokens: 4000 → 6000

2. `app/llm/adapters/vertex_adapter.py` - GenAI SDK integration:
   - Added `_complete_with_genai` method for Google GenAI SDK
   - Fixed model path format for Vertex mode
   - Using detection helper for consistency

## What Works Now

### OpenAI/GPT-5:
- ✅ Ungrounded requests work perfectly
- ✅ Grounded requests return content with citations and URLs
- ✅ Detection correctly identifies grounding signals
- ✅ Shape summary provides debugging telemetry
- ✅ Two-step safety net ensures answer generation

### Vertex/Gemini:
- ✅ Ungrounded requests work perfectly  
- ✅ Grounded requests work with GenAI SDK
- ✅ Detection handles all response formats
- ✅ Web search provides current information

## Key Technical Details

### Content Extraction Hierarchy (OpenAI):
1. Primary: `response.output_text` (convenience field)
2. Secondary: Last `message` item → aggregate `content[*]` where type in `{output_text, redacted_text}`
3. Never: `response.text` (it's config, not content!)
4. Fallback: Two-step synthesis if no message after tools

### Token Configuration:
```python
DEFAULT_MAX = 6000  # Was 4000
CAP = 6000         # Was 4000
```

### System Prompt Guardrail (OpenAI Grounded):
```
"After finishing any tool calls, you MUST produce a final assistant message 
containing the answer in plain text. Limit yourself to 2-3 web searches before answering."
```

### Shape Summary Telemetry:
```json
{
  "output_types": {"message": 1, "web_search_call": 3, "reasoning": 4},
  "last_message_content_types": ["output_text"],
  "url_citations_count": 7,
  "extraction_path": "message_blocks",
  "why_no_content": null
}
```

## Test Results

### 4-Way Longevity Test (All Passing):
```
✓ openai | grounded=False: Returns brands list
✓ openai | grounded=True: Returns brands with citations and URLs
✓ vertex | grounded=False: Returns brands with explanations
✓ vertex | grounded=True: Returns brands with web-sourced information
```

### Unit Tests:
```
tests/test_grounding_detection.py ... 14 passed
```

## Environment Configuration
```bash
# OpenAI
OPENAI_DEFAULT_MAX_OUTPUT_TOKENS=6000
OPENAI_MAX_OUTPUT_TOKENS_CAP=6000
OPENAI_GROUNDING_TOOL=web_search
OPENAI_TOOL_CHOICE=auto

# Vertex/Gemini
VERTEX_LOCATION=europe-west4
GOOGLE_CLOUD_PROJECT=contestra-ai
GOOGLE_GENAI_USE_VERTEXAI=true

# Timeouts
LLM_TIMEOUT_UN=60
LLM_TIMEOUT_GR=240
```

## Lessons Learned

1. **Always use 6000 tokens** - Grounded requests need extra tokens for reasoning + output
2. **`response.text` is config, not content** - Never call string methods on it
3. **Explicit synthesis instruction needed** - Models may stop after tool calls without instruction
4. **Shape summary is invaluable** - Helps diagnose "why no content" scenarios
5. **Two-step safety net works** - Synthesis fallback ensures answer generation

## Conclusion
Grounding is now fully functional for both providers. The system correctly:
- Detects when grounding should be used
- Performs web searches
- Synthesizes answers from search results
- Returns properly formatted responses with citations
- Provides comprehensive telemetry for debugging