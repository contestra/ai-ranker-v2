# GPT-5 Ungrounded Fix Summary

## ✅ All Changes Successfully Implemented

### Changes Made

1. **Removed Hard Error Gate**
   - Deleted the blanket ValueError for ungrounded GPT-5
   - Now allows ungrounded requests to proceed with proper payload shaping

2. **Enhanced Payload Shaping**
   ```python
   # Added reasoning hint to encourage text emission
   "reasoning": {"effort": "minimal"}
   
   # Added text format hints
   "text": {"format": {"type": "text"}}
   ```

3. **Improved Extraction Logic**
   - Primary: Extract from message items
   - Fallback 1: Extract from reasoning content (ungrounded only)
   - Fallback 2: Extract from output_text field
   - Properly tags `text_source` in telemetry

4. **Added Retry Mechanism**
   - If ungrounded GPT-5 returns empty, retries once with hint:
     "Please respond directly in plain text without using tools."
   - Adds `ungrounded_retry=1` to telemetry when triggered

5. **Fixed Streaming Issue**
   - Fixed GPT-4 regression by properly handling streaming responses
   - Creates message object if missing in chunk

6. **Comprehensive Telemetry**
   - `text_source`: message, reasoning_fallback, output_text, message_retry, etc.
   - `ungrounded_retry`: 1 when retry was triggered
   - `response_api`: responses_sdk vs chat_completions
   - All existing telemetry preserved

### Test Results

All acceptance tests passed ✅:

1. **Ungrounded Hello World** ✅
   - Input: "Say 'hello world'."
   - Output: "hello world"
   - No retry needed

2. **Ungrounded Strict JSON** ✅
   - Input: Generate JSON with schema
   - Output: Valid JSON `{"message":"hello"}`
   - Strict schema working

3. **Grounded Required Mode** ✅
   - Still fails closed when no tools called
   - API limitation acknowledged (tool_choice must be 'auto')

4. **GPT-4 Regression Check** ✅
   - GPT-4 ungrounded still works normally
   - Uses Chat Completions API

### Key Insights

- **Reasoning hint works**: Adding `"reasoning": {"effort": "minimal"}` helps GPT-5 emit text
- **Text format helps**: The `text.format.type="text"` hint encourages message output
- **Retry rarely needed**: With proper payload shaping, first attempt usually succeeds
- **Fallback extraction important**: Sometimes text appears in reasoning or output_text fields

### API Behavior Confirmed

- GPT-5 with empty tools CAN produce text output (contrary to previous tests)
- Proper payload shaping is critical for success
- The model responds to reasoning effort hints
- Strict JSON schema works with ungrounded

### Recommendation

The adapter now properly handles GPT-5 ungrounded requests. The combination of:
- Reasoning hints
- Text format hints
- Extraction fallbacks
- Conditional retry

...provides robust support for ungrounded GPT-5 text generation while maintaining all grounded functionality and fail-closed behavior for REQUIRED mode.