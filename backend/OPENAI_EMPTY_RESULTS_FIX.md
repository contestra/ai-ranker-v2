# OpenAI Empty Results Fix - Implementation Summary

## Problem Identified

**NOT an entitlement issue** - The OpenAI API accepts `web_search` tools and invokes them successfully. The issue is **empty retrieval**: searches return 0 results, causing the model to produce only reasoning blocks with no final message.

## Evidence

1. Raw API tests show:
   - HTTP 200 responses with `web_search` tools properly configured
   - `web_search_call` items in output with `status: "completed"`
   - Query executed: "White House official website homepage"
   - Results array: **empty**
   - No message output, only reasoning blocks

2. This affects even obvious queries that should have results (White House, BBC News)

## Solution Implemented

### 1. Two-Tier Grounding Semantics

Added distinction between attempted vs effective:

```python
{
    "grounding_attempted": true,    # Tool was invoked
    "grounded_effective": false,     # But got no results/citations
    "tool_call_count": 1,           # Number of invocations
    "tool_result_count": 0,         # Number of actual results
    "why_not_grounded": "web_search_empty_results"
}
```

### 2. New Error Class

Created `GroundingEmptyResultsError` to distinguish from `GroundingNotSupportedError`:

- **GROUNDING_NOT_SUPPORTED**: Model doesn't support the tool (400 error)
- **GROUNDING_EMPTY_RESULTS**: Tool invoked but returned 0 results
- **GROUNDING_REQUIRED_ERROR**: Other grounding failures

### 3. Enhanced Detection

Updated to recognize `web_search_call` output type (not just `tool_call`):

```python
# Detects both formats
if item_type == 'web_search_call':  # OpenAI specific
    grounding_attempted = True
    # Check for actual results
    results = item.get('results', [])
    if results:
        tool_result_count += len(results)
```

### 4. Telemetry Fields

Added comprehensive tracking:

- `grounding_attempted`: bool - Was tool invoked?
- `grounded_effective`: bool - Did we get results + citations?
- `tool_call_count`: int - Number of tool invocations
- `tool_result_count`: int - Sum of results across calls
- `web_search_count`: int - Web search calls specifically
- `why_not_grounded`: string - Precise failure reason

### 5. REQUIRED Mode Refinement

REQUIRED mode now distinguishes:

```python
if grounding_mode == "REQUIRED" and not grounded_effective:
    if why_not_grounded == "web_search_empty_results":
        raise GroundingEmptyResultsError(...)  # Empty retrieval
    elif grounding_not_supported:
        raise GroundingNotSupportedError(...)   # Tool not supported
    else:
        raise GroundingRequiredFailedError(...) # Other failures
```

## Test Results

### 2x2 Matrix: Attempted vs Effective

|                | Effective | Ineffective |
|----------------|-----------|-------------|
| **Attempted**  | 0         | All grounded queries |
| **Not Attempted** | 0      | Ungrounded queries |

Currently, ALL grounded queries fall into "Attempted but Ineffective" due to empty results.

## Files Modified

1. **`app/llm/adapters/openai_adapter.py`**
   - Integrated `analyze_openai_grounding()` for comprehensive analysis
   - Added telemetry fields for attempted vs effective
   - Distinguished error types in REQUIRED mode

2. **`app/llm/grounding_empty_results.py`** (new)
   - `analyze_openai_grounding()` - Comprehensive grounding analysis
   - `GroundingEmptyResultsError` - New error class

3. **`app/llm/unified_llm_adapter.py`**
   - Previous model adjustment changes still in place

## Dashboards & Monitoring

### Recommended UI

Show 2x2 matrix in dashboards:

```
Grounding Attempts (last 24h)
┌─────────────┬──────────┬──────────────┐
│             │ Effective │ Ineffective  │
├─────────────┼──────────┼──────────────┤
│ Attempted   │    0%     │    100%      │
│ Not Attempted│   0%     │    100%      │
└─────────────┴──────────┴──────────────┘

Top failure reason: web_search_empty_results (100%)
```

### SQL Queries

```sql
-- Empty results analysis
SELECT 
    DATE(created_at) as date,
    COUNT(*) FILTER (WHERE metadata->>'grounding_attempted' = 'true') as attempted,
    COUNT(*) FILTER (WHERE metadata->>'grounded_effective' = 'true') as effective,
    COUNT(*) FILTER (WHERE metadata->>'why_not_grounded' = 'web_search_empty_results') as empty_results
FROM llm_telemetry
WHERE vendor = 'openai'
GROUP BY DATE(created_at);
```

## Runbook Addition

**If `tool_call_count > 0` and `tool_result_count = 0`:**
- Classify as **Empty Results** (not Entitlement, not Unsupported)
- This means the search infrastructure is returning no results
- Consider:
  1. Regional restrictions on search
  2. Temporary search service issues
  3. Query phrasing that doesn't match indexed content

## Next Steps

1. **Monitor** empty results rate in production
2. **Investigate** why OpenAI's web search returns empty for obvious queries
3. **Consider** fallback strategies for empty results in AUTO mode
4. **Document** this as a known limitation for stakeholders

## Conclusion

The implementation correctly distinguishes between:
- Tool not supported (entitlement/model issue)
- Tool supported but returns empty (current situation)
- Tool supported and returns results (ideal state)

This provides precise telemetry for troubleshooting and clear error messages for API consumers.