# Reasoning/Thinking Hint Tracking Enhancement

## Nice-to-Have Improvement
Added comprehensive tracking of when reasoning/thinking hints are dropped or applied across router and adapters.

## Problem
Previously, the router tracked when it dropped reasoning hints, but:
- Adapters didn't track when they chose not to apply hints
- No clear reason was provided for why hints were dropped
- Inconsistent metadata between router and adapter drops

## Solution
Enhanced both router and adapters to provide consistent hint tracking with clear reasons.

## Changes Made

### 1. OpenAI Adapter (`app/llm/adapters/openai_adapter.py`)
Added tracking for reasoning hints:
```python
# When hints are applied
metadata["reasoning_effort_applied"] = reasoning_effort

# When hints are dropped
metadata["reasoning_hint_dropped"] = True
metadata["reasoning_hint_drop_reason"] = "model_not_capable"
```

### 2. Google Base Adapter (`app/llm/adapters/_google_base_adapter.py`)
Added tracking for thinking hints:
```python
# When hints are applied
metadata["thinking_hint_applied"] = True

# When hints are dropped
metadata["thinking_hint_dropped"] = True
metadata["thinking_hint_drop_reason"] = "model_not_capable"
```

### 3. Router (`app/llm/unified_llm_adapter.py`)
Enhanced to:
- Preserve adapter-level hint drop metadata
- Add drop reasons when router drops hints
- Ensure metadata parity across all paths

```python
# Preserve adapter-level drops if they exist
if 'reasoning_hint_dropped' not in response.metadata:
    response.metadata['reasoning_hint_dropped'] = reasoning_hint_dropped

# Add drop reason if router dropped
if reasoning_hint_dropped and 'reasoning_hint_drop_reason' not in response.metadata:
    response.metadata['reasoning_hint_drop_reason'] = 'router_capability_gate'
```

## Metadata Fields

### For Reasoning Hints (OpenAI)
- `reasoning_hint_dropped`: Boolean indicating if hint was dropped
- `reasoning_hint_drop_reason`: Why it was dropped
  - `"router_capability_gate"`: Router dropped based on capabilities
  - `"model_not_capable"`: Adapter dropped for non-reasoning model
- `reasoning_effort_applied`: The actual effort value applied (when successful)

### For Thinking Hints (Google)
- `thinking_hint_dropped`: Boolean indicating if hint was dropped
- `thinking_hint_drop_reason`: Why it was dropped
  - `"router_capability_gate"`: Router dropped based on capabilities
  - `"model_not_capable"`: Adapter dropped for non-thinking model
- `thinking_hint_applied`: True when thinking config was applied
- `thinking_budget_tokens`: The actual budget applied
- `include_thoughts`: Whether thoughts are included

## Benefits
1. **Clear Visibility**: Know exactly when and why hints are dropped
2. **Debugging**: Drop reasons help identify configuration issues
3. **Telemetry**: Track hint application success rates
4. **Consistency**: Same metadata pattern across all adapters
5. **Two-Level Tracking**: Both router and adapter drops are captured

## Testing
Created `test_reasoning_hint_tracking.py` that verifies:
- Router correctly identifies model capabilities
- Hints are dropped for non-capable models
- Metadata includes appropriate drop reasons
- Parity maintained across OpenAI and Google adapters

## Example Telemetry
```json
{
  "reasoning_hint_dropped": true,
  "reasoning_hint_drop_reason": "router_capability_gate",
  "model": "gpt-4o",
  "requested_reasoning_effort": "high"
}
```

This allows dashboards to track:
- What percentage of requests with reasoning hints are dropped
- Which models are being used incorrectly with hints
- Whether drops are happening at router or adapter level