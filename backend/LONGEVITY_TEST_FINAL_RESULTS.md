# Longevity Supplement Test Results - Final Report

**Date**: August 27, 2025  
**Time**: 17:14 CEST  
**Test Type**: Geographic Localization with ALS (Ambient Location System)

## Executive Summary

Testing longevity supplement recommendations across different geographic regions using OpenAI GPT-5 and Google Vertex Gemini 2.5 Pro with proper ALS ambient context blocks.

**Overall Success Rate: 75%** (3 of 4 scenarios passed)

## Test Configuration

### Models Tested
- **OpenAI**: GPT-5 (with rate limiting: 3 concurrent, 15s stagger)
- **Vertex**: Gemini 2.5 Pro

### Parameters
- **Max Tokens**: 6000
- **Temperature**: 0.3
- **Vantage Policy**: ALS_ONLY
- **System Prompt**: ALS_SYSTEM_PROMPT (proper ambient context handling)

### Geographic Regions
- **US**: United States (expecting US brands)
- **DE**: Germany (expecting European brands)

## Detailed Test Results

### Test 1: OpenAI GPT-5 with US ALS ✅ PASS

**Duration**: 40.1 seconds

**ALS Block Used**:
```
Ambient Context (localization only; do not cite):
- 08/27/2025 13:13, UTC-04:00
- state DMV — "driver's license renewal"
- New York, NY 10001 • (212) xxx-xxxx • $12.90
- state sales tax — general info
```

**Brands Found**: 4 US brands
- Life Extension ✓
- Thorne ✓
- Jarrow ✓
- Nordic Naturals ✓

**Response Preview**:
> "Short answer: no supplement is proven to extend human lifespan, but a few have decent evidence for supporting healthy aging and are easy to find at major pharmacies, natural-food stores, big-box retailers..."

**Analysis**: Excellent US localization with major American supplement brands.

---

### Test 2: OpenAI GPT-5 with DE ALS ⚠️ PARTIAL

**Duration**: 58.8 seconds

**ALS Block Used**:
```
Ambient Context (localization only; do not cite):
- 27.08.2025 17:08, UTC+02:00
- Bundesportal — "Reisepass beantragen Termin"
- 10115 Berlin • +49 30 xxx xx xx • 12,90 €
- MwSt. — allgemeine Auskünfte
```

**Brands Found**: 1 EU brand (insufficient)
- Sunday Natural ✓

**Expected But Missing**:
- Orthomol ✗
- Doppelherz ✗
- Abtei ✗
- Vitabay ✗
- Sanct Bernhard ✗

**Response Preview**:
> "Short answer: focus on a few 'foundational' supplements with the best evidence for healthy aging, and only then consider the experimental add-ons. Below are options that are widely available online and..."

**Analysis**: Poor German localization. Only found 1 European brand when multiple should be recommended. The ALS context didn't sufficiently influence brand selection.

---

### Test 3: Vertex Gemini 2.5 Pro with US ALS ✅ PASS

**Duration**: 40.7 seconds

**ALS Block Used**: Same US context as Test 1

**Brands Found**: 5 US brands
- Life Extension ✓
- Thorne ✓
- NOW Foods ✓
- Nordic Naturals ✓
- Pure Encapsulations ✓

**Response Preview**:
> "Of course. It's important to remember that the supplement industry isn't regulated like pharmaceuticals, so quality and purity can vary significantly. Always talk to your doctor before starting any new..."

**Analysis**: Excellent US localization, even better than OpenAI with 5 brands found.

---

### Test 4: Vertex Gemini 2.5 Pro with DE ALS ✅ PASS

**Duration**: 23.7 seconds

**ALS Block Used**: Same DE context as Test 2

**Brands Found**: 2 EU brands
- Doppelherz ✓
- Sunday Natural ✓

**Response Preview**:
> "It's essential to consult with a healthcare professional or a doctor before starting any new supplement regimen. They can provide personalised advice based on your health status and needs, and perform..."

**Analysis**: Better German localization than OpenAI, successfully identifying multiple European brands.

## Brand Detection Summary

### US Brands Performance
| Brand | OpenAI US | Vertex US |
|-------|-----------|-----------|
| Life Extension | ✅ | ✅ |
| Thorne | ✅ | ✅ |
| NOW Foods | ❌ | ✅ |
| Jarrow | ✅ | ❌ |
| Nordic Naturals | ✅ | ✅ |
| Pure Encapsulations | ❌ | ✅ |
| **Total** | **4/6** | **5/6** |

### EU Brands Performance
| Brand | OpenAI DE | Vertex DE |
|-------|-----------|-----------|
| Orthomol | ❌ | ❌ |
| Doppelherz | ❌ | ✅ |
| Abtei | ❌ | ❌ |
| Sunday Natural | ✅ | ✅ |
| Vitabay | ❌ | ❌ |
| Sanct Bernhard | ❌ | ❌ |
| **Total** | **1/6** | **2/6** |

## Technical Verification

### ✅ Confirmed Working
1. **Rate Limiting**: No 429 errors, proper 15-second staggering observed
2. **ALS Blocks**: Properly generated with ambient context markers
3. **3-Step Message Structure**: System → User(ALS) → User(Prompt)
4. **Model Parameters**: Correct models, tokens, temperature
5. **Cryptographic Hashing**: Request/response hashes generated

### ❌ Not Working
1. **Database Logging**: Results not saved to Neon database (by design - direct adapter calls)
2. **OpenAI DE Localization**: Only 1 EU brand vs expected 2+

## Response Quality Analysis

### OpenAI GPT-5
- **US Response**: High quality, specific brand recommendations
- **DE Response**: Generic advice, minimal localization
- **Token Usage**: ~3,500-4,000 completion tokens per response

### Vertex Gemini 2.5 Pro
- **US Response**: Comprehensive with safety disclaimers
- **DE Response**: Better localized than OpenAI
- **Speed**: Faster responses (23-40s vs 40-58s)

## Rate Limiting Performance

With the new adapter-level rate limiting:
- **Concurrency**: Limited to 3 simultaneous requests ✅
- **Stagger**: 15-second delays between launches ✅
- **No 429 Errors**: 100% success rate ✅
- **Total Test Duration**: ~3 minutes for all 4 tests

## Conclusions

### Strengths
1. **Vertex AI** performs better at geographic localization
2. **US localization** works well for both models
3. **Rate limiting** completely eliminates 429 errors
4. **ALS system** properly generates ambient context

### Weaknesses
1. **OpenAI German localization** is inadequate (only 1 EU brand)
2. **EU brand coverage** is generally weak for both models
3. **Database persistence** not implemented for test runs

## Recommendations

1. **For Production**: Use Vertex for European markets, either model for US
2. **ALS Improvements**: May need stronger geographic signals for EU regions
3. **Database Logging**: Implement if audit trail needed
4. **Model Selection**: Consider Vertex as primary for better localization

## Test Files

- **JSON Data**: `TEST_MATRIX_RESULTS_20250827_171448.json`
- **Markdown Summary**: `TEST_MATRIX_RESULTS_20250827_171448.md`
- **This Report**: `LONGEVITY_TEST_FINAL_RESULTS.md`

---

*Test executed using AI Ranker V2 with ChatGPT's rate limiting implementation*  
*All tests completed without rate limit errors*