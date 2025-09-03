# Looker Studio Dashboard Configuration for `required_pass_reason`

## Overview
This document outlines the Looker Studio configuration to surface the new `required_pass_reason` telemetry dimension alongside existing grounding metrics. This enables monitoring of how REQUIRED grounding mode passes (strict anchored vs. relaxed unlinked_google).

---

## 1. BigQuery Data Source Configuration

### Add Field in BigQuery Connector

In **Looker Studio → Data Source (analytics.runs)**:

```text
Field Name: Required Pass Reason
Formula: required_pass_reason
Type: Text (Dimension)
Description: How REQUIRED mode passed: 'anchored' (strict) or 'unlinked_google' (relaxed for Google vendors)
```

### Add Calculated Metrics

```text
Field Name: Anchored Pass Rate
Formula: SUM(CASE WHEN required_pass_reason = "anchored" THEN 1 ELSE 0 END) / COUNT(run_id)
Type: Percent
Format: 0.00%

Field Name: Unlinked Google Pass Rate  
Formula: SUM(CASE WHEN required_pass_reason = "unlinked_google" THEN 1 ELSE 0 END) / COUNT(run_id)
Type: Percent
Format: 0.00%

Field Name: Grounding Evidence Rate
Formula: SUM(CASE WHEN required_pass_reason IN ("anchored", "unlinked_google") THEN 1 ELSE 0 END) / COUNT(run_id)
Type: Percent
Format: 0.00%
```

---

## 2. Overview Dashboard Tab Updates

### Key Metrics Scorecards

Add 3 new scorecards to the top row:

| Metric | Formula | Target | Alert Threshold |
|--------|---------|--------|-----------------|
| **Anchored Pass Rate** | `% required_pass_reason = "anchored"` | >60% | <40% (yellow), <20% (red) |
| **Unlinked Google Rate** | `% required_pass_reason = "unlinked_google"` | <30% | >50% (yellow), >80% (red) |
| **No Evidence Rate** | `% required_pass_reason = "none"` | <10% | >20% (yellow), >40% (red) |

### Time Series Chart

**Chart Title**: "REQUIRED Mode Pass Reasons Over Time"

