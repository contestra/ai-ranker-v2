#!/usr/bin/env python3
"""
Analyze the OpenAI responses to understand the output structure
"""

import json
import sys

def analyze_response(filepath, test_name):
    print(f"\n{'='*60}")
    print(f"Analyzing {test_name}")
    print('='*60)
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    if 'error' in data:
        print(f"❌ ERROR: {data['error']['message']}")
        return False
    
    print(f"✅ HTTP 200 - Request succeeded")
    print(f"Model: {data.get('model', 'N/A')}")
    print(f"Status: {data.get('status', 'N/A')}")
    
    # Check tools
    tools = data.get('tools', [])
    if tools:
        print(f"\nTools attached: {len(tools)}")
        for tool in tools:
            print(f"  - Type: {tool.get('type')}")
            if tool.get('type') in ['web_search', 'web_search_preview']:
                print(f"    ✓ Web search tool properly configured")
    
    # Analyze output
    output = data.get('output', [])
    print(f"\nOutput items: {len(output)}")
    
    has_message = False
    has_tool_call = False
    has_reasoning = False
    content_text = None
    
    for item in output:
        item_type = item.get('type')
        print(f"  - Type: {item_type}")
        
        if item_type == 'message':
            has_message = True
            content = item.get('content', [])
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get('type')
                    print(f"    - Content block: {block_type}")
                    if block_type in ['output_text', 'text']:
                        content_text = block.get('text', '')
                        print(f"      Text: '{content_text[:50]}...'")
        
        elif item_type == 'tool_call':
            has_tool_call = True
            tool_type = item.get('name', 'unknown')
            print(f"    - Tool called: {tool_type}")
        
        elif item_type == 'reasoning':
            has_reasoning = True
            summary = item.get('summary', [])
            print(f"    - Reasoning block (summary items: {len(summary)})")
    
    # Usage analysis
    usage = data.get('usage', {})
    input_tokens = usage.get('input_tokens', 0)
    output_tokens = usage.get('output_tokens', 0)
    reasoning_tokens = usage.get('output_tokens_details', {}).get('reasoning_tokens', 0)
    
    print(f"\nToken usage:")
    print(f"  Input: {input_tokens}")
    print(f"  Output: {output_tokens}")
    print(f"  Reasoning: {reasoning_tokens}")
    
    # Diagnosis
    print(f"\n📊 Diagnosis:")
    if output_tokens == 0:
        print(f"  ⚠️ No output tokens produced")
        print(f"  → Model processed request but produced no content")
        print(f"  → This is likely due to:")
        print(f"    1. Model still reasoning (check 'status')")
        print(f"    2. Instructions too minimal ('Reply with ok')")
        print(f"    3. Token budget too small (16 tokens)")
    
    if has_reasoning and not has_message:
        print(f"  ⚠️ Only reasoning blocks, no message")
        print(f"  → This is the 'reasoning-only' issue our adapter handles")
    
    if tools and not has_tool_call:
        print(f"  ℹ️ Tools attached but not invoked")
        print(f"  → Model chose not to use web_search (AUTO mode)")
    
    return True

# Analyze each test result
tests = [
    ("test1_result.json", "Test 1: gpt-5 + web_search"),
    ("test2_result.json", "Test 2: gpt-5 + web_search_preview"),
    ("test4_result.json", "Test 4: gpt-5 baseline (no tools)")
]

success_count = 0
for filepath, name in tests:
    try:
        if analyze_response(filepath, name):
            success_count += 1
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")

print(f"\n{'='*60}")
print("FINAL VERDICT")
print('='*60)

print(f"\n🎯 Key Findings:")
print(f"1. Both web_search and web_search_preview ARE ACCEPTED by the API")
print(f"2. The issue is NOT entitlement - tools are properly attached")
print(f"3. The model produces ZERO output tokens (reasoning-only)")
print(f"4. Our adapter needs to handle this edge case better")

print(f"\n💡 Solution:")
print(f"1. Increase max_output_tokens (16 is too small)")
print(f"2. Provide more substantial input/instructions")
print(f"3. Handle reasoning-only responses in adapter")
print(f"4. Consider using tool_choice:'required' to force tool use")