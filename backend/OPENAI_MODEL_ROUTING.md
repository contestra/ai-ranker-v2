# OpenAI Model Routing Strategy

## Core Routing Policy

Based on the grounding requirement, OpenAI requests are routed to different model variants:

| Request Type | Model | Reason |
|-------------|-------|--------|
| **Grounded** | `gpt-5` | Supports web_search tools via Responses API |
| **Ungrounded** | `gpt-5-chat-latest` | Chat variant, no tool support needed |

## Why This Routing?

1. **Tool Support**: `gpt-5-chat-latest` rejects hosted web_search tools with error:
   ```
   "Hosted tool 'web_search_preview' is not supported with gpt-5-chat-latest"
   ```

2. **Performance**: Each variant is optimized for its use case:
   - `gpt-5` - Optimized for tool use and structured responses
   - `gpt-5-chat-latest` - Optimized for conversational responses

## Implementation

### Current State
The routing is implemented in `unified_llm_adapter.py` but requires opt-in via environment variable:
```python
MODEL_ADJUST_FOR_GROUNDING=true  # Currently defaults to false
```

### Recommended Configuration
Enable automatic model adjustment to avoid grounding failures:
```bash
export MODEL_ADJUST_FOR_GROUNDING=true
export ALLOWED_OPENAI_MODELS=gpt-5,gpt-5-chat-latest
```

### Code Location
- **Unified Adapter**: `/app/llm/unified_llm_adapter.py` lines 136-157
  - Checks if grounded=True and model=gpt-5-chat-latest
  - Swaps to gpt-5 when MODEL_ADJUST_FOR_GROUNDING=true
  - Stores original model in metadata for telemetry

### Telemetry
When model adjustment occurs:
```json
{
  "model_adjusted_for_grounding": true,
  "original_model": "gpt-5-chat-latest",
  "effective_model": "gpt-5"
}
```

## Validation

### Test Commands
```bash
# Grounded request (should use gpt-5)
curl -X POST $API_BASE/chat/completions \
  -d '{"model": "gpt-5-chat-latest", "grounded": true, ...}'

# Ungrounded request (should use gpt-5-chat-latest)  
curl -X POST $API_BASE/chat/completions \
  -d '{"model": "gpt-5-chat-latest", "grounded": false, ...}'
```

### Expected Behavior
- Grounded + gpt-5-chat-latest → Automatically adjusted to gpt-5
- Grounded + gpt-5 → No adjustment needed
- Ungrounded + any model → No adjustment

## Fail-Safe Behavior

If MODEL_ADJUST_FOR_GROUNDING=false (current default):
1. Grounded requests to gpt-5-chat-latest will attempt tools
2. Will receive "tool not supported" error
3. Adapter will retry without tools (fallback)
4. REQUIRED mode will fail-closed
5. AUTO mode will proceed ungrounded

## Recommendation

**Enable MODEL_ADJUST_FOR_GROUNDING=true in production** to ensure:
- Grounded requests always succeed when possible
- No unnecessary fallbacks or retries
- Clear telemetry about model routing
- Consistent behavior across all grounded requests

---
*Last Updated: 2025-09-01*
*Context: ChatGPT feedback on model routing strategy*