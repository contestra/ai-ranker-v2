# Finish Reason Harmonization

## Improvement
Harmonized finish_reason handling across OpenAI and Google adapters for easier cross-vendor comparisons, with future-proofing for when OpenAI SDK adds native finish_reason support.

## Problem
Previously:
- Inconsistent finish_reason extraction between adapters
- OpenAI had basic fallback logic
- No standardization for cross-vendor comparison
- Not prepared for future SDK changes

## Solution
Enhanced both adapters with:
1. Consistent metadata storage location
2. Source tracking to know where finish_reason came from
3. Standardized values for cross-vendor comparison
4. Future-proofing for SDK updates

## Changes Made

### 1. OpenAI Adapter (`app/llm/adapters/openai_adapter.py`)

#### Priority-based extraction:
```python
# Priority 1: Future SDK field
if hasattr(response, 'finish_reason'):
    finish_reason = str(response.finish_reason)
    finish_reason_source = "sdk_native"

# Priority 2: Current SDK field  
elif hasattr(response, 'stop_reason'):
    finish_reason = str(response.stop_reason)
    finish_reason_source = "stop_reason"

# Priority 3: Inference
else:
    if content:
        finish_reason = "stop"
        finish_reason_source = "inferred_from_content"
```

#### Standardization mapping:
- `stop` → `STOP`
- `length` → `MAX_TOKENS`
- `content_filter` → `SAFETY`
- `tool_calls_only` → `TOOL_CALLS`

### 2. Google Base Adapter (`app/llm/adapters/_google_base_adapter.py`)

#### Enhanced extraction with enum/int handling:
```python
# Map Google enum/int values
reason_map = {
    1: "STOP",
    2: "MAX_TOKENS",
    3: "SAFETY",
    4: "RECITATION",
    5: "OTHER"
}
```

## Metadata Fields

All adapters now provide:

| Field | Description | Example |
|-------|-------------|---------|
| `finish_reason` | Raw finish reason from vendor | `"stop"`, `"2"`, `"STOP"` |
| `finish_reason_source` | Where the value came from | `"sdk_native"`, `"stop_reason"`, `"inferred_from_content"` |
| `finish_reason_standardized` | Standardized for comparison | `"STOP"`, `"MAX_TOKENS"`, `"SAFETY"` |

## Standardized Values

Common values across vendors:
- `STOP` - Normal completion
- `MAX_TOKENS` - Hit token limit
- `SAFETY` - Content filtered
- `ERROR` - Error occurred
- `UNKNOWN` - Unknown reason

Vendor-specific (preserved):
- `TOOL_CALLS` - OpenAI tool calls only
- `RECITATION` - Google recitation issue

## Benefits

1. **Cross-Vendor Analytics**: Compare completion patterns across all providers
2. **Unified Dashboards**: Single view of finish reasons across vendors
3. **Issue Detection**: Quickly identify MAX_TOKENS or SAFETY issues
4. **Future-Proof**: Ready for OpenAI SDK updates
5. **Debugging**: Source tracking helps understand data origin

## Example Telemetry

### OpenAI (Current SDK):
```json
{
  "finish_reason": "length",
  "finish_reason_source": "stop_reason",
  "finish_reason_standardized": "MAX_TOKENS"
}
```

### OpenAI (Future SDK):
```json
{
  "finish_reason": "stop",
  "finish_reason_source": "sdk_native",
  "finish_reason_standardized": "STOP"
}
```

### Google:
```json
{
  "finish_reason": "MAX_TOKENS",
  "finish_reason_source": "sdk_native",
  "finish_reason_standardized": "MAX_TOKENS"
}
```

## Testing
Created `test_finish_reason_harmonization.py` that documents:
- Priority-based extraction logic
- Standardization mappings
- Cross-vendor comparison benefits
- Future-proofing approach