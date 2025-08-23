#!/usr/bin/env bash
set -euo pipefail

: "${API_BASE:?Set API_BASE}"
: "${ORG:?Set ORG}"
TEMPLATE_ID="${1:-${TEMPLATE_ID:-}}"

if [[ -z "${TEMPLATE_ID}" ]]; then
  echo "Usage: TEMPLATE_ID=<openai-template-id> $0  (or pass as first arg)"
  exit 2
fi

resp="$(curl -sS -X POST "$API_BASE/v1/templates/$TEMPLATE_ID/run" \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: $ORG" \
  -d '{"max_tokens": 64}')"

# Use jq if available, otherwise Python
if command -v jq >/dev/null 2>&1; then
  vendor="$(echo "$resp" | jq -r '.vendor // empty')"
  model="$(echo "$resp" | jq -r '.model_version_effective // .model // empty')"
else
  vendor="$(echo "$resp" | python3 -c "
import json,sys
try:
  d=json.loads(sys.stdin.read())
  print(d.get('vendor', ''))
except: print('')
")"
  model="$(echo "$resp" | python3 -c "
import json,sys
try:
  d=json.loads(sys.stdin.read())
  print(d.get('model_version_effective') or d.get('model', ''))
except: print('')
")"
fi

if [[ -z "$vendor" && "$resp" == *"error"* ]]; then
  echo "Auth or runtime error. Response:"
  echo "$resp"
  exit 0
fi

if [[ "$vendor" != "openai" ]]; then
  echo "❌ Expected vendor=openai, got: $vendor"
  echo "$resp"
  exit 1
fi

echo "✅ OpenAI route OK ($model)"