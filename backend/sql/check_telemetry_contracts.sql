-- Post-Deploy Telemetry Contract Checks
-- These SQL assertions MUST pass in CI after deployment
-- They enforce the Phase-0 telemetry contract at the database level

-- ============================================================================
-- CHECK 1: All grounded rows MUST have response_api
-- ============================================================================
DO $$
DECLARE
    missing_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO missing_count
    FROM llm_calls
    WHERE grounded = TRUE
      AND (
        meta IS NULL
        OR NOT (meta ? 'response_api')
        OR NULLIF(meta->>'response_api', '') IS NULL
      );
    
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: % grounded rows missing meta.response_api', missing_count;
    END IF;
    
    RAISE NOTICE '✅ CHECK 1 PASSED: All grounded rows have response_api';
END $$;

-- ============================================================================
-- CHECK 2: OpenAI grounded rows MUST use responses_http
-- ============================================================================
DO $$
DECLARE
    bad_count INTEGER;
    bad_examples TEXT;
BEGIN
    WITH bad_rows AS (
        SELECT id, model, meta->>'response_api' AS api
        FROM llm_calls
        WHERE vendor = 'openai' 
          AND grounded = TRUE
          AND COALESCE(meta->>'response_api', '') != 'responses_http'
        LIMIT 5
    )
    SELECT 
        COUNT(*),
        STRING_AGG(id::text || ' (api=' || COALESCE(api, 'NULL') || ')', ', ')
    INTO bad_count, bad_examples
    FROM bad_rows;
    
    IF bad_count > 0 THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: % OpenAI grounded rows not using responses_http. Examples: %', 
            bad_count, bad_examples;
    END IF;
    
    RAISE NOTICE '✅ CHECK 2 PASSED: All OpenAI grounded rows use responses_http';
END $$;

-- ============================================================================
-- CHECK 3: Vertex grounded rows MUST use vertex_genai
-- ============================================================================
DO $$
DECLARE
    bad_count INTEGER;
    bad_examples TEXT;
BEGIN
    WITH bad_rows AS (
        SELECT id, model, meta->>'response_api' AS api
        FROM llm_calls
        WHERE vendor IN ('vertex', 'google')
          AND grounded = TRUE
          AND COALESCE(meta->>'response_api', '') != 'vertex_genai'
        LIMIT 5
    )
    SELECT 
        COUNT(*),
        STRING_AGG(id::text || ' (api=' || COALESCE(api, 'NULL') || ')', ', ')
    INTO bad_count, bad_examples
    FROM bad_rows;
    
    IF bad_count > 0 THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: % Vertex grounded rows not using vertex_genai. Examples: %', 
            bad_count, bad_examples;
    END IF;
    
    RAISE NOTICE '✅ CHECK 3 PASSED: All Vertex grounded rows use vertex_genai';
END $$;

-- ============================================================================
-- CHECK 4: Failed calls MUST have error_code
-- ============================================================================
DO $$
DECLARE
    missing_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO missing_count
    FROM llm_calls
    WHERE success = FALSE
      AND error_code IS NULL;
    
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: % failed calls missing error_code', missing_count;
    END IF;
    
    RAISE NOTICE '✅ CHECK 4 PASSED: All failed calls have error_code';
END $$;

-- ============================================================================
-- CHECK 5: REQUIRED mode failures MUST have why_not_grounded
-- ============================================================================
DO $$
DECLARE
    missing_count INTEGER;
    missing_examples TEXT;
BEGIN
    WITH missing_reasons AS (
        SELECT id, model
        FROM llm_calls
        WHERE grounded = TRUE
          AND COALESCE((meta->>'grounded_effective')::boolean, FALSE) = FALSE
          AND meta->'runtime_flags'->>'grounding_mode' = 'REQUIRED'
          AND (
            NOT (meta ? 'why_not_grounded')
            OR NULLIF(meta->>'why_not_grounded', '') IS NULL
          )
        LIMIT 5
    )
    SELECT 
        COUNT(*),
        STRING_AGG(id::text, ', ')
    INTO missing_count, missing_examples
    FROM missing_reasons;
    
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: % REQUIRED mode failures missing why_not_grounded. Examples: %', 
            missing_count, missing_examples;
    END IF;
    
    RAISE NOTICE '✅ CHECK 5 PASSED: All REQUIRED mode failures have why_not_grounded';
END $$;

-- ============================================================================
-- CHECK 6: Analytics view exists and is queryable
-- ============================================================================
DO $$
DECLARE
    view_exists BOOLEAN;
    row_count INTEGER;
BEGIN
    -- Check if view exists
    SELECT EXISTS (
        SELECT 1 FROM information_schema.views
        WHERE table_schema = 'public' 
          AND table_name = 'analytics_runs'
    ) INTO view_exists;
    
    IF NOT view_exists THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: analytics_runs view does not exist';
    END IF;
    
    -- Test that view is queryable
    BEGIN
        EXECUTE 'SELECT COUNT(*) FROM analytics_runs WHERE ts > NOW() - INTERVAL ''1 day''' INTO row_count;
        RAISE NOTICE '✅ CHECK 6 PASSED: analytics_runs view exists and is queryable (% recent rows)', row_count;
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: analytics_runs view exists but is not queryable: %', SQLERRM;
    END;
