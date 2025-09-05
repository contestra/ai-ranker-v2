#!/usr/bin/env python3
"""Test that Vertex grounded+JSON single-call still works after removing GoogleSearch FFC."""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the app module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Set required environment variables
os.environ["LLM_TIMEOUT_UN"] = "60"
os.environ["LLM_TIMEOUT_GR"] = "120"


async def test_grounded_json():
    """Test grounded+JSON single-call flow."""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter = UnifiedLLMAdapter()
    
    print("\n" + "="*80)
    print("VERTEX GROUNDED+JSON TEST")
    print("="*80 + "\n")
    
    # Define schema for structured output
    json_schema = {
        "name": "HealthSummary",
        "type": "object",
        "schema": {
            "type": "object",
            "properties": {
                "main_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Main health topics mentioned"
                },
                "has_citations": {
                    "type": "boolean",
                    "description": "Whether citations were found"
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of findings"
                }
            },
            "required": ["main_topics", "has_citations", "summary"]
        }
    }
    
    # Test both AUTO and REQUIRED modes
    for grounding_mode in ["AUTO", "REQUIRED"]:
        print(f"\n🔧 Testing grounding_mode={grounding_mode}")
        print("-" * 60)
        
        request = LLMRequest(
            vendor="vertex",
            model="gemini-2.5-pro",
            messages=[{
                "role": "user",
                "content": "What are the latest developments in AI healthcare? Provide a structured summary."
            }],
            grounded=True,
            max_tokens=800,
            temperature=0.7,
            meta={
                "json_schema": json_schema,
                "grounding_mode": grounding_mode
            }
        )
        
        try:
            start = datetime.now()
            response = await adapter.complete(request)
            elapsed = (datetime.now() - start).total_seconds()
            
            print(f"✅ Success: {response.success}")
            print(f"⏱️  Time: {elapsed:.2f}s")
            
            # Check content is valid JSON
            if response.content:
                try:
                    parsed = json.loads(response.content)
                    print(f"📋 Valid JSON: Yes")
                    print(f"📊 Structure:")
                    print(f"  - main_topics: {len(parsed.get('main_topics', []))} items")
                    print(f"  - has_citations: {parsed.get('has_citations', False)}")
                    print(f"  - summary length: {len(parsed.get('summary', ''))} chars")
                    
                    # Show first topic
                    if parsed.get('main_topics'):
                        print(f"  - First topic: {parsed['main_topics'][0][:50]}...")
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON: {e}")
                    print(f"Content: {response.content[:200]}...")
            else:
                print("❌ Empty content")
            
            # Check metadata
            if hasattr(response, 'metadata') and response.metadata:
                meta = response.metadata
                print(f"\n🔍 Metadata:")
                print(f"  - Tool calls: {meta.get('tool_call_count', 0)}")
                print(f"  - Grounding evidence: {meta.get('grounded_evidence_present', False)}")
                print(f"  - Grounding enforced: {meta.get('grounding_mode_enforced', 'N/A')}")
                print(f"  - JSON response: {meta.get('json_response', False)}")
                print(f"  - Anchored citations: {meta.get('anchored_citations_count', 0)}")
                print(f"  - Unlinked sources: {meta.get('unlinked_sources_count', 0)}")
                
                # For REQUIRED mode, verify it would fail if no grounding
                if grounding_mode == "REQUIRED" and not meta.get('grounded_evidence_present'):
                    print(f"  ⚠️ WARNING: REQUIRED mode but no grounding evidence!")
            
            # Check citations
            if hasattr(response, 'citations') and response.citations:
                print(f"\n📚 Citations: {len(response.citations)}")
                for i, cite in enumerate(response.citations[:2], 1):
                    print(f"  [{i}] {cite.get('title', 'No title')[:60]}...")
                    
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            if "NoneType" in str(e):
                print("  This is likely an issue with response processing")
            import traceback
            print("\nFull traceback:")
            traceback.print_exc()
    
    print("\n" + "="*80)
    print("Test complete. Grounded+JSON should work with emit_result forced via FFC.")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_grounded_json())