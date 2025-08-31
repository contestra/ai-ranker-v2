#!/bin/bash
# Test with a real grounding query that should trigger web search

echo "=================================================="
echo "Testing REAL Grounding with Proper Parameters"
echo "=================================================="
echo ""

source .env

# Test with a real question that needs grounding
echo "[TEST] gpt-5 + web_search with real query"
echo "-------------------------------------------"
echo "Model: gpt-5"
echo "Tool: web_search"
echo "Query: What's the latest news about AI?"
echo "Tokens: 1000 (proper budget)"
echo ""

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": "What is the latest news about AI today?",
    "instructions": "Search for recent AI news and provide a summary. You must produce a final message with the answer.",
    "tools": [{"type":"web_search"}],
    "tool_choice": "auto",
    "max_output_tokens": 1000,
    "text": {"verbosity": "medium"}
  }' > real_grounding_result.json 2>&1

if [ $? -eq 0 ]; then
    echo "✅ API call succeeded"
    
    # Check for tool calls
    if grep -q '"type":"tool_call"' real_grounding_result.json; then
        echo "✅ TOOL CALLS DETECTED - Web search was invoked!"
    else
        echo "⚠️ No tool calls detected"
    fi
    
    # Check for message output
    if grep -q '"type":"message"' real_grounding_result.json; then
        echo "✅ MESSAGE OUTPUT DETECTED"
    else
        echo "⚠️ No message output"
    fi
    
    # Check output tokens
    output_tokens=$(python3 -c "import json; d=json.load(open('real_grounding_result.json')); print(d.get('usage',{}).get('output_tokens',0))")
    echo "Output tokens: $output_tokens"
    
    if [ "$output_tokens" -gt 0 ]; then
        echo "✅ Model produced content!"
    else
        echo "❌ Still no output tokens"
    fi
    
    echo ""
    echo "Full response saved to: real_grounding_result.json"
    echo ""
    
    # Pretty print key parts
    echo "Response structure:"
    python3 -c "
import json
d = json.load(open('real_grounding_result.json'))
output = d.get('output', [])
for item in output:
    t = item.get('type')
    print(f'  - {t}')
    if t == 'tool_call':
        print(f'    Tool: {item.get(\"name\")}')
    elif t == 'message':
        content = item.get('content', [])
        for c in content:
            if isinstance(c, dict) and c.get('type') == 'output_text':
                text = c.get('text', '')[:100]
                print(f'    Text: {text}...')
"
    
else
    echo "❌ API call failed"
    cat real_grounding_result.json
fi