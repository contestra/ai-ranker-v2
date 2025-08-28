#!/usr/bin/env python3
"""
Real-world adapter tests with actual API calls.
Tests both OpenAI and Vertex with grounded/ungrounded modes.
"""

import asyncio
import json
import os
import sys
import time
from typing import Dict, Any

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.types import LLMRequest, LLMResponse
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter

# Test prompts covering different scenarios
TEST_PROMPTS = {
    "simple_qa": {
        "system": "You are a helpful assistant.",
        "user": "What is the capital of France? Answer in one word."
    },
    "current_events": {
        "system": "You are a knowledgeable assistant with access to current information.",
        "user": "What are the latest developments in AI safety research as of 2024?"
    },
    "technical": {
        "system": "You are a technical expert.",
        "user": "Explain the difference between TCP and UDP protocols in networking."
    },
    "json_output": {
        "system": "You are a data formatter. Always respond with valid JSON.",
        "user": "List 3 programming languages with their key features. Format as JSON with 'languages' array."
    },
    "grounded_search": {
        "system": "You are a research assistant. Use web search to provide accurate, current information.",
        "user": "What is the current stock price of NVDA and its market cap? Search for the latest data."
    }
}

class AdapterTester:
    def __init__(self):
        self.openai_adapter = None
        self.vertex_adapter = None
        self.results = []
        
    async def setup(self):
        """Initialize adapters if API keys are available."""
        # Check OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                self.openai_adapter = OpenAIAdapter()
                print("✅ OpenAI adapter initialized")
            except Exception as e:
                print(f"❌ OpenAI adapter failed: {e}")
        else:
            print("⚠️  OPENAI_API_KEY not set - skipping OpenAI tests")
        
        # Check Vertex
        if os.getenv("GOOGLE_CLOUD_PROJECT"):
            try:
                self.vertex_adapter = VertexAdapter()
                print("✅ Vertex adapter initialized")
            except Exception as e:
                print(f"❌ Vertex adapter failed: {e}")
        else:
            print("⚠️  GOOGLE_CLOUD_PROJECT not set - skipping Vertex tests")
    
    async def test_adapter(self, adapter, vendor: str, prompt_key: str, grounded: bool, json_mode: bool):
        """Test a single adapter with given configuration."""
        prompt = TEST_PROMPTS[prompt_key]
        
        request = LLMRequest(
            vendor=vendor,
            model="gpt-5" if vendor == "openai" else "publishers/google/models/gemini-2.5-pro",
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]}
            ],
            grounded=grounded,
            json_mode=json_mode,
            max_tokens=500,
            temperature=0.3,
            meta={"grounding_mode": "AUTO"} if grounded else {}
        )
        
        test_name = f"{vendor}_{prompt_key}_{'grounded' if grounded else 'ungrounded'}_{'json' if json_mode else 'text'}"
        print(f"\n🔄 Testing: {test_name}")
        
        try:
            start = time.time()
            response = await adapter.complete(request, timeout=60)
            latency = time.time() - start
            
            result = {
                "test": test_name,
                "vendor": vendor,
                "prompt": prompt_key,
                "grounded": grounded,
                "json_mode": json_mode,
                "success": True,
                "latency_s": round(latency, 2),
                "response_len": len(response.content),
                "grounded_effective": response.metadata.get('grounded_effective') if hasattr(response, 'metadata') else None,
                "usage": response.usage if hasattr(response, 'usage') else {},
                "sample": response.content[:200] + "..." if len(response.content) > 200 else response.content
            }
            
            # Validate JSON if expected
            if json_mode:
                try:
                    json.loads(response.content)
                    result["valid_json"] = True
                except:
                    result["valid_json"] = False
            
            # Check metadata
            if hasattr(response, 'metadata'):
                result["metadata"] = {
                    "model": response.metadata.get("model"),
                    "grounded_effective": response.metadata.get("grounded_effective"),
                    "tool_call_count": response.metadata.get("tool_call_count", 0),
                    "two_step_used": response.metadata.get("two_step_used", False)
                }
            
            self.results.append(result)
            print(f"  ✅ Success in {latency:.2f}s")
            print(f"  📝 Response: {result['sample']}")
            if grounded:
                print(f"  🔍 Grounded effective: {result.get('grounded_effective', 'N/A')}")
            
        except Exception as e:
            self.results.append({
                "test": test_name,
                "vendor": vendor,
                "success": False,
                "error": str(e)[:200]
            })
            print(f"  ❌ Failed: {str(e)[:100]}")
    
    async def run_all_tests(self):
        """Run comprehensive test suite."""
        await self.setup()
        
        tests = []
        
        # OpenAI tests
        if self.openai_adapter:
            print("\n" + "="*60)
            print("OPENAI ADAPTER TESTS")
            print("="*60)
            
            # Ungrounded text
            tests.append(self.test_adapter(self.openai_adapter, "openai", "simple_qa", False, False))
            tests.append(self.test_adapter(self.openai_adapter, "openai", "technical", False, False))
            
            # Ungrounded JSON
            tests.append(self.test_adapter(self.openai_adapter, "openai", "json_output", False, True))
            
            # Grounded text (AUTO mode)
            tests.append(self.test_adapter(self.openai_adapter, "openai", "current_events", True, False))
            tests.append(self.test_adapter(self.openai_adapter, "openai", "grounded_search", True, False))
            
            # Grounded JSON
            tests.append(self.test_adapter(self.openai_adapter, "openai", "json_output", True, True))
        
        # Vertex tests
        if self.vertex_adapter:
            print("\n" + "="*60)
            print("VERTEX ADAPTER TESTS")
            print("="*60)
            
            # Ungrounded text
            tests.append(self.test_adapter(self.vertex_adapter, "vertex", "simple_qa", False, False))
            tests.append(self.test_adapter(self.vertex_adapter, "vertex", "technical", False, False))
            
            # Ungrounded JSON
            tests.append(self.test_adapter(self.vertex_adapter, "vertex", "json_output", False, True))
            
            # Grounded text (with new google_search field support)
            tests.append(self.test_adapter(self.vertex_adapter, "vertex", "current_events", True, False))
            tests.append(self.test_adapter(self.vertex_adapter, "vertex", "grounded_search", True, False))
            
            # Grounded JSON (two-step flow)
            tests.append(self.test_adapter(self.vertex_adapter, "vertex", "json_output", True, True))
        
        # Run all tests
        await asyncio.gather(*tests, return_exceptions=True)
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary."""
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        
        successful = [r for r in self.results if r.get("success")]
        failed = [r for r in self.results if not r.get("success")]
        
        print(f"\n✅ Successful: {len(successful)}/{len(self.results)}")
        print(f"❌ Failed: {len(failed)}/{len(self.results)}")
        
        if successful:
            print("\n📊 Performance Stats:")
            for vendor in ["openai", "vertex"]:
                vendor_results = [r for r in successful if r["vendor"] == vendor]
                if vendor_results:
                    avg_latency = sum(r["latency_s"] for r in vendor_results) / len(vendor_results)
                    print(f"  {vendor.upper()}:")
                    print(f"    - Avg latency: {avg_latency:.2f}s")
                    print(f"    - Tests passed: {len(vendor_results)}")
                    
                    grounded_results = [r for r in vendor_results if r.get("grounded")]
                    if grounded_results:
                        grounded_effective = sum(1 for r in grounded_results if r.get("grounded_effective"))
                        print(f"    - Grounding success: {grounded_effective}/{len(grounded_results)}")
                    
                    json_results = [r for r in vendor_results if r.get("json_mode")]
                    if json_results:
                        json_valid = sum(1 for r in json_results if r.get("valid_json"))
                        print(f"    - Valid JSON: {json_valid}/{len(json_results)}")
        
        if failed:
            print("\n⚠️  Failed Tests:")
            for r in failed:
                print(f"  - {r['test']}: {r.get('error', 'Unknown error')}")
        
        # Save results
        with open("adapter_test_results.json", "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print("\n💾 Full results saved to adapter_test_results.json")

async def main():
    """Run the test suite."""
    print("🚀 Starting Real Adapter Tests")
    print("================================")
    
    tester = AdapterTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())