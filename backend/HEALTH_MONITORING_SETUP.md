# Health Monitoring Setup - Production Checklist

## 📊 Prometheus Metrics Export

### Metrics Endpoint
`GET /metrics` - Prometheus-compatible metrics export

### Available Metrics
- `contestra_auth_token_seconds_remaining{auth_mode}` - Seconds to token expiry
- `contestra_auth_status{status}` - Auth status (ok=0, warn=0, error=1)
- `contestra_proxy_mode` - Proxy mode (direct=0, backbone=1, rotating=2)
- `contestra_proxy_rtt_ms{service,probe}` - RTT measurements
- `contestra_llm_latency_ms{vendor,path,proxied}` - LLM latency histogram
- `contestra_llm_rate_limit_events_total{vendor}` - 429 rate limit counter

## 🚀 Ship It (Minimal Requirements)

### 1. Environment Configuration
```bash
# Production .env
AUTH_EXPIRY_WARN_HOURS=48  # 48h warning for auth expiry
```

### 2. Health Endpoints

#### `/health/auth` - Authentication Monitoring
- Reports authentication mode (WIF vs ADC vs SA)
- Shows token expiry and warns if <24h remaining
- Returns principal, project, quota project
- Status: ok/warn/error based on expiry threshold

#### `/health/proxy` - Proxy Connectivity
- Detects proxy mode: direct, backbone, rotating, or unknown
- Hits IP services twice to detect rotation
- Cross-checks with secondary service for validation
- Returns RTT metrics and stability assessment

#### `/health/llm` - End-to-End Validation  
- Executes real LLM call (~50 tokens) to verify routing
- Validates vantage policy (NONE/ALS_ONLY/PROXY_ONLY/ALS_PLUS_PROXY)
- Returns same metadata as [LLM_ROUTE] logs
- Tracks usage, duration, and grounding effectiveness

### 3. SLO Probes
- Add all three endpoints to uptime monitoring (1-5 min intervals)
- Track `rtt_ms` p95 to catch network regressions
- Monitor LLM health `duration_ms` for performance degradation

## 🚨 Alert Conditions

### Auth Mode/Expiry Alerts
```yaml
# Critical - Page immediately
- condition: health_auth_status == "error"
  severity: critical
  message: "ADC missing or expired - authentication failure"

# Warning - Rotate credentials soon  
- condition: health_auth_status == "warn" AND seconds_remaining < 14400  # 4 hours
  severity: warning
  message: "Auth expiring in < 4h - rotate credentials"

# Warning - Unexpected auth mode change
- condition: health_auth_mode != expected_mode
  severity: warning
  message: "Auth mode changed unexpectedly"
```

### Proxy Routing Alerts
```yaml
# Warning - Wrong proxy mode for job
- condition: health_proxy_mode_guess == "rotating" AND job_requires_backbone == true
  severity: warning
  message: "Rotating proxy detected but backbone required for 6000 tokens"

# Warning - Proxy connectivity issues
- condition: health_proxy_failures > 3 in last 10 minutes
  severity: warning
  message: "Proxy/egress connectivity issues detected"
```

### LLM Health Alerts
```yaml
# Critical - LLM endpoint failure
- condition: health_llm_status == "error"
  severity: critical
  message: "LLM health check failed - check vendor connectivity"

# Warning - Slow LLM response
- condition: health_llm_duration_ms > 10000  # 10 seconds
  severity: warning
  message: "LLM health check slow - potential performance degradation"

# Warning - Grounding not effective
- condition: health_llm_grounded == true AND grounded_effective == false
  severity: warning
  message: "Grounding requested but not effective"
```

## 📊 Dashboard Tiles

### Auth Tile
```json
{
  "auth_mode": "WIF-ImpersonatedSA",
  "principal": "svc-contestra@contestra-ai.iam",
  "seconds_remaining": 172800,
  "status": "ok"
}
```

### Proxy Tile
```json
{
  "mode_guess": "backbone",
  "proxy_uri": "http://user:***@proxy.webshare.io:80",
  "rtt_p95_ms": 250,
  "error_count_1h": 0
}
```

### LLM Tile
```json
{
  "vendor": "openai",
  "status": "ok",
  "duration_ms": 3784,
  "vantage_policy": "ALS_ONLY",
  "grounded_effective": false,
  "usage": {"input": 46, "output": 72}
}
```

## 🔍 Operational Notes

### Expected States

#### Development (WSL/Local)
- **Auth**: 
  - Before ADC: `status="error"`, `auth_mode="unknown"`
  - After ADC: `status="ok"`, `auth_mode="ADC-User"`
- **Proxy**: 
  - No proxy: `mode_guess="direct"`, IP stable
  - With proxy: `mode_guess="backbone"` for >2000 tokens

#### Production (WIF)
- **Auth**: 
  - Normal: `status="ok"`, `auth_mode="WIF-ImpersonatedSA"`
  - No expiry shown (WIF refreshes automatically)
- **Proxy**: 
  - Should be `backbone` for production workloads
  - Alert if `rotating` detected during long runs

### Verification Commands

