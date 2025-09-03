# Looker LookML Configuration for `required_pass_reason`

## Overview
Production-ready LookML setup for analyzing `required_pass_reason` alongside grounding metrics. This enables analysts to slice data by pass reasons (anchored vs unlinked_google) and optionally pivot by brand.

---

## 1. Persistent Derived Table (PDT): Last 30 Days

### File: `views/runs_recent.view.lkml`

```lookml
view: runs_recent {
  derived_table: {
    sql:
      SELECT
        run_id,
        provider,
        model,
        grounding_mode_requested,
        grounded_effective,
        tool_call_count,
        anchored_citations_count,
        unlinked_sources_count,
        required_pass_reason,
        why_not_grounded,
        latency_ms,
        created_at
      FROM `analytics.runs`
      WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
      ;;
    # Refresh daily or use a datagroup tied to your ETL
    sql_trigger_value: SELECT FORMAT_TIMESTAMP('%Y-%m-%d', MAX(created_at)) FROM `analytics.runs` ;;
    persist_for: "24 hours"
  }

  # Keys & timestamps
  dimension: run_id { 
    primary_key: yes
    type: string
    sql: ${TABLE}.run_id ;;
  }
  
  dimension_group: created {
    type: time
    timeframes: [raw, time, date, week, month, month_num, year, hour_of_day, day_of_week]
    sql: ${TABLE}.created_at ;;
  }

  # Core dimensions
  dimension: provider { 
    type: string
    description: "LLM provider (openai, vertex, gemini_direct)"
  }
  
  dimension: model { 
    type: string
    description: "Model identifier"
  }
  
  dimension: grounding_mode_requested { 
    type: string
    description: "Grounding mode: AUTO, REQUIRED, or NONE"
  }
  
  dimension: required_pass_reason {
    type: string
    description: "How REQUIRED passed: 'anchored', 'unlinked_google', or 'none'"
    suggestions: ["anchored", "unlinked_google", "none"]
  }
  
  dimension: grounded_effective { 
    type: yesno
    sql: ${TABLE}.grounded_effective ;;
    description: "Whether grounding was actually performed"
  }
  
  dimension: why_not_grounded { 
    type: string
    description: "Reason grounding wasn't effective"
  }

  # Metrics-like dimensions for transparency
  dimension: tool_call_count { 
    type: number
    value_format_name: decimal_0
    description: "Number of tool/function calls made"
  }
  
  dimension: anchored_citations_count { 
    type: number
    value_format_name: decimal_0
    description: "Citations anchored to text spans"
  }
  
  dimension: unlinked_sources_count { 
    type: number
    value_format_name: decimal_0
    description: "Sources found but not anchored"
  }
  
  dimension: latency_ms { 
    type: number
    value_format_name: decimal_0
    description: "Response latency in milliseconds"
  }

  # Derived dimensions
  dimension: has_anchored_citations {
    type: yesno
    sql: ${anchored_citations_count} > 0 ;;
    description: "Has at least one anchored citation"
  }
  
  dimension: grounding_quality_tier {
    type: string
    sql:
      CASE
        WHEN ${required_pass_reason} = 'anchored' THEN '1-Best (Anchored)'
        WHEN ${required_pass_reason} = 'unlinked_google' THEN '2-Good (Unlinked)'
        WHEN ${grounded_effective} = TRUE THEN '3-OK (Grounded)'
        ELSE '4-None'
      END ;;
    description: "Quality tier for grounding evidence"
  }

  # Base measures
  measure: runs { 
    type: count
    drill_fields: [detail*]
    description: "Total number of runs"
  }

  measure: avg_latency_ms { 
    type: average
    sql: ${latency_ms} ;;
    value_format_name: decimal_0
    description: "Average response latency"
  }
  
  measure: avg_tool_calls { 
    type: average
    sql: ${tool_call_count} ;;
    value_format_name: decimal_2
    description: "Average tool calls per run"
  }
  
  measure: total_anchored_citations {
    type: sum
    sql: ${anchored_citations_count} ;;
    description: "Total anchored citations across runs"
  }
  
  measure: total_unlinked_sources {
    type: sum
    sql: ${unlinked_sources_count} ;;
    description: "Total unlinked sources across runs"
  }

  # Filtered measures for required_pass_reason
  measure: required_passes_anchored {
    type: count
    filters: [required_pass_reason: "anchored"]
    description: "Runs that passed REQUIRED via anchored citations"
  }
  
  measure: required_passes_unlinked_google {
    type: count
    filters: [required_pass_reason: "unlinked_google"]
    description: "Runs that passed REQUIRED via unlinked Google evidence"
  }
  
  measure: required_passes_none {
    type: count
    filters: [required_pass_reason: "none"]
    description: "Runs with no grounding evidence"
  }

  # Percentage measures
  measure: share_required_anchored {
    type: number
    sql: SAFE_DIVIDE(${required_passes_anchored}, NULLIF(${runs}, 0)) ;;
    value_format_name: percent_2
    description: "% of runs with anchored pass"
  }
  
  measure: share_required_unlinked_google {
    type: number
    sql: SAFE_DIVIDE(${required_passes_unlinked_google}, NULLIF(${runs}, 0)) ;;
    value_format_name: percent_2
    description: "% of runs with unlinked Google pass"
  }
  
  measure: share_required_none {
    type: number
    sql: SAFE_DIVIDE(${required_passes_none}, NULLIF(${runs}, 0)) ;;
    value_format_name: percent_2
    description: "% of runs with no evidence"
  }
  
  # Quality score measure
  measure: avg_grounding_quality_score {
    type: average
    sql: 
      CASE
        WHEN ${required_pass_reason} = 'anchored' THEN 100
        WHEN ${required_pass_reason} = 'unlinked_google' THEN 60
        WHEN ${grounded_effective} = TRUE THEN 30
        ELSE 0
      END ;;
    value_format_name: decimal_0
    description: "Average grounding quality (0-100 scale)"
  }

  # Display label for dashboards
  dimension: required_pass_reason_label {
    type: string
    sql:
      CASE
        WHEN ${required_pass_reason} = 'anchored' THEN '✅ Anchored'
        WHEN ${required_pass_reason} = 'unlinked_google' THEN '⚠️ Unlinked (Google)'
        WHEN ${required_pass_reason} = 'none' THEN '❌ None'
        ELSE '❓ Unknown'
      END ;;
    description: "User-friendly label with icons"
  }

  # Drill fields
  set: detail {
    fields: [
      run_id, created_time, provider, model, 
      grounding_mode_requested, grounded_effective,
      required_pass_reason_label, tool_call_count, 
      anchored_citations_count, unlinked_sources_count, 
      latency_ms
    ]
  }
}
```

