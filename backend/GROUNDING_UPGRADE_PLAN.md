# Grounding Implementation Upgrade Plan

## Executive Summary
Both OpenAI and Vertex adapters currently lack grounding support. This plan outlines the implementation of two grounding modes (UN/GR) for both providers using direct SDK approaches learned from legacy code analysis.

## Grounding Requirements

### Two Modes Only
1. **UN (Ungrounded)** - Model knowledge only, no web search
2. **GR (Grounded)** - Web search enabled
   - **Gemini**: Auto-grounding (searches when needed)
   - **GPT-5**: Always performs web search

### No Support For
- ❌ Vertex forced grounding mode
- ❌ Complex grounding configurations
- ❌ LangChain/LangSmith integration

## Current State Analysis

### OpenAI Adapter (`openai_adapter.py`)
- ✅ Basic completion working
- ✅ Responses API integration
- ❌ Missing: Web search tools
- ❌ Missing: Grounding detection
- ❌ Missing: Citation extraction

### Vertex Adapter (`vertex_adapter.py`)
- ✅ Basic completion working
- ✅ ADC/WIF authentication
- ❌ Missing: GoogleSearch tool
- ❌ Missing: Grounding metadata extraction
- ❌ Missing: Global location for better grounding

## Implementation Plan

### Phase 1: Update Type Definitions

**File**: `app/llm/types.py`
```python
from enum import Enum

class GroundingMode(str, Enum):
    UN = "ungrounded"  # No web search
    GR = "grounded"    # Web search enabled

# Update LLMRequest
class LLMRequest:
    grounding_mode: GroundingMode = GroundingMode.UN  # Replace boolean
    
# Update LLMResponse  
class LLMResponse:
    grounded_effective: bool  # Did grounding actually occur?
    grounding_metadata: Optional[Dict]  # Citations, queries, etc.
```

### Phase 2: OpenAI Adapter Upgrade

**File**: `app/llm/adapters/openai_adapter.py`

#### Changes Required:
1. **Add Web Search Tool**:
```python
async def complete(self, request: LLMRequest) -> LLMResponse:
    params = {...}
    
    # Add web search for GR mode
    if request.grounding_mode == GroundingMode.GR:
        params["tools"] = [{"type": "web_search"}]
        params["tool_choice"] = "auto"  # GPT-5 limitation
```

2. **Detect Grounding**:
```python
def _detect_grounding(response) -> tuple[bool, Dict]:
    """Check if web search was actually used"""
    tool_calls = 0
    citations = []
    
    output = getattr(response, "output", [])
    for item in output:
        if item.get("type") == "web_search_result":
            tool_calls += 1
            citations.extend(item.get("results", []))
    
    return tool_calls > 0, {"tool_calls": tool_calls, "citations": citations}
```

3. **Handle GPT-5 Specifics**:
```python
# GPT-5 requires temperature=1.0 with tools
if request.model == "gpt-5" and request.grounding_mode == GroundingMode.GR:
    params["temperature"] = 1.0
```

### Phase 3: Vertex Adapter Upgrade

**File**: `app/llm/adapters/vertex_adapter.py`

#### Changes Required:
1. **Import Grounding Tools**:
```python
from vertexai.generative_models import Tool, grounding
```

2. **Configure GoogleSearch**:
```python
async def complete(self, req: LLMRequest) -> LLMResponse:
    # Use global location for better grounding
    vertexai.init(
        project=project,
        location="global" if req.grounding_mode == GroundingMode.GR else "europe-west4"
    )
    
    # Add GoogleSearch tool for GR mode
    if req.grounding_mode == GroundingMode.GR:
        google_search_tool = Tool.from_google_search_retrieval(
            grounding.GoogleSearchRetrieval()
        )
        model = GenerativeModel(model_name, tools=[google_search_tool])
    else:
        model = GenerativeModel(model_name)
```

3. **Extract Grounding Metadata**:
```python
def _extract_grounding_metadata(resp) -> tuple[bool, Dict]:
    """Extract grounding signals from Gemini response"""
    candidates = getattr(resp, "candidates", [])
    if not candidates:
        return False, {}
    
    gm = getattr(candidates[0], "grounding_metadata", None)
    if not gm:
        return False, {}
    
    queries = getattr(gm, "web_search_queries", [])
    chunks = getattr(gm, "grounding_chunks", [])
    
    grounded = bool(queries or chunks)
    return grounded, {
        "queries": queries,
        "chunks": len(chunks),
        "grounded": grounded
    }
```

### Phase 4: Update Unified Adapter

**File**: `app/llm/unified_llm_adapter.py`

#### Changes Required:
1. **Pass Through Grounding Mode**:
```python
async def complete(self, request: LLMRequest) -> LLMResponse:
    # Ensure grounding_mode is passed to provider adapters
    # Current routing logic remains unchanged
```

### Phase 5: Testing Strategy

#### Test Cases:
1. **UN Mode Tests**:
   - Verify no web search occurs
   - Check grounded_effective = False
   - Ensure fast response times

2. **GR Mode Tests**:
   - OpenAI: Verify web_search tool is called
   - Vertex: Verify grounding_metadata present
   - Check citations extraction
   - Validate grounded_effective = True

3. **Edge Cases**:
   - JSON mode + grounding (Vertex limitation)
   - Token starvation with grounding
   - Grounding with different models

### Phase 6: Documentation Update

#### Files to Update:
- `API_DOCUMENTATION.md` - Add grounding_mode parameter
- `ADAPTER_STATUS.md` - Mark grounding as implemented
- `README.md` - Update feature list

## Implementation Timeline

| Phase | Task | Effort | Priority |
|-------|------|--------|----------|
| 1 | Update type definitions | 1 hour | High |
| 2 | OpenAI adapter grounding | 3 hours | High |
| 3 | Vertex adapter grounding | 3 hours | High |
| 4 | Update unified adapter | 1 hour | Medium |
| 5 | Testing | 2 hours | High |
| 6 | Documentation | 1 hour | Medium |

**Total Estimated Effort**: 11 hours

## Risk Mitigation

### Known Issues:
1. **GPT-5 tool_choice limitation** - Must use "auto", not "required"
2. **Vertex JSON + grounding conflict** - Cannot use both simultaneously
3. **Model support** - Only Gemini 2.5+ supports grounding

### Mitigation Strategies:
1. Clear error messages when grounding fails
2. Fallback to ungrounded if grounding unavailable
3. Log grounding attempts for debugging

## Success Criteria

- ✅ Both adapters support UN/GR modes
- ✅ Grounding detection works reliably
- ✅ Citations extracted when available
- ✅ No regression in existing functionality
- ✅ Clear documentation of limitations

## Code Quality Principles

- **No LangChain** - Direct SDK only
- **Simple implementation** - Avoid over-engineering
- **Clear separation** - Grounding logic isolated
- **Robust detection** - Multiple signals for grounding
- **Fail gracefully** - Fallback to ungrounded if needed

## Conclusion

This upgrade adds essential grounding support while maintaining our direct adapter architecture. The implementation leverages patterns from legacy code but avoids unnecessary complexity. The two-mode approach (UN/GR) simplifies both implementation and usage.

Last Updated: 2025-01-23
Status: **Ready for Implementation**