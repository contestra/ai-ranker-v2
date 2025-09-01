"""Create analytics_runs view and response_api check for grounded rows

This migration implements Phase-0 telemetry requirements:
- One normalized row per LLM call with rich metadata
- Analytics view for easy dashboard queries
- CHECK constraint ensuring grounded calls have response_api
- Proper indexes for performance

As ChatGPT noted: "Phase-0 requires a normalized row + provenance for each 
run so dashboards can calculate grounding success, fail-closed reasons, 
and surfaces."

Revision ID: 20250901_analytics_view_check
Revises: initial
Create Date: 2025-09-01
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250901_analytics_view_check"
down_revision = None  # First migration
branch_labels = None
depends_on = None


def upgrade():
    """
    Create telemetry infrastructure with proper constraints.
    """
    
    # -- 1) Ensure base table exists (idempotent in case it already does)
    op.execute("""
    CREATE TABLE IF NOT EXISTS llm_calls (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      ts timestamptz NOT NULL DEFAULT now(),
      request_id text,
      tenant_id text,
      vendor text NOT NULL,
      model text NOT NULL,
      grounded boolean NOT NULL DEFAULT false,
      json_mode boolean NOT NULL DEFAULT false,
      latency_ms int,
      tokens_in int,
      tokens_out int,
      cost_est_cents numeric(10,4),
      success boolean NOT NULL,
      error_code text,
      meta jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    """)
    
    # -- 2) Create indexes for common query patterns
    op.execute("CREATE INDEX IF NOT EXISTS llm_calls_ts_idx ON llm_calls (ts DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS llm_calls_vendor_grounded_idx ON llm_calls (vendor, grounded);")
    op.execute("CREATE INDEX IF NOT EXISTS llm_calls_tenant_idx ON llm_calls (tenant_id) WHERE tenant_id IS NOT NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS llm_calls_request_id_idx ON llm_calls (request_id) WHERE request_id IS NOT NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS llm_calls_meta_gin_idx ON llm_calls USING gin (meta);")
    
    # -- 3) Add CHECK constraint: grounded rows MUST have response_api in meta
    #     This enforces our Phase-0 contract for observability.
    #     Adapters MUST emit response_api so analytics can slice by surface.
    op.execute("""
    DO $$ 
    BEGIN
      IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'llm_calls_grounded_requires_response_api_ck'
      ) THEN
        ALTER TABLE llm_calls
        ADD CONSTRAINT llm_calls_grounded_requires_response_api_ck
        CHECK (
          grounded = FALSE
          OR (
            meta ? 'response_api' 
            AND NULLIF(meta->>'response_api', '') IS NOT NULL
          )
        );
      END IF;
    END$$;
    """)
    
    # -- 4) Add CHECK constraint: success=false requires error_code
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'llm_calls_error_requires_code_ck'
      ) THEN
        ALTER TABLE llm_calls
        ADD CONSTRAINT llm_calls_error_requires_code_ck
        CHECK (
          success = TRUE
          OR error_code IS NOT NULL
        );
      END IF;
    END$$;
    """)
    
    # -- 5) Create/replace analytics view that flattens common meta fields
    #     This makes dashboards and monitoring queries simple.
    op.execute("""
    CREATE OR REPLACE VIEW analytics_runs AS
    SELECT
      id,
      ts,
      request_id,
      tenant_id,
      vendor,
      model,
      grounded,
      json_mode,
      success,
      error_code,
      latency_ms,
      tokens_in,
      tokens_out,
      cost_est_cents,
      
      -- Core telemetry fields from meta
      (meta->>'response_api') AS response_api,
      NULLIF((meta->>'grounded_effective'), '')::boolean AS grounded_effective,
      NULLIF((meta->>'model_adjusted_for_grounding'), '')::boolean AS model_adjusted_for_grounding,
      (meta->>'original_model') AS original_model,
      
      -- Citation metrics
      NULLIF((meta->>'tool_call_count'), '')::int AS tool_call_count,
      NULLIF((meta->>'anchored_citations_count'), '')::int AS anchored_citations_count,
      NULLIF((meta->>'unlinked_sources_count'), '')::int AS unlinked_sources_count,
      (meta->'citations_shape_set')::jsonb AS citations_shape_set,
      
      -- Failure tracking
      (meta->>'why_not_grounded') AS why_not_grounded,
      
      -- Feature flags (nested JSON)
      (meta->'feature_flags')::jsonb AS feature_flags,
      (meta->'runtime_flags')::jsonb AS runtime_flags,
      
      -- A/B testing
      NULLIF((meta->>'ab_bucket'), '')::float AS ab_bucket,
      
      -- ALS/ambient signals
      NULLIF((meta->>'als_injected'), '')::boolean AS als_injected,
      (meta->>'country_code') AS country_code,
      
      -- Proxy/routing info
      (meta->>'proxy_mode') AS proxy_mode,
      (meta->>'vantage_policy') AS vantage_policy,
      
      -- Two-step grounding (Vertex specific)
      NULLIF((meta->>'two_step_used'), '')::boolean AS two_step_used,
      NULLIF((meta->>'step2_tools_invoked'), '')::boolean AS step2_tools_invoked,
      
      -- Full meta for detailed analysis
      meta AS meta_raw
      
    FROM llm_calls;
    """)
    
    # -- 6) Create materialized view for hourly stats (optional, for performance)
    op.execute("""
    CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_hourly_stats AS
    SELECT 
      date_trunc('hour', ts) AS hour,
      vendor,
      model,
      COUNT(*) AS total_calls,
      COUNT(*) FILTER (WHERE success = true) AS successful_calls,
      COUNT(*) FILTER (WHERE grounded = true) AS grounded_requested,
      COUNT(*) FILTER (WHERE (meta->>'grounded_effective')::boolean = true) AS grounded_effective,
      COUNT(*) FILTER (WHERE (meta->>'model_adjusted_for_grounding')::boolean = true) AS model_adjustments,
      AVG(latency_ms) AS avg_latency_ms,
      PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
      PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
      PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_latency_ms,
      SUM(tokens_in) AS total_tokens_in,
      SUM(tokens_out) AS total_tokens_out,
      SUM(cost_est_cents) AS total_cost_cents
    FROM llm_calls
    WHERE ts > NOW() - INTERVAL '7 days'
    GROUP BY hour, vendor, model
    WITH DATA;
    """)
    
    # Create index on materialized view
    op.execute("CREATE INDEX IF NOT EXISTS telemetry_hourly_stats_hour_idx ON telemetry_hourly_stats (hour DESC);")
    
    # -- 7) Add table comments for documentation
    op.execute("""
    COMMENT ON TABLE llm_calls IS 
    'Phase-0 telemetry: one normalized row per LLM call with rich metadata for observability';
    """)
    
    op.execute("""
    COMMENT ON VIEW analytics_runs IS 
    'Flattened view of llm_calls for analytics, dashboards, and monitoring queries';
    """)
    
    op.execute("""
    COMMENT ON COLUMN llm_calls.meta IS 
    'Rich telemetry in JSONB: flags, citations, routing decisions, grounding status, etc.';
    """)
    
    op.execute("""
    COMMENT ON COLUMN analytics_runs.response_api IS 
    'API surface used: responses_http (OpenAI grounded), vertex_genai (Vertex grounded), etc.';
    """)
    
    op.execute("""
    COMMENT ON COLUMN analytics_runs.grounded_effective IS 
    'Whether grounding actually occurred (vs just requested)';
    """)
    
    op.execute("""
    COMMENT ON COLUMN analytics_runs.why_not_grounded IS 
    'Reason for grounding failure in REQUIRED mode (for debugging)';
    """)


