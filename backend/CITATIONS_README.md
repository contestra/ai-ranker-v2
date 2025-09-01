# Citation Extraction System Documentation

## Overview

This document describes the unified citation extraction system implemented across OpenAI and Vertex adapters. The system provides a consistent schema for citations, handles provider-specific quirks, and enforces REQUIRED grounding mode at the router level.

## Uniform Citation Schema

Each citation follows this standardized Python dictionary structure:

```python
{
    "provider": "openai" | "vertex",           # Source provider
    "url": "<canonical URL if available>",     # Final URL (end-site preferred over redirects)
    "source_domain": "<registrable domain>",   # Extracted domain (e.g., "example.com")
    "title": "<page/article title>",          # Best-effort title extraction
    "snippet": "<supporting text>",           # Short excerpt if available
    "source_type": "web" | "doc" | "news" | "video" | "unknown",  # Content type
    "rank": <int or None>,                    # Position in provider's result list
    "raw": { ... }                            # Untouched provider object for forensics
}
```

### Key Fields

- **`source_domain`**: MANDATORY field. The registrable domain of the actual content source. Critical for ALS (Ambient Location Signals) analysis.
- **`url`**: The canonical URL. For Vertex redirects, this may be a redirect URL if the true URL cannot be determined.
- **`raw`**: Contains the original provider data. If only a redirect URL is available, includes `"redirect": true`.

## Provider-Specific Implementation

### OpenAI Citation Extraction

**Function**: `_extract_openai_citations(response) -> List[Dict]`

**Extraction Sources**:
1. **Tool Outputs**: Scans `web_search` and `web_search_preview` tool results
2. **URL Citations**: Checks for `url_citation` type annotations
3. **Message Annotations**: Looks for embedded citations in message content

**Key Features**:
- Deduplication by normalized URL (strips UTM params, anchors, lowercases host)
- Preserves earliest rank when deduplicating
- Extracts titles from search result text when structured data unavailable

**Provider Quirks**:
- OpenAI Responses API may return empty tool results even when tools are invoked
- Citations may appear in multiple formats within the same response
- `web_search_preview` tool type used as fallback when `web_search` unsupported

### Vertex Citation Extraction

**Function**: `_extract_vertex_citations(response) -> List[Dict]`

**Extraction Sources** (checked in order):
1. `grounding_metadata.citations`
2. `grounding_metadata.cited_sources` / `citedSources`
3. `grounding_metadata.grounding_attributions` / `groundingAttributions`
4. `grounding_metadata.supporting_content` / `supportingContent`
5. `grounding_metadata.sources`
6. `grounding_metadata.grounding_chunks` / `groundingChunks`
7. `grounding_metadata.grounding_supports` / `groundingSupports`
8. `grounding_metadata.webSearchSources`
9. `grounding_metadata.retrieval_metadata` / `retrievalMetadata`

**Key Features**:
- Handles both SDK objects and dict representations
- Prioritizes end-site URLs over Vertex redirects
- Extracts true domains from multiple sources:
  1. Direct URL if not a redirect
  2. Nested `web.uri`, `source.url`, `reference.url` fields
  3. Title field if it appears to be a domain
  4. Sibling metadata fields (`domain`, `host`)

**Provider Quirks**:
- Vertex often returns redirect URLs (`vertexaisearch.cloud.google.com/grounding-api-redirect/...`)
- True source URLs may be nested in various metadata fields
- Field names vary between SDK versions (camelCase vs snake_case)
- Some responses have grounding metadata but empty citation arrays

## Two-Step Vertex Reshaping

For Vertex grounded + JSON mode requests:

1. **Step 1**: Grounded request with Google Search tool
   - Citations extracted via `_extract_vertex_citations()`
   - Stored in adapter metadata: `metadata["citations"]`
   - Also sets `metadata["grounded_effective"]`

2. **Step 2**: Reshape to JSON with tools disabled
   - Citations carried forward from Step 1 metadata
   - No new citation extraction attempted (tools disabled)

## REQUIRED Mode Enforcement

The router (`unified_llm_adapter.py`) enforces REQUIRED grounding mode via post-validation:

```python
if grounding_mode == "REQUIRED" and request.grounded:
    # Check both grounding effectiveness AND citation presence
    if not response.grounded_effective:
        raise GroundingRequiredFailedError("Model did not invoke grounding tools")
    elif not response.metadata.get('citations'):
        raise GroundingRequiredFailedError("Grounding tools invoked but no citations extracted")
```

### Key Points:
- OpenAI cannot force tool invocation (no `tool_choice:"required"` for web_search)
- Post-validation ensures consistent behavior across providers
- Fails closed if either grounding fails OR citations are empty

## ALS Analysis Integration

The ALS analyzer (`als_ambient_utils.py`) prioritizes `source_domain` when available:

```python
def extract_tld_counts(citations: List) -> Dict[str, int]:
    for item in citations:
        if isinstance(item, dict):
            # Prefer source_domain over URL parsing
            if 'source_domain' in item:
                domain = item['source_domain']
            elif 'url' in item:
                # Fall back to parsing URL
                domain = extract_from_url(item['url'])
```

### Benefits:
- Accurate TLD counting even with Vertex redirects
- Distinguishes real sources from redirector domains
- Separate tracking of redirector vs true domains

## Debugging and Forensics

### Environment Variables
- `DEBUG_GROUNDING=true`: Enables detailed citation extraction logging

### Warning Logs
When tools are invoked but no citations extracted:
```
[CITATIONS] OpenAI: 2 tool calls but 0 citations extracted. First output item: {...}
[CITATIONS] Vertex: 1 tool calls but 0 citations extracted. Grounding metadata keys found: [...]
```

### Forensic Data
The `raw` field in each citation preserves original provider data for debugging:
- OpenAI: Tool type, original result structure
- Vertex: Includes `"redirect": true` flag when only redirect URL available

## Testing

Run unit tests:
```bash
python -m pytest tests/test_citations.py -v
```

Test coverage includes:
- OpenAI citation extraction from various formats
- Vertex citation extraction with end-sites, redirects, and metadata
- URL normalization and deduplication
- Registrable domain extraction
- REQUIRED mode validation logic

## Migration Notes

### From Old System
- Replace calls to `_extract_vertex_citations2()` with `_extract_vertex_citations()`
- Update ALS analysis to use citation dicts instead of URL strings
- Ensure REQUIRED mode uses post-validation, not `tool_choice:"required"`

### Breaking Changes
- Citation format changed from strings to dicts
- `source_domain` field now mandatory
- REQUIRED mode enforces non-empty citations