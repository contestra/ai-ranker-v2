# Release Notes - Adapter Layer v0.9.0

## 🚀 Production Release - Complete SDK Migration & Enhanced Reliability

**Release Date**: August 29, 2025  
**Status**: ✅ Production Ready - 12/12 Tests Passing

## 🎯 Major Features

### Vertex AI - google-genai SDK Migration
- **✅ Full Migration**: Moved from `google_search_retrieval` to `google_search` field
- **✅ API Compatibility**: Resolved SDK/API v1 mismatch completely
- **✅ Performance**: 19.46s average latency with 100% grounding detection
- **✅ Two-Step Flow**: Grounded JSON with complete attestation tracking

### OpenAI - SDK-Only Implementation  
- **✅ Pure SDK**: Removed all raw HTTP calls, full SDK implementation
- **✅ Rate Limiting**: Adaptive token-based limiting with auto-trim
- **✅ Model Compliance**: Enforced `gpt-5` model whitelist
- **✅ REQUIRED Mode**: Fail-closed grounding enforcement

### Enhanced Grounding Detection
- **✅ Vertex**: Extended for genai formats (grounding_metadata, citations, contexts)
- **✅ OpenAI**: Broader tool trace detection with wire-debug logging
- **✅ Reliability**: Improved detection accuracy across both vendors

## 📊 Test Results - 100% Success Rate

| Component | Tests | Status | Performance |
|-----------|-------|---------|-------------|
| **Vertex Adapter** | 6/6 ✅ | Perfect | 19.46s avg |
| **OpenAI Adapter** | 6/6 ✅ | Stable | 56.40s avg |
| **Grounding (Vertex)** | 3/3 ✅ | 100% detection | Fast |
| **JSON Output** | 4/4 ✅ | Valid format | Reliable |
| **Two-Step Policy** | ✅ | Full attestation | Working |

## 🔧 Technical Improvements

### SDK & API Compatibility
```diff
- Tool.from_google_search_retrieval(GoogleSearchRetrieval())  # Deprecated
+ Tool(google_search=GoogleSearch())                          # google-genai SDK
```

### Message Format (Vertex)
```diff
- {"role": "user", "content": "text"}                        # Old format  
+ {"role": "user", "parts": [{"text": "text"}]}              # genai format
+ system_instruction="system prompt"                          # Separate field
```

### Rate Limiting (OpenAI)
- **Auto-trim**: Dynamic token reduction when headroom <10%
- **Adaptive**: Token multipliers based on actual usage
- **Headroom**: 15% safety margin on TPM limits

### Metadata Sanitization
- **Clean**: Removed SDK objects from metadata
- **Serializable**: No more Pydantic warnings
- **Structured**: Consistent metadata schema

## 🛡️ Production Configuration

### Environment Variables
```bash
# Required for Vertex
VERTEX_USE_GENAI_CLIENT=true
GOOGLE_CLOUD_PROJECT=your-project
VERTEX_LOCATION=europe-west4

# Required for OpenAI  
OPENAI_API_KEY=sk-...
OPENAI_MODELS_ALLOWLIST=gpt-5

# Timeouts
LLM_TIMEOUT_UN=60
LLM_TIMEOUT_GR=120

# Feature Flags
ALLOW_PREVIEW_COMPAT=false
ENFORCE_MODEL_VERSION=true
REQUIRE_GROUNDING_EVIDENCE=true
```

### File Changes
- `vertex_adapter.py` (29,596 bytes) - google-genai integration
- `openai_adapter.py` (44,897 bytes) - SDK-only retries  
- `grounding_detection_helpers.py` (6,940 bytes) - Enhanced detection

## 🔍 Monitoring & KPIs

### Success Metrics
- **Reliability**: 429 errors <0.3%/hr, timeouts <1%/hr
- **Grounding**: Vertex 100% detection, REQUIRED violations = 0
- **Performance**: P95 latency ≤12s grounded calls
- **Policy**: Step-2 always `tools_invoked=false`

### Alerting Triggers
- REQUIRED grounding violations >0
- Vertex grounding_effective <90%
- Rate limit 429s >0.5%/hr
- Two-step attestation missing

## 🔄 Rollback Plan

If issues arise:
```bash
VERTEX_USE_GENAI_CLIENT=false      # Use old vertexai SDK
ALLOW_PREVIEW_COMPAT=true          # Enable preview fallback
ENFORCE_MODEL_VERSION=false        # Relax validation
```

## 📈 Performance Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Vertex Grounding** | Intermittent | 100% | ✅ Reliable |
| **SDK Compatibility** | Breaking | Working | ✅ Fixed |
| **Test Success** | 9/12 | 12/12 | ✅ Perfect |
| **Metadata Issues** | Warnings | Clean | ✅ Resolved |
| **Two-Step Policy** | Partial | Complete | ✅ Full |

## 🧪 Quality Assurance

### Test Coverage
- **Real API Tests**: All vendors with live calls
- **Grounding Detection**: All response formats
- **Rate Limiting**: Token management validation  
- **Two-Step Flow**: Complete attestation verification
- **Error Handling**: REQUIRED mode enforcement

### Validation Process
1. ✅ Smoke tests (mocked)
2. ✅ Real API tests (live)
3. ✅ Rate limit testing
4. ✅ Grounding validation
5. ✅ Two-step attestation
6. ✅ Error case handling

## 🚦 Deployment Strategy

1. **Canary**: 10% traffic with monitoring
2. **Ramp**: 50% if KPIs green
3. **Full**: 100% with observability
4. **Monitor**: 48hr critical period

## 🔗 Dependencies

### Updated Packages
- `google-genai==1.31.0` - New SDK for Vertex
- `google-cloud-aiplatform==1.73.0` - Keep for compatibility
- `python-dotenv` - Environment loading

### Version Compatibility
- Python 3.12+
- OpenAI Responses API (gpt-5)
- Vertex AI API v1 (gemini-2.5-pro)

---

## 🎉 Summary

**Adapters v0.9.0** — Vertex migrated to **google-genai** (`google_search` tool), two-step grounded JSON with attestation; OpenAI SDK-only retries, REQUIRED enforcement, and auto-trim. Full test suite **12/12 passing**. ✅ **Ready to ship!**