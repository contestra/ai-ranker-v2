#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"

echo "== Preflight =="
curl -s "${API_BASE}/preflight/vertex" | jq .

echo "== Simple generate =="
curl -s -X POST "${API_BASE}/v1/vertex/generate" \
  -H "Content-Type: application/json" \
  -d '{"model":"publishers/google/models/gemini-2.5-pro","prompt":"Say PING.","max_output_tokens":64}' | jq .

# Optional: local-only SA key expiry visibility (requires gcloud & SA email env)
if [ -n "${SA_EMAIL:-}" ]; then
  echo "== SA key metadata (local only) =="
  gcloud iam service-accounts keys list \
    --iam-account="$SA_EMAIL" \
    --format="table(name,validAfterTime,validBeforeTime)"
fi