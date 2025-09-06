# Adapter Hardening Documentation

## Overview
This document describes the adapter hardening improvements implemented to eliminate AttributeErrors, improve observability, and standardize telemetry across all LLM adapters.

## Table of Contents
1. [Meta Field Handling](#meta-field-handling)
2. [Vendor Path Provenance](#vendor-path-provenance)
3. [Telemetry Canonicalization](#telemetry-canonicalization)
4. [OpenAI Tool Negotiation](#openai-tool-negotiation)
5. [Environment Variables](#environment-variables)
6. [Migration Guide](#migration-guide)

---

## Meta Field Handling

### Problem Solved
- Eliminated `AttributeError: 'NoneType' object has no attribute 'get'` when callers omit meta field
- Unified handling of `meta` vs `metadata` field naming inconsistencies

### Implementation

#### Meta Utilities (`app/llm/util/meta_utils.py`)

```python
def get_meta(request) -> Dict[str, Any]:
    """Return metadata dict, never None."""
    # Checks both 'metadata' and 'meta' fields
    # Always returns a dict, never None
    
def ensure_meta_aliases(request) -> None:
    """Make 'metadata' and 'meta' interchangeable."""
    # Sets both fields to the same dict
    # Allows downstream code to use either name
```

#### Usage in Adapters
All adapters now use at the start of `complete()`:
```python
ensure_meta_aliases(request)
meta = get_meta(request)
# Now safe to use meta.get(...) throughout
```

### Benefits
- No more AttributeErrors when meta field is missing
- Consistent behavior across all adapters
- Backward compatible with existing callers

---

## Vendor Path Provenance

### Purpose
Track the exact adapter route taken for each request, useful for:
- Debugging routing issues
- Analytics and dashboards
- Audit trails

### Implementation

#### Router (`app/llm/unified_llm_adapter.py`)
```python
def _derive_vendor_path(adapter_name: str) -> str:
    """Returns path like 'router→openai/OpenAIAdapter'"""
```

### Output Format
Every response now includes:
```json
{
  "metadata": {
    "vendor_path": "router→openai/OpenAIAdapter"
  }
}
```

Possible values:
- `"router→openai/OpenAIAdapter"`
- `"router→vertex/VertexAdapter"`
- `"router→gemini/GeminiAdapter"`

---

## Telemetry Canonicalization

### Purpose
Standardize telemetry keys across all vendors for consistent analytics and REQUIRED enforcement.

### Canonical Keys

All adapters now emit these standardized keys:

| Canonical Key | Type | Description | Legacy Aliases |
|--------------|------|-------------|----------------|
| `tool_call_count` | int | Actual count of tool/search calls | `web_search_count`, `tool_call_count_capped` |
| `anchored_citations_count` | int | Citations with explicit URLs | `citation_count` |
| `unlinked_sources_count` | int | Evidence without URLs | Computed from total - anchored |
| `web_tool_type` | string | Tool type used | N/A |
| `usage` | object | Normalized token usage | N/A |
| `response_api` | string | API surface used | N/A |

### Web Tool Types

Valid values for `web_tool_type`:
- `"google_search"` - Google Search tool (Vertex/Gemini)
- `"web_search"` - OpenAI web search tool
- `"web_search_preview"` - OpenAI preview tool
- `"none"` - No web tool used

### Usage Normalization

Canonical format:
```json
{
  "usage": {
    "input_tokens": 123,
    "output_tokens": 456,
    "total_tokens": 579
  },
  "vendor_usage": {
    // Original vendor format preserved
  }
}
```

### Router Behavior
The router reads canonical keys first, falls back to legacy aliases:
```python
# Tool calls - canonical first, then aliases
tool_calls = md.get("tool_call_count")
if tool_calls is None:
    tool_calls = md.get("web_search_count") or 0

# Same pattern for other keys
```

---

## OpenAI Tool Negotiation

### Purpose
Robustly handle cases where `web_search` tool is not available, automatically falling back to `web_search_preview`.

### Feature Flag
```bash
OPENAI_SEARCH_NEGOTIATION_ENABLED=true  # Default: enabled
```

### Detection Strategy

1. **Structured fields first** (more stable):
   - HTTP status (400, 404)
   - Error type (`invalid_request_error`, `unsupported_feature`)
   - Error code (contains "tool")

2. **Message strings second** (fallback):
   - "hosted tool 'web_search' is not supported"
   - "unsupported tool type: web_search"
   - "unknown tool: web_search"
   - "tools not enabled for this model"

### Telemetry Breadcrumbs

When negotiation occurs:
```json
{
  "metadata": {
    "web_tool_type_initial": "web_search",
    "web_tool_type_final": "web_search_preview",
    "web_tool_negotiation": "web_search→web_search_preview",
    "web_tool_negotiation_reason": "400:invalid_request_error:tool_not_supported"
  }
}
```

When no negotiation needed:
```json
{
  "metadata": {
    "web_tool_negotiation": "none"
  }
}
```

### Logging
INFO level when negotiation happens:
```
[OPENAI] tool negotiation: web_search→web_search_preview reason=400:invalid_request_error:NA
```

---

## Environment Variables

### New Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_SEARCH_NEGOTIATION_ENABLED` | `true` | Enable automatic web_search→web_search_preview fallback |

### Existing Variables (Unchanged)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_PROVOKER_ENABLED` | `true` | Enable provoker retry for empty grounded responses |
| `OPENAI_GROUNDED_TWO_STEP` | `false` | Enable two-step synthesis fallback |
| `OPENAI_GROUNDED_MAX_TOKENS` | `6000` | Max tokens for grounded requests |
| `REQUIRED_RELAX_FOR_GOOGLE` | `false` | Allow unlinked-only citations for Google vendors |

---

## Citation Presentation (P8)

### Problem Solved
- UI shows repetitive citations from same domain
- Important authority sources get buried in noise
- No visual hierarchy for credibility

### Implementation

#### Presentation Function (`app/llm/unified_llm_adapter.py`)
```python
def present_citations_for_ui(final_citations, per_domain_cap=1, max_total=8):
    """Cosmetic citation capping for UI friendliness."""
    # 1. Order: official → tier-1 → others
    # 2. Cap per domain (default 1)
    # 3. Ensure at least one official + one tier-1
    # 4. Global cap for UI
```

#### Router Integration
```python
# After policy enforcement, before return
md = response.metadata or {}
final_citations = md.get("citations")
if final_citations:
    presented = present_citations_for_ui(final_citations)
    md.setdefault("presentation", {})
    md["presentation"]["citations_compact"] = presented
```

### Output
```json
{
  "metadata": {
    "citations": [...],  // Full deduped list
    "presentation": {
      "citations_compact": [...]  // UI-friendly subset
    }
  }
}
```

---

## Wire Citations Consistently (P8a)

### Problem Solved
- Citations stored inconsistently across adapters
- Router needs fallback for legacy paths
- UI presentation needs reliable source

### Implementation

#### Adapter Changes
All adapters now persist deduped citations:
```python
# After P6 deduplication
metadata["citations"] = deduped_citations or []
```

#### Router Fallback
```python
# Prefer adapter-written list, fallback to response.citations
final_citations = md.get("citations")
if not final_citations and hasattr(response, "citations"):
    final_citations = getattr(response, "citations") or []
```

### Benefits
- Consistent citation storage across all adapters
- Router has robust fallback for legacy paths
- UI presentation always has reliable source
- No impact on REQUIRED enforcement or analytics

---

## Migration Guide

### For Dashboard/Analytics Consumers

#### Reading Telemetry (Recommended Pattern)
```python
# Always check canonical first, fallback to legacy
tool_count = metadata.get("tool_call_count")
if tool_count is None:
    # Fallback to legacy fields
    tool_count = metadata.get("web_search_count", 0)

anchored = metadata.get("anchored_citations_count")
if anchored is None:
    anchored = metadata.get("citation_count", 0)
```

#### Accessing Citations
```python
# Citations are now in metadata
citations = metadata.get("citations", [])

# For UI display, use compact list
if "presentation" in metadata:
    ui_citations = metadata["presentation"].get("citations_compact", [])
```

#### New Fields to Track
- `vendor_path` - Which adapter handled the request
- `web_tool_type` - Specific tool used (enum)
- `web_tool_negotiation` - Whether fallback occurred
- `usage.input_tokens` - Normalized token counts

### For Adapter Callers

#### No Changes Required
All changes are backward compatible:
- Legacy fields still present
- Meta field handling is automatic
- Existing code continues to work

#### Optional Improvements
```python
# Can now safely omit meta field
request = LLMRequest(
    vendor="openai",
    model="gpt-5-2025-08-07",
    messages=[...],
    grounded=True
    # No meta field - won't cause errors
)
```

### For New Adapter Implementations

#### Required Pattern
```python
async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
    # Step 1: Normalize meta
    ensure_meta_aliases(request)
    meta = get_meta(request)
    
    # Step 2: Use meta safely throughout
    if meta.get("some_option"):
        # ...
    
    # Step 3: Set canonical telemetry
    metadata["tool_call_count"] = actual_count
    metadata["anchored_citations_count"] = anchored
    metadata["unlinked_sources_count"] = unlinked
    metadata["web_tool_type"] = "google_search"  # or appropriate type
    
    # Step 4: Debug logging
    logger.debug(
        f"[ADAPTER:{vendor}] tool_call_count={tool_count} "
        f"anchored={anchored} unlinked={unlinked} "
        f"web_tool_type={web_tool_type}"
    )
```

---

## Testing

### Baseline Tests
Run baseline smoke tests to verify no regression:
```bash
python3 baseline_smoke_tests.py
```

Expected output:
- All tests pass
- New telemetry fields present
- Legacy fields preserved
- No behavior changes

### Meta Guarding Test
Verify meta field handling:
```bash
python3 test_meta_guarding.py
```

### Tool Negotiation Test
Test with negotiation enabled/disabled:
```bash
# With negotiation (default)
OPENAI_SEARCH_NEGOTIATION_ENABLED=true python3 test_openai_grounded.py

# Without negotiation
OPENAI_SEARCH_NEGOTIATION_ENABLED=false python3 test_openai_grounded.py
```

---

## Acceptance Criteria

All implementations meet these criteria:

### Meta Handling ✅
- No AttributeErrors with missing meta field
- Both `meta` and `metadata` work interchangeably
- Backward compatible with existing code

### Vendor Path ✅
- `vendor_path` present in all responses
- Correct format: `"router→{adapter}/{class}"`
- Useful for debugging and analytics

### Telemetry ✅
- Canonical keys present in all adapters
- Legacy keys preserved for backward compatibility
- Router reads canonical first, falls back to aliases
- Usage normalized across vendors

### Tool Negotiation ✅
- Automatic fallback when web_search unavailable
- Clear breadcrumbs in metadata
- Structured error detection preferred
- Feature flag for control

### No Behavior Changes ✅
- Final text unchanged
- Citations unchanged
- REQUIRED enforcement unchanged
- Provoker policy unchanged

---

## Support

For questions or issues:
1. Check test results in `tmp/baseline/`
2. Review debug logs for `[ADAPTER:]` and `[ROUTER]` prefixes
3. Verify environment variables are set correctly
4. Run specific test files to isolate issues