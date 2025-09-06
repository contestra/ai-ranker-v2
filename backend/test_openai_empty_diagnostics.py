#!/usr/bin/env python3
"""Test OpenAI empty response diagnostics for grounded mode."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter

async def test_empty_diagnostics():
    adapter = UnifiedLLMAdapter()
    
    print("=" * 80)
    print("Testing OpenAI Empty Response Diagnostics")
    print("=" * 80)
    
    # Test with various provoker settings
    test_configs = [
        {
            "name": "Provoker Disabled",
            "env": {"OPENAI_PROVOKER_ENABLED": "false", "OPENAI_GROUNDED_TWO_STEP": "false"},
            "expected_fields": ["initial_empty_reason", "final_empty_reason"]
        },
        {
            "name": "Provoker Enabled (Default)",
            "env": {"OPENAI_PROVOKER_ENABLED": "true", "OPENAI_GROUNDED_TWO_STEP": "false"},
            "expected_fields": ["initial_tool_type", "retry_tool_type", "provoker_value"]
        },
        {
            "name": "Two-Step Synthesis Enabled",
            "env": {"OPENAI_PROVOKER_ENABLED": "true", "OPENAI_GROUNDED_TWO_STEP": "true"},
            "expected_fields": ["synthesis_step_used", "synthesis_tool_count"]
        }
    ]
    
    # Use a prompt that might trigger searches but no synthesis
    # (This simulates the problematic empty response scenario)
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is the latest research on quantum computing?"}],
        grounded=True,
        meta={"grounding_mode": "AUTO"},
        max_tokens=500,
        temperature=0.0
    )
    
    for config in test_configs:
        print(f"\n{config['name']}")
        print("-" * 60)
        
        # Set environment variables
        for key, value in config["env"].items():
            os.environ[key] = value
            print(f"  {key}={value}")
        
        try:
            response = await adapter.complete(request, session=None)
            
            print(f"\n✅ Success: {response.success}")
            print(f"Grounded Effective: {response.grounded_effective}")
            
            if response.metadata:
                print(f"\n📊 Diagnostic Metadata:")
                
                # Check for empty response diagnostics
                diagnostic_fields = [
                    "initial_empty_reason",
                    "initial_tool_type", 
                    "retry_tool_type",
                    "tool_type_changed",
                    "provoker_retry_used",
                    "provoker_value",
                    "provoker_no_content_reason",
                    "synthesis_step_used",
                    "synthesis_no_content_reason",
                    "final_empty_reason",
                    "empty_despite_tools"
                ]
                
                for field in diagnostic_fields:
                    if field in response.metadata:
                        value = response.metadata[field]
                        if field == "provoker_value" and value:
                            # Truncate long provoker text
                            value = value[:50] + "..."
                        print(f"  - {field}: {value}")
                
                # Standard grounding metadata
                print(f"\n📈 Grounding Metrics:")
                print(f"  - Tool calls: {response.metadata.get('tool_call_count', 0)}")
                print(f"  - Web tool type: {response.metadata.get('web_tool_type', 'N/A')}")
                print(f"  - Citations: {response.metadata.get('citation_count', 0)}")
                print(f"  - Text source: {response.metadata.get('text_source', 'N/A')}")
                
                # Check if we got the expected diagnostic fields
                print(f"\n✓ Expected fields present:")
                for field in config["expected_fields"]:
                    if field in response.metadata:
                        print(f"  - {field}: ✅")
                    else:
                        print(f"  - {field}: ❌ (missing)")
            
            if response.content:
                print(f"\n📝 Content preview: {response.content[:100]}...")
            else:
                print(f"\n⚠️ Empty content returned")
                
        except Exception as e:
            print(f"\n❌ Error: {str(e)[:200]}")
        
        print()

if __name__ == "__main__":
    asyncio.run(test_empty_diagnostics())