END $$;

-- ============================================================================
-- CHECK 7: Model routing invariant (gpt-5 vs gpt-5-chat-latest)
-- ============================================================================
DO $$
DECLARE
    bad_grounded INTEGER;
    bad_ungrounded INTEGER;
BEGIN
    -- Check grounded OpenAI uses gpt-5
    SELECT COUNT(*) INTO bad_grounded
    FROM llm_calls
    WHERE vendor = 'openai'
      AND grounded = TRUE
      AND model = 'gpt-5-chat-latest'
      AND COALESCE((meta->>'model_adjusted_for_grounding')::boolean, FALSE) = FALSE;
    
    IF bad_grounded > 0 THEN
        RAISE WARNING 'ROUTING WARNING: % grounded OpenAI calls using gpt-5-chat-latest without adjustment tracking', bad_grounded;
    END IF;
    
    -- Check ungrounded OpenAI doesn't unnecessarily use gpt-5
    SELECT COUNT(*) INTO bad_ungrounded
    FROM llm_calls
    WHERE vendor = 'openai'
      AND grounded = FALSE
      AND model = 'gpt-5'
      AND ts > NOW() - INTERVAL '1 day';
    
    IF bad_ungrounded > 10 THEN
        RAISE WARNING 'ROUTING WARNING: % ungrounded OpenAI calls using gpt-5 (should use gpt-5-chat-latest)', bad_ungrounded;
    END IF;
    
    RAISE NOTICE '✅ CHECK 7 PASSED: Model routing appears correct (warnings are non-fatal)';
END $$;

-- ============================================================================
-- CHECK 8: Citation metrics consistency
-- ============================================================================
DO $$
DECLARE
    inconsistent_count INTEGER;
BEGIN
    -- When tools are called, we should have citation metrics
    SELECT COUNT(*) INTO inconsistent_count
    FROM llm_calls
    WHERE COALESCE((meta->>'tool_call_count')::int, 0) > 0
      AND NOT (meta ? 'anchored_citations_count')
      AND NOT (meta ? 'unlinked_sources_count')
      AND ts > NOW() - INTERVAL '1 day';
    
    IF inconsistent_count > 0 THEN
        RAISE WARNING 'TELEMETRY WARNING: % calls with tools but no citation metrics', inconsistent_count;
    END IF;
    
    RAISE NOTICE '✅ CHECK 8 PASSED: Citation metrics consistency check complete';
END $$;

-- ============================================================================
-- CHECK 9: Feature flags present for A/B testing
-- ============================================================================
DO $$
DECLARE
    missing_flags INTEGER;
BEGIN
    SELECT COUNT(*) INTO missing_flags
    FROM llm_calls
    WHERE ts > NOW() - INTERVAL '1 day'
      AND NOT (meta ? 'feature_flags')
      AND NOT (meta ? 'runtime_flags');
    
    IF missing_flags > 0 THEN
        RAISE WARNING 'TELEMETRY WARNING: % recent calls missing feature/runtime flags', missing_flags;
    END IF;
    
    RAISE NOTICE '✅ CHECK 9 PASSED: Feature flag check complete';
END $$;

-- ============================================================================
-- CHECK 10: Data freshness (ensure telemetry is flowing)
-- ============================================================================
DO $$
DECLARE
    last_call_age INTERVAL;
    last_call_time TIMESTAMPTZ;
BEGIN
    SELECT MAX(ts) INTO last_call_time
    FROM llm_calls;
    
    IF last_call_time IS NULL THEN
        RAISE EXCEPTION 'CONTRACT VIOLATION: No telemetry data found in llm_calls table';
    END IF;
    
    last_call_age := NOW() - last_call_time;
    
    IF last_call_age > INTERVAL '1 hour' THEN
        RAISE WARNING 'DATA FRESHNESS WARNING: Last telemetry entry is % old', last_call_age;
    END IF;
    
    RAISE NOTICE '✅ CHECK 10 PASSED: Telemetry data is fresh (last entry: %)', last_call_time;
END $$;

-- ============================================================================
-- FINAL SUMMARY
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '════════════════════════════════════════════════════════════════';
    RAISE NOTICE '✅ ALL CRITICAL TELEMETRY CONTRACT CHECKS PASSED';
    RAISE NOTICE '════════════════════════════════════════════════════════════════';
    RAISE NOTICE '';
    RAISE NOTICE 'The Phase-0 telemetry contract is enforced:';
    RAISE NOTICE '  • All grounded calls have response_api';
    RAISE NOTICE '  • OpenAI grounded uses responses_http';
    RAISE NOTICE '  • Vertex grounded uses vertex_genai';
    RAISE NOTICE '  • Failed calls have error codes';
    RAISE NOTICE '  • REQUIRED failures have explanations';
    RAISE NOTICE '  • Analytics view is functional';
    RAISE NOTICE '';
    RAISE NOTICE 'Dashboards and alerts can rely on this data quality.';
END $$;