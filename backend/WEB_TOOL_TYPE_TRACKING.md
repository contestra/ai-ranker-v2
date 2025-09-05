# Web Tool Type Tracking Enhancement

## Improvement
Added consistent tracking of web tool types across adapters, including both initial and final values when negotiation occurs.

## Problem
Previously:
- Google adapter used `"google_search"` 
- OpenAI adapter used `"web_search"` or `"web_search_preview"`
- Only tracked final tool type, not initial attempts
- No visibility into tool negotiation/fallback

## Solution
Enhanced both adapters to track initial and final tool types consistently, with additional tracking for negotiation and retries.

## Changes Made

### 1. OpenAI Adapter (`app/llm/adapters/openai_adapter.py`)

#### Standard grounded call:
```python
metadata["web_tool_type_initial"] = "web_search"  # Always starts with this
metadata["web_tool_type_final"] = web_tool_type   # What actually worked
metadata["web_tool_type"] = web_tool_type         # Backward compatibility
if web_tool_type != "web_search":
    metadata["web_tool_type_negotiated"] = True   # Track fallback occurred
```

#### Provoker retry path:
```python
metadata["provoker_initial_tool_type"] = web_tool_type  # Before retry
metadata["provoker_final_tool_type"] = retry_tool_type  # After retry
if retry_tool_type != web_tool_type:
    metadata["provoker_tool_type_changed"] = True
```

### 2. Google Base Adapter (`app/llm/adapters/_google_base_adapter.py`)

```python
metadata["web_tool_type_initial"] = "google_search"
metadata["web_tool_type_final"] = "google_search"  # No negotiation in Google
metadata["web_tool_type"] = "google_search"        # Backward compatibility
```

## Metadata Fields

### Common Fields (All Adapters):
- `web_tool_type`: Final tool type used (backward compatibility)
- `web_tool_type_initial`: What the adapter started with
- `web_tool_type_final`: What the adapter ended up using

### OpenAI-Specific Fields:
- `web_tool_type_negotiated`: `true` if fallback from web_search to web_search_preview
- `provoker_initial_tool_type`: Tool type before provoker retry
- `provoker_final_tool_type`: Tool type after provoker retry  
- `provoker_tool_type_changed`: `true` if tool changed during retry

## Tool Type Values:
- OpenAI: `"web_search"`, `"web_search_preview"`
- Google: `"google_search"`

## Benefits

1. **Quality Correlation**: Can now correlate answer quality with specific tool versions
2. **Negotiation Visibility**: Track when and why fallbacks occur
3. **Retry Analysis**: Understand impact of tool changes during retries
4. **Cross-Vendor Comparison**: Compare effectiveness of different search tools
5. **Debugging**: Clear visibility into tool selection process

## Example Scenarios

### Scenario 1: OpenAI with successful web_search
```json
{
  "web_tool_type_initial": "web_search",
  "web_tool_type_final": "web_search",
  "web_tool_type": "web_search"
}
```

### Scenario 2: OpenAI with fallback
```json
{
  "web_tool_type_initial": "web_search",
  "web_tool_type_final": "web_search_preview",
  "web_tool_type": "web_search_preview",
  "web_tool_type_negotiated": true
}
```

### Scenario 3: OpenAI with provoker retry and tool change
```json
{
  "web_tool_type_initial": "web_search",
  "web_tool_type_final": "web_search_preview",
  "web_tool_type": "web_search_preview",
  "provoker_initial_tool_type": "web_search",
  "provoker_final_tool_type": "web_search_preview",
  "provoker_tool_type_changed": true
}
```

### Scenario 4: Google (no negotiation)
```json
{
  "web_tool_type_initial": "google_search",
  "web_tool_type_final": "google_search",
  "web_tool_type": "google_search"
}
```

## Testing
Created `test_web_tool_type_tracking.py` that documents:
- All tracking scenarios
- Expected metadata fields
- Correlation benefits
- Cross-adapter consistency