```bash
# Check auth status
curl -s http://localhost:8000/health/auth | jq '.status, .auth_mode, .seconds_remaining'

# Check proxy mode (should be backbone for production)
curl -s http://localhost:8000/health/proxy | jq '.mode_guess, .match_stable'

# Full proxy test with timing
curl -s "http://localhost:8000/health/proxy?timeout_ms=5000&sleep_ms=800" | jq '.'

# LLM health check - OpenAI with US ALS
curl -s "http://localhost:8000/health/llm?vendor=openai&cc=US&max_tokens=50" | jq '.status, .duration_ms, .text_preview'

# LLM health check - Vertex with Germany ALS
curl -s "http://localhost:8000/health/llm?vendor=vertex&cc=DE&max_tokens=50" | jq '.status, .vantage_policy'

# LLM health check with grounding
curl -s "http://localhost:8000/health/llm?vendor=openai&grounded=true&max_tokens=50" | jq '.grounded_effective'
```

### Proxy Mode Requirements by Token Count
| Max Tokens | Required Mode | Reason |
|------------|---------------|---------|
| ≤2000 | rotating OK | Short responses complete quickly |
| >2000 | backbone required | Long responses need stable connection |
| 6000 (standard) | backbone required | Avoid mid-response IP rotation |

## 🎯 Integration Points

### 1. Prometheus Scrape Configuration
```yaml
scrape_configs:
  - job_name: 'contestra-app'
    scrape_interval: 15s
    static_configs:
      - targets: ['app:8000']
    metrics_path: /metrics
```

### 2. Prometheus Alert Rules
Alert rules are provided in `prometheus/contestra-alerts.yaml`:
```yaml
rule_files:
  - /etc/prometheus/contestra-alerts.yaml
```

Key alerts:
- **AuthTokenExpiringSoon**: Token expiry < 4 hours
- **ProxyModeRotatingDetected**: Rotating proxy when backbone required
- **OpenAIHighRateLimitRate**: 429 rate > 3% over 10 minutes

### 3. Grafana Dashboard Setup

#### Import Pre-Built Dashboard
Import the dashboard from `grafana/contestra-ops-dashboard.json`:
1. Go to Grafana → Dashboards → Import
2. Upload JSON file or paste contents
3. Select your Prometheus datasource
4. Dashboard includes:
   - Auth token seconds remaining & status
   - Proxy mode gauge & RTT table
   - LLM p95 latency by vendor/path/proxied
   - OpenAI 429 rate % over 10m
   - Throughput (requests/min) by vendor/path

#### Dashboard Variables
- `vendor`: Filter by openai/vertex (multi-select)
- `path`: Filter by genai/sdk/na (multi-select)  
- `proxied`: Filter by true/false (multi-select)
- Time range default: last 6h, refresh: 15s

#### Alert Annotations
Dashboard includes inline alert annotations that show when:
- Auth token expiring (<4h) - orange marker
- Rotating proxy detected - red marker
- OpenAI 429 > 3% - red marker

### 4. Looker Studio (Business Reporting)

#### BigQuery Views
Create views using SQL files in `looker/`:
```sql
-- Main view: looker/v_run_kpis.sql
CREATE OR REPLACE VIEW `project.dataset.v_run_kpis` AS ...

-- Daily aggregates: looker/v_run_kpis_daily.sql  
CREATE OR REPLACE VIEW `project.dataset.v_run_kpis_daily` AS ...
```

#### Looker Studio Configuration
1. Connect to BigQuery dataset
2. Use `v_run_kpis` for detailed reports
3. Use `v_run_kpis_daily` for performance dashboards
4. See `looker/field-mapping.md` for dimension/metric setup

#### Recommended Charts
- Time series: Requests by vendor/path
- Scorecard: Success rate %
- Time series: p95 latency (ms)
- Bar chart: Geographic split by country
- Table: Recent run details

### 5. Grafana Dashboard Panels (Manual Setup)
```sql
-- Auth expiring soon
SELECT seconds_remaining 
FROM health_auth 
WHERE seconds_remaining < 14400 
  AND status = 'warn'

-- Wrong proxy mode
SELECT mode_guess 
FROM health_proxy 
WHERE mode_guess = 'rotating' 
  AND job_label = 'production_6000_tokens'
```

### 6. PagerDuty Integration
```json
{
  "routing_key": "auth_critical",
  "event_action": "trigger",
  "payload": {
    "summary": "ADC authentication failed",
    "severity": "critical",
    "source": "/health/auth",
    "custom_details": {
      "status": "error",
      "auth_mode": "unknown"
    }
  }
}
```

## 📝 Runbook References

- **Auth expired**: See `VERTEX_AUTH_SETUP.md` for ADC/WIF setup
- **Proxy issues**: See `ADAPTER_OPS_PLAYBOOK.md` for proxy configuration
- **Rate limits**: Check `IMPORTANT_MODELS.md` for token limits

## 🔒 Security Notes

- Never log full proxy URIs (use masked format)
- Auth tokens should not be exposed in health checks
- Principal emails can be logged (they're not secrets)

---
**Last Updated**: 2025-08-27
**Status**: Ready for Production