def downgrade():
    """
    Remove telemetry infrastructure in reverse order.
    """
    # Drop in reverse order of dependencies
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_hourly_stats CASCADE;")
    op.execute("DROP VIEW IF EXISTS analytics_runs CASCADE;")
    
    # Drop constraints
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'llm_calls_grounded_requires_response_api_ck'
      ) THEN
        ALTER TABLE llm_calls
        DROP CONSTRAINT llm_calls_grounded_requires_response_api_ck;
      END IF;
    END$$;
    """)
    
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'llm_calls_error_requires_code_ck'
      ) THEN
        ALTER TABLE llm_calls
        DROP CONSTRAINT llm_calls_error_requires_code_ck;
      END IF;
    END$$;
    """)
    
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS llm_calls_meta_gin_idx;")
    op.execute("DROP INDEX IF EXISTS llm_calls_request_id_idx;")
    op.execute("DROP INDEX IF EXISTS llm_calls_tenant_idx;")
    op.execute("DROP INDEX IF EXISTS llm_calls_vendor_grounded_idx;")
    op.execute("DROP INDEX IF EXISTS llm_calls_ts_idx;")
    
    # Finally drop the table
    op.execute("DROP TABLE IF EXISTS llm_calls CASCADE;")


def verify_migration():
    """
    Post-migration verification queries to ensure contract is enforced.
    Run these in CI after migration to catch issues early.
    """
    verification_queries = [
        # 1. Verify no grounded rows lack response_api
        """
        SELECT COUNT(*) AS missing_response_api
        FROM llm_calls
        WHERE grounded = TRUE
          AND (meta ? 'response_api') IS NOT TRUE;
        -- Expected: 0 (enforced by CHECK constraint)
        """,
        
        # 2. Verify analytics view is queryable
        """
        SELECT COUNT(*) AS view_rows
        FROM analytics_runs
        LIMIT 1;
        -- Should execute without error
        """,
        
        # 3. Verify materialized view refreshes
        """
        REFRESH MATERIALIZED VIEW telemetry_hourly_stats;
        -- Should execute without error
        """,
        
        # 4. Verify indexes are being used
        """
        EXPLAIN (FORMAT JSON)
        SELECT * FROM llm_calls
        WHERE vendor = 'openai' AND grounded = true
        ORDER BY ts DESC
        LIMIT 10;
        -- Should show index scan on llm_calls_vendor_grounded_idx
        """
    ]
    
    return verification_queries