#!/usr/bin/env bash
set -euo pipefail

# Materialize WIF credentials at runtime (production only)
if [ -n "${WIF_CREDENTIALS_JSON:-}" ]; then
  install -d -m 0750 /etc/gcloud
  printf '%s' "$WIF_CREDENTIALS_JSON" > /etc/gcloud/wif-credentials.json
  chmod 0640 /etc/gcloud/wif-credentials.json
fi

# Start API
exec uvicorn app.main:app --host 0.0.0.0 --port 8000