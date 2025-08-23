#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
ORG="${ORG:-default}"

red() { printf "\033[31m%s\033[0m\n" "$*"; }
grn() { printf "\033[32m%s\033[0m\n" "$*"; }
ylw() { printf "\033[33m%s\033[0m\n" "$*"; }

curl_json() {
  # usage: curl_json METHOD URL BODY_JSON OUT_FILE
  local method="$1" url="$2" body="$3" out="$4"
  http_code=$(curl -sS -o "$out" -w "%{http_code}" -X "$method" "$url" \
    -H "Content-Type: application/json" \
    -H "X-Organization-Id: $ORG" \
    --data-binary "$body") || { red "curl failed"; cat "$out" || true; exit 1; }
  if [[ "$http_code" -lt 200 || "$http_code" -ge 300 ]]; then
    red "HTTP $http_code from $url"; cat "$out" || true; exit 1;
  fi
}

echo "== OpenAI Preflight =="
curl -sS "$API_BASE/ops/openai-preflight" | python3 -m json.tool || true

echo "== Create template (2+2) =="
REQ_TMPL=$(cat <<'JSON'
{
  "template_name": "Smoke OpenAI 2+2",
  "canonical": {
    "messages": [
      { "role": "user", "content": "What is 2+2?" }
    ],
    "vendor": "openai",
    "model": "gpt-5"
  }
}
JSON
)
mkdir -p .tmp && TMP=.tmp
curl_json POST "$API_BASE/v1/templates" "$REQ_TMPL" "$TMP/tpl.json"
python3 -m json.tool < "$TMP/tpl.json" || true
TID=$(python3 - "$TMP/tpl.json" <<'PY'
import sys, json
with open(sys.argv[1]) as f:
    d=json.load(f)
print(d.get("template_id") or d.get("id") or "")
PY
)
if [[ -z "$TID" ]]; then red "template_id not found"; cat "$TMP/tpl.json"; exit 1; fi
ylw "Template ID: $TID"

echo "== Run template (max_tokens=128) =="
RUN_REQ='{"max_tokens":128}'
curl_json POST "$API_BASE/v1/templates/$TID/run" "$RUN_REQ" "$TMP/run.json"
python3 -m json.tool < "$TMP/run.json" || true
CONTENT_LEN=$(python3 - "$TMP/run.json" <<'PY'
import sys, json
d=json.load(open(sys.argv[1]))
print(len((d.get("output") or d.get("content") or "").strip()))
PY
)
if [[ "$CONTENT_LEN" -eq 0 ]]; then red "❌ Empty content."; exit 2; fi
grn "✅ OpenAI smoke ok."
