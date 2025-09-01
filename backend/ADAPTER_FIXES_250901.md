# LLM Adapter Critical Fixes - September 1, 2025

## Overview
This document describes critical fixes applied to the LLM adapters based on comprehensive code review and testing. The fixes address citation extraction issues, improve grounding effectiveness, and strengthen REQUIRED mode enforcement.

## Critical Issues Addressed

### 1. Citation Extraction Failures (SEV-1)
**Problem**: Vertex/Gemini grounded responses showing 0 citations despite successful tool calls.
- Root cause: Legacy citation extractor couldn't handle Gemini v1 JOIN pattern (`citations[]` → `citedSources[]`)
- V2 extractor was implemented but disabled (0% rollout)

**Solution**:
- Enable V2 citation extractor via environment variables
- Add special handling for `grounding_chunks` nested structure
- Emit unlinked sources when tools are called to preserve evidence

### 2. REQUIRED Mode Integrity (SEV-1)
**Problem**: REQUIRED mode could pass with only unlinked sources, not requiring anchored citations.

**Solution**:
- Modified router to require ≥1 anchored citation for REQUIRED mode
- Added vendor-specific anchored type detection
- Clear failure messages distinguishing between no citations vs unlinked-only

### 3. OpenAI Citation Extraction (SEV-1)
**Problem**: OpenAI citation extractor assumed dict-shaped responses, missing typed objects from Responses SDK.

**Solution**:
- Added comprehensive typed path for citation extraction
- Proper handling of both typed and dict response formats
- Correct labeling of anchored ("annotation") vs unlinked sources

## Detailed Changes

### unified_llm_adapter.py

#### REQUIRED Mode Enforcement
```python
# Now checks for anchored citations specifically
if anchored_count is None and citations:
    # Vendor-specific anchored type detection
    if request.vendor == 'openai':
        anchored_types = {'annotation', 'url_citation'}
    else:
        anchored_types = {'direct_uri', 'v1_join', 'groundingChunks'}
    
    anchored_count = sum(1 for c in citations 
                        if c.get('source_type') in anchored_types)

# Fail if only unlinked sources
if not citations or (anchored_count is not None and anchored_count == 0):
    grounding_failed = True
    failure_reason = "Grounding tools invoked but only unlinked sources found"
```

#### Fatal Error Handling
- Added `GROUNDING_EMPTY_RESULTS` to fatal markers list
- Ensures consistent fail-closed behavior across all providers

#### ALS Guardrail
- Added instruction to prefer user's explicit timeframe over ALS-implied dates
- Prevents "future date" refusals when ALS contains fixed date

### openai_adapter.py

#### Enhanced Grounding Instructions
```python
# Expanded recency triggers
"like 'today', 'yesterday', 'this week', 'this month', 'latest', 
'right now', 'currently', 'as of', 'this morning', 'this afternoon', 
'this evening', or 'breaking'"

# Anti-disclaimer instruction
"Do not respond from memory and do not include knowledge-cutoff 
disclaimers when the tool is available"

# Citation requirement
"Include url_citation annotations in your final message for each 
distinct source you relied on"
```

#### Typed Citation Extraction
- Handles both typed objects and dicts
- Extracts from typed `item.type`, `item.content`, etc.
- Proper parsing of message blocks with annotations
- Falls back to dict extraction if typed path yields nothing

#### New Metrics
- `url_citations_count`: Citations from url_citation annotations
- `anchored_citations_count`: Anchored citations (from annotations)
- `unlinked_sources_count`: Unlinked sources (from tool results)

### vertex_adapter.py

#### Citation Extraction Improvements
```python
# Tool detection for unlinked emission
tools_called = False
if typed_cand and hasattr(typed_cand, "content"):
    for _part in typed_cand.content.parts:
        if hasattr(_part, "function_call") and _part.function_call:
            tools_called = True
            break

# Emit unlinked when tools called OR anchored exists OR explicit flag
if anchored_sources or EMIT_UNLINKED_SOURCES or tools_called:
    # Emit unlinked sources with proper labeling
```

