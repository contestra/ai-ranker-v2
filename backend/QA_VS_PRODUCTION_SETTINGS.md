# QA vs Production Settings Guide
## September 1, 2025

## Executive Summary
Based on ChatGPT's review and extensive testing, here are the recommended settings for QA/staging vs production environments to balance visibility with contract compliance.

## Environment Settings

### Production Settings (Default)
```bash
# Citation Extraction - V2 enabled, legacy disabled
export CITATION_EXTRACTOR_V2=1.0
export CITATION_EXTRACTOR_ENABLE_LEGACY=false
export CITATIONS_EXTRACTOR_ENABLE=true

# CRITICAL: Keep unlinked emission OFF in production
export CITATION_EXTRACTOR_EMIT_UNLINKED=false

# Debugging OFF in production
export DEBUG_GROUNDING=false

# HTTP resolution disabled for security
export ALLOW_HTTP_RESOLVE=false
```

### QA/Staging Settings
```bash
# Citation Extraction - V2 enabled, legacy disabled
export CITATION_EXTRACTOR_V2=1.0
export CITATION_EXTRACTOR_ENABLE_LEGACY=false
export CITATIONS_EXTRACTOR_ENABLE=true

# IMPORTANT: Enable unlinked emission for visibility
export CITATION_EXTRACTOR_EMIT_UNLINKED=true

# Enable debug logging for troubleshooting
export DEBUG_GROUNDING=true

# HTTP resolution disabled for security
export ALLOW_HTTP_RESOLVE=false
```

## Key Differences

### 1. Unlinked Emission (`CITATION_EXTRACTOR_EMIT_UNLINKED`)
- **Production**: `false` - Only anchored citations shown
- **QA/Staging**: `true` - All evidence surfaced for debugging
- **Impact**: In QA, you'll see 5-10 unlinked sources when tools are called

### 2. Debug Logging (`DEBUG_GROUNDING`)
- **Production**: `false` - Minimal logging for performance
- **QA/Staging**: `true` - Detailed logs for troubleshooting
- **Impact**: Verbose citation extraction and grounding logs in QA

## REQUIRED Mode Contract

### Production Behavior (Unlinked OFF)
- REQUIRED mode fails if no **anchored** citations found
- Only `direct_uri` and `v1_join` types count as anchored
- Unlinked sources are ignored for REQUIRED enforcement
- Result: Strict compliance, fail-closed behavior

### QA/Staging Behavior (Unlinked ON)
- REQUIRED mode still fails if no **anchored** citations
- Unlinked sources are **visible** but don't satisfy REQUIRED
- Result: Same contract, but with evidence trail for debugging

## Test Results Summary

### With Unlinked OFF (Production)
- Future query (Aug 2025): 0 citations shown
- Current queries (2024): 0 citations shown
- Reality: Evidence exists but hidden (unlinked only)

### With Unlinked ON (QA)
- Future query (Aug 2025): 9 citations (all unlinked)
- Current AI query: 7 citations (all unlinked)
- Current election query: 5 citations (all unlinked)
- Reality: Evidence visible for debugging

## Telemetry Differences

### Production Telemetry
```json
{
  "grounded_effective": true,
  "tool_call_count": 1,
  "citations_count": 0,
  "anchored_citations_count": 0,
  "unlinked_sources_count": 0,
  "grounded_evidence_unavailable": true,
  "citations_status_reason": "provider_returned_empty_evidence"
}
```

### QA Telemetry
```json
{
  "grounded_effective": true,
  "tool_call_count": 1,
  "citations_count": 9,
  "anchored_citations_count": 0,
  "unlinked_sources_count": 9,
  "grounded_evidence_unavailable": false,
  "citations_status_reason": "no_anchored_citations"
}
```

## Recommendations

### 1. For Development Teams
- Use QA settings during development and testing
- Enable unlinked emission to understand evidence flow
- Review citation types to identify anchoring issues

### 2. For Production Deployment
- Keep unlinked emission OFF for clean metrics
- Monitor `grounded_evidence_unavailable` flag
- Alert on high rates of `provider_returned_empty_evidence`

### 3. For Debugging Production Issues
- Temporarily enable in staging to reproduce issues
- Compare anchored vs unlinked counts
- Use audit samples to understand provider behavior

### 4. For Provider Escalation
When opening tickets with Google/Vertex:
- Include tool_call_count and grounded_effective values
- Show audit keys and samples from citations_audit
- Highlight that only unlinked sources are returned
- Request anchored citation support (JOIN spans)

## Testing Guidance

### Positive Test Cases (Use Current/Past Events)
```python
queries = [
    "What were the key results of the 2024 US presidential election?",
    "Latest AI developments from OpenAI in 2024",
    "Major climate agreements in 2024"
]
```

### Negative Test Case (Future Event)
```python
queries = [
    "What will happen in August 2025?"  # Returns empty or unlinked only
]
```

## Migration Path

### Phase 1: Current State
- Production: Unlinked OFF, 0 citations shown
- QA: Enable unlinked to understand evidence

### Phase 2: After Vertex Fix (Future)
- When Vertex provides anchored citations
- Both environments can show citations
- REQUIRED mode will work as designed

### Phase 3: Full Production (Future)
- Consider enabling unlinked in AUTO mode only
- Keep REQUIRED mode anchored-only
- Add citation quality scoring

## Summary

The key insight from ChatGPT's review: **"Your adapters are behaving as designed; the '0 citations' is a Gemini evidence-emission gap for this query type, not an extraction failure."**

By using different settings for QA vs production, we can:
1. Maintain strict REQUIRED mode contract in production
2. Have full visibility into evidence during QA/debugging
3. Properly diagnose provider vs code issues
4. Be ready when providers improve citation anchoring