---

## 2. Optional Brand Mapping View

### File: `views/runs_brand_map.view.lkml`

```lookml
view: runs_brand_map {
  sql_table_name: `analytics.runs_brand_map` ;;

  dimension: run_id { 
    primary_key: yes
    type: string
    sql: ${TABLE}.run_id ;;
    hidden: yes  # Hide join key from explore
  }
  
  dimension: brand { 
    type: string
    description: "Brand/customer associated with this run"
  }
  
  dimension: brand_group {
    type: string
    sql: ${TABLE}.brand_group ;;
    description: "Higher-level brand grouping"
  }
  
  dimension: brand_tier {
    type: string
    sql: ${TABLE}.brand_tier ;;
    description: "Brand tier (enterprise, pro, starter)"
    suggestions: ["enterprise", "pro", "starter"]
  }
  
  dimension: brand_region {
    type: string
    sql: ${TABLE}.brand_region ;;
    description: "Geographic region of brand"
  }
  
  # Measures specific to brands
  measure: unique_brands {
    type: count_distinct
    sql: ${brand} ;;
    description: "Number of unique brands"
  }
}
```

---

## 3. Main Explore Configuration

### File: `explores/runs_recent.explore.lkml`

```lookml
explore: runs_recent {
  label: "AI Runs Analysis (Last 30 Days)"
  description: "Analyze grounding performance and REQUIRED policy outcomes with pass reasons"
  
  # Optional brand mapping join
  join: runs_brand_map {
    type: left_outer
    relationship: many_to_one
    sql_on: ${runs_recent.run_id} = ${runs_brand_map.run_id} ;;
    # Comment out if table doesn't exist yet
  }

  # Default filters
  always_filter: {
    filters: [runs_recent.created_date: "30 days"]
  }

  # Conditional formatting hints
  conditionally_filter: {
    filters: [runs_recent.grounding_mode_requested: "REQUIRED"]
    unless: [runs_recent.provider, runs_recent.model]
  }

  # Query optimization
  aggregate_table: daily_summary {
    query: {
      dimensions: [
        runs_recent.created_date,
        runs_recent.provider,
        runs_recent.required_pass_reason
      ]
      measures: [
        runs_recent.runs,
        runs_recent.avg_latency_ms,
        runs_recent.share_required_anchored,
        runs_recent.share_required_unlinked_google
      ]
    }
    materialization: {
      datagroup_trigger: etl_datagroup
    }
  }

  # Suggested fields for quick access
  fields: [
    # Dimensions
    runs_recent.created_date,
    runs_recent.provider,
    runs_recent.model,
    runs_recent.grounding_mode_requested,
    runs_recent.required_pass_reason_label,
    runs_recent.grounding_quality_tier,
    
    # Core measures
    runs_recent.runs,
    runs_recent.share_required_anchored,
    runs_recent.share_required_unlinked_google,
    runs_recent.avg_grounding_quality_score,
    
    # Performance measures
    runs_recent.avg_latency_ms,
    runs_recent.avg_tool_calls,
    
    # Citation measures
    runs_recent.total_anchored_citations,
    runs_recent.total_unlinked_sources,
    
    # Brand fields (if joined)
    runs_brand_map.brand,
    runs_brand_map.brand_tier,
    runs_brand_map.unique_brands
  ]
}
```

