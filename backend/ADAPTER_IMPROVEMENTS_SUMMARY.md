# Adapter Improvements Summary - August 31, 2025

## Overview
This document summarizes all improvements made to the LLM adapters based on comprehensive review and testing.

## 1. Cache Poisoning Fix
- **Issue**: Tri-state cache keyed on pre-adjusted model causing conflicts
- **Solution**: Check model_adjusted flag and skip normalization for already-adjusted models
- **Impact**: Eliminates cache poisoning between gpt-5 and gpt-5-chat-latest

## 2. REQUIRED Mode Enforcement
- **Issue**: OpenAI cannot force tool usage, leading to silent failures
- **Solution**: 
  - Fail-closed immediately for OpenAI REQUIRED mode with clear error
  - Router post-validation for all providers
- **Impact**: Consistent behavior across providers, clear failure modes

## 3. Vertex Domain Extraction
- **Issue**: Redirect URLs mask actual source domains in ALS testing
- **Solution**: 
  - Extract true URLs from nested metadata when available
  - Parse source_domain from multiple sources
  - Add is_redirect flag for transparency
- **Impact**: ALS effects now visible (.ch, .de domains appear in correct contexts)

## 4. Google-genai Requirement
- **Issue**: Vertex grounded requests fail silently without google-genai
- **Solution**: 
  - Fail-closed with clear error if google-genai unavailable
  - Startup checks and warnings
  - Clear installation instructions in error
- **Impact**: No more mysterious grounded_effective=false issues

## 5. Temperature Policy Documentation
- **Issue**: User temperatures overridden for GPT-5 and grounded requests
- **Solution**: 
  - Clear code comments explaining policy
  - Debug logging when override occurs
  - Documentation for downstream teams
- **Impact**: No surprises about temperature behavior

## 6. Retry Gate for web_search_preview
- **Issue**: Non-grounded requests unnecessarily retry with web_search_preview
- **Solution**: Only retry if original request had tools attached
- **Impact**: Reduced API calls, consistent behavior

## 7. ALS Metadata Mirroring
- **Feature**: Router ensures ALS metadata propagation
- **Implementation**: Copies ALS fields from request to response if missing
- **Impact**: Guaranteed ALS visibility even if adapter forgets

## 8. Enhanced QA Reporting
- **Issue**: Unclear when errors are expected vs. problematic
- **Solution**: 
  - Clear run tags: `provider:model:mode_sent→status`
  - Explicit REQUIRED failure context
  - Grounding mode analysis
- **Impact**: Reviewers immediately understand failure reasons

## 9. Model Allowlist Documentation
- **Issue**: Mismatch between code comments and actual allowed models
- **Solution**: Updated documentation to reflect both gemini-2.5-pro and gemini-2.0-flash
- **Impact**: Clear understanding of supported models

## Files Modified

### Core Adapters
- `app/llm/unified_llm_adapter.py` - Router with post-validation and ALS mirroring
- `app/llm/adapters/openai_adapter.py` - All OpenAI fixes
- `app/llm/adapters/vertex_adapter.py` - Domain extraction and genai requirement
- `app/llm/models.py` - Updated model allowlists

### Test Utilities
- `tests/util/als_ambient_utils.py` - Enhanced domain extraction
- `tests/test_als_ambient_matrix_enhanced.py` - Improved QA reporting

### Documentation
- `ROUTER_BEHAVIORS_DOCUMENTATION.md` - Comprehensive behavior guide
- `VERTEX_GROUNDING_REQUIREMENTS.md` - Google-genai requirement details
- `VERTEX_DOMAIN_EXTRACTION.md` - True domain extraction explanation
- `ENHANCED_QA_REPORT_EXAMPLE.md` - Example of improved reporting

## Testing

All changes include test files:
- `test_vertex_genai_requirement.py`
- `test_vertex_true_domains.py`
- `test_retry_gate.py`

## Deployment Notes

1. **Required Dependencies**:
   ```bash
   pip install google-genai>=0.8.3
   ```

2. **Environment Variables**:
   - Ensure `VERTEX_USE_GENAI_CLIENT != "false"`
   - Check `ALLOWED_VERTEX_MODELS` includes desired models

3. **Verification**:
   - Check startup logs for genai initialization
   - Run a grounded request to confirm functionality
   - Review QA reports for improved clarity

## Key Outcomes

✅ **Reliability**: Fail-closed behavior prevents silent failures
✅ **Visibility**: True domains and ALS effects now observable
✅ **Clarity**: Error messages guide users to solutions
✅ **Consistency**: Uniform behavior across providers
✅ **Documentation**: Clear guides for all behaviors

## Next Steps

1. Deploy changes to staging environment
2. Run full ALS matrix test with new reporting
3. Verify all grounded requests show proper domain distribution
4. Monitor for any new edge cases

---

*These improvements address all issues identified in the comprehensive adapter review and ensure robust, predictable behavior for all LLM operations.*