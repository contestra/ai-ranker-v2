# Comprehensive Longevity News Test - Summary Report

## Test Date: August 31, 2025
## Prompt: "today is 31st August, 2025 - tell me the top longevity news of August"

## Executive Summary

Ran 16 test combinations across 2 models (GPT-5 and Gemini-2.5-pro) with variations:
- Countries: US and DE
- Grounding: Enabled/Disabled
- ALS (Ambient Location Signals): Enabled/Disabled

## Key Findings

### 1. Model Performance

#### GPT-5 (OpenAI)
- **Success Rate**: 8/8 (100%)
- **Grounding Effective**: 0/4 (0%)
- **Issue**: Web search tool not supported for `gpt-5-chat-latest` model
- **Error Message**: "Hosted tool 'web_search_preview' is not supported with gpt-5-chat-latest"
- **Fallback Behavior**: Model proceeds without grounding when requested

#### Gemini-2.5-pro (Vertex)
- **Success Rate**: 4/8 (50%)
- **Grounding Effective**: 4/4 (100% when successful)
- **Issue**: Ungrounded requests fail with empty responses
- **Error Pattern**: "Response candidate content has no parts" with finish_reason="MAX_TOKENS"
- **Working Configuration**: Only succeeds when grounding is enabled

### 2. Citation Extraction Issue

**Critical Finding**: No citations were extracted in ANY test (0 citations across all 16 tests)

**Root Cause Identified**:
- Vertex adapter shows `why_not_grounded: citations_missing_in_metadata`
- The `_extract_vertex_citations` function is being called but not finding citations in the response structure
- Grounding tools are being invoked (tool_call_count > 0) but citation metadata is not being properly extracted

**Technical Details**:
- Grounding is working at the API level (grounded_effective=True for Vertex)
- The issue is in the citation extraction logic, not the grounding itself
- The adapter's audit shows grounding metadata exists but citations aren't being parsed correctly

### 3. ALS (Ambient Location Signals) Effectiveness

#### ALS Metadata Verification
- ✅ ALS context is properly injected
- ✅ Correct country codes and locales are set
- ✅ ALS metadata is mirrored by router
- ✅ SHA256 hashes confirm ALS blocks are unique per country

#### ALS Impact on Results
- ❌ No .de domains found in DE tests (with or without ALS)
- ❌ No geographic steering detected in responses
- **Reason**: Without citations being extracted, we cannot measure TLD distribution

**ALS Metadata Examples**:
- US: `als_country: "US", als_locale: "us-US", als_variant_id: "variant_5"`
- DE: `als_country: "DE", als_locale: "de-DE", als_variant_id: "variant_0"`

### 4. Response Quality

Despite citation issues, both models generated substantive responses:
- GPT-5: 2100-2500 character responses
- Gemini-2.5-pro: 4400-5200 character responses (when grounded)
- Content appears relevant to longevity news theme

## Technical Issues Discovered

### Issue 1: LLMRequest Parameter Error
- **Initial Error**: `LLMRequest.__init__() got an unexpected keyword argument 'grounding_mode'`
- **Fix Applied**: Pass `grounding_mode` via `meta` dict instead of constructor parameter
- **Status**: ✅ Resolved

### Issue 2: Missing Vendor Parameter
- **Error**: LLMRequest requires `vendor` parameter
- **Fix Applied**: Added vendor detection based on model name
- **Status**: ✅ Resolved

### Issue 3: Citation Extraction Failure
- **Error**: Citations not being extracted despite grounding working
- **Root Cause**: Mismatch between Vertex API response structure and extraction logic
- **Status**: ❌ Needs fixing in `_extract_vertex_citations` function

## Recommendations

### Immediate Actions

1. **Fix Citation Extraction**:
   - Update `_extract_vertex_citations` to handle current Vertex SDK response structure
   - Add comprehensive logging to understand actual grounding metadata format
   - Test with direct SDK calls to verify citation structure

2. **OpenAI Grounding Support**:
   - Investigate alternative models that support web_search tool
   - Consider using `gpt-4o` or other models with grounding capabilities
   - Update allowed models list if needed

3. **Vertex Ungrounded Requests**:
   - Investigate why Gemini-2.5-pro fails without grounding
   - May need different generation config for ungrounded requests
   - Consider increasing max_tokens or adjusting safety settings

### Long-term Improvements

1. **Enhanced Testing**:
   - Add unit tests specifically for citation extraction
   - Create mock responses with known citation structures
   - Add integration tests with real API responses

2. **Monitoring**:
   - Add metrics for citation extraction success rate
   - Track grounding effectiveness by model
   - Monitor ALS impact when citations are available

3. **Documentation**:
   - Document the expected citation schema from each provider
   - Create troubleshooting guide for grounding issues
   - Update adapter documentation with current limitations

## Test Artifacts

- Full test script: `/home/leedr/ai-ranker-v2/backend/test_longevity_comprehensive.py`
- Test results JSON: `/home/leedr/ai-ranker-v2/backend/longevity_test_results_20250831_215426.json`
- Test log: `/home/leedr/ai-ranker-v2/backend/longevity_test_complete.txt`

## Conclusion

While the test infrastructure is working correctly and ALS context is being properly injected, the primary blocker is the citation extraction failure. This prevents us from:
1. Validating grounding effectiveness with actual source URLs
2. Measuring ALS impact on geographic steering
3. Analyzing TLD distribution for country-specific results

Once the citation extraction is fixed, the comprehensive test suite will provide valuable insights into ALS effectiveness and grounding performance across both models.