---

## 4. Alerting Looks Configuration

### File: `looks/grounding_alerts.lkml`

```lookml
# Alert 1: High Unlinked Google Rate
look: alert_high_unlinked_google {
  title: "High Unlinked Google Rate Alert"
  explore: runs_recent
  
  filters: {
    runs_recent.created_time: "6 hours"
    runs_recent.grounding_mode_requested: "REQUIRED"
  }
  
  dimensions: []
  
  measures: [
    runs_recent.share_required_unlinked_google,
    runs_recent.runs
  ]
  
  # Alert condition
  alert_condition: {
    threshold: 0.80
    operator: greater_than
    field: runs_recent.share_required_unlinked_google
  }
  
  # Notification
  alert_actions: {
    slack_channel: "#eng-alerts"
    email: "platform-team@company.com"
    message: "⚠️ Unlinked Google rate is {{value}} (threshold: 80%) over last 6 hours with {{runs_recent.runs}} runs"
  }
}

# Alert 2: Anchored Rate Drop
look: alert_anchored_rate_drop {
  title: "Anchored Rate Weekly Drop Alert"
  explore: runs_recent
  
  filters: {
    runs_recent.grounding_mode_requested: "REQUIRED"
  }
  
  dimensions: [runs_recent.created_week]
  
  measures: [runs_recent.share_required_anchored]
  
  # Week-over-week comparison
  table_calculations: [{
    label: "WoW Change"
    expression: "(${runs_recent.share_required_anchored} - offset(${runs_recent.share_required_anchored}, 1)) / offset(${runs_recent.share_required_anchored}, 1)"
    value_format_name: percent_2
  }]
  
  alert_condition: {
    threshold: -0.20
    operator: less_than
    field: table_calculations.wow_change
  }
  
  alert_actions: {
    slack_channel: "#eng-alerts"
    message: "📉 Anchored rate dropped {{wow_change}} week-over-week"
  }
}

# Alert 3: Non-Google Unlinked Detection
look: alert_non_google_unlinked {
  title: "Non-Google Unlinked Detection"
  explore: runs_recent
  
  filters: {
    runs_recent.created_time: "1 hour"
    runs_recent.required_pass_reason: "unlinked_google"
    runs_recent.provider: "-vertex,-gemini,-gemini_direct"
  }
  
  dimensions: [
    runs_recent.provider,
    runs_recent.model,
    runs_recent.run_id
  ]
  
  measures: [runs_recent.runs]
  
  alert_condition: {
    threshold: 0
    operator: greater_than
    field: runs_recent.runs
  }
  
  alert_actions: {
    pagerduty: true
    priority: "high"
    message: "🚨 CRITICAL: Non-Google vendor has unlinked_google pass reason"
  }
}
```

---

## 5. Sample Dashboard YAML

### File: `dashboards/grounding_performance.dashboard.lkml`

