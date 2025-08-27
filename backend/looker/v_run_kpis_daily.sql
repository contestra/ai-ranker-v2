-- Daily aggregate view for fast Looker Studio charts
-- Replace 'project.dataset' with your actual BigQuery project and dataset names
CREATE OR REPLACE VIEW `project.dataset.v_run_kpis_daily` AS
SELECT
  DATE(event_ts) AS date,
  vendor,
  route_path,
  cc,
  vantage_policy,
  proxy_mode,
  COUNT(*) AS requests,
  SUM(CASE WHEN error = '' THEN 1 ELSE 0 END) AS successes,
  APPROX_QUANTILES(duration_ms, 100)[OFFSET(95)] AS p95_ms,
  AVG(output_tokens) AS avg_out_tokens,
  AVG(SAFE_DIVIDE(output_tokens, duration_ms/1000.0)) AS avg_tokens_per_sec,
  AVG(CAST(proxy_effective AS INT64)) AS proxy_usage_rate,
  AVG(CAST(finalize_pass AS INT64)) AS finalize_rate
FROM `project.dataset.v_run_kpis`
GROUP BY 1,2,3,4,5,6;