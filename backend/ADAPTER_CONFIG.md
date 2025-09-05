# LLM Adapter Configuration Guide

## Environment Variables

### Critical for Production

#### Vertex AI Configuration
```bash
# REQUIRED for grounding to work properly
VERTEX_LOCATION=us-central1

# Project configuration
VERTEX_PROJECT=your-project-id  # or GCP_PROJECT or GOOGLE_CLOUD_PROJECT
```
**Note**: Vertex grounding only works in `us-central1`. The `europe-west4` region does not trigger GoogleSearch tools.

#### OpenAI Configuration
```bash
# Disable provoker retry for empty grounded responses (recommended for GPT-5)
OPENAI_PROVOKER_ENABLED=false

# API Key
OPENAI_API_KEY=your-api-key
```

#### Gemini Direct Configuration
```bash
# API Key for direct Gemini access
GEMINI_API_KEY=your-api-key  # or GOOGLE_API_KEY
```

### Optional Configurations

#### Token Limits
```bash
# Maximum tokens for different scenarios
OPENAI_GROUNDED_MAX_TOKENS=6000
VERTEX_MAX_OUTPUT_TOKENS=8192
VERTEX_GROUNDED_MAX_TOKENS=6000
GEMINI_MAX_OUTPUT_TOKENS=8192
GEMINI_GROUNDED_MAX_TOKENS=6000
```

#### Feature Flags
```bash
# Two-step synthesis for OpenAI (not recommended)
OPENAI_GROUNDED_TWO_STEP=false  # Default: false
```

## Adapter Architecture

### Refactored Google Adapters
The Vertex and Gemini adapters now share 95% of their code through a base class:
- `_google_base_adapter.py` - Shared logic for all Google models
- `vertex_adapter.py` - Thin subclass (~50 lines)
- `gemini_adapter.py` - Thin subclass (~50 lines)

### Key Features
1. **Single-call FFC**: Grounding + JSON schema handled in one API call
2. **Citation extraction**: Web sources separated from search queries
3. **Redirect decoding**: Authority domains extracted from Vertex redirect URLs
4. **REQUIRED mode enforcement**: Fail-closed when grounding evidence absent

## Model Support Status

### Fully Working
- ✅ **Gemini 2.5 Pro/Flash** (via Direct or Vertex)
- ✅ **GPT-4o** (grounded and ungrounded)
- ✅ **GPT-5** (ungrounded only - grounded returns empty)

### Known Limitations
- ⚠️ **GPT-5 grounded**: Returns empty content despite performing searches
- ⚠️ **Vertex in europe-west4**: Grounding configured but not executed

## Grounding Modes

### AUTO Mode
- Model decides whether to use grounding
- No error if grounding not triggered
- Records `grounded_effective: false` when not grounded

### REQUIRED Mode
- Must show grounding evidence or fails
- OpenAI: Requires tool calls and/or citations
- Google: Requires grounding_metadata presence
- Raises `GroundingRequiredFailedError` if evidence absent

## Testing

### Test Commands
```bash
# Test Vertex with proper region for grounding
VERTEX_LOCATION=us-central1 python3 test_vertex_grounded.py

# Test without provoker retry
OPENAI_PROVOKER_ENABLED=false python3 test_openai_grounded.py
```

### Recommended Test Prompt for Grounding
```
"summarise the health and longevity news of August 2025 in one paragraph, provide citations"
```
This prompt reliably triggers grounding when available.

## Deployment Notes

1. **Always set `VERTEX_LOCATION=us-central1`** for production if grounding is needed
2. **Consider disabling `OPENAI_PROVOKER_ENABLED`** to avoid unnecessary retries with GPT-5
3. **Monitor `grounded_effective` in telemetry** to track actual grounding usage
4. **Use REQUIRED mode sparingly** - only when grounding is absolutely necessary

## Recent Changes (September 2025)

- Eliminated 95% code duplication between Google adapters
- Fixed method scoping issues in router
- Separated search queries from citations in telemetry
- Added debug logging for grounding configuration
- Confirmed Vertex grounding requires us-central1 region
- All adapters now use SDK-only routing (no HTTP fallbacks)