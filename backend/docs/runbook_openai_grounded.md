# OpenAI Grounded Mode Operations Runbook

## Overview

OpenAI grounded mode uses the Responses API with `web_search` tools. Due to an API limitation where the model sometimes returns web search results without synthesizing a final answer, we've implemented a deterministic three-stage fallback chain.

## Environment Configuration

### Production Settings

```bash
# Required for production
export OPENAI_PROVOKER_ENABLED=true          # Enable provoker retry (default: true)
export OPENAI_GROUNDED_TWO_STEP=true         # Enable two-step synthesis (default: false, MUST BE TRUE IN PROD)
export OPENAI_GROUNDED_MAX_TOKENS=6000       # Max output tokens for grounded (default: 6000)
export OPENAI_GROUNDED_MAX_EVIDENCE=5        # Max citations in evidence list (default: 5)

# Optional
export OPENAI_SEED_KEY_ID=v1_2025            # Seed key for reproducibility (default: v1_2025)
```

### Development/Testing Settings

```bash
# For testing without fallbacks
export OPENAI_PROVOKER_ENABLED=false
export OPENAI_GROUNDED_TWO_STEP=false
```

## Fallback Chain

1. **Initial Request**: Standard grounded call with `web_search` tools
2. **Provoker Retry**: If empty response but tool calls present, adds synthesis prompt
3. **Two-Step Fallback**: If still empty, runs synthesis without tools using evidence list

## Monitoring Metrics

### Key Performance Indicators

Monitor these metrics in BigQuery/dashboards:

| Metric | Query | Alert Threshold |
|--------|-------|-----------------|
| **Provoker Usage Rate** | `SUM(provoker_retry_used) / COUNT(*) WHERE grounded=true` | >50% = investigate |
| **Two-Step Usage Rate** | `SUM(synthesis_step_used) / COUNT(*) WHERE grounded=true` | >30% = investigate |
| **REQUIRED Pass Rate** | `COUNT(*) WHERE grounding_mode='REQUIRED' AND success=true / COUNT(*) WHERE grounding_mode='REQUIRED'` | <95% = alert |
| **Avg Grounded Content Length** | `AVG(LENGTH(content)) WHERE grounded=true AND content != ''` | <500 chars = alert |
| **Avg Citations Per Run** | `AVG(citation_count) WHERE grounded=true` | <2 = investigate |
| **Top Domains** | `SELECT domain, COUNT(*) FROM citations GROUP BY domain ORDER BY COUNT DESC LIMIT 10` | Monitor for quality |

### Telemetry Fields to Track

```sql
-- Daily summary query
SELECT 
  DATE(timestamp) as date,
  COUNT(*) as total_grounded_requests,
  SUM(CASE WHEN provoker_retry_used THEN 1 ELSE 0 END) as provoker_used,
  SUM(CASE WHEN synthesis_step_used THEN 1 ELSE 0 END) as synthesis_used,
  AVG(synthesis_tool_count) as avg_tool_calls,
  AVG(synthesis_evidence_count) as avg_evidence_count,
  AVG(LENGTH(content)) as avg_content_length,
  SUM(CASE WHEN content = '' THEN 1 ELSE 0 END) as empty_responses,
  SUM(CASE WHEN grounding_mode = 'REQUIRED' AND fail_closed_reason IS NOT NULL THEN 1 ELSE 0 END) as required_failures
FROM llm_runs
WHERE vendor = 'openai' AND grounded = true
GROUP BY DATE(timestamp)
ORDER BY date DESC
```

## Known Issues

### Issue: Empty Synthesis Despite Web Search

**Symptoms**: 
- Model performs web searches (`tool_call_count > 0`)
- Returns empty `output_text` and no message items
- Telemetry shows `provoker_retry_used=true` but still empty

**Root Cause**: OpenAI Responses API limitation where the model doesn't always synthesize after tool calls

**Mitigation**: Three-stage fallback chain (enabled by default in production)

**Long-term Fix**: Awaiting OpenAI API improvements

## Rollback Procedures

### Quick Rollback (Disable Two-Step)

If two-step synthesis causes issues:

```bash
# Immediate rollback
export OPENAI_GROUNDED_TWO_STEP=false

# Restart service
./restart_backend.sh
```

**Impact**: Grounded requests may return empty when OpenAI doesn't synthesize

### Full Rollback (Disable All Fallbacks)

Emergency only - will break grounded mode:

