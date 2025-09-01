-- Telemetry Contract Verification Queries
-- Run these after deployment to ensure telemetry is working correctly

-- ============================================================================
-- 1. CRITICAL: Verify grounded rows have response_api (enforced by CHECK)
-- ============================================================================
SELECT 
    'Grounded rows missing response_api' AS check_name,
    COUNT(*) AS issue_count,
    CASE 
        WHEN COUNT(*) = 0 THEN '✅ PASS'
        ELSE '❌ FAIL - CHECK constraint not working!'
    END AS status
FROM llm_calls
WHERE grounded = TRUE
  AND (meta ? 'response_api') IS NOT TRUE;

-- ============================================================================
-- 2. Verify OpenAI routing invariant
-- ============================================================================
SELECT 
    'OpenAI routing check' AS check_name,
    vendor,
    model,
    grounded,
    response_api,
    COUNT(*) AS call_count
FROM analytics_runs
WHERE vendor = 'openai'
  AND ts > NOW() - INTERVAL '1 hour'
GROUP BY vendor, model, grounded, response_api
ORDER BY grounded DESC, model;

-- Expected:
-- grounded=true  → model=gpt-5, response_api=responses_http
-- grounded=false → model=gpt-5-chat-latest, response_api=NULL or chat_completions

-- ============================================================================
-- 3. Model adjustment tracking
-- ============================================================================
SELECT 
    'Model adjustments in last hour' AS metric,
    COUNT(*) FILTER (WHERE model_adjusted_for_grounding = TRUE) AS adjusted,
    COUNT(*) FILTER (WHERE original_model IS NOT NULL) AS has_original,
    COUNT(*) AS total_openai_grounded
FROM analytics_runs
WHERE vendor = 'openai'
  AND grounded = TRUE
  AND ts > NOW() - INTERVAL '1 hour';

-- ============================================================================
-- 4. Citation extraction effectiveness
-- ============================================================================
SELECT 
    'Citation metrics' AS metric,
    COUNT(*) FILTER (WHERE tool_call_count > 0) AS calls_with_tools,
    COUNT(*) FILTER (WHERE anchored_citations_count > 0) AS calls_with_citations,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE anchored_citations_count > 0) /
        NULLIF(COUNT(*) FILTER (WHERE tool_call_count > 0), 0),
        2
    ) AS citation_success_rate
FROM analytics_runs
WHERE grounded = TRUE
  AND ts > NOW() - INTERVAL '24 hours';

-- ============================================================================
-- 5. REQUIRED mode failure analysis
-- ============================================================================
SELECT 
    'REQUIRED mode failures' AS analysis,
    why_not_grounded,
    COUNT(*) AS failure_count
FROM analytics_runs
WHERE grounded = TRUE
  AND grounded_effective = FALSE
  AND runtime_flags->>'grounding_mode' = 'REQUIRED'
  AND ts > NOW() - INTERVAL '24 hours'
GROUP BY why_not_grounded
ORDER BY failure_count DESC;

-- ============================================================================
-- 6. Feature flag distribution (for A/B testing)
-- ============================================================================
SELECT 
    'Feature flag: citation_extractor_v2' AS flag,
    (feature_flags->>'citation_extractor_v2')::float AS version,
    COUNT(*) AS call_count,
    AVG(CASE WHEN anchored_citations_count > 0 THEN 1 ELSE 0 END) AS success_rate
FROM analytics_runs
WHERE grounded = TRUE
  AND ts > NOW() - INTERVAL '24 hours'
GROUP BY version
ORDER BY version;

-- ============================================================================
-- 7. Performance metrics by vendor/model
-- ============================================================================
SELECT 
    vendor,
    model,
    COUNT(*) AS calls,
    ROUND(AVG(latency_ms)) AS avg_latency_ms,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_ms
FROM analytics_runs
WHERE ts > NOW() - INTERVAL '1 hour'
GROUP BY vendor, model
ORDER BY calls DESC;

-- ============================================================================
-- 8. Comprehensive health check
-- ============================================================================
WITH health_metrics AS (
    SELECT 
        COUNT(*) AS total_calls,
        COUNT(*) FILTER (WHERE success = TRUE) AS successful,
        COUNT(*) FILTER (WHERE grounded = TRUE) AS grounded_requested,
        COUNT(*) FILTER (WHERE grounded_effective = TRUE) AS grounded_effective,
        AVG(latency_ms) AS avg_latency,
        MAX(ts) AS last_call_time
    FROM analytics_runs
    WHERE ts > NOW() - INTERVAL '1 hour'
)
SELECT 
    total_calls,
    successful,
    ROUND(100.0 * successful / NULLIF(total_calls, 0), 2) AS success_rate,
    grounded_requested,
    grounded_effective,
    ROUND(100.0 * grounded_effective / NULLIF(grounded_requested, 0), 2) AS grounding_success_rate,
    ROUND(avg_latency) AS avg_latency_ms,
    AGE(NOW(), last_call_time) AS time_since_last_call
FROM health_metrics;

-- ============================================================================
-- 9. Data quality check
-- ============================================================================
SELECT 
    'Data Quality Report' AS report,
    COUNT(*) FILTER (WHERE meta IS NULL) AS null_meta,
    COUNT(*) FILTER (WHERE vendor IS NULL) AS null_vendor,
    COUNT(*) FILTER (WHERE model IS NULL) AS null_model,
    COUNT(*) FILTER (WHERE success = FALSE AND error_code IS NULL) AS missing_error_codes,
    COUNT(*) FILTER (
        WHERE grounded = TRUE 
        AND grounded_effective = FALSE 
        AND why_not_grounded IS NULL
    ) AS missing_failure_reasons
FROM llm_calls
WHERE ts > NOW() - INTERVAL '24 hours';

-- All values should be 0 for good data quality

-- ============================================================================
-- 10. Alert threshold checks
-- ============================================================================
WITH alert_metrics AS (
    SELECT 
        -- Tools called but no citations (should be < 2%)
        100.0 * COUNT(*) FILTER (
            WHERE tool_call_count > 0 
            AND anchored_citations_count = 0
        ) / NULLIF(COUNT(*) FILTER (WHERE tool_call_count > 0), 0) AS tools_no_citations_rate,
        
        -- P95 latency (should be < 25s)
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) / 1000.0 AS p95_latency_seconds,
        
        -- Error rate (should be < 1%)
        100.0 * COUNT(*) FILTER (WHERE success = FALSE) / NULLIF(COUNT(*), 0) AS error_rate
        
    FROM analytics_runs
    WHERE ts > NOW() - INTERVAL '15 minutes'
)
SELECT 
    'Alert Thresholds' AS check,
    CASE 
        WHEN tools_no_citations_rate > 5 THEN '🚨 CRITICAL: Tools without citations > 5%'
        WHEN tools_no_citations_rate > 2 THEN '⚠️  WARNING: Tools without citations > 2%'
        ELSE '✅ OK: Tools without citations < 2%'
    END AS citation_alert,
    
    CASE 
        WHEN p95_latency_seconds > 45 THEN '🚨 CRITICAL: P95 latency > 45s'
        WHEN p95_latency_seconds > 25 THEN '⚠️  WARNING: P95 latency > 25s'
        ELSE '✅ OK: P95 latency < 25s'
    END AS latency_alert,
    
    CASE 
        WHEN error_rate > 5 THEN '🚨 CRITICAL: Error rate > 5%'
        WHEN error_rate > 1 THEN '⚠️  WARNING: Error rate > 1%'
        ELSE '✅ OK: Error rate < 1%'
    END AS error_alert
    
FROM alert_metrics;