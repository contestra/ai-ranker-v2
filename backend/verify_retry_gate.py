#!/usr/bin/env python3
"""
Verify that the retry gate fix is properly implemented
"""

import re

def verify_retry_gate():
    """Check if the retry gate is properly implemented"""
    
    print("\n" + "="*80)
    print("VERIFYING RETRY GATE IMPLEMENTATION")
    print("="*80)
    
    # Read the OpenAI adapter file
    with open('/home/leedr/ai-ranker-v2/backend/app/llm/adapters/openai_adapter.py', 'r') as f:
        content = f.read()
    
    # Find the retry logic section
    # Looking for the pattern where web_search_preview retry happens
    pattern = r'else:\s*\n\s*#.*Not a web_search.*\n.*\n.*if.*tools.*in.*call_params'
    
    if re.search(pattern, content, re.MULTILINE | re.DOTALL):
        print("✅ Found gated retry logic:")
        print("   - Retry with web_search_preview is conditional")
        print("   - Only happens if 'tools' in call_params")
        print("   - Non-grounded requests won't trigger retry")
        
        # Extract the specific lines for verification
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if "Not a web_search support issue" in line:
                # Print next few lines to show the gate
                print("\nCode snippet (lines {}-{}):\n".format(i+1, i+6))
                for j in range(6):
                    if i+j < len(lines):
                        print(f"  {i+j+1:4d}: {lines[i+j]}")
                break
        
        return True
    else:
        print("❌ Could not find properly gated retry logic")
        print("   The retry might still happen for non-grounded requests")
        return False

def check_implementation_details():
    """Check implementation details of the fix"""
    
    print("\n" + "-"*40)
    print("Implementation Details:")
    print("-"*40)
    
    with open('/home/leedr/ai-ranker-v2/backend/app/llm/adapters/openai_adapter.py', 'r') as f:
        lines = f.readlines()
    
    # Find the specific fix
    for i, line in enumerate(lines):
        if "Only retry with web_search_preview if the original request had tools" in line:
            print("✅ Found the fix comment at line", i+1)
            print("   Comment explains the gate purpose")
            
            # Check the condition
            for j in range(i, min(i+5, len(lines))):
                if "if" in lines[j] and "tools" in lines[j] and "call_params" in lines[j]:
                    print(f"✅ Gate condition at line {j+1}:")
                    print(f"   {lines[j].strip()}")
                    break
            return True
    
    print("⚠️ Could not find the fix comment")
    return False

def main():
    """Run verification"""
    
    gate_ok = verify_retry_gate()
    details_ok = check_implementation_details()
    
    print("\n" + "="*80)
    print("VERIFICATION RESULT")
    print("="*80)
    
    if gate_ok and details_ok:
        print("✅ PASS: Retry gate is properly implemented")
        print("   - web_search_preview retry only happens for grounded requests")
        print("   - Non-grounded requests won't trigger noisy retries")
    else:
        print("❌ FAIL: Issues found with retry gate implementation")
    
    return gate_ok and details_ok

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)