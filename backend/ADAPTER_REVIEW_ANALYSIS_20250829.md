# Adapter Review Analysis - August 29, 2025

## Executive Summary

Comprehensive review identified critical issues with ALS determinism and vendor parity. The good news: **we already fixed the main ALS determinism issue** in the latest commit. However, several other P0 issues remain that affect telemetry accuracy and vendor parity.

## Status of Identified Issues

### ✅ Already Fixed (in latest commit)

1. **ALS Determinism (P0 #1)**
   - **Issue**: `randomize=True` causing SHA256 drift
   - **Fix Applied**: HMAC-based deterministic variant selection
   - **Status**: FIXED - 100% deterministic across all configurations
   - **Evidence**: `test_als_determinism.py` passing

### ❌ Still Need Fixing

#### P0 - Highest Priority

2. **Vertex LLMResponse Parity (P0 #2)**
   - **Issue**: VertexAdapter missing fields in LLMResponse (latency_ms, success, vendor, grounded_effective)
   - **Impact**: Asymmetric telemetry, breaks consumers
   - **Fix Required**: Mirror OpenAIAdapter's return shape

3. **Vendor Inference for Vertex (P0 #3)**
   - **Issue**: Can't infer vendor for "publishers/google/models/..." format
   - **Impact**: "Cannot infer vendor" errors
   - **Fix Required**: Update `get_vendor_for_model` pattern matching

4. **Token Usage Schema Mismatch (P0 #4)**
   - **Issue**: OpenAI returns input_tokens/output_tokens, telemetry expects prompt_tokens/completion_tokens
   - **Impact**: OpenAI calls record 0s in database
   - **Fix Required**: Normalize keys before telemetry emission

5. **Region Consistency (P0 #5)**
   - **Issue**: Vertex defaults to europe-west4 for init but us-central1 for metadata
   - **Impact**: Misleading telemetry
   - **Fix Required**: Align defaults

#### P1 - Important Quality

6. **Step-2 JSON Validation**
   - **Issue**: Vertex two-step doesn't validate JSON output
   - **Impact**: Silent failures possible
   - **Fix Required**: Add json.loads validation

7. **Metadata Sanitization**
   - **Issue**: Lists with nested dicts not sanitized recursively
   - **Impact**: Potential SDK object leaks
   - **Fix Required**: Deep sanitization

8. **Temperature Inheritance**
   - **Issue**: Tools temperature could inherit to synthesis fallback
   - **Impact**: Currently OK (GPT-5 only), future risk
   - **Fix Required**: Explicit temperature handling in fallback

9. **Router Model Validation**
   - **Issue**: Local validate_model doesn't match central rules
   - **Impact**: Confusion, unused code
   - **Fix Required**: Remove or align

10. **Vertex Text Extraction**
    - **Issue**: Only extracts first part of first candidate
    - **Impact**: Content loss possible
    - **Fix Required**: Concatenate all text parts

11. **ALS Text Persistence**
    - **Issue**: Raw ALS text stored in metadata
    - **Impact**: Potential location signal leaks
    - **Fix Required**: Store only SHA256, not raw text

## What's Working Well ✅

1. **Grounding Semantics**
   - OpenAI: web_search tool with REQUIRED/AUTO modes
   - Vertex: Two-step flow with attestation
   - Both implementations solid

2. **OpenAI Temperature Rule**
   - tools_attached boolean properly implemented
   - Correct temperature=1.0 enforcement

3. **ALS Determinism** (after our fix)
   - HMAC-based variant selection
   - Fixed timezone handling
   - Placeholder date instead of datetime.now()

## Priority Action Plan

### Immediate (P0) - Do Now
1. ✅ ALS Determinism - DONE
2. Fix Vertex LLMResponse shape
3. Fix vendor inference pattern
4. Normalize token usage keys
5. Align region defaults

### Next Sprint (P1)
6. Add Step-2 JSON validation
7. Deep metadata sanitization
8. Future-proof temperature handling
9. Clean up router validation
10. Fix text extraction
11. Remove raw ALS from metadata

### Polish (P2)
- Update docstrings for allowed models
- Add defensive grounding checks

## Quick Verification Tests

After fixes, verify:
- [ ] 3 identical runs → identical als_block_sha256 ✅ (DONE)
- [ ] Vertex telemetry shows latency_ms, success=True
- [ ] "publishers/google/models/..." routes without error
- [ ] OpenAI shows non-zero token counts in telemetry
- [ ] Vertex region matches init location
- [ ] Step-2 JSON failures surface in metadata

## Files Requiring Changes

1. **vertex_adapter.py**
   - Add LLMResponse fields
   - Validate Step-2 JSON
   - Fix text extraction

2. **openai_adapter.py**
   - Normalize token usage keys
   - Future-proof temperature logic

3. **unified_llm_adapter.py**
   - ✅ ALS determinism (DONE)
   - Fix vendor inference
   - Remove/fix validate_model
   - Deep sanitization
   - Remove raw ALS text

## Conclusion

Main ALS determinism issue is resolved. Remaining P0 issues primarily affect telemetry accuracy and vendor parity. All are straightforward fixes that can be implemented quickly without architectural changes.