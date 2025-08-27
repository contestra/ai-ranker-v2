# Longevity Supplement Geographic A/B Test Matrix

## Test Objective
Validate geographic differentiation in LLM responses based on ALS (Ambient Location System) and proxy routing configurations.

## The Prompt
```
What are the best longevity supplements available in my area? 
Please recommend specific brands and products I can purchase locally.
```

## Complete Test Matrix (32 Tests)

### Test Configuration

| # | Vendor | Country | Vantage Policy | Grounded | Description | Expected Result |
|---|--------|---------|---------------|----------|-------------|-----------------|
| **OpenAI Tests (gpt-5)** |
| 1 | OpenAI | - | NONE | false | No ALS, No Proxy, Ungrounded | Generic/Global brands |
| 2 | OpenAI | - | NONE | true | No ALS, No Proxy, Grounded | Generic + web research |
| 3 | OpenAI | US | PROXY_ONLY | false | No ALS, US Proxy, Ungrounded | US proxy location brands |
| 4 | OpenAI | US | PROXY_ONLY | true | No ALS, US Proxy, Grounded | US proxy + research |
| 5 | OpenAI | DE | PROXY_ONLY | false | No ALS, DE Proxy, Ungrounded | DE proxy location brands |
| 6 | OpenAI | DE | PROXY_ONLY | true | No ALS, DE Proxy, Grounded | DE proxy + research |
| 7 | OpenAI | US | ALS_ONLY | false | US ALS, No Proxy, Ungrounded | US-focused brands |
| 8 | OpenAI | US | ALS_ONLY | true | US ALS, No Proxy, Grounded | US brands + research |
| 9 | OpenAI | US | ALS_PLUS_PROXY | false | US ALS + Proxy, Ungrounded | US brands via proxy |
| 10 | OpenAI | US | ALS_PLUS_PROXY | true | US ALS + Proxy, Grounded | US brands + research via proxy |
| 11 | OpenAI | DE | ALS_ONLY | false | DE ALS, No Proxy, Ungrounded | DE/EU-focused brands |
| 12 | OpenAI | DE | ALS_ONLY | true | DE ALS, No Proxy, Grounded | DE/EU brands + research |
| 13 | OpenAI | DE | ALS_PLUS_PROXY | false | DE ALS + Proxy, Ungrounded | DE/EU brands via proxy |
| 14 | OpenAI | DE | ALS_PLUS_PROXY | true | DE ALS + Proxy, Grounded | DE/EU brands + research via proxy |
| **Vertex Tests (gemini-2.5-pro)** |
| 15 | Vertex | - | NONE | false | No ALS, No Proxy, Ungrounded | Generic/Global brands |
| 16 | Vertex | - | NONE | true | No ALS, No Proxy, Grounded | Generic + Google Search |
| 17 | Vertex | US | PROXY_ONLY | false | No ALS, US Proxy, Ungrounded | US proxy location brands |
| 18 | Vertex | US | PROXY_ONLY | true | No ALS, US Proxy, Grounded | US proxy + Google Search |
| 19 | Vertex | DE | PROXY_ONLY | false | No ALS, DE Proxy, Ungrounded | DE proxy location brands |
| 20 | Vertex | DE | PROXY_ONLY | true | No ALS, DE Proxy, Grounded | DE proxy + Google Search |
| 21 | Vertex | US | ALS_ONLY | false | US ALS, No Proxy, Ungrounded | US-focused brands |
| 22 | Vertex | US | ALS_ONLY | true | US ALS, No Proxy, Grounded | US brands + Google Search |
| 23 | Vertex | US | ALS_PLUS_PROXY | false | US ALS + Proxy, Ungrounded | US brands via proxy |
| 24 | Vertex | US | ALS_PLUS_PROXY | true | US ALS + Proxy, Grounded | US brands + Google Search via proxy |
| 25 | Vertex | DE | ALS_ONLY | false | DE ALS, No Proxy, Ungrounded | DE/EU-focused brands |
| 26 | Vertex | DE | ALS_ONLY | true | DE ALS, No Proxy, Grounded | DE/EU brands + Google Search |
| 27 | Vertex | DE | ALS_PLUS_PROXY | false | DE ALS + Proxy, Ungrounded | DE/EU brands via proxy |
| 28 | Vertex | DE | ALS_PLUS_PROXY | true | DE ALS + Proxy, Grounded | DE/EU brands + Google Search via proxy |

## Vendor-Specific Parameters

### OpenAI (gpt-5)
- **Model**: gpt-5
- **Max Tokens**: 6000 (ALWAYS!)
- **Temperature**: 1.0 (FORCED - gpt-5 always uses 1.0)
- **Text Parameter**: `{"verbosity": "medium"}`
- **Grounding**: Uses `tools: [{"type": "web_search"}]` when grounded=true
- **Tool Choice**: "auto"
- **Streaming**: true (for performance)

### Vertex (gemini-2.5-pro)
- **Model**: gemini-2.5-pro  
- **Max Tokens**: 6000 (ALWAYS!)
- **Temperature**: 0.3
- **Grounding**: Google Search when grounded=true (server-side, ALS affects results)
- **Note**: Uses "thinking tokens" (~400) so needs higher max_tokens

## Expected Geographic Differentiation

### US Market Brands
- Life Extension
- Thorne Research
- NOW Foods
- Jarrow Formulas
- Pure Encapsulations
- Doctor's Best
- Nordic Naturals
- Garden of Life

### DE/EU Market Brands
- Orthomol
- Doppelherz
- Abtei
- Tetesept
- Schaebens
- Klosterfrau
- Merz
- EU-certified supplements

### Generic/Global (NONE policy)
- Mix of international brands
- No specific geographic focus
- General supplement recommendations

## Test Execution Notes

1. **Rate Limiting**: 
   - OpenAI: Max 3 concurrent, 15s stagger
   - Vertex: Max 4 concurrent (1 if proxied)

2. **Timeouts**:
   - OpenAI: 240s read, 300s total
   - Vertex: 480s direct, 300s proxied

3. **Proxy Behavior**:
   - PROXY_ONLY requires country specification (US or DE)
   - Vertex grounded uses GenAI path (no proxy effect on Google Search)
   - OpenAI respects proxy for all requests

4. **Success Criteria**:
   - Clear geographic differentiation in brand recommendations
   - Consistent results within same country/policy combinations
   - Grounded results should include recent research/studies

## Test Implementation
See `/tmp/test_longevity_matrix.py` for the complete test implementation.

---
**Last Updated**: 2025-08-27
**Status**: Ready for execution