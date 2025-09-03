# Production Gemini Model Configuration

## ⚠️ CRITICAL PRODUCTION REQUIREMENT

**ONLY USE gemini-2.5-pro IN PRODUCTION**

### DO NOT USE:
- ❌ **gemini-2.0-flash** - NEVER use for testing or production
- ❌ **gemini-1.5-flash** - NEVER use for testing or production  
- ❌ Any other flash variants

### ONLY USE:
- ✅ **gemini-2.5-pro** - The ONLY approved production model

## Why This Matters

1. **Production Consistency**: All production traffic must use the same model for consistent behavior
2. **Testing Accuracy**: Testing with flash models gives misleading results since production uses 2.5-pro
3. **Support Quality**: While flash models may return better grounding data in tests, production MUST use 2.5-pro

## Defensive Handling

The implementation includes defensive handling for when gemini-2.5-pro returns empty metadata:

```python
if len(web_searches) > 0 and len(chunks) == 0:
    # API ran search but returned no grounding data
    # Set defensive telemetry and fallback to unlinked_google
    telemetry["why_not_anchored"] = "API_RESPONSE_MISSING_GROUNDING_CHUNKS"
```

## Enforcement in Code

The gemini_adapter.py now includes automatic blocking of flash models:

```python
# Validate we're not using flash
if "flash" in model_id.lower():
    logger.error(f"BLOCKED: Attempted to use flash model: {model_id}")
    return "models/gemini-2.5-pro"  # Force to production model
```

## Testing Guidelines

When testing anchored citations:
1. ALWAYS use gemini-2.5-pro
2. Accept that it may return empty grounding metadata  
3. Verify defensive handling works correctly
4. DO NOT switch to flash models for "better" test results

## Production Status

- Adapter: Configured for gemini-2.5-pro only
- Tests: Updated to use gemini-2.5-pro exclusively
- Documentation: Clear warnings against flash usage
- Code: Automatic blocking of flash model attempts