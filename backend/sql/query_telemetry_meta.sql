-- Query to verify telemetry meta persistence
-- Run after deploying the migration to check data is flowing

-- ============================================================================
-- 1. Check if meta column exists and has data
-- ============================================================================
SELECT 
    COUNT(*) AS total_rows,
    COUNT(meta) AS rows_with_meta,
    COUNT(*) FILTER (WHERE meta IS NOT NULL) AS non_null_meta
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour';

-- ============================================================================
-- 2. Sample recent telemetry with rich metadata
-- ============================================================================
SELECT 
    id,
    vendor,
    model,
    grounded,
    grounded_effective,
    success,
    latency_ms,
    total_tokens,
    meta->>'response_api' AS response_api,
    meta->>'grounding_mode_requested' AS grounding_mode,
    meta->>'tool_call_count' AS tool_calls,
    meta->>'citations_count' AS citations,
    meta->>'als_present' AS als_present,
    meta->>'model_adjusted_for_grounding' AS model_adjusted,
    created_at
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 10;

-- ============================================================================
-- 3. Grounding effectiveness by vendor
-- ============================================================================
SELECT 
    vendor,
    COUNT(*) AS total_calls,
    COUNT(*) FILTER (WHERE grounded = TRUE) AS grounded_requested,
    COUNT(*) FILTER (WHERE grounded_effective = TRUE) AS grounded_effective,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE grounded_effective = TRUE) / 
        NULLIF(COUNT(*) FILTER (WHERE grounded = TRUE), 0),
        2
    ) AS grounding_success_rate
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY vendor;

-- ============================================================================
-- 4. Response API distribution (telemetry contract verification)
-- ============================================================================
SELECT 
    vendor,
    grounded,
    meta->>'response_api' AS response_api,
    COUNT(*) AS call_count
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY vendor, grounded, meta->>'response_api'
ORDER BY vendor, grounded, response_api;

-- ============================================================================
-- 5. Feature flag distribution for A/B testing
-- ============================================================================
SELECT 
    meta->'feature_flags'->>'citation_extractor_v2' AS citation_extractor_version,
    COUNT(*) AS call_count,
    AVG((meta->>'citations_count')::int) AS avg_citations
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '24 hours'
    AND grounded = TRUE
GROUP BY meta->'feature_flags'->>'citation_extractor_v2'
ORDER BY citation_extractor_version;

-- ============================================================================
-- 6. ALS propagation verification
-- ============================================================================
SELECT 
    vendor,
    COUNT(*) AS total_calls,
    COUNT(*) FILTER (WHERE (meta->>'als_present')::boolean = TRUE) AS als_present,
    COUNT(DISTINCT meta->>'als_variant_id') AS unique_variants,
    COUNT(DISTINCT meta->>'als_country') AS unique_countries
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY vendor;

-- ============================================================================
-- 7. Model routing verification (OpenAI specific)
-- ============================================================================
SELECT 
    model,
    grounded,
    grounded_effective,
    meta->>'original_model' AS original_model,
    (meta->>'model_adjusted_for_grounding')::boolean AS adjusted,
    COUNT(*) AS call_count
FROM llm_telemetry
WHERE vendor = 'openai'
    AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY model, grounded, grounded_effective, meta->>'original_model', 
         (meta->>'model_adjusted_for_grounding')::boolean
ORDER BY model, grounded;

-- ============================================================================
-- 8. Citation extraction effectiveness
-- ============================================================================
SELECT 
    vendor,
    AVG((meta->>'tool_call_count')::int) AS avg_tool_calls,
    AVG((meta->>'citations_count')::int) AS avg_citations,
    AVG((meta->>'anchored_citations_count')::int) AS avg_anchored,
    AVG((meta->>'unlinked_sources_count')::int) AS avg_unlinked,
    COUNT(*) FILTER (WHERE (meta->>'tool_call_count')::int > 0 
                       AND (meta->>'citations_count')::int = 0) AS tools_no_citations
FROM llm_telemetry
WHERE grounded_effective = TRUE
    AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY vendor;

-- ============================================================================
-- 9. REQUIRED mode failure analysis
-- ============================================================================
SELECT 
    vendor,
    meta->>'why_not_grounded' AS failure_reason,
    COUNT(*) AS failure_count
FROM llm_telemetry
WHERE grounded = TRUE
    AND grounded_effective = FALSE
    AND meta->>'grounding_mode_requested' = 'REQUIRED'
    AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY vendor, meta->>'why_not_grounded'
ORDER BY failure_count DESC;

-- ============================================================================
-- 10. Performance by configuration
-- ============================================================================
SELECT 
    vendor,
    model,
    grounded,
    json_mode,
    COUNT(*) AS calls,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_ms,
    AVG(total_tokens) AS avg_tokens
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '24 hours'
    AND success = TRUE
GROUP BY vendor, model, grounded, json_mode
ORDER BY calls DESC;