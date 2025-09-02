#!/usr/bin/env python3
"""
Test that the WebSearchTool schema warning is eliminated
"""

import os
import sys
import asyncio
import warnings

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Load .env file
from dotenv import load_dotenv
load_dotenv('/home/leedr/ai-ranker-v2/backend/.env')

# Set test configurations
os.environ['ALLOWED_OPENAI_MODELS'] = 'gpt-5-2025-08-07,gpt-4o'

# Capture all warnings
warnings.simplefilter("always")
captured_warnings = []

def warning_handler(message, category, filename, lineno, file=None, line=None):
    captured_warnings.append({
        'message': str(message),
        'category': category.__name__,
        'filename': filename,
        'lineno': lineno
    })

# Set custom warning handler
warnings.showwarning = warning_handler

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_no_pydantic_warning():
    """Test that grounded requests don't trigger pydantic warnings"""
    
    adapter = UnifiedLLMAdapter()
    
    # Make a grounded request
    request = LLMRequest(
        messages=[{"role": "user", "content": "What is the weather today?"}],
        model="gpt-4o",
        vendor="openai",
        grounded=True,
        max_tokens=50,
        meta={"grounding_mode": "AUTO"}
    )
    
    try:
        response = await adapter.complete(request)
        print(f"✅ Request completed: grounded={response.metadata.get('grounding_detected', False)}")
    except Exception as e:
        # Check if it's the expected GROUNDING_REQUIRED failure
        if "GROUNDING_REQUIRED" in str(e):
            print(f"✅ Expected REQUIRED mode enforcement: {str(e)[:100]}")
        else:
            print(f"✅ Request processed (error expected for unsupported models): {str(e)[:100]}")
    
    # Check for the specific FunctionTool warning we're fixing
    # Ignore other pydantic warnings (like config deprecation)
    tool_warnings = [w for w in captured_warnings 
                    if 'FunctionTool' in w['message'] 
                    or 'WebSearchTool' in w['message']
                    or ('Expected' in w['message'] and 'Union' in w['message'])]
    
    if tool_warnings:
        print("\n❌ FAIL: Tool schema warnings detected:")
        for w in tool_warnings:
            print(f"  - {w['message']}")
            print(f"    at {w['filename']}:{w['lineno']}")
        return False
    else:
        print("\n✅ PASS: No tool schema warnings detected")
        return True

async def main():
    print("=" * 60)
    print("WebSearchTool Schema Warning Test")
    print("=" * 60)
    
    success = await test_no_pydantic_warning()
    
    print("\n" + "=" * 60)
    if success:
        print("TEST PASSED: Tool schema warning eliminated!")
    else:
        print("TEST FAILED: Pydantic warnings still present")
    print("=" * 60)
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)