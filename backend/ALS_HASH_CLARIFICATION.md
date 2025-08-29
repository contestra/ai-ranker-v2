# ALS SHA256 Hash Analysis - UPDATED

## Understanding Which Hash Changes Matter

Based on the clarification, the SHA256 differences observed between test runs are **NOT necessarily bugs**. Here's what we actually have:

### Hash Types and Expected Behavior

1. **template_sha256**: Recipe hash - MUST be stable for identical template JSON
2. **response_output_sha256**: Model output hash - EXPECTED to drift with different outputs
3. **run_sha256**: Full execution hash - EXPECTED to differ between runs (includes runtime facts)

### Our Test Results Analysis

Looking at our two test runs:
- **als_test_results_20250829_095314.json** (Run 1)
- **als_test_results_20250829_095550.json** (Run 2)

The SHA256 values we're seeing are likely **als_block_sha256** values, which are part of the ALS provenance. These SHOULD be deterministic for the same:
- Country code (US/DE)
- Locale (en-US/en-DE)
- Template configuration

## Key Finding: ALS Block Generation Issue

The fact that **7 out of 8** configurations produced different `als_block_sha256` values between runs suggests:

### Likely Cause: Non-Deterministic ALS Block Generation
The ALS block generation is including runtime-variable data such as:
- Timestamps
- Random seeds without fixed initialization
- Session/request IDs
- Dynamic external data

### This IS a Bug Because:
- **ALS blocks** should be deterministic for the same country/locale
- The **als_block_sha256** should be cacheable and reusable
- Same inputs (country_code, locale) should produce identical ALS text

## What's Working Correctly ✅

1. **ALS Applied**: 100% application rate
2. **Length Compliance**: All under 350 NFC chars
3. **Regional Differentiation**: US vs DE producing different blocks
4. **Provenance Capture**: SHA256 being calculated and stored
5. **Message Order**: system → ALS → user maintained

## What Needs Fixing 🔧

1. **ALS Generation Determinism**: 
   - Remove any timestamps from ALS block
   - Use fixed seeds for any randomization
   - Ensure only country_code and locale affect output

2. **Verification Tests Needed**:
   ```python
   # Same inputs must produce same ALS block
   als1 = generate_als_block(country='US', locale='en-US')
   als2 = generate_als_block(country='US', locale='en-US')
   assert als1 == als2
   assert hashlib.sha256(als1).hexdigest() == hashlib.sha256(als2).hexdigest()
   ```

## Expected vs Unexpected Drift

### Expected Drift ✅
- **run_sha256**: Different between executions (includes latency, tokens, etc.)
- **response_output_sha256**: Different model outputs
- **Execution metrics**: tokens, latency varying between runs

### Unexpected Drift (BUG) ❌
- **als_block_sha256**: Should be identical for same country/locale
- **template_sha256**: Should be identical for same template JSON

## Next Steps

1. **Investigate ALS Generation**: Find source of non-determinism
2. **Fix Generation Logic**: Remove runtime-variable inputs
3. **Add Determinism Tests**: Ensure repeatability
4. **Verify Cache-ability**: Confirm ALS blocks can be cached by SHA256

## Conclusion

The SHA256 differences we're seeing in `als_block_sha256` between runs **ARE a bug** because ALS blocks should be deterministic for caching and compliance. However, if these were `run_sha256` values, the differences would be expected and correct.

The system is functioning but needs ALS generation to be made deterministic for production readiness.