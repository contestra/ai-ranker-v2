#!/usr/bin/env python3
"""Test that ALS is actually being applied to messages"""
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

import os
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

adapter = UnifiedLLMAdapter()

# Test US ALS
request = LLMRequest(
    vendor="openai",
    model="gpt-5",
    messages=[{"role": "user", "content": "What is 2+2?"}],
    als_context={'country_code': 'US', 'locale': 'en-US'}
)

print("Original message:")
print(request.messages[0]['content'])
print("\n" + "="*50)

# Apply ALS
modified_request = adapter._apply_als(request)

print("\nModified message (with ALS):")
print(modified_request.messages[0]['content'][:300] + "...")

print("\n" + "="*50)
print("\nALS Metadata:")
for key, value in modified_request.metadata.items():
    if 'als' in key:
        print(f"  {key}: {value}")

# Check if ALS was actually prepended
if modified_request.messages[0]['content'].startswith("Ambient Context"):
    print("\n✅ ALS successfully prepended to message")
else:
    print("\n❌ ALS not found in message!")