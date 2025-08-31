# Cache Poisoning Fixes Summary
## Date: 2025-08-31

## Problem Statement
The tri-state cache was being poisoned due to model key mismatches. The cache was keyed on the pre-adjusted model (`gpt-5-chat-latest`) while the runtime actually used `gpt-5` after adjustment, causing conflicting signals about tool support.

## Root Causes Identified

1. **Model Normalization Reversal**: The `normalize_model` function was reversing the model adjustment:
   - Unified adapter: `gpt-5-chat-latest` → `gpt-5` (for grounded requests)
   - OpenAI adapter: Called `normalize_model` which changed `gpt-5` → `gpt-5-chat-latest` (undoing adjustment)

2. **Cache Key Mismatch**: The cache was using the normalized model as key, which could differ from the adjusted model.

3. **Duplicate Adjustment**: When users sent `gpt-5` directly, it was normalized to `gpt-5-chat-latest`, then adjusted back to `gpt-5`.

4. **Tool Choice Incompatibility**: REQUIRED mode was setting `tool_choice="required"` which isn't supported with web_search tools.

## Fixes Applied

### 1. Preserve Model Adjustment in OpenAI Adapter
**File**: `app/llm/adapters/openai_adapter.py`
```python
# Check if model was already adjusted for grounding - if so, skip normalization
model_adjusted = False
if hasattr(request, 'metadata') and request.metadata:
    model_adjusted = request.metadata.get('model_adjusted_for_grounding', False)

if model_adjusted:
    # Model was already adjusted in unified adapter, use as-is
    model_name = request.model
    logger.debug(f"[MODEL] Using pre-adjusted model: {model_name}")
else:
    # Normal normalization path
    model_name = normalize_model("openai", request.model)
```

### 2. Fix Adjustment Logic to Check Pre-Normalized Model
**File**: `app/llm/unified_llm_adapter.py`
```python
# Store original model before normalization for adjustment check
original_model_pre_norm = request.model
# Normalize model
request.model = normalize_model(request.vendor, request.model)

# Only adjust if original (pre-normalized) model was gpt-5-chat-latest
if (request.vendor == "openai" and 
    request.grounded is True and 
    original_model_pre_norm == "gpt-5-chat-latest" and  # Check pre-normalized
    model_adjust_enabled):
```

### 3. Fix Tool Choice for Web Search
**File**: `app/llm/adapters/openai_adapter.py`
```python
# Set tool_choice - web_search tools only support "auto"
# Even in REQUIRED mode, we must use "auto" but enforce afterward
params["tool_choice"] = "auto"  # web_search doesn't support "required"
logger.debug(f"[TOOL_CHOICE] Using tool_choice=auto (web_search limitation)")
```

### 4. Enhanced Logging for Cache Operations
**File**: `app/llm/adapters/openai_adapter.py`
```python
# Cache check logging
logger.debug(f"[CACHE_CHECK] Checking cache for model: {model_name} (adjusted: {model_adjusted})")
logger.debug(f"[CACHE_CHECK] Result for {model_name}: {cached_tool_type}")

# Cache set logging
logger.info(f"[CACHE_SET] Set tool type for {model}: {tool_type}")
logger.debug(f"[CACHE_SET] Current cache state: {list(self._web_search_tool_type.keys())}")

# API call logging
logger.info(f"[API_CALL] Using model: {model_name} (was_adjusted: {model_adjusted})")
```

### 5. Fix Error Messages to Use Correct Model
**File**: `app/llm/adapters/openai_adapter.py`
```python
# Use model_name (effective model) instead of request.model in error messages
raise GroundingNotSupportedError(
    f"GROUNDING_NOT_SUPPORTED: Model {model_name} does not support..."
)
```

## Verification Tests Created

1. **test_cache_fix.py**: Verifies cache key consistency with model adjustment
2. **test_sanity_matrix.py**: Comprehensive matrix testing all combinations

## Test Results

### Cache Fix Test Results
- ✅ Model adjustment preserved correctly
- ✅ No cache poisoning detected
- ✅ Cache uses correct model key (post-adjustment)
- ✅ Direct gpt-5 requests no longer cause duplicate adjustment

### Sanity Matrix Results
- ✅ Model adjustment: 4/4 correct
- ✅ Cache integrity: 2/2 consistent
- ✅ No cache key conflicts
- ⚠️  REQUIRED mode enforcement limited by API (tool_choice must be "auto")

## Impact

1. **Cache Poisoning Eliminated**: Cache now correctly keys on the effective model
2. **Consistent Behavior**: Same model/grounding combination always produces same result
3. **Proper Model Flow**: gpt-5-chat-latest → gpt-5 adjustment only happens when needed
4. **Clear Telemetry**: Comprehensive logging tracks model transformation

## Remaining Considerations

1. **Empty Results**: OpenAI web_search still returns empty results (API-side issue)
2. **REQUIRED Mode**: Cannot force tool invocation due to API limitations
3. **Tool Variants**: Still using two-pass fallback for web_search vs web_search_preview

## Recommendation

The cache poisoning issue has been fully resolved. The system now:
- Correctly handles model adjustment without conflicts
- Maintains cache integrity across all model variations
- Provides clear telemetry for debugging
- Gracefully handles API limitations

Next steps should focus on:
1. Implementing retry-on-empty for critical grounding requests
2. Adding metrics to track empty result rates
3. Consider fallback to alternate providers when grounding is critical