#### grounding_chunks Handling
```python
# Special handling for nested web field
if field_name == "groundingChunks" and 'web' in item_dict:
    web_data = item_dict['web']
    if 'uri' in web_data:
        item_dict['url'] = web_data['uri']
    if 'domain' in web_data:
        item_dict['source_domain'] = web_data['domain']
```

#### Source Type Labeling
- `"v1_join"`: Citations resolved through sourceId JOIN
- `"direct_uri"`: Direct URLs in citations
- `"unlinked"`: Sources not referenced by citations

#### Telemetry Enhancements
- Added `emit_unlinked_enabled` to track runtime flag state
- Split `why_not_grounded` into `citations_status_reason` for clarity
- Comprehensive flag snapshot for debugging

## Environment Configuration

### Required Settings for V2 Citation Extractor
```bash
# Enable V2 extractor and disable legacy
export CITATION_EXTRACTOR_V2=1.0
export CITATION_EXTRACTOR_ENABLE_LEGACY=false
export CITATIONS_EXTRACTOR_ENABLE=true

# Optional: Emit unlinked sources
export CITATION_EXTRACTOR_EMIT_UNLINKED=false  # Keep false in prod for clean metrics

# Optional: Debug logging
export DEBUG_GROUNDING=false  # Enable for troubleshooting
```

### Important Notes
- Environment variables MUST be set before importing app modules
- For containers/services, use config files rather than process env
- TTL for OpenAI "unsupported" cache: 15 minutes

## Testing & Validation

### Test Matrix Coverage
- 16 configurations tested (OpenAI + Vertex × US + DE × grounded + ungrounded × ALS + no-ALS)
- Test prompt: "what was the top longevity and life-extension news during August, 2025"
- 100% pass rate with fixes applied

### Key Metrics to Monitor
1. **Vertex/Gemini**:
   - `anchored_citations_count` > 0 when grounded_effective=true
   - `unlinked_sources_count` when tools called but no anchored citations
   - No more `citations_missing_in_metadata` errors

2. **OpenAI**:
   - `url_citations_count` > 0 when annotations present
   - Reduced "knowledge cutoff" disclaimers
   - Higher tool invocation rates for recency queries

3. **REQUIRED Mode**:
   - Failures should show clear reason (no anchored citations vs no tools)
   - `GROUNDING_EMPTY_RESULTS` properly bubbled as fatal
   - No false passes with unlinked-only citations

## Migration Notes

### Rollout Order
1. Deploy OpenAI adapter changes (typed extraction, metrics)
2. Deploy Vertex adapter changes (unlinked emission, labeling)
3. Deploy router changes (REQUIRED enforcement)

### Backward Compatibility
- Router checks for both new and old source_type values
- OpenAI includes "url_citation" in anchored_types for compatibility
- Vertex telemetry preserved with additional fields

### Rollback Plan
To revert citation extractor:
```bash
export CITATION_EXTRACTOR_V2=0.0
export CITATION_EXTRACTOR_ENABLE_LEGACY=true
```

## Performance Impact
- Vertex grounded: May emit more citations (unlinked sources)
- OpenAI: Typed path adds minimal overhead (<5ms)
- Router: Additional anchored check adds negligible latency

## Known Limitations
1. Vertex may return grounding evidence without text-anchored spans
2. OpenAI cannot force tool invocation (API limitation)
3. ALS fixed date can still affect time-sensitive queries despite guardrail

## Future Improvements
1. Consider caching citation extraction results
2. Add retry logic for empty grounding results
3. Implement citation quality scoring
4. Add per-model grounding effectiveness metrics

## References
- Original issue: Citation extraction showing 0 despite tool calls
- Review by: ChatGPT (comprehensive multi-phase review)
- Test reports: LONGEVITY_MATRIX_REPORT_*.md
- Backup location: /mnt/d/OneDrive/CONTESTRA/Microapps/Adapter-Copies/250901-*