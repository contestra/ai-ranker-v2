#!/usr/bin/env python3
"""Debug US ALS non-determinism"""
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

import os
os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

# Generate US ALS 5 times and show what's different
adapter = UnifiedLLMAdapter()

for i in range(5):
    request = LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": "Test"}],
        als_context={'country_code': 'US', 'locale': 'en-US'}
    )
    
    modified_request = adapter._apply_als(request)
    
    als_text = modified_request.metadata.get('als_block_text', '')
    als_sha = modified_request.metadata.get('als_block_sha256', '')
    variant_id = modified_request.metadata.get('als_variant_id')
    
    print(f"\n=== Run {i+1} ===")
    print(f"SHA256: {als_sha[:16]}...")
    print(f"Variant: {variant_id}")
    print(f"Length: {len(als_text)}")
    print(f"First 100 chars: {als_text[:100]}...")
    print(f"ALS Text:\n{als_text}")