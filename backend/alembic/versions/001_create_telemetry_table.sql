-- Phase-0 telemetry table for LLM calls
-- Single normalized row per call with rich metadata in JSONB

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
  meta jsonb
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS llm_calls_ts_idx ON llm_calls (ts);
CREATE INDEX IF NOT EXISTS llm_calls_vendor_grounded_idx ON llm_calls (vendor, grounded);
CREATE INDEX IF NOT EXISTS llm_calls_tenant_idx ON llm_calls (tenant_id);
CREATE INDEX IF NOT EXISTS llm_calls_request_id_idx ON llm_calls (request_id);
CREATE INDEX IF NOT EXISTS llm_calls_meta_gin_idx ON llm_calls USING gin (meta);

-- Analytics view to flatten JSONB for dashboards
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
  (meta->>'grounded_effective')::boolean AS grounded_effective,
  (meta->>'model_adjusted_for_grounding')::boolean AS model_adjusted_for_grounding,
  (meta->>'original_model') AS original_model,
  
  -- Citation metrics
  (meta->>'tool_call_count')::int AS tool_call_count,
  (meta->>'anchored_citations_count')::int AS anchored_citations_count,
  (meta->>'unlinked_sources_count')::int AS unlinked_sources_count,
  (meta->'citations_shape_set')::jsonb AS citations_shape_set,
  
  -- Failure tracking
  (meta->>'why_not_grounded') AS why_not_grounded,
  
  -- Feature flags (nested JSON)
  (meta->'feature_flags') AS feature_flags,
  (meta->'runtime_flags') AS runtime_flags,
  
  -- ALS/ambient signals
  (meta->>'als_injected')::boolean AS als_injected,
  (meta->>'country_code') AS country_code,
  
  -- Proxy info
  (meta->>'proxy_mode') AS proxy_mode,
  (meta->>'vantage_policy') AS vantage_policy
  
FROM llm_calls;

-- Optional: Add CHECK constraint to ensure grounded calls have response_api
ALTER TABLE llm_calls ADD CONSTRAINT check_grounded_has_response_api
  CHECK (
    (grounded = false) OR 
    (grounded = true AND meta->>'response_api' IS NOT NULL)
  );

-- Comment for documentation
COMMENT ON TABLE llm_calls IS 'Phase-0 telemetry: one normalized row per LLM call with rich metadata';
COMMENT ON VIEW analytics_runs IS 'Flattened view of llm_calls for analytics and dashboards';
COMMENT ON COLUMN llm_calls.meta IS 'Rich telemetry: flags, citations, routing decisions, etc.';