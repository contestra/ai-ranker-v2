# Google-GenAI Grounding Fix Documentation

## Executive Summary
Successfully resolved the issue with grounding support in the google-genai SDK. The SDK **DOES** support grounding with GoogleSearch, but tools must be passed through `GenerateContentConfig` rather than as direct parameters.

## Problem Statement
The vertex_adapter.py was incorrectly attempting to use:
1. `genai.GenerativeModel` class (which doesn't exist in google-genai)
2. Direct `tools` and `tool_config` parameters to `generate_content()` (not supported)

This led to the incorrect conclusion that google-genai doesn't support grounding.

## Solution

### Key Discovery
Tools ARE supported in google-genai, but must be passed through the `GenerateContentConfig` object:

```python
# CORRECT approach
from google.genai.types import (
    GenerateContentConfig,
    Tool,
    GoogleSearch,
    ToolConfig,
    FunctionCallingConfig
)

# Configure tools
tools = [Tool(google_search=GoogleSearch())]

# Tool config
tool_config = ToolConfig(
    function_calling_config=FunctionCallingConfig(
        mode="ANY"  # or "AUTO"
    )
)

# Pass tools through config
config = GenerateContentConfig(
    systemInstruction="Your system prompt",
    temperature=0.7,
    maxOutputTokens=2000,
    tools=tools,  # Tools go HERE
    toolConfig=tool_config,  # Tool config goes HERE
    safetySettings=safety_settings
)

# Call with config only
response = client.models.generate_content(
    model="publishers/google/models/gemini-2.5-pro",
    contents=prompt,  # Just the prompt string
    config=config  # Contains everything including tools
)
```

### What Was Wrong

#### Before (Incorrect):
```python
# Trying to use non-existent GenerativeModel
model = genai.GenerativeModel(...)
model.generate_content(prompt, tools=tools)  # Wrong!

# Or trying to pass tools directly
client.models.generate_content(
    model="...",
    contents=contents,
    config=config,
    tools=tools,  # ERROR: unexpected keyword argument
    tool_config=tool_config  # ERROR: unexpected keyword argument
)
```

#### After (Correct):
```python
# Use client.models.generate_content
# Pass ALL parameters through GenerateContentConfig
client.models.generate_content(
    model="...",
    contents=prompt,
    config=config  # Contains tools, tool_config, system instruction, etc.
)
```

## Test Results

### Health & Wellness Test (August 2025)
- ✅ **Grounding successful**
- Response time: 43.8 seconds
- Web searches: 7 queries performed
- Grounding chunks: 11
- Grounding supports: 24

### Longevity Test
- ✅ **Grounding successful**
- Response time: 42.7 seconds  
- Web searches: 4 queries performed
- Grounding chunks: 11
- Grounding supports: 25

## Important Limitations

1. **Cannot mix tool types**: GoogleSearch cannot be combined with FunctionDeclaration tools
   - Error: "Multiple tools are supported only when they are all search tools"
   - Solution: Use GoogleSearch alone for grounding, or FunctionDeclaration alone for structured output

2. **System instruction placement**: Goes in `GenerateContentConfig.systemInstruction`, not as a separate Content message

3. **Parameter naming**: google-genai uses camelCase for config parameters:
   - `maxOutputTokens` (not `max_output_tokens`)
   - `topP` (not `top_p`)
   - `systemInstruction` (not `system_instruction`)
   - `toolConfig` (not `tool_config`)
   - `safetySettings` (not `safety_settings`)

## Files Modified

### Core Implementation
- `app/llm/adapters/vertex_adapter.py` - Fixed to pass tools through config
- Removed attempts to use non-existent `genai.GenerativeModel`
- Updated `_create_generation_config()` to include tools, tool_config, and safety settings

### Test Files
- `test_genai_grounded_correct.py` - Demonstrates correct usage
- `test_genai_grounded_simple.py` - Simple GoogleSearch-only test
- `test_health_wellness_august2025.py` - Real-world grounding test
- `test_genai_ungrounded.py` - Updated to use correct API

## Verification

Run the test to verify grounding works:
```bash
python3 test_genai_grounded_simple.py
```

Expected output:
```
✅ GROUNDING SUCCESSFUL! GoogleSearch was used.
✅ KEY FINDINGS:
   1. google-genai DOES support tools through GenerateContentConfig
   2. Tools must be passed in config, not as direct parameters
   3. GoogleSearch tool works for grounding
   4. Cannot mix GoogleSearch with FunctionDeclaration tools
```

## Migration Checklist

When updating code to use google-genai grounding:

1. ✅ Remove any usage of `genai.GenerativeModel` (doesn't exist)
2. ✅ Use `client.models.generate_content()` method
3. ✅ Pass tools through `GenerateContentConfig`, not as direct parameters
4. ✅ Include `systemInstruction` in config, not as separate Content
5. ✅ Use camelCase for config parameter names
6. ✅ Don't mix GoogleSearch with FunctionDeclaration tools
7. ✅ Check for grounding_metadata in response to verify grounding occurred

## Conclusion

The google-genai SDK fully supports grounding with GoogleSearch. The initial confusion arose from:
1. Incorrect API usage (trying to use non-existent GenerativeModel class)
2. Attempting to pass tools as direct parameters instead of through config
3. Not following the SDK's camelCase naming conventions

With the corrected implementation, grounding works reliably and returns comprehensive web search metadata including queries, chunks, and supports.