-- BigQuery view for Looker Studio
-- Replace 'project.dataset' with your actual BigQuery project and dataset names
CREATE OR REPLACE VIEW `project.dataset.v_run_kpis` AS
SELECT
  event_ts,
  run_id,
  vendor,
  SAFE_CAST(JSON_VALUE(metadata, '$.grounded') AS BOOL)              AS grounded,
  JSON_VALUE(metadata, '$.vantage_policy')                           AS vantage_policy,
  JSON_VALUE(metadata, '$.proxy_mode')                               AS proxy_mode,
  JSON_VALUE(metadata, '$.proxy_country')                            AS proxy_country,
  SAFE_CAST(JSON_VALUE(metadata, '$.sdk_env_proxy') AS BOOL)         AS sdk_env_proxy,
  SAFE_CAST(JSON_VALUE(metadata, '$.proxy_effective') AS BOOL)       AS proxy_effective,
  SAFE_CAST(JSON_VALUE(metadata, '$.streaming') AS BOOL)             AS streaming,
  SAFE_CAST(JSON_VALUE(metadata, '$.effective_tokens') AS INT64)     AS effective_tokens,
  SAFE_CAST(JSON_VALUE(metadata, '$.duration_ms') AS INT64)          AS duration_ms,
  SAFE_CAST(JSON_VALUE(metadata, '$.usage.input_tokens') AS INT64)   AS input_tokens,
  SAFE_CAST(JSON_VALUE(metadata, '$.usage.output_tokens') AS INT64)  AS output_tokens,
  SAFE_CAST(JSON_VALUE(metadata, '$.sla_exceeded') AS BOOL)          AS sla_exceeded,
  SAFE_CAST(JSON_VALUE(metadata, '$.degrade_step') AS INT64)         AS degrade_step,
  SAFE_CAST(JSON_VALUE(metadata, '$.finalize_pass') AS BOOL)         AS finalize_pass,
  JSON_VALUE(metadata, '$.finalize_reason')                          AS finalize_reason,
  JSON_VALUE(metadata, '$.model')                                    AS model,
  COALESCE(JSON_VALUE(metadata, '$.als_country'),
           JSON_VALUE(metadata, '$.proxy_country'))                  AS cc,
  COALESCE(JSON_VALUE(metadata, '$.details.path'),
           CASE WHEN vendor = 'vertex' THEN 'sdk' ELSE 'na' END)     AS route_path,
  SAFE_CAST(JSON_VALUE(metadata, '$.vendor_switched') AS BOOL)       AS vendor_switched,
  IFNULL(error, '')                                                  AS error
FROM `project.dataset.run_logs`;