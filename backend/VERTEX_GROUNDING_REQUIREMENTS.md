# Vertex Grounding Requirements

## Critical Requirement: google-genai

**All Vertex grounded requests REQUIRE the google-genai client library.**

The vertexai SDK fallback does not properly support grounding, leading to `grounded_effective = False` in QA reports.

## Installation

```bash
pip install google-genai>=0.8.3
```

## Behavior

### With google-genai Available
- Grounded requests work correctly
- Citations are properly extracted
- `grounded_effective = true` when tools are invoked

### Without google-genai
- **Grounded requests fail immediately** with clear error:
  ```
  GROUNDING_REQUIRES_GENAI: Grounded requests require google-genai client.
  Current state: GENAI_AVAILABLE=False, use_genai=False.
  To fix: pip install google-genai>=0.8.3 and ensure VERTEX_USE_GENAI_CLIENT != 'false'
  ```
- Ungrounded requests continue to work using vertexai SDK

## Startup Checks

The adapter performs startup checks and logs warnings:

```python
[VERTEX_STARTUP] google-genai not available. Grounded requests will fail.
To fix: pip install google-genai>=0.8.3
```

Or if disabled by environment:

```python
[VERTEX_STARTUP] google-genai disabled by VERTEX_USE_GENAI_CLIENT=false.
Grounded requests will fail. To fix: unset or set VERTEX_USE_GENAI_CLIENT=true
```

## Environment Variables

- `VERTEX_USE_GENAI_CLIENT`: Set to `"false"` to disable google-genai (not recommended)
  - Default: `"true"`
  - If set to `"false"`, grounded requests will fail

## Implementation Details

The fail-closed check happens early in the request flow:

```python
# In vertex_adapter.py complete() method
if is_grounded and not self.use_genai:
    raise ValueError("GROUNDING_REQUIRES_GENAI: ...")
```

This ensures:
1. Fast failure with clear error message
2. No confusing fallback behavior
3. Clear guidance on how to fix

## QA Impact

This change directly addresses the "Vertex grounded_effective = False" rows in QA reports:

### Before
- Grounded requests silently fell back to vertexai SDK
- Tools were never invoked
- QA reports showed: `vertex:gemini-2.5-pro:AUTO→auto_no_tools`

### After
- Grounded requests without google-genai fail immediately
- Clear error: `GROUNDING_REQUIRES_GENAI`
- QA reports show: `vertex:gemini-2.5-pro:AUTO→ERROR` with clear reason

## Testing

Run the test to verify behavior:

```bash
python test_vertex_genai_requirement.py
```

Expected output:
- Ungrounded requests: Continue to work
- Grounded requests without genai: Fail with clear error
- Error message: Contains installation instructions

## Deployment Checklist

1. ✅ Ensure `google-genai>=0.8.3` is in requirements.txt
2. ✅ Verify VERTEX_USE_GENAI_CLIENT is not set to "false"
3. ✅ Check startup logs for successful initialization:
   ```
   [VERTEX_STARTUP] google-genai client initialized successfully (grounding enabled)
   ```
4. ✅ Test a grounded request to confirm it works

## Troubleshooting

### Issue: ImportError for google.genai
**Solution**: `pip install google-genai>=0.8.3`

### Issue: VERTEX_USE_GENAI_CLIENT=false
**Solution**: Unset the variable or set to "true"

### Issue: Authentication errors with google-genai
**Solution**: Ensure ADC is configured: `gcloud auth application-default login`

### Issue: Still seeing grounded_effective=false
**Check**:
1. Startup logs show genai initialized
2. No errors during initialization
3. Request actually has `grounded=True`
4. Model is invoking tools (check tool_call_count)