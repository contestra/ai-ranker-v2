# P0 Fixes Remaining After ALS Determinism

## Status Update
✅ **ALS Determinism Fixed** - The main SHA256 drift issue is resolved with HMAC-based selection

## Remaining P0 Issues

### 1. Vertex LLMResponse Parity 🔴
**Problem**: VertexAdapter doesn't set critical fields on LLMResponse object
```python
# OpenAI returns:
LLMResponse(
    success=True,
    vendor="openai", 
    latency_ms=calculated,
    grounded_effective=bool
)

# Vertex missing these fields, causing telemetry gaps
```

**Fix Required**: 
- Set `success=True` on response
- Set `vendor="vertex"`
- Move `latency_ms` from metadata to response object
- Move `grounded_effective` to response object

### 2. Vendor Inference Pattern 🔴
**Problem**: Can't detect Vertex for "publishers/google/models/gemini-..."
```python
# Current logic only checks:
if model.startswith("gemini-"):
    return "vertex"

# Misses: "publishers/google/models/gemini-2.5-pro"
```

**Fix Required**:
```python
if "publishers/google/models/gemini-" in model or model.startswith("gemini-"):
    return "vertex"
```

### 3. Token Usage Keys 🔴
**Problem**: Telemetry expects different keys than OpenAI provides
```python
# OpenAI provides:
usage = {
    "input_tokens": 100,
    "output_tokens": 200
}

# Telemetry expects:
usage = {
    "prompt_tokens": 100,
    "completion_tokens": 200
}

# Result: OpenAI token counts stored as 0
```

**Fix Required**: Map keys before telemetry emission

### 4. Region Consistency 🔴
**Problem**: Conflicting defaults
```python
# Vertex init:
location = os.getenv("VERTEX_LOCATION", "europe-west4")

# Metadata reports:
"region": os.getenv("VERTEX_LOCATION", "us-central1")
```

**Fix Required**: Use same default in both places

## Impact Summary

| Issue | Impact | Telemetry Effect |
|-------|--------|------------------|
| Vertex Response | High | Missing latency, success, vendor data |
| Vendor Inference | High | Routing failures for Vertex |
| Token Keys | Medium | Zero token counts for OpenAI |
| Region | Low | Misleading location data |

## Quick Win Order
1. Fix vendor inference (1 line change)
2. Fix region default (1 line change)  
3. Fix token key mapping (5 lines)
4. Fix Vertex response shape (10 lines)

All P0s can be fixed in ~30 minutes of focused work.