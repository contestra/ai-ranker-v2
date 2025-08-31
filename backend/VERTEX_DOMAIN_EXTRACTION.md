# Vertex True Domain Extraction

## Problem
Vertex grounding returns redirect URLs like:
```
https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG...
```

These mask the actual source domains, making it impossible to see ALS effects (.ch, .de domains) in QA reports.

## Solution

### 1. Enhanced Citation Extraction

The `_extract_vertex_citations2` function now:

1. **Looks for non-redirect URLs first**:
   - `sourceUrl`, `pageUrl`, `source_uri` fields
   - Nested `web.uri`, `source.url`, `reference.url`
   - Only uses redirect URLs as fallback

2. **Extracts source domains from multiple sources**:
   ```python
   # Priority order:
   1. True URL (if not a redirect) -> parse domain
   2. Title field (if it looks like a domain)
   3. Nested metadata (web.domain, source.host)
   ```

3. **Adds metadata to citations**:
   ```python
   citation = {
       "url": final_url,          # Prefer true URL over redirect
       "source_domain": "nih.gov", # Actual domain extracted
       "is_redirect": True,        # Flag if using redirect
       ...
   }
   ```

### 2. ALS Utility Integration

The `extract_tld_counts` function:
- **Prefers** `citation["source_domain"]` when available
- **Falls back** to parsing the URL's TLD
- Handles both dict citations and string URLs

```python
if isinstance(item, dict):
    # Prefer source_domain if available
    if 'source_domain' in item and item['source_domain']:
        domain = item['source_domain'].lower()
    elif 'url' in item:
        # Fall back to parsing URL
```

## Impact on ALS QA

### Before
```
Citations: All show vertexaisearch.cloud.google.com
TLDs: .com(10) - all redirects counted as .com
ALS effects: Not visible
```

### After
```
Citations: Mix of true URLs and redirects with source_domain
TLDs: .com(5), .ch(2), .de(2), .org(1) - actual distribution
ALS effects: Visible - CH context shows more .ch domains
```

## Example Citation Structure

### Redirect with source_domain extracted:
```json
{
  "provider": "vertex",
  "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/...",
  "title": "ethz.ch",
  "source_domain": "ethz.ch",
  "is_redirect": true,
  "snippet": "Research from ETH Zurich..."
}
```

### True URL found:
```json
{
  "provider": "vertex",
  "url": "https://www.nature.com/articles/s41586-024-1234",
  "title": "Nature",
  "source_domain": "nature.com",
  "snippet": "Published research..."
}
```

## Testing

Run the test to see domain extraction:
```bash
python test_vertex_true_domains.py
```

Expected output:
- Mix of redirect and true URLs
- Source domains extracted for most citations
- TLD distribution shows variety (.com, .org, .edu, .ch, .de)
- ALS contexts show increased local domains

## Benefits

1. **ALS Visibility**: Can now see when CH context increases .ch domains
2. **Accurate Metrics**: TLD counts reflect actual source distribution
3. **Better Debugging**: `is_redirect` flag shows when using fallback
4. **Flexible Extraction**: Multiple strategies to find true domain

## Implementation Notes

- Backwards compatible - old code still works
- Graceful degradation - uses redirects if no true URL found
- No performance impact - extraction happens during existing parsing
- Logging preserves all information for debugging