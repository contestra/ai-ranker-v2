# Vertex Anchored Citation Fix - Implementation Summary
## September 2, 2025

## What ChatGPT Recommended ✅

ChatGPT identified that `groundingChunks` should be treated as **unlinked evidence**, not anchored citations, and recommended centralizing the definitions to prevent drift.

## Changes Implemented

### 1. Centralized Definitions (Module Level)
```python
# In vertex_adapter.py at module level
ANCHORED_CITATION_TYPES = {"direct_uri", "v1_join"}
UNLINKED_CITATION_TYPES = {"unlinked", "legacy", "text_harvest", "groundingChunks"}
```

**Rationale**: 
- `direct_uri` and `v1_join` are text-anchored with specific spans
- `groundingChunks` are evidence/sources but not anchored to text
- Router already enforces this stricter definition for REQUIRED mode

### 2. Updated All Tallies

#### Before (Inconsistent):
```python
# Some places:
if cit.get("source_type") in ["direct_uri", "v1_join", "groundingChunks"]:
    anchored_count += 1

# Other places:
anchored_count = len([c for c in citations if c.get('source_type') in {'direct_uri', 'v1_join'}])
```

#### After (Consistent):
```python
# All places now use centralized constants:
if cit.get("source_type") in ANCHORED_CITATION_TYPES:
    anchored_count += 1

anchored_count = len([c for c in citations if c.get('source_type') in ANCHORED_CITATION_TYPES])
```

### 3. Code Comments Added
```python
# Router counts as anchored only JOIN/direct - text-anchored citations with specific spans
# Chunks/supports are evidence but not text-anchored, so they count as unlinked
```

### 4. Telemetry Consistency Verified

All telemetry paths now use the same definitions:
- `_select_and_extract_citations()` - Uses `ANCHORED_CITATION_TYPES`
- `_extract_vertex_citations()` - Uses `ANCHORED_CITATION_TYPES`
- Forensics logging - Uses `ANCHORED_CITATION_TYPES`

## Impact

### Before Fix
- **Mismatch**: Vertex counted `groundingChunks` as anchored
- **Router**: Only counted `direct_uri` and `v1_join` as anchored
- **Result**: REQUIRED mode could pass with only chunks (incorrect)

### After Fix
- **Aligned**: Both adapter and router use same definition
- **REQUIRED Mode**: Correctly fails without text-anchored citations
- **Telemetry**: Accurate anchored vs unlinked counts

## Router Alignment

The router (`unified_llm_adapter.py`) already had the correct definition:
```python
# Vertex: only JOIN-anchored or direct citations count as anchored
# groundingChunks are unlinked evidence, not text-anchored
anchored_types = {'direct_uri', 'v1_join'}
```

Now the adapter matches this exactly.

## Testing Impact

### Test Expectations Update
When Vertex returns only `groundingChunks`:
- **Before**: `anchored_citations_count = 1+`, REQUIRED passes
- **After**: `anchored_citations_count = 0`, REQUIRED fails (correct)
- **Unlinked**: `unlinked_sources_count = 1+` (evidence still captured)

### REQUIRED Mode Behavior
- ✅ Fails correctly when only chunks/evidence available
- ✅ Passes only with true text-anchored citations
- ✅ Consistent with OpenAI's annotation requirement

## Benefits

1. **No Drift**: Single source of truth for citation types
2. **Router Consistency**: Adapter and router in perfect alignment
3. **Clear Semantics**: Anchored = text spans, Unlinked = evidence/sources
4. **REQUIRED Integrity**: Enforces high bar for grounded responses
5. **Future-Proof**: Easy to modify types in one place

## Files Modified

- `app/llm/adapters/vertex_adapter.py`:
  - Added module-level constants
  - Updated all anchored/unlinked counting
  - Added explanatory comments
  - Removed duplicate definitions

## Conclusion

ChatGPT's recommendation was implemented fully. The fix ensures:
- `groundingChunks` are correctly classified as unlinked evidence
- REQUIRED mode maintains strict anchored citation requirements
- All telemetry and counting logic uses centralized definitions
- No possibility of definition drift between components

This aligns the Vertex adapter with the router's enforcement and provides the correct semantics for grounded responses.