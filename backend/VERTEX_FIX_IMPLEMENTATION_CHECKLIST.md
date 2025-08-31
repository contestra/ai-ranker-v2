# Vertex SDK-Only Fix - Implementation Checklist

## ✅ ChatGPT Approved V2 Plan
ChatGPT reviewed and approved V2 with minor clarifications. Ready to implement.

## Implementation Map - Exact Locations

### 1. Fix Text Extraction (`_extract_text_from_candidates`)
**File**: `vertex_adapter.py` lines 70-150
**Changes**:
- [x] Loop ALL candidates (not just candidates[0])
- [x] Loop ALL parts in each candidate
- [ ] Collect text → json_data → inline_data from all parts
- [ ] Try resp.text as fallback
- [ ] Add audit log if still empty
- [ ] Handle both string and enum finish_reason (2 = MAX_TOKENS)

### 2. Add Smart Retry (Ungrounded Branch)
**File**: `vertex_adapter.py` lines 663-720
**Trigger Conditions**:
- [ ] text == ""
- [ ] resp.usage_metadata.candidates_token_count == 0
- [ ] resp.candidates[0].finish_reason in ["MAX_TOKENS", "2", 2]

**Retry Config**:
- [ ] Set response_mime_type = "text/plain" via GenerationConfig
- [ ] Increase max_output_tokens *= 1.5
- [ ] Slight temp reduction: 0.7 → 0.6 (NOT 0.3)
- [ ] Keep tools=None
- [ ] Log retry attempt in metadata

### 3. Fix Message Construction
**File**: `vertex_adapter.py`
**Line 572**: Model creation
- [ ] Add system_instruction parameter to GenerativeModel

**Lines 200-242**: `_build_content_with_als`
- [ ] Stop concatenating system into user message
- [ ] Keep ALS as first part of user content
- [ ] Return system text separately for system_instruction

### 4. Enhance Telemetry
**File**: `vertex_adapter.py` lines 700-750
**On Empty After Retry**:
- [ ] Set success=False
- [ ] Add error_type="EMPTY_COMPLETION"
- [ ] Add why_no_content with:
  - finish_reason (SAFETY|MAX_TOKENS|NO_PARTS)
  - candidates_token_count
  - retry_attempted (true/false)
- [ ] Keep existing fields: grounded_effective, tool_call_count
- [ ] Maintain response_api="vertex_genai", region="europe-west4"

### 5. Safety Detection
**Add to metadata**:
- [ ] Detect finish_reason == SAFETY (or enum equivalent)
- [ ] Differentiate from MAX_TOKENS empties
- [ ] Log safety category if available

## Code Patterns to Use

### Finish Reason Check
```python
# Handle both string and enum
finish_reason = resp.candidates[0].finish_reason if resp.candidates else None
is_max_tokens = (
    str(finish_reason) == "2" or 
    finish_reason == 2 or
    "MAX_TOKENS" in str(finish_reason)
)
```

### Retry Decision
```python
# After first attempt
should_retry = (
    not text or
    resp.usage_metadata.candidates_token_count == 0 or
    is_max_tokens
)
```

### System Instruction
```python
# Model creation
model = gm.GenerativeModel(
    model_id,
    system_instruction=system_text  # Separate from user
)
```

### User Content
```python
# ALS stays in user message
user_content = f"{als_block}\n\n{user_prompt}" if als_block else user_prompt
```

## Testing Checklist

### Before Changes
- [ ] Run test_vertex_fix.py - note empty responses
- [ ] Run VAT test - note empty ungrounded
- [ ] Save current telemetry output

### After Each Change
1. **After extraction fix**:
   - [ ] Some previously empty responses should have content
   
2. **After retry logic**:
   - [ ] MAX_TOKENS cases should succeed on retry
   - [ ] Check logs for retry attempts
   
3. **After message construction**:
   - [ ] Verify system/ALS/user order preserved
   - [ ] Check ALS SHA256 unchanged
   
4. **After telemetry**:
   - [ ] Verify success=False for true empties
   - [ ] Check why_no_content populated

### Final Validation
- [ ] VAT (US/DE) ungrounded: Non-empty, tokens > 0
- [ ] Brands (US/DE) ungrounded: Non-empty responses
- [ ] ALS SHA256: Identical for same locale
- [ ] Grounded: Unchanged behavior
- [ ] No google-genai usage

## Rollback Points
Each change is independent:
1. Extraction can be reverted alone
2. Retry can be disabled with flag
3. Message construction has fallback
4. Telemetry changes are additive

## Success Metrics
- Zero empty responses for normal prompts
- MAX_TOKENS handled gracefully
- Clear telemetry for true failures
- No performance regression
- 100% SDK compliance

---
Ready to implement. Each checkbox can be checked off as completed.