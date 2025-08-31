# OpenAI API Limitations Documentation
## Date: 2025-08-31

## Critical API Limitation: tool_choice:"required" Not Supported

### Discovery
Through direct API testing, we've confirmed that OpenAI's Responses API (`/v1/responses`) does NOT support `tool_choice:"required"` with web_search tools.

### Test Case
```bash
curl https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": [{"role":"user","content":[{"type":"input_text","text":"Give the official URL of the White House homepage."}]}],
    "tools": [{"type":"web_search"}],
    "tool_choice": "required",
    "max_output_tokens": 64
  }'
```

### API Response
```json
{
    "error": {
        "message": "Tool choices other than 'auto' are not supported with model 'gpt-5' and the following tool types: 'web_search_preview'.",
        "type": "invalid_request_error",
        "param": "tool_choice",
        "code": null
    }
}
```

## Implementation Decision: Fail-Closed for REQUIRED Mode

Per the PRD requirements, REQUIRED mode MUST force grounding or fail. Since the API doesn't support forcing web_search invocation, we fail-closed with a clear error message.

### Current Behavior

1. **AUTO Mode**: Works correctly
   - Sets `tool_choice:"auto"` 
   - Model decides whether to use web_search
   - Proceeds with or without grounding based on model's decision

2. **REQUIRED Mode**: Fails immediately (fail-closed)
   - Cannot set `tool_choice:"required"` due to API limitation
   - Returns error: `GROUNDING_NOT_SUPPORTED: Model {model} with web_search tools cannot guarantee REQUIRED mode`
   - This is the correct behavior per PRD - fail-closed when unable to guarantee grounding

### Why This Is Correct

The PRD explicitly states:
- REQUIRED mode must force grounding or fail
- Systems should fail-closed when requirements cannot be met
- Silent downgrade from REQUIRED to AUTO would violate the contract

Since OpenAI's API doesn't allow us to force web_search invocation, the only correct behavior is to fail with a clear error explaining the limitation.

## Alternative Approaches (Not Implemented)

These approaches were considered but rejected as they violate PRD requirements:

1. **Silent Downgrade**: Use `tool_choice:"auto"` for REQUIRED mode
   - ❌ Violates fail-closed principle
   - ❌ Breaks REQUIRED mode contract
   - ❌ User expects forced grounding but gets optional

2. **Post-hoc Enforcement**: Use AUTO then fail if tool wasn't invoked
   - ❌ Wastes API calls and tokens
   - ❌ Unpredictable failure timing
   - ❌ Still can't guarantee grounding

## Recommendations for Users

1. **For OpenAI grounding**: Always use AUTO mode
   - The model will use web_search when it deems necessary
   - Monitor `grounding_attempted` and `grounded_effective` in telemetry

2. **For guaranteed grounding**: Use Vertex AI
   - Vertex supports proper grounding enforcement
   - Can use REQUIRED mode successfully

3. **For critical grounding needs**: Implement application-level retry
   - Use AUTO mode
   - Check `grounded_effective` in response
   - Retry with modified query if not grounded
   - Add explicit grounding instructions to prompt

## Other Known Limitations

1. **Empty Results**: Web_search often returns empty results even for obvious queries
   - This is an OpenAI-side issue
   - We distinguish between "not supported" and "empty results"
   - Empty results tracked via `GROUNDING_EMPTY_RESULTS` error

2. **Tool Variants**: Must use two-pass fallback
   - Try `web_search` first
   - On 400 "not supported", retry with `web_search_preview`
   - Only mark as unsupported if both fail

3. **Model-Specific Support**: Tool support varies by model
   - Cache support status per model+variant
   - TTL of 15 minutes for "unsupported" entries
   - Allows periodic retry as models are updated

## Telemetry Fields for Monitoring

Track these fields to understand grounding behavior:
- `grounding_attempted`: Was web_search tool invoked?
- `grounded_effective`: Did we get actual results with citations?
- `tool_call_count`: Number of tool invocations
- `tool_result_count`: Number of actual results returned
- `why_not_grounded`: Precise reason if not effective
- `response_api_tool_type`: Which variant was used (web_search vs web_search_preview)