#!/bin/bash
# Raw OpenAI API probe to test tool support outside of our adapter

echo "=================================================="
echo "OpenAI Raw API Probe - Testing Tool Support"
echo "=================================================="
echo ""

# Load environment
source .env

if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ OPENAI_API_KEY not set"
    exit 1
fi

echo "✓ API Key loaded"
echo ""

# Test 1: gpt-5 with web_search (NOT preview)
echo "[TEST 1] gpt-5 + web_search tool"
echo "----------------------------------"
echo "Request:"
echo '  model: "gpt-5"'
echo '  tools: [{"type":"web_search"}]'
echo ""

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": "test",
    "instructions": "Reply with ok",
    "tools": [{"type":"web_search"}],
    "tool_choice": "auto",
    "max_output_tokens": 16
  }' | python3 -m json.tool > test1_result.json 2>&1

if [ $? -eq 0 ] && ! grep -q "error" test1_result.json; then
    echo "✅ SUCCESS - gpt-5 supports web_search!"
    echo "Response saved to test1_result.json"
else
    echo "❌ FAILED"
    cat test1_result.json
fi
echo ""

# Test 2: gpt-5 with web_search_preview
echo "[TEST 2] gpt-5 + web_search_preview tool"
echo "------------------------------------------"
echo "Request:"
echo '  model: "gpt-5"'
echo '  tools: [{"type":"web_search_preview"}]'
echo ""

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": "test",
    "instructions": "Reply with ok",
    "tools": [{"type":"web_search_preview"}],
    "tool_choice": "auto",
    "max_output_tokens": 16
  }' | python3 -m json.tool > test2_result.json 2>&1

if [ $? -eq 0 ] && ! grep -q "error" test2_result.json; then
    echo "✅ SUCCESS - gpt-5 supports web_search_preview!"
    echo "Response saved to test2_result.json"
else
    echo "❌ FAILED"
    cat test2_result.json
fi
echo ""

# Test 3: gpt-5-chat-latest with web_search
echo "[TEST 3] gpt-5-chat-latest + web_search tool"
echo "----------------------------------------------"
echo "Request:"
echo '  model: "gpt-5-chat-latest"'
echo '  tools: [{"type":"web_search"}]'
echo ""

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5-chat-latest",
    "input": "test",
    "instructions": "Reply with ok",
    "tools": [{"type":"web_search"}],
    "tool_choice": "auto",
    "max_output_tokens": 16
  }' | python3 -m json.tool > test3_result.json 2>&1

if [ $? -eq 0 ] && ! grep -q "error" test3_result.json; then
    echo "✅ SUCCESS - gpt-5-chat-latest supports web_search!"
    echo "Response saved to test3_result.json"
else
    echo "❌ FAILED (Expected for chat variant)"
    cat test3_result.json
fi
echo ""

# Test 4: Try without any tools to verify basic connectivity
echo "[TEST 4] gpt-5 without tools (baseline)"
echo "-----------------------------------------"
echo "Request:"
echo '  model: "gpt-5"'
echo '  tools: none'
echo ""

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": "test",
    "instructions": "Reply with ok",
    "max_output_tokens": 16
  }' | python3 -m json.tool > test4_result.json 2>&1

if [ $? -eq 0 ] && ! grep -q "error" test4_result.json; then
    echo "✅ SUCCESS - Basic API call works"
    echo "Response saved to test4_result.json"
else
    echo "❌ FAILED - Even basic call failed"
    cat test4_result.json
fi
echo ""

echo "=================================================="
echo "SUMMARY"
echo "=================================================="
echo ""

# Analyze results
if [ -f test1_result.json ] && ! grep -q "error" test1_result.json 2>/dev/null; then
    echo "✅ gpt-5 + web_search = WORKS"
    echo "   → Adapter should use 'web_search' for gpt-5"
elif [ -f test2_result.json ] && ! grep -q "error" test2_result.json 2>/dev/null; then
    echo "✅ gpt-5 + web_search_preview = WORKS"
    echo "   → Adapter should use 'web_search_preview' for gpt-5"
else
    echo "❌ Neither tool variant works with gpt-5"
    echo "   → Check if different tool name or model name"
fi

echo ""
echo "Raw result files saved:"
echo "  - test1_result.json (gpt-5 + web_search)"
echo "  - test2_result.json (gpt-5 + web_search_preview)"
echo "  - test3_result.json (gpt-5-chat-latest + web_search)"
echo "  - test4_result.json (gpt-5 baseline)"