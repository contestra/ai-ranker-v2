# Vertex SDK-Only Fix Plan V2 - With ChatGPT Corrections

## Context
- **Problem**: Vertex ungrounded returns empty responses with 0 completion tokens
- **Root Cause**: Vertex SDK returns candidates with NO parts when hitting MAX_TOKENS
- **Constraint**: Must NOT use google-genai (per PRD - not mature, drift risk)
- **ChatGPT Review**: Plan is solid, needs 2 corrections + enhancements

## Critical Corrections from ChatGPT

### 1. ❌ DON'T Move ALS to system_instruction
**Original Plan Error**: Move ALS into system_instruction
**Correction**: Keep message order as `system → ALS block → user prompt`
- System goes in `system_instruction` parameter
- ALS stays as first part of user message
- User's actual prompt follows ALS
**Why**: Engineering guide requires ALS as user-visible block, not fused into system

### 2. ❌ DON'T Drop Temperature to 0.3
**Original Plan Error**: Lower retry temperature to 0.3
**Correction**: Keep temperature user-like (0.6-0.7)
- First attempt: Normal temp (0.7-1.0)
- Retry: Slight step-down only (e.g., 0.7→0.6)
- Never drop to 0.3 (probe-mode, not real user behavior)
**Why**: Must reflect real user experience, not probe mode

## Enhanced SDK-Only Solution (5 Changes)

### 1. Fix Text Extraction - Check ALL Parts & Candidates ✅
**Location**: `_extract_text_from_candidates`
**Fix**:
- Iterate ALL candidates (not just first)
- Iterate ALL parts in each candidate
- Check text, json_data, inline_data across ALL
- Fallback to resp.text with exception handling
- Add compact audit log on miss

### 2. Smart Retry for MAX_TOKENS + Empty ✅
**Location**: Ungrounded branch in `complete`
**Trigger**: 
- text == "" OR 
- candidates_token_count == 0 OR 
- finish_reason == "MAX_TOKENS"
**Retry Config**:
- `response_mime_type = "text/plain"` (forces single text part)
- **Increase max_output_tokens by 50-100%** (prevent another MAX_TOKENS)
- Temperature slight step-down (0.7→0.6, NOT 0.3)
- Keep tools=None

### 3. Proper Message Construction ✅
**Location**: Model creation and content building
**Fix**:
- Use `GenerativeModel(..., system_instruction=system_text)`
- Build user content as: `ALS + "\n\n" + user_prompt`
- DON'T put ALS in system_instruction
**Result**: `system → ALS → user` order preserved

### 4. Enhanced Telemetry ✅
**Location**: Final LLMResponse
**Changes**:
- If empty after retry: `success=False`, `error_type="EMPTY_COMPLETION"`
- Add `why_no_content` with:
  - finish_reason
  - token counts
  - whether retry was attempted
  - safety block info if applicable

### 5. Safety/Finish Reason Handling ✅
**Location**: Response processing
**Add**:
- Detect safety blocks explicitly
- Log "reasoning-only" responses with no parts
- Include finish_reason in all metadata
- Differentiate token-cap empties from safety blocks

## Implementation Details

### Text Extraction Improvements
```python
# Pseudocode structure (no actual code per request)
for candidate in all_candidates:
    for part in candidate.parts:
        check part.text
        check part.json_data (serialize)
        check part.inline_data (decode)
    if still empty:
        try resp.text
        catch and log
```

### Retry Logic
```python
# After first attempt in ungrounded branch
if (text == "" or 
    usage.get('candidates_token_count', 0) == 0 or
    finish_reason in ["MAX_TOKENS", "2"]):
    
    # Retry with:
    # - max_output_tokens *= 1.5
    # - response_mime_type = "text/plain"
    # - temperature = min(original_temp * 0.9, 0.6)
```

### Message Order
```python
# Correct order (NOT putting ALS in system)
system_instruction = system_text  # System only
user_content = f"{als_block}\n\n{user_prompt}"  # ALS + user
```

## What We WON'T Do
- ❌ Use google-genai
- ❌ Put ALS in system_instruction
- ❌ Drop temperature to 0.3
- ❌ Change grounded flows
- ❌ Modify region/routing

## Test Plan
1. **VAT Test** (US/DE ungrounded) - expect content, tokens > 0
2. **Brands Test** (US/DE ungrounded) - expect content
3. **Verify**:
   - Retry triggers on MAX_TOKENS
   - Temperature stays user-like
   - ALS order preserved
   - SHA256 unchanged

## Expected Outcomes
- ✅ Vertex ungrounded returns content
- ✅ Handles MAX_TOKENS gracefully
- ✅ Preserves ALS semantics (system → ALS → user)
- ✅ Reflects real user experience (no 0.3 temp)
- ✅ Truthful telemetry (success=False when empty)
- ✅ 100% Vertex SDK compliant

## Quick Acceptance Criteria
- VAT (US/DE) ungrounded: Non-empty content, completion_tokens > 0
- Brands (US/DE) ungrounded: No blank "Full Response"
- ALS SHA256: Unchanged for same locale
- Grounded paths: Unchanged behavior/latency
- Telemetry: Clear failure signals when truly empty

## Summary of Changes from V1
1. **KEEP ALS in user message** (not system_instruction)
2. **KEEP temperature user-like** (0.6-0.7, not 0.3)
3. **ADD token increase on retry** (+50-100%)
4. **ADD finish_reason detection** for smart retry
5. **ADD safety block differentiation** in telemetry

This revised plan incorporates ChatGPT's corrections while maintaining SDK-only approach and PRD compliance.