**Configuration**:
- **Dimension**: Date (ts_utc)
- **Breakdown Dimension**: required_pass_reason
- **Metric**: COUNT(run_id)
- **Chart Type**: Stacked Area Chart
- **Color Scheme**:
  - `anchored`: Green (#0F9D58)
  - `unlinked_google`: Yellow (#F4B400)
  - `none`: Red (#DB4437)

### Trend Analysis Chart

**Chart Title**: "Anchored Citation Trend (7-day moving average)"

**Configuration**:
- **Dimension**: Date
- **Metric**: Anchored Pass Rate (7-day MA)
- **Secondary Metric**: Unlinked Google Rate (7-day MA)
- **Chart Type**: Line Chart with trend line

---

## 3. Run Details Tab Configuration

### Breakdown Table

**Table Title**: "Grounding Performance by Provider & Model"

**Dimensions** (in order):
1. `provider`
2. `model`
3. `grounding_mode_requested`
4. `required_pass_reason`

**Metrics**:
1. `COUNT(run_id)` as "Total Runs"
2. `AVG(latency_ms)` as "Avg Latency (ms)"
3. `AVG(tool_call_count)` as "Avg Tool Calls"
4. `SUM(anchored_citations_count)` as "Total Anchored Citations"
5. `SUM(unlinked_sources_count)` as "Total Unlinked Sources"

**Formatting**:
- Conditional formatting on `required_pass_reason`:
  - `anchored`: Green background
  - `unlinked_google`: Yellow background
  - `none`: Light red background

### Interactive Filters

Add dropdown filters in this order:
1. **Required Pass Reason** (multi-select)
   - Default: All selected
2. **Provider** (existing)
3. **Model** (existing)
4. **Grounding Mode** (existing)
5. **Date Range** (existing)

---

## 4. Alerting Configuration

### Looker Studio Alerts (via Scheduled Email)

#### Alert 1: High Unlinked Google Rate
```sql
-- Trigger Condition
SELECT COUNT(*) > 0
FROM (
  SELECT 
    SUM(CASE WHEN required_pass_reason = 'unlinked_google' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as unlinked_pct
  FROM analytics.runs
  WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 6 HOUR)
    AND grounding_mode_requested = 'REQUIRED'
) WHERE unlinked_pct > 80
```
**Action**: Email eng-team@company.com
**Frequency**: Every 6 hours

#### Alert 2: Anchored Rate Drop
```sql
-- Trigger if anchored rate drops >20% week-over-week
SELECT COUNT(*) > 0
FROM (
  WITH weekly_rates AS (
    SELECT 
      DATE_TRUNC(created_at, WEEK) as week,
      SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as anchored_rate
    FROM analytics.runs
    WHERE grounding_mode_requested = 'REQUIRED'
    GROUP BY 1
  )
  SELECT 
    curr.anchored_rate - prev.anchored_rate as rate_change
  FROM weekly_rates curr
  JOIN weekly_rates prev ON DATE_ADD(prev.week, INTERVAL 1 WEEK) = curr.week
  WHERE curr.week = DATE_TRUNC(CURRENT_DATE(), WEEK)
) WHERE rate_change < -20
```
**Action**: Slack #eng-alerts channel
**Frequency**: Weekly on Monday

#### Alert 3: Non-Google Unlinked Detection
```sql
-- Should never happen - indicates bug
SELECT COUNT(*) 
FROM analytics.runs
WHERE required_pass_reason = 'unlinked_google'
  AND vendor NOT IN ('vertex', 'gemini', 'gemini_direct')
  AND created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
```
**Action**: PagerDuty high priority
**Frequency**: Every hour

---

## 5. Executive Dashboard Components

### Summary Card with Narrative

Add a text widget with dynamic values:

```markdown
## Grounding Evidence Quality

In the last 7 days:
- **{anchored_rate}%** of REQUIRED grounding requests had citations directly anchored to answer text (best quality)
- **{unlinked_google_rate}%** used Google's relaxed validation (web search performed, URLs found, but no text anchoring)
- **{none_rate}%** had no grounding evidence (investigate if >10%)

📊 **Trend**: Anchored rate is {trend_direction} {trend_change}% from last week
```

### Definitions Panel

Add a collapsible "ℹ️ Definitions" panel:

```markdown
**Required Pass Reasons Explained:**

• **anchored** ✅ - Strict validation passed. Citations are tied to specific text spans in the answer.
  Best quality for fact-checking.

• **unlinked_google** ⚠️ - Relaxed validation for Google vendors (Vertex/Gemini). 
  Web search was performed and URLs discovered, but not anchored to specific text.
  Acceptable for Google due to API limitations.

• **none** ❌ - No grounding evidence found. For REQUIRED mode, this causes request failure.
```

---

## 6. Advanced: Looker Explore Configuration

### SQL for Derived Table

```sql
-- Create explore-friendly view with pre-computed metrics
CREATE OR REPLACE VIEW analytics.runs_explore AS
WITH run_metrics AS (
  SELECT 
    run_id,
    provider,
    model,
    grounding_mode_requested,
    required_pass_reason,
    grounded_effective,
    tool_call_count,
    anchored_citations_count,
    unlinked_sources_count,
    latency_ms,
    created_at,
    
    -- Computed flags
    CASE 
      WHEN required_pass_reason = 'anchored' THEN 1 
      ELSE 0 
    END as is_anchored,
    
    CASE 
      WHEN required_pass_reason = 'unlinked_google' THEN 1 
      ELSE 0 
    END as is_unlinked_google,
    
    CASE 
      WHEN required_pass_reason = 'none' THEN 1 
      ELSE 0 
    END as has_no_evidence,
    
    -- Quality score (0-100)
    CASE
      WHEN required_pass_reason = 'anchored' THEN 100
      WHEN required_pass_reason = 'unlinked_google' THEN 60
      ELSE 0
    END as grounding_quality_score
    
  FROM analytics.runs
)
SELECT * FROM run_metrics;
```

### Looker Explore YAML

```yaml
explore: runs_explore {
  label: "LLM Grounding Analysis"
  
  dimension: required_pass_reason {
    type: string
    label: "Required Pass Reason"
    description: "How REQUIRED mode validation passed"
    
    suggestions: ["anchored", "unlinked_google", "none"]
  }
  
  measure: anchored_rate {
    type: average
    sql: ${is_anchored}
    value_format_name: percent_2
    label: "Anchored Pass Rate"
  }
  
  measure: unlinked_google_rate {
    type: average
    sql: ${is_unlinked_google}
    value_format_name: percent_2
    label: "Unlinked Google Rate"
  }
  
  measure: avg_quality_score {
    type: average
    sql: ${grounding_quality_score}
    value_format_name: decimal_0
    label: "Avg Grounding Quality (0-100)"
  }
}
```

---

## 7. Monitoring & Optimization Roadmap

### Phase 1 (Weeks 1-2): Baseline
- Establish baseline metrics for anchored vs unlinked rates
- Identify models/providers with highest anchored rates
- Document any anomalies

### Phase 2 (Weeks 3-4): Optimization  
- If anchored rate <40%, investigate extraction logic
- If unlinked_google >60%, check if Google API improved
- A/B test prompt modifications to improve anchored rate

### Phase 3 (Month 2): Policy Tightening
- When anchored rate consistently >60%, consider tightening REQUIRED policy
- Remove relaxation for Google vendors if they start providing anchors
- Add more granular pass reasons (e.g., "partial_anchored")

### Success Metrics
- **Target**: 70% anchored rate within 3 months
- **Acceptable**: 50% anchored + 30% unlinked_google
- **Alert**: <40% combined evidence rate

---

## Appendix: Sample Queries for Analysis

### Daily Summary Email Query
```sql
SELECT
  DATE(created_at) as date,
  COUNT(*) as total_runs,
  ROUND(100.0 * SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) / COUNT(*), 2) as anchored_pct,
  ROUND(100.0 * SUM(CASE WHEN required_pass_reason = 'unlinked_google' THEN 1 ELSE 0 END) / COUNT(*), 2) as unlinked_pct,
  ROUND(100.0 * SUM(CASE WHEN required_pass_reason = 'none' THEN 1 ELSE 0 END) / COUNT(*), 2) as none_pct
FROM analytics.runs
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND grounding_mode_requested = 'REQUIRED'
GROUP BY date;
```

### Provider Performance Ranking
```sql
SELECT
  provider,
  COUNT(*) as total_required_runs,
  ROUND(100.0 * SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) / COUNT(*), 2) as anchored_rate,
  RANK() OVER (ORDER BY SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) DESC) as quality_rank
FROM analytics.runs  
WHERE grounding_mode_requested = 'REQUIRED'
  AND created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY provider
ORDER BY quality_rank;
```

---

*Last Updated: 2025-09-03*
*Next Review: After 30 days of data collection*