```bash
# Disable all fallbacks
export OPENAI_PROVOKER_ENABLED=false
export OPENAI_GROUNDED_TWO_STEP=false

# Restart service
./restart_backend.sh
```

**Impact**: High rate of empty grounded responses, REQUIRED mode will fail frequently

## Troubleshooting

### High Provoker Usage Rate

If >50% of grounded requests use provoker:

1. Check OpenAI service status
2. Review recent prompts for complexity
3. Consider increasing `OPENAI_GROUNDED_MAX_TOKENS`
4. Monitor `finish_reason` in telemetry

### High Two-Step Usage Rate

If >30% of grounded requests use two-step synthesis:

1. Verify provoker is enabled (`OPENAI_PROVOKER_ENABLED=true`)
2. Check if specific prompt patterns trigger the issue
3. Review OpenAI API changelog for updates
4. Consider filing support ticket with OpenAI

### REQUIRED Mode Failures

If REQUIRED pass rate <95%:

1. Check citation extraction:
   ```sql
   SELECT fail_closed_reason, COUNT(*) 
   FROM llm_runs 
   WHERE grounding_mode='REQUIRED' AND success=false 
   GROUP BY fail_closed_reason
   ```

2. Common causes:
   - `no_tool_calls_with_required`: Model didn't search
   - `no_citations_with_required`: Searches returned no results

3. Mitigations:
   - Ensure `OPENAI_GROUNDED_TWO_STEP=true`
   - Review prompt quality
   - Check if specific topics lack searchable content

### Empty Response Debugging

```python
# Debug script to test grounded mode
import asyncio
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_grounded():
    adapter = UnifiedLLMAdapter()
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-2025-08-07",
        messages=[{"role": "user", "content": "What's the latest news?"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"}
    )
    response = await adapter.complete(request)
    
    print(f"Success: {response.success}")
    print(f"Content length: {len(response.content or '')}")
    print(f"Metadata: {response.metadata}")
    
    # Check fallback usage
    if response.metadata.get('provoker_retry_used'):
        print("⚠️ Provoker was needed")
    if response.metadata.get('synthesis_step_used'):
        print("⚠️ Two-step synthesis was needed")

asyncio.run(test_grounded())
```

## Performance Tuning

### Token Budget Optimization

```bash
# For long-form content
export OPENAI_GROUNDED_MAX_TOKENS=8000

# For brief answers
export OPENAI_GROUNDED_MAX_TOKENS=4000
```

### Evidence List Tuning

```bash
# More citations for research tasks
export OPENAI_GROUNDED_MAX_EVIDENCE=10

# Fewer for quick answers
export OPENAI_GROUNDED_MAX_EVIDENCE=3
```

## Integration Points

### BigQuery Schema

Ensure these fields exist in your BigQuery table:

```sql
-- Additional fields for OpenAI grounded telemetry
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS provoker_retry_used BOOLEAN;
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS synthesis_step_used BOOLEAN;
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS synthesis_tool_count INTEGER;
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS synthesis_evidence_count INTEGER;
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS provoker_value STRING;
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS response_output_sha256 STRING;
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS provider_api_version STRING;
ALTER TABLE llm_runs ADD COLUMN IF NOT EXISTS why_not_grounded STRING;
```

### Alerting Rules

```yaml
# Prometheus/AlertManager config
- alert: OpenAIGroundedHighFailureRate
  expr: |
    (sum(rate(llm_requests_total{vendor="openai",grounded="true",success="false"}[5m])) /
     sum(rate(llm_requests_total{vendor="openai",grounded="true"}[5m]))) > 0.1
  for: 5m
  annotations:
    summary: "High failure rate for OpenAI grounded requests"
    description: "{{ $value | humanizePercentage }} of grounded requests failing"

- alert: OpenAIGroundedHighSynthesisRate
  expr: |
    (sum(rate(llm_synthesis_used_total{vendor="openai"}[5m])) /
     sum(rate(llm_requests_total{vendor="openai",grounded="true"}[5m]))) > 0.3
  for: 10m
  annotations:
    summary: "High two-step synthesis usage"
    description: "{{ $value | humanizePercentage }} of requests need synthesis fallback"
```

## Contact

For escalation:
- **On-Call**: Check PagerDuty rotation
- **Slack**: #ai-platform-alerts
- **OpenAI Support**: via enterprise portal (for API issues)

---

**Last Updated**: 2025-09-05
**Version**: 1.0.0
**Owner**: AI Platform Team