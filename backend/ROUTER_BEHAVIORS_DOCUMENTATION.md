# Router Behaviors Documentation

## Post-Validation for REQUIRED Grounding Mode

### Behavior
When `grounding_mode: "REQUIRED"` is specified, the router enforces that grounding tools MUST be invoked, even for providers that cannot force tool usage (like OpenAI).

### Implementation
```python
# In unified_llm_adapter.py after response is received:
if grounding_mode == "REQUIRED" and request.grounded:
    if not response.grounded_effective:
        raise ValueError("GROUNDING_REQUIRED_FAILED: Model did not invoke tools")
```

### Flow
1. Request with `grounding_mode: "REQUIRED"` is sent to provider
2. Provider attempts grounding (OpenAI uses AUTO mode internally)
3. Router checks `grounded_effective` in response
4. If false, router raises error to fail the request
5. This ensures uniform behavior across all providers

### Error Message
```
GROUNDING_REQUIRED_FAILED: Model {model} did not invoke grounding tools despite REQUIRED mode. Provider cannot force tool usage.
```

## OpenAI Temperature Policy

### Policy Rules
1. **GPT-5**: ALWAYS uses `temperature=1.0` (model requirement)
2. **Grounded Requests**: ANY request with tools attached uses `temperature=1.0`
3. **Override Behavior**: User-provided temperatures are OVERRIDDEN in these cases

### Implementation
```python
if model_name == "gpt-5" or tools_attached:
    params["temperature"] = 1.0
    # Log override if user provided different value
    if request.temperature != 1.0:
        logger.debug(f"[TEMPERATURE_OVERRIDE] {request.temperature} -> 1.0")
```

### Implications for Downstream Teams
- **Warning**: User-specified temperatures are ignored for:
  - All GPT-5 requests
  - All grounded/tool-using requests
- **Rationale**: Ensures consistent behavior and model compliance
- **Logging**: Override is logged for debugging/audit

### Examples
```python
# User requests temperature=0.7 with GPT-5
request = LLMRequest(model="gpt-5", temperature=0.7, ...)
# Actually uses: temperature=1.0

# User requests temperature=0.3 with grounding
request = LLMRequest(grounded=True, temperature=0.3, ...)  
# Actually uses: temperature=1.0
```

## ALS Metadata Mirroring

### Purpose
Router-level hardening ensures ALS (Ambient Location Signals) metadata is always propagated to responses, even if a provider adapter forgets to copy it.

### Implementation
```python
# After receiving response from provider:
if request.metadata.get('als_present'):
    for k in ALS_METADATA_FIELDS:
        if k in request.metadata and k not in response.metadata:
            response.metadata[k] = request.metadata[k]
    response.metadata['als_mirrored_by_router'] = True
```

### Metadata Fields Mirrored
- `als_present`
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
- `als_country`
- `als_locale`
- `als_nfc_length`
- `als_template_id`

### Benefits
- **Consistency**: ALS data always available in responses
- **Debugging**: `als_mirrored_by_router` flag indicates router intervention
- **Resilience**: Protects against provider adapter bugs/omissions

## Retry Gate for web_search_preview

### Behavior
The OpenAI adapter only retries with `web_search_preview` if the original request had tools attached. This prevents noisy retries for non-grounded requests.

### Implementation
```python
# In error handler:
if "tools" in call_params and call_params["tools"]:
    # Retry with web_search_preview
    retry_params["tools"] = [{"type": "web_search_preview"}]
```

### Benefits
- Reduces unnecessary API calls
- Prevents inconsistent behavior
- Maintains retry for genuinely grounded requests

## Summary

These router behaviors ensure:
1. **Consistent grounding enforcement** across all providers via post-validation
2. **Predictable temperature behavior** with clear override rules
3. **Reliable ALS propagation** through metadata mirroring
4. **Efficient retry logic** that respects request intent

All behaviors are logged for debugging and audit purposes.