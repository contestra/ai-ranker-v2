-- BigQuery Migration: Add required_pass_reason column for REQUIRED mode telemetry
-- Date: 2025-09-03
-- Purpose: Track why REQUIRED grounding mode passed (anchored vs unlinked_google)

-- ============================================================================
-- 1) ADD NEW COLUMN (with guard to prevent errors if already exists)
-- ============================================================================

ALTER TABLE `analytics.runs`
ADD COLUMN IF NOT EXISTS required_pass_reason STRING
OPTIONS (description="Reason REQUIRED passed: 'anchored' or 'unlinked_google'; 'none' if not applicable");

-- Optional: Enforce allowed values via CHECK constraint
-- Uncomment if you want strict validation
/*
ALTER TABLE `analytics.runs`
ADD CONSTRAINT required_pass_reason_allowed
CHECK (required_pass_reason IN ('anchored', 'unlinked_google', 'none') OR required_pass_reason IS NULL);
*/

-- ============================================================================
-- 2) BACKFILL HISTORICAL DATA (one-shot)
-- ============================================================================
-- Sets sensible historical values so dashboards don't look empty
-- Logic:
--   - Keep existing values if present
--   - 'anchored' if grounded with anchored citations
--   - 'unlinked_google' if Google vendor with tool calls and unlinked sources
--   - 'none' otherwise

UPDATE `analytics.runs`
SET required_pass_reason = CASE
  -- Preserve existing values
  WHEN COALESCE(required_pass_reason, '') <> '' THEN required_pass_reason
  
  -- Strict path: anchored citations present
  WHEN grounded_effective = TRUE AND COALESCE(anchored_citations_count, 0) > 0 THEN 'anchored'
  
  -- Relaxed path: Google vendors with evidence but no anchors
  WHEN vendor IN ('vertex', 'gemini', 'gemini_direct') 
       AND COALESCE(tool_call_count, 0) > 0 
       AND COALESCE(unlinked_sources_count, 
                    COALESCE(citation_count, 0) - COALESCE(anchored_citations_count, 0)) > 0
    THEN 'unlinked_google'
    
  -- Default: not applicable
  ELSE 'none'
END
WHERE TRUE;

-- ============================================================================
-- 3) UPDATE VIEW FOR DOWNSTREAM CONSUMERS
-- ============================================================================

CREATE OR REPLACE VIEW `analytics.runs_recent` AS
SELECT
  run_id,
  provider,
  model,
  grounding_mode_requested,
  grounded_effective,
  tool_call_count,
  anchored_citations_count,
  unlinked_sources_count,
  required_pass_reason,          -- NEW: Surface in view
  why_not_grounded,
  latency_ms,
  created_at
FROM `analytics.runs`
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY);

-- ============================================================================
-- 4) VALIDATION QUERIES (run these to verify migration)
-- ============================================================================

-- 4a) Distribution by reason (last 7 days)
SELECT 
  required_pass_reason,
  COUNT(*) AS count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS percentage
FROM `analytics.runs`
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY required_pass_reason
ORDER BY count DESC;

-- 4b) Sanity check: relaxed passes should be Google vendors only
SELECT 
  vendor,
  COUNT(*) AS unlinked_google_count
FROM `analytics.runs`
WHERE required_pass_reason = 'unlinked_google'
GROUP BY vendor
ORDER BY unlinked_google_count DESC;

-- 4c) Anchored rate by vendor (last 30 days)
SELECT 
  vendor,
  SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) AS anchored,
  SUM(CASE WHEN required_pass_reason = 'unlinked_google' THEN 1 ELSE 0 END) AS unlinked_google,
  SUM(CASE WHEN required_pass_reason = 'none' THEN 1 ELSE 0 END) AS none,
  COUNT(*) AS total,
  ROUND(100.0 * SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) / COUNT(*), 2) AS anchored_pct
FROM `analytics.runs`
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY vendor
ORDER BY total DESC;

-- 4d) Trend analysis: anchored vs unlinked over time
SELECT 
  DATE(created_at) AS date,
  SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) AS anchored,
  SUM(CASE WHEN required_pass_reason = 'unlinked_google' THEN 1 ELSE 0 END) AS unlinked_google,
  ROUND(100.0 * SUM(CASE WHEN required_pass_reason = 'anchored' THEN 1 ELSE 0 END) / 
        NULLIF(SUM(CASE WHEN required_pass_reason IN ('anchored', 'unlinked_google') THEN 1 ELSE 0 END), 0), 2) AS anchored_rate
FROM `analytics.runs`
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND grounding_mode_requested = 'REQUIRED'
GROUP BY date
ORDER BY date DESC;

-- ============================================================================
-- 5) DASHBOARD & ALERTING RECOMMENDATIONS
-- ============================================================================
/*
Dashboard Updates:
1. Add filter dropdown for required_pass_reason
2. Create pie chart showing distribution of pass reasons
3. Add time series chart for anchored vs unlinked_google trend

Alerting Rules:
1. Alert if unlinked_google percentage > 80% for 6+ hours
   - Indicates potential issue with anchor extraction
   
2. Alert if anchored percentage suddenly drops by >20%
   - May indicate API changes or extraction issues
   
3. Monitor vendor != 'vertex/gemini' with unlinked_google
   - Should never happen per business logic

Metrics to Track:
- required_pass_reason.anchored.rate (goal: increase over time)
- required_pass_reason.unlinked_google.rate (goal: decrease as Google improves)
- required_pass_reason.none.rate (should be minimal for REQUIRED mode)
*/

-- ============================================================================
-- ROLLBACK (if needed)
-- ============================================================================
/*
-- To rollback this migration:
ALTER TABLE `analytics.runs` DROP COLUMN required_pass_reason;

-- Re-create old view without the column
CREATE OR REPLACE VIEW `analytics.runs_recent` AS
SELECT
  run_id,
  provider,
  model,
  grounding_mode_requested,
  grounded_effective,
  tool_call_count,
  anchored_citations_count,
  unlinked_sources_count,
  -- required_pass_reason removed
  why_not_grounded,
  latency_ms,
  created_at
FROM `analytics.runs`
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY);
*/