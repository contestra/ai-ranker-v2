# TextEnvelope Fallback Implementation Summary

## ✅ All Components Successfully Implemented

### What Was Built

A deterministic fallback mechanism that ensures ungrounded GPT-5 always returns usable text, even when the model produces only reasoning items with no message content.

### Key Components

#### 1. TextEnvelope Schema Constant
```python
TEXT_ENVELOPE_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"}
    },
    "required": ["content"],
    "additionalProperties": False
}
```

#### 2. Smart Retry Logic in `_call_responses_api`
- **Location**: Inside the API call helper, after first response
- **Trigger**: Empty response (no message items, no output_text) for ungrounded only
- **Action**: Retry once with TextEnvelope JSON schema
- **Parse**: Extract content from JSON envelope `{"content": "..."}`
- **Inject**: Store unwrapped text in `response._envelope_content` for seamless extraction

#### 3. Extraction Priority Chain
1. Message items (primary)
2. Envelope content (from retry)
3. Reasoning content (fallback)
4. output_text field (last resort)

#### 4. Comprehensive Telemetry
- `ungrounded_retry`: 1 when retry triggered, 0 otherwise
- `retry_reason`: "empty_output" when triggered
- `text_source`: "json_envelope_fallback" when envelope used
- `output_json_valid`: true/false for JSON parsing success
- All existing telemetry preserved

#### 5. Feature Flag Control
- `UNGROUNDED_JSON_ENVELOPE_FALLBACK=on|off`
- Default: "on"
- When "off", no retry occurs even if response is empty

### Test Results

All tests passed ✅:

1. **Normal Ungrounded** ✅
   - Works on first try without retry
   - Text source: "message"

2. **Force Envelope Fallback** ✅
   - Mocked empty first response
   - Retry with TextEnvelope succeeds
   - Returns unwrapped content

3. **Grounded Unaffected** ✅
   - REQUIRED mode still fails closed
   - No envelope retry attempted for grounded

4. **Streaming Compatibility** ✅
   - GPT-4 streaming unaffected
   - Synthetic message fix still works

5. **Feature Flag Off** ✅
   - No retry when disabled
   - Single API call only

### Architecture Benefits

1. **Low Risk**: Retry only triggers when normal path produces nothing
2. **Deterministic**: JSON schema guarantees structured output
3. **Transparent**: Seamless integration with existing extraction
4. **Observable**: Full telemetry for monitoring fallback usage
5. **Configurable**: Feature flag for emergency disable

### Why This Matters

GPT-5's Responses API sometimes returns only reasoning items with no actual text content. The TextEnvelope fallback ensures we always get usable text by:

1. Detecting empty responses quickly (message-first probe)
2. Retrying once with a minimal JSON schema
3. Unwrapping the content field from the JSON
4. Preserving all grounded behavior unchanged

### Monitoring Recommendations

Track these metrics to understand fallback usage:
- `ungrounded_retry=1` frequency (how often fallback triggers)
- `text_source=json_envelope_fallback` count
- Compare retry rates across different prompts/models

### Future Considerations

1. The fallback could be extended to support other schemas if needed
2. Retry budget could be configurable (currently hardcoded to 1)
3. Could add prompt-specific hints to reduce retry frequency

### Conclusion

The TextEnvelope fallback provides a robust safety net for ungrounded GPT-5 text generation while maintaining full backward compatibility and adding minimal latency only when needed.