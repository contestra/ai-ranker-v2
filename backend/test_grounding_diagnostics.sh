#!/bin/bash
# Diagnostic probes to distinguish empty results from not supported

echo "=================================================="
echo "OpenAI Grounding Diagnostics - Empty vs Unsupported"
echo "=================================================="
echo ""

source .env

# Test A: Query that MUST have results (White House)
echo "[TEST A] Query with guaranteed results"
echo "---------------------------------------"
echo "Query: Official White House homepage URL"
echo "Expected: Should return results"
echo ""

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": "As of 2025-08-31, give the official URL of the White House homepage.",
    "instructions": "Search for the White House official website and provide its URL. You must produce a final message with the answer.",
    "tools": [{"type":"web_search"}],
    "tool_choice": "auto",
    "max_output_tokens": 500,
    "text": {"verbosity": "medium"}
  }' > test_a_whitehouse.json 2>&1

echo "Analyzing Test A..."
python3 -c "
import json
try:
    d = json.load(open('test_a_whitehouse.json'))
    
    # Count web_search_calls
    calls = [x for x in d.get('output', []) if x.get('type') == 'web_search_call']
    print(f'  Web search calls: {len(calls)}')
    
    # Count results
    total_results = 0
    for call in calls:
        results = call.get('results', [])
        total_results += len(results)
        if results:
            print(f'  Query: {call.get(\"query\", \"N/A\")}')
            print(f'  Results found: {len(results)}')
            for r in results[:2]:
                print(f'    - {r.get(\"title\", \"N/A\")}: {r.get(\"url\", \"N/A\")[:50]}')
    
    if len(calls) > 0 and total_results == 0:
        print('  ❌ EMPTY RESULTS - Tool invoked but returned nothing')
    elif len(calls) > 0 and total_results > 0:
        print('  ✅ RESULTS FOUND - Tool working correctly')
    else:
        print('  ⚠️ No tool calls detected')
        
except Exception as e:
    print(f'  Error: {e}')
"
echo ""

# Test B: Query about recent news (BBC)
echo "[TEST B] Query about current news"
echo "----------------------------------"
echo "Query: BBC top story with source URL"
echo "Expected: Should attempt search"
echo ""

curl -s https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": "As of 2025-08-31, list one official source URL for todays top story on the BBC homepage.",
    "instructions": "Search for current BBC news and provide a source URL. You must produce a final message with the answer.",
    "tools": [{"type":"web_search"}],
    "tool_choice": "auto",
    "max_output_tokens": 500,
    "text": {"verbosity": "medium"}
  }' > test_b_bbc.json 2>&1

echo "Analyzing Test B..."
python3 -c "
import json
try:
    d = json.load(open('test_b_bbc.json'))
    
    # Count web_search_calls
    calls = [x for x in d.get('output', []) if x.get('type') == 'web_search_call']
    print(f'  Web search calls: {len(calls)}')
    
    # Count results
    total_results = 0
    for call in calls:
        results = call.get('results', [])
        total_results += len(results)
        if results:
            print(f'  Query: {call.get(\"query\", \"N/A\")}')
            print(f'  Results found: {len(results)}')
    
    if len(calls) > 0 and total_results == 0:
        print('  ❌ EMPTY RESULTS - Tool invoked but returned nothing')
    elif len(calls) > 0 and total_results > 0:
        print('  ✅ RESULTS FOUND - Tool working correctly')
    else:
        print('  ⚠️ No tool calls detected')
        
except Exception as e:
    print(f'  Error: {e}')
"
echo ""

# Test C: Check for message output
echo "[TEST C] Check for final message output"
echo "----------------------------------------"
echo ""

echo "Test A (White House) output structure:"
python3 -c "
import json
try:
    d = json.load(open('test_a_whitehouse.json'))
    output_types = [x.get('type') for x in d.get('output', [])]
    print(f'  Output types: {output_types}')
    
    # Check for message
    messages = [x for x in d.get('output', []) if x.get('type') == 'message']
    if messages:
        print('  ✅ Message output found')
        for msg in messages:
            content = msg.get('content', [])
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'output_text':
                    text = c.get('text', '')[:100]
                    print(f'    Text: {text}...')
    else:
        print('  ❌ No message output - only reasoning')
        
except Exception as e:
    print(f'  Error: {e}')
"

echo ""
echo "=================================================="
echo "DIAGNOSIS SUMMARY"
echo "=================================================="
echo ""

# Final analysis
python3 -c "
import json

test_a = json.load(open('test_a_whitehouse.json'))
test_b = json.load(open('test_b_bbc.json'))

a_calls = len([x for x in test_a.get('output', []) if x.get('type') == 'web_search_call'])
b_calls = len([x for x in test_b.get('output', []) if x.get('type') == 'web_search_call'])

a_results = sum(len(x.get('results', [])) for x in test_a.get('output', []) if x.get('type') == 'web_search_call')
b_results = sum(len(x.get('results', [])) for x in test_b.get('output', []) if x.get('type') == 'web_search_call')

print('📊 Tool Invocation:')
print(f'  Test A: {a_calls} calls, {a_results} results')
print(f'  Test B: {b_calls} calls, {b_results} results')
print()

if a_calls > 0 or b_calls > 0:
    print('✅ web_search tool IS SUPPORTED')
    print('   The model can invoke the tool')
    
    if a_results == 0 and b_results == 0:
        print()
        print('❌ BUT: All searches return EMPTY RESULTS')
        print('   This is NOT an entitlement issue')
        print('   This is an EMPTY RETRIEVAL issue')
        print()
        print('🔧 Adapter should:')
        print('   - Set grounding_attempted = true')
        print('   - Set grounded_effective = false')
        print('   - Set why_not_grounded = \"web_search_empty_results\"')
        print('   - REQUIRED mode: fail with GROUNDING_EMPTY_RESULTS')
    elif a_results > 0 or b_results > 0:
        print()
        print('✅ Search results ARE being returned')
        print('   The tool is fully functional')
else:
    print('❌ No tool invocations detected')
    print('   Check if tool_choice:required is working')
"
echo ""
echo "Raw results saved:"
echo "  - test_a_whitehouse.json"
echo "  - test_b_bbc.json"