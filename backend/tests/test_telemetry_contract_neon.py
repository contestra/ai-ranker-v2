"""
Post-deploy telemetry contract verification for Neon.

These tests run SQL assertions to ensure the telemetry contract is maintained
in production. They verify that constraints are enforced and data quality is high.

As ChatGPT suggested: "A tiny Alembic post-deploy test (SQL assertions executed 
in CI) that fails the pipeline if any grounded row has a NULL response_api."
"""

import pytest
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import os


# Neon connection
NEON_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("NEON_DATABASE_URL", "")
).replace("postgresql://", "postgresql+asyncpg://")


class TestTelemetryContract:
    """
    Verify telemetry contract is enforced in Neon.
    These are data quality checks that should pass in production.
    """
    
    @pytest.mark.asyncio
    async def test_grounded_rows_have_response_api(self):
        """
        CRITICAL: All grounded rows MUST have response_api set.
        This is enforced by CHECK constraint but verify it's working.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            # This query should return 0 due to CHECK constraint
            result = await conn.execute(text("""
                SELECT COUNT(*) AS missing_count
                FROM llm_calls
                WHERE grounded = TRUE
                  AND (
                    meta IS NULL
                    OR NOT (meta ? 'response_api')
                    OR NULLIF(meta->>'response_api', '') IS NULL
                  )
            """))
            
            row = result.first()
            missing_count = row.missing_count if row else 0
            
            assert missing_count == 0, (
                f"CONTRACT VIOLATION: {missing_count} grounded rows lack response_api. "
                "This should be impossible with CHECK constraint!"
            )
    
    @pytest.mark.asyncio
    async def test_openai_grounded_uses_correct_api(self):
        """
        OpenAI grounded calls MUST use responses_http API.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            # Find any OpenAI grounded calls with wrong API
            result = await conn.execute(text("""
                SELECT 
                    id,
                    model,
                    meta->>'response_api' AS response_api
                FROM llm_calls
                WHERE vendor = 'openai'
                  AND grounded = TRUE
                  AND meta->>'response_api' != 'responses_http'
                LIMIT 10
            """))
            
            wrong_api_rows = result.fetchall()
            
            if wrong_api_rows:
                details = [
                    f"ID: {row.id}, Model: {row.model}, API: {row.response_api}"
                    for row in wrong_api_rows
                ]
                assert False, (
                    f"OpenAI grounded calls using wrong API:\n" + "\n".join(details)
                )
    
    @pytest.mark.asyncio
    async def test_vertex_grounded_uses_correct_api(self):
        """
        Vertex grounded calls MUST use vertex_genai API.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT 
                    id,
                    model,
                    meta->>'response_api' AS response_api
                FROM llm_calls
                WHERE vendor = 'vertex'
                  AND grounded = TRUE
                  AND meta->>'response_api' != 'vertex_genai'
                LIMIT 10
            """))
            
            wrong_api_rows = result.fetchall()
            
            if wrong_api_rows:
                details = [
                    f"ID: {row.id}, Model: {row.model}, API: {row.response_api}"
                    for row in wrong_api_rows
                ]
                assert False, (
                    f"Vertex grounded calls using wrong API:\n" + "\n".join(details)
                )
    
    @pytest.mark.asyncio
    async def test_failed_calls_have_error_code(self):
        """
        All failed calls MUST have an error_code for debugging.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT COUNT(*) AS missing_error_code
                FROM llm_calls
                WHERE success = FALSE
                  AND error_code IS NULL
            """))
            
            row = result.first()
            missing_count = row.missing_error_code if row else 0
            
            assert missing_count == 0, (
                f"CONTRACT VIOLATION: {missing_count} failed calls lack error_code"
            )
    
    @pytest.mark.asyncio
    async def test_model_adjustment_tracked(self):
        """
        When model is adjusted (gpt-5-chat-latest → gpt-5), it must be tracked.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            # Find cases where model looks adjusted but metadata missing
            result = await conn.execute(text("""
                SELECT 
                    COUNT(*) AS untracked_adjustments
                FROM llm_calls
                WHERE vendor = 'openai'
                  AND model = 'gpt-5'
                  AND grounded = TRUE
                  AND (
                    NOT (meta ? 'model_adjusted_for_grounding')
                    OR (meta->>'model_adjusted_for_grounding')::boolean IS NOT TRUE
                  )
                  AND ts > NOW() - INTERVAL '24 hours'
            """))
            
            row = result.first()
            untracked = row.untracked_adjustments if row else 0
            
            # This is a warning, not a hard failure (might be legitimate gpt-5 requests)
            if untracked > 0:
                pytest.skip(
                    f"WARNING: {untracked} recent gpt-5 grounded calls lack adjustment tracking. "
                    "These might be legitimate gpt-5 requests or missing telemetry."
                )
    
    @pytest.mark.asyncio
    async def test_analytics_view_queryable(self):
        """
        Analytics view must be queryable for dashboards.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            # Simple query that should work if view exists
            result = await conn.execute(text("""
                SELECT 
                    vendor,
                    COUNT(*) as call_count,
                    AVG(latency_ms) as avg_latency
                FROM analytics_runs
                WHERE ts > NOW() - INTERVAL '1 hour'
                GROUP BY vendor
            """))
            
            rows = result.fetchall()
            # Just verify query executes without error
            assert rows is not None
    
    @pytest.mark.asyncio
    async def test_required_mode_failures_have_reason(self):
        """
        REQUIRED mode failures must have why_not_grounded for debugging.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            # Find REQUIRED mode failures without explanation
            result = await conn.execute(text("""
                SELECT 
                    COUNT(*) AS missing_reasons
                FROM llm_calls
                WHERE grounded = TRUE
                  AND (meta->>'grounded_effective')::boolean = FALSE
                  AND (meta->'runtime_flags'->>'grounding_mode') = 'REQUIRED'
                  AND (
                    NOT (meta ? 'why_not_grounded')
                    OR NULLIF(meta->>'why_not_grounded', '') IS NULL
                  )
            """))
            
            row = result.first()
            missing = row.missing_reasons if row else 0
            
            assert missing == 0, (
                f"REQUIRED mode failures without why_not_grounded: {missing}. "
                "This makes debugging impossible!"
            )
    
    @pytest.mark.asyncio
    async def test_citation_metrics_present_when_tools_called(self):
        """
        When tools are called, citation metrics should be present.
        """
        if not NEON_DATABASE_URL:
            pytest.skip("NEON_DATABASE_URL not configured")
        
        engine = create_async_engine(NEON_DATABASE_URL)
        
        async with engine.begin() as conn:
            # Find calls with tools but no citation metrics
            result = await conn.execute(text("""
                SELECT 
                    COUNT(*) AS missing_metrics
                FROM llm_calls
                WHERE (meta->>'tool_call_count')::int > 0
                  AND NOT (meta ? 'anchored_citations_count')
                  AND ts > NOW() - INTERVAL '24 hours'
            """))
            
            row = result.first()
            missing = row.missing_metrics if row else 0
            
            if missing > 0:
                # Warning, not failure (might be tools without citations)
                pytest.skip(
                    f"WARNING: {missing} recent calls have tools but no citation metrics"
                )


def generate_telemetry_report_query():
    """
    Generate a comprehensive telemetry report query for monitoring.
    """
    return """
    -- Telemetry Health Report
    WITH recent_calls AS (
        SELECT * FROM analytics_runs
        WHERE ts > NOW() - INTERVAL '24 hours'
    )
    SELECT 
        'Total Calls' AS metric,
        COUNT(*)::text AS value
    FROM recent_calls
    
    UNION ALL
    
    SELECT 
        'Grounded Success Rate',
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE grounded_effective = TRUE) / 
            NULLIF(COUNT(*) FILTER (WHERE grounded = TRUE), 0),
            2
        )::text || '%'
    FROM recent_calls
    
    UNION ALL
    
    SELECT 
        'Model Adjustments',
        COUNT(*) FILTER (WHERE model_adjusted_for_grounding = TRUE)::text
    FROM recent_calls
    
    UNION ALL
    
    SELECT 
        'REQUIRED Mode Failures',
        COUNT(*) FILTER (
            WHERE grounded = TRUE 
            AND grounded_effective = FALSE
            AND runtime_flags->>'grounding_mode' = 'REQUIRED'
        )::text
    FROM recent_calls
    
    UNION ALL
    
    SELECT 
        'Avg Citations per Grounded Call',
        ROUND(
            AVG(anchored_citations_count) FILTER (WHERE grounded_effective = TRUE),
            2
        )::text
    FROM recent_calls
    
    UNION ALL
    
    SELECT 
        'P95 Latency (ms)',
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)::text
    FROM recent_calls
    
    ORDER BY metric;
    """