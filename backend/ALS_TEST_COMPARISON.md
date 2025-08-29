# ALS Test Results Comparison

## Test Run 1 (als_test_results_20250829_095314.json)
**Time**: Earlier run
**Notable characteristics**: 
- Some tests had 0ms latency (OpenAI Grounded tests)
- Empty content_preview for grounded tests
- Different SHA256 patterns

## Test Run 2 (als_test_results_20250829_095550.json)  
**Time**: Later run (used in comprehensive report)
**Notable characteristics**:
- All tests had realistic latencies
- Full content_preview for all tests
- Different SHA256 patterns from Run 1

## SHA256 Hash Comparison

### Critical Finding: SHA256 Instability
The SHA256 hashes are **different between runs** for the same configuration:

| Test Config | Run 1 SHA256 | Run 2 SHA256 | Match? |
|------------|--------------|--------------|--------|
| OpenAI Ungrounded US | 81ffbef9c6b39424 | 758fc1df8a47958a | ❌ |
| OpenAI Ungrounded DE | 277667b8fbbdd054 | 5b9007d7119ba60d | ❌ |
| OpenAI Grounded US | b5f4ce5f0445859d | 5172b84ab66dab64 | ❌ |
| OpenAI Grounded DE | f1bf15fde78dee58 | 5c8597cc699d0ed7 | ❌ |
| Vertex Ungrounded US | 8f11b16fa9905e0a | 74f107b3d03c5400 | ❌ |
| Vertex Ungrounded DE | 38b1de729f316429 | dbdf8461a2887bd1 | ❌ |
| Vertex Grounded US | f874cdef7f2335cf | 7a046661ce908181 | ❌ |
| Vertex Grounded DE | 3ef2257ed8e73936 | 3ef2257ed8e73936 | ✅ |

**Only 1 out of 8 configurations had matching SHA256!**

## Implications

### 🔴 CRITICAL ISSUE: Non-Deterministic ALS Generation

The ALS blocks are not deterministic across runs for the same:
- Country (US/DE)
- Vendor (OpenAI/Vertex)
- Grounding mode
- Model

This violates the **Immutability PRD** requirement that ALS blocks should be:
1. Deterministic for the same context
2. Cacheable based on SHA256
3. Reproducible across runs

### Possible Causes

1. **Timestamp in ALS Block**: If current time is included in ALS generation
2. **Random Seed**: If randomization is used without fixed seed
3. **Dynamic Data**: If ALS pulls from changing external sources
4. **Session/Request ID**: If unique identifiers are included

### Impact on Production

1. **Cache Inefficiency**: Cannot cache ALS blocks by SHA256
2. **Audit Trail Issues**: Cannot verify ALS block integrity
3. **Testing Challenges**: Cannot create deterministic test fixtures
4. **Compliance Risk**: Cannot prove consistent treatment by region

## Recommendations

### Immediate Actions Required

1. **Investigate ALS Generation Logic**
   - Check for timestamp inclusion
   - Review randomization usage
   - Identify all dynamic inputs

2. **Make ALS Deterministic**
   - Use fixed seed for any randomization
   - Remove timestamps or make them configurable
   - Ensure only country_code and locale affect output

3. **Add Determinism Tests**
   ```python
   # Test that same inputs produce same SHA256
   als1 = generate_als_block(country='US', locale='en-US')
   als2 = generate_als_block(country='US', locale='en-US')
   assert hashlib.sha256(als1).hexdigest() == hashlib.sha256(als2).hexdigest()
   ```

## Other Observations

### Successful Elements ✅
- ALS applied to all requests (100%)
- Length compliance (all under 350 chars)
- Regional differentiation working
- Telemetry fields populated

### Issues Beyond SHA256 ⚠️
- Vertex grounded tests in Run 1 had missing metadata
- OpenAI grounded tests in Run 1 had 0ms latency (likely failed)
- Content extraction varied between runs

## Conclusion

While ALS is being applied consistently, the **non-deterministic generation is a P0 blocker** for production. The same context must always produce the same ALS block and SHA256 hash for:
- Caching efficiency
- Audit compliance  
- Testing reliability
- Legal requirements

**Next Step**: Fix ALS generation to be fully deterministic based only on country_code and locale inputs.