```yaml
- dashboard: grounding_performance
  title: Grounding Performance Dashboard
  layout: newspaper
  preferred_viewer: dashboards-next
  
  elements:
  
  # KPI Tiles Row
  - title: Anchored Pass Rate
    name: kpi_anchored_rate
    model: analytics
    explore: runs_recent
    type: single_value
    fields: [runs_recent.share_required_anchored]
    filters:
      runs_recent.grounding_mode_requested: "REQUIRED"
    custom_color_enabled: true
    custom_color: "#0F9D58"
    show_comparison: true
    comparison_type: change
    comparison_time_range: 7 days ago for 7 days
    
  - title: Unlinked Google Rate
    name: kpi_unlinked_rate
    model: analytics
    explore: runs_recent
    type: single_value
    fields: [runs_recent.share_required_unlinked_google]
    filters:
      runs_recent.grounding_mode_requested: "REQUIRED"
    custom_color_enabled: true
    custom_color: "#F4B400"
    conditional_formatting: [{
      type: greater_than
      value: 0.5
      background_color: "#FCE4EC"
    }]
    
  - title: Quality Score
    name: kpi_quality_score
    model: analytics
    explore: runs_recent
    type: single_value
    fields: [runs_recent.avg_grounding_quality_score]
    value_format_name: decimal_0
    custom_color: "#4285F4"
    
  # Trend Chart
  - title: Pass Reason Trend
    name: trend_pass_reason
    model: analytics
    explore: runs_recent
    type: looker_area
    fields: [
      runs_recent.created_date,
      runs_recent.required_passes_anchored,
      runs_recent.required_passes_unlinked_google,
      runs_recent.required_passes_none
    ]
    filters:
      runs_recent.grounding_mode_requested: "REQUIRED"
    stacking: percent
    colors: ["#0F9D58", "#F4B400", "#DB4437"]
    
  # Provider Breakdown
  - title: Provider Performance
    name: table_provider_performance
    model: analytics
    explore: runs_recent
    type: looker_grid
    fields: [
      runs_recent.provider,
      runs_recent.runs,
      runs_recent.share_required_anchored,
      runs_recent.share_required_unlinked_google,
      runs_recent.avg_latency_ms,
      runs_recent.avg_tool_calls
    ]
    filters:
      runs_recent.grounding_mode_requested: "REQUIRED"
    sorts: [runs_recent.runs desc]
    
  # Pivot Table
  - title: Model x Pass Reason Matrix
    name: pivot_model_reason
    model: analytics
    explore: runs_recent
    type: table
    fields: [runs_recent.model, runs_recent.required_pass_reason_label, runs_recent.runs]
    pivots: [runs_recent.required_pass_reason_label]
    filters:
      runs_recent.grounding_mode_requested: "REQUIRED"
    sorts: [runs_recent.runs desc 0]
    
  # Brand Analysis (if available)
  - title: Top Brands by Quality
    name: table_brand_quality
    model: analytics
    explore: runs_recent
    type: looker_grid
    fields: [
      runs_brand_map.brand,
      runs_recent.runs,
      runs_recent.avg_grounding_quality_score,
      runs_recent.share_required_anchored
    ]
    filters:
      runs_recent.grounding_mode_requested: "REQUIRED"
    sorts: [runs_recent.avg_grounding_quality_score desc]
    limit: 20
```

---

## 6. Usage Examples for Analysts

### Common Queries

**1. Daily Performance Summary**
```sql
-- In Looker SQL Runner
SELECT
  runs_recent.created_date,
  runs_recent.provider,
  COUNT(*) as total_runs,
  AVG(CASE WHEN runs_recent.required_pass_reason = 'anchored' THEN 1 ELSE 0 END) as anchored_rate,
  AVG(runs_recent.latency_ms) as avg_latency
FROM runs_recent
WHERE runs_recent.grounding_mode_requested = 'REQUIRED'
GROUP BY 1, 2
ORDER BY 1 DESC, 2
```

**2. Brand-Specific Analysis**
- Navigate to `runs_recent` explore
- Add `runs_brand_map.brand` to filters
- Select specific brand(s)
- View `share_required_anchored` by `created_week`

**3. Model Comparison**
- Pivot: Rows = `model`, Columns = `required_pass_reason_label`
- Measure: `runs`
- Filter: `grounding_mode_requested = REQUIRED`

---

## 7. Maintenance & Optimization

### Weekly Tasks
1. Review alert frequency - adjust thresholds if too noisy
2. Check PDT refresh performance - optimize if >5 minutes
3. Monitor `share_required_unlinked_google` trend

### Monthly Tasks
1. Review grounding quality scores by provider
2. Analyze brand-level patterns for enterprise customers
3. Update aggregate tables if query patterns change

### Optimization Tips
- Use `aggregate_table` for frequently-accessed rollups
- Add indexes to BigQuery table on `(created_at, provider, required_pass_reason)`
- Consider partitioning by `created_at` if table >1TB

---

## 8. Troubleshooting

### Common Issues

**PDT not refreshing:**
```sql
-- Check trigger value
SELECT FORMAT_TIMESTAMP('%Y-%m-%d', MAX(created_at)) 
FROM `analytics.runs`;

-- Force refresh
looker deploy --refresh-pdt runs_recent
```

**Missing brand data:**
- Verify `runs_brand_map` table exists
- Check join conditions match primary keys
- Review ETL logs for brand mapping pipeline

**High unlinked_google rate:**
1. Check if Google API changed
2. Review citation extraction logic
3. Compare with OpenAI anchored rate as baseline

---

## Notes & Gotchas

1. **Required field**: Assumes `required_pass_reason` exists in BigQuery (per migration)
2. **PDT trigger**: Uses `sql_trigger_value` - replace with datagroup if available
3. **Brand join**: Comment out if `runs_brand_map` table doesn't exist yet
4. **Performance**: PDT covers 30 days - adjust if too slow/large
5. **Icons**: Dashboard labels use emoji - may need font support

---

*Last Updated: 2025-09-03*
*LookML Version: 7.0+*
*BigQuery Dataset: analytics.runs*