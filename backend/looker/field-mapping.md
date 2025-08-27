# Looker Studio — Field Mapping Cheat-Sheet (Contestra LLM Runs)

Use BigQuery view `project.dataset.v_run_kpis` as the main source.

## Dimensions
- **event_ts** (Time) — `event_ts`
- **vendor** (Text) — `vendor`
- **route_path** (Text) — `route_path` (`genai`/`sdk`/`na`)
- **vantage_policy** (Text) — `vantage_policy`
- **proxy_mode** (Text) — `proxy_mode` (`backbone`/`rotating`/`null`)
- **cc** (Text) — `cc` (ALS/proxy country)
- **model** (Text) — `model`
- **finalize_pass** (Boolean) — `finalize_pass`
- **vendor_switched** (Boolean) — `vendor_switched`

## Metrics
- **Requests** — `COUNT(run_id)`
- **Success Rate** — `COUNTIF(error = '') / COUNT(run_id)`
- **p95 Latency (ms)** — `APPROX_QUANTILES(duration_ms, 100)[OFFSET(95)]` (precompute in daily view)
- **Avg Output Tokens** — `AVG(output_tokens)`
- **Tokens/sec** — `SAFE_DIVIDE(output_tokens, duration_ms/1000.0)`
- **Proxy Usage %** — `100 * AVG(CAST(proxy_effective AS INT64))`
- **Finalize Pass %** — `100 * AVG(CAST(finalize_pass AS INT64))`

## Suggested Charts
1. **Time series** — Requests over time (by vendor/path)  
2. **Scorecard** — Success Rate  
3. **Time series** — p95 Latency (ms)  
4. **Bar** — ALS Geo Split by `cc`  
5. **Table** — Recent runs (vendor, path, cc, duration, output_tokens, error)

## Filters
- Vendor (`vendor`), Path (`route_path`), Country (`cc`), Proxy Mode (`proxy_mode`), Date Range (event_ts)