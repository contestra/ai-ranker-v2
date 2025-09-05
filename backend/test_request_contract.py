#!/usr/bin/env python3
"""Test the request contract helpers and documentation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest
from app.llm.request_contract import RequestHelper, get_grounding_mode, get_json_schema, supports_thinking

def test_request_contract():
    print("=" * 80)
    print("Testing Request Contract (Meta vs Metadata)")
    print("=" * 80)
    
    # Create a request with user config in meta
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
        meta={
            "grounding_mode": "REQUIRED",
            "json_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            "reasoning_effort": "high",
            "thinking_budget": 1000,
            "include_thoughts": True
        }
    )
    
    print("\n1. User Configuration (request.meta):")
    print("-" * 40)
    print(f"  grounding_mode: {RequestHelper.get_user_config(request, 'grounding_mode')}")
    print(f"  json_schema: {RequestHelper.get_user_config(request, 'json_schema')}")
    print(f"  reasoning_effort: {RequestHelper.get_user_config(request, 'reasoning_effort')}")
    print(f"  thinking_budget: {RequestHelper.get_user_config(request, 'thinking_budget')}")
    print(f"  include_thoughts: {RequestHelper.get_user_config(request, 'include_thoughts')}")
    
    # Simulate router adding metadata
    request.metadata = {
        "capabilities": {
            "supports_thinking_budget": True,
            "supports_reasoning_effort": True,
            "include_thoughts_allowed": True
        },
        "original_model": "gpt-4o",
        "thinking_budget_tokens": 1000,
        "router_pacing_delay": 500,
        "als_present": True,
        "als_country": "DE"
    }
    
    print("\n2. Router Internal State (request.metadata):")
    print("-" * 40)
    print(f"  original_model: {RequestHelper.get_router_state(request, 'original_model')}")
    print(f"  thinking_budget_tokens: {RequestHelper.get_router_state(request, 'thinking_budget_tokens')}")
    print(f"  router_pacing_delay: {RequestHelper.get_router_state(request, 'router_pacing_delay')}")
    print(f"  als_present: {RequestHelper.get_router_state(request, 'als_present')}")
    print(f"  als_country: {RequestHelper.get_router_state(request, 'als_country')}")
    
    print("\n3. Capabilities (request.metadata.capabilities):")
    print("-" * 40)
    print(f"  supports_thinking_budget: {RequestHelper.get_capability(request, 'supports_thinking_budget')}")
    print(f"  supports_reasoning_effort: {RequestHelper.get_capability(request, 'supports_reasoning_effort')}")
    print(f"  include_thoughts_allowed: {RequestHelper.get_capability(request, 'include_thoughts_allowed')}")
    
    print("\n4. Convenience Functions:")
    print("-" * 40)
    print(f"  get_grounding_mode(): {get_grounding_mode(request)}")
    print(f"  get_json_schema(): {get_json_schema(request)}")
    print(f"  supports_thinking(): {supports_thinking(request)}")
    
    print("\n5. Complex Config Getters:")
    print("-" * 40)
    print(f"  thinking_config: {RequestHelper.get_thinking_config(request)}")
    print(f"  reasoning_config: {RequestHelper.get_reasoning_config(request)}")
    
    print("\n" + "=" * 80)
    print("CONTRACT SUMMARY")
    print("=" * 80)
    print("✓ request.meta = User configuration (grounding_mode, json_schema, etc.)")
    print("✓ request.metadata = Router internal state (capabilities, als_*, etc.)")
    print("✓ Helpers provide consistent access patterns")
    print("✓ Prevents accidental field confusion")
    print("\nSee app/llm/request_contract.py for full documentation")

if __name__ == "__main__":
    test_request_contract()