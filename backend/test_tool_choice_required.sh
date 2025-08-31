#!/bin/bash
# Test if tool_choice:"required" works with gpt-5 + web_search

source .env

echo "=================================================="
echo "Testing tool_choice:required with gpt-5 + web_search"
echo "=================================================="
echo

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": [{"role":"user","content":[{"type":"input_text","text":"Give the official URL of the White House homepage."}]}],
    "tools": [{"type":"web_search"}],
    "tool_choice": "required",
    "max_output_tokens": 64
  }' | jq '.'

echo
echo "=================================================="
echo "If 200: tool_choice:required IS supported - keep it"
echo "If 400: tool_choice:required NOT supported - document and fail-closed"
echo "=================================================="