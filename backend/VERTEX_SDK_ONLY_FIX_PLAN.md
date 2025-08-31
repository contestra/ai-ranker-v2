# Vertex SDK-Only Fix Plan for Ungrounded Empty Responses

## Context
- **Problem**: Vertex ungrounded returns empty responses with 0 completion tokens
- **Root Cause**: Vertex SDK returns candidates with NO parts when hitting MAX_TOKENS
- **Constraint**: Must NOT use google-genai (per PRD requirements - not mature, drift risk)
- **Current State**: My previous attempt to use google-genai was wrong - violated PRD

## Why google-genai is OFF LIMITS
1. **PRD Requirement**: Adapters must use Vertex AI SDK only, no direct Gemini API
2. **Maturity Issues**: google-genai flagged as not fully mature with dev/runtime issues
3. **Feature Coverage**: Partial feature coverage vs Vertex SDK
4. **Response Drift**: Different response shapes could break determinism
5. **Team Decision**: Vertex SDK is the canonical path, google-genai only for tooling

## The REAL Issue
When Vertex hits MAX_TOKENS with low limits, it returns:
```json
{
  "candidates": [{
    "content": {"role": "model"},  // NO parts array!
    "finish_reason": "MAX_TOKENS"
  }],
  "usage_metadata": {
    "prompt_token_count": 90,
    "total_token_count": 589
  }
}
```

## SDK-Only Solution (4 Changes)

### 1. Fix Text Extraction - Check ALL Parts
**Location**: `_extract_text_from_candidates`
**Current Bug**: Only checks `parts[0]`, misses text in later parts
**Fix**:
- Iterate ALL candidates (not just first)
- Iterate ALL parts (not just first)
- Accumulate text from any part.text found
- Check json_data and inline_data across ALL parts
- Only fallback to resp.text if still empty

### 2. Add One-Shot Retry for Empty/0-Token
**Location**: Ungrounded branch in `complete` method
**Trigger**: If text == "" OR completion_tokens == 0
**Retry Config**:
- Set `response_mime_type = "text/plain"` (forces single text part)
- Lower temperature to 0.3 (reduces thinking-only responses)
- Keep tools=None
- Same timeout
**Why**: Mirrors OpenAI's plain-text nudge pattern

### 3. Use Proper system_instruction
**Location**: `_build_content_with_als` and model construction
**Current Bug**: Concatenates system + ALS + user into single user message
**Fix**:
- Pass system text via `GenerativeModel(..., system_instruction=...)`
- Keep user content as pure user role
- ALS goes with system instruction, not user
**Why**: SDK treats system differently, reduces non-text parts

### 4. Telemetry Truthfulness
**Location**: Final LLMResponse in `complete`
**Change**: 
- If content empty AFTER retry, set `success=False`
- Add `error_type="EMPTY_COMPLETION"`
- Include `why_no_content` with details
**Why**: Current matrices show "Success" for empty responses, hiding the issue

## Implementation Order
1. First fix extraction (immediate improvement)
2. Add retry logic (catches remaining empties)
3. Fix system_instruction (prevents future issues)
4. Fix success flag (visibility into failures)

## What We WON'T Do
- ❌ Use google-genai for ungrounded
- ❌ Change vendor routing
- ❌ Modify region settings (stays europe-west4)
- ❌ Touch grounded flows (they work)
- ❌ Add new dependencies

## Test Plan
1. Run VAT test (US/DE ungrounded) - expect content
2. Run Brands test (US/DE ungrounded) - expect content
3. Verify completion_tokens > 0
4. Check retry triggers only on empty
5. Confirm ALS hashes unchanged

## Expected Outcome
- Vertex ungrounded will return content
- No changes to grounded behavior
- Stay 100% on Vertex SDK
- Comply with all PRD requirements
- No google-genai dependency

## Code Locations to Modify
1. `vertex_adapter.py::_extract_text_from_candidates` (lines 70-150)
2. `vertex_adapter.py::complete` ungrounded branch (lines 665-700)
3. `vertex_adapter.py::_build_content_with_als` (lines 200-242)
4. `vertex_adapter.py` model construction (line 572)

## Rollback Plan
All changes are additive/defensive:
- Extraction improvement is backward compatible
- Retry only triggers on empty (no change to success path)
- system_instruction is SDK-supported feature
- Success flag change only affects telemetry

This plan keeps us 100% on Vertex SDK, fixes the empty responses, and maintains PRD compliance.