#!/usr/bin/env python3
"""
Comprehensive test of longevity supplement brands prompt
Tests both models (OpenAI/Vertex), grounded/ungrounded, with/without ALS, US/DE regions
"""
import asyncio
import os
import sys
import json
import time
from datetime import datetime
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

# The prompt to test
PROMPT = "List the 10 most trusted longevity supplement brands"

class LongevityBrandsTestSuite:
    def __init__(self):
        self.adapter = UnifiedLLMAdapter()
        self.results = []
        self.start_time = time.time()
        
    async def run_test(self, vendor, model, grounded, vantage_policy, country, test_name):
        """Run a single test configuration"""
        print(f"\n{'='*60}")
        print(f"🧪 TEST: {test_name}")
        print(f"{'='*60}")
        print(f"Vendor: {vendor}")
        print(f"Model: {model}")
        print(f"Grounded: {grounded}")
        print(f"Policy: {vantage_policy}")
        print(f"Country: {country}")
        print(f"Prompt: {PROMPT}")
        
        request = LLMRequest(
            vendor=vendor,
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            temperature=0.3,  # Lower for consistency
            max_tokens=500,
            grounded=grounded,
            vantage_policy=vantage_policy,
            meta={"country": country} if country else None
        )
        
        try:
            start = time.perf_counter()
            response = await self.adapter.complete(request)
            latency_ms = int((time.perf_counter() - start) * 1000)
            
            print(f"\n✅ SUCCESS in {latency_ms}ms")
            print(f"\n📝 Response Preview:")
            print(response.content[:500] + "..." if len(response.content) > 500 else response.content)
            
            # Extract brand names if possible
            brands = self.extract_brands(response.content)
            if brands:
                print(f"\n🏷️ Brands detected ({len(brands)}):")
                for i, brand in enumerate(brands[:10], 1):
                    print(f"  {i}. {brand}")
            
            # Metadata analysis
            meta = response.metadata
            print(f"\n📊 Metadata:")
            print(f"  - grounded_effective: {meta.get('grounded_effective', 'N/A')}")
            print(f"  - web_grounded: {meta.get('web_grounded', 'N/A')}")
            print(f"  - tool_call_count: {meta.get('tool_call_count', 'N/A')}")
            print(f"  - Usage: {response.usage}")
            
            result = {
                "test": test_name,
                "vendor": vendor,
                "model": model,
                "grounded": grounded,
                "policy": vantage_policy,
                "country": country,
                "success": True,
                "latency_ms": latency_ms,
                "brands_count": len(brands),
                "brands": brands[:10],
                "grounded_effective": meta.get('grounded_effective', False),
                "usage": response.usage
            }
            
        except Exception as e:
            print(f"\n❌ FAILED: {e}")
            result = {
                "test": test_name,
                "vendor": vendor,
                "model": model,
                "grounded": grounded,
                "policy": vantage_policy,
                "country": country,
                "success": False,
                "error": str(e)
            }
        
        self.results.append(result)
        return result
    
    def extract_brands(self, content):
        """Try to extract brand names from the response"""
        brands = []
        lines = content.split('\n')
        
        for line in lines:
            # Look for numbered lists or bullet points
            line = line.strip()
            if not line:
                continue
                
            # Remove common prefixes
            for prefix in ['1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.',
                          '-', '*', '•', '**']:
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break
            
            # Remove markdown bold
            line = line.replace('**', '').strip()
            
            # Look for brand-like names (capitalized words)
            if line and line[0].isupper() and len(line) < 100:
                # Clean up common suffixes
                for suffix in [' -', ' –', ':', '(']:
                    if suffix in line:
                        line = line[:line.index(suffix)].strip()
                if line and line not in brands:
                    brands.append(line)
        
        return brands
    
    async def run_all_tests(self):
        """Run comprehensive test matrix"""
        print("\n" + "="*80)
        print("🔬 LONGEVITY SUPPLEMENT BRANDS - COMPREHENSIVE TEST SUITE")
        print("="*80)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Prompt: '{PROMPT}'")
        print("="*80)
        
        # Test matrix
        tests = [
            # OpenAI tests
            ("openai", "gpt-5", False, "NONE", None, "OpenAI Ungrounded - No ALS"),
            ("openai", "gpt-5", True, "NONE", None, "OpenAI Grounded - No ALS"),
            ("openai", "gpt-5", False, "ALS", "US", "OpenAI Ungrounded - ALS US"),
            ("openai", "gpt-5", True, "ALS", "US", "OpenAI Grounded - ALS US"),
            ("openai", "gpt-5", False, "ALS", "DE", "OpenAI Ungrounded - ALS DE"),
            ("openai", "gpt-5", True, "ALS", "DE", "OpenAI Grounded - ALS DE"),
            
            # Vertex tests
            ("vertex", "gemini-2.0-flash-exp", False, "NONE", None, "Vertex Ungrounded - No ALS"),
            ("vertex", "gemini-2.0-flash-exp", True, "NONE", None, "Vertex Grounded - No ALS"),
            ("vertex", "gemini-2.0-flash-exp", False, "ALS", "US", "Vertex Ungrounded - ALS US"),
            ("vertex", "gemini-2.0-flash-exp", True, "ALS", "US", "Vertex Grounded - ALS US"),
            ("vertex", "gemini-2.0-flash-exp", False, "ALS", "DE", "Vertex Ungrounded - ALS DE"),
            ("vertex", "gemini-2.0-flash-exp", True, "ALS", "DE", "Vertex Grounded - ALS DE"),
        ]
        
        print(f"\n📋 Running {len(tests)} test configurations...")
        
        for vendor, model, grounded, policy, country, name in tests:
            await self.run_test(vendor, model, grounded, policy, country, name)
            # Small delay between tests to avoid rate limits
            await asyncio.sleep(1)
        
        # Generate summary
        self.print_summary()
        self.save_results()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("📊 TEST SUMMARY")
        print("="*80)
        
        total = len(self.results)
        successful = sum(1 for r in self.results if r['success'])
        failed = total - successful
        
        print(f"\nTotal tests: {total}")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"Success rate: {successful/total*100:.1f}%")
        print(f"Total time: {int(time.time() - self.start_time)}s")
        
        # Analyze grounding effectiveness
        grounded_tests = [r for r in self.results if r.get('grounded') and r['success']]
        if grounded_tests:
            effective_count = sum(1 for r in grounded_tests if r.get('grounded_effective'))
            print(f"\nGrounding effectiveness: {effective_count}/{len(grounded_tests)} ({effective_count/len(grounded_tests)*100:.1f}%)")
        
        # Compare vendors
        print("\n🏭 By Vendor:")
        for vendor in ['openai', 'vertex']:
            vendor_results = [r for r in self.results if r['vendor'] == vendor]
            vendor_success = sum(1 for r in vendor_results if r['success'])
            if vendor_results:
                avg_latency = sum(r.get('latency_ms', 0) for r in vendor_results if r['success']) / max(1, vendor_success)
                print(f"  {vendor}: {vendor_success}/{len(vendor_results)} successful, avg latency: {int(avg_latency)}ms")
        
        # Compare policies
        print("\n📜 By Policy:")
        for policy in ['NONE', 'ALS']:
            policy_results = [r for r in self.results if r['policy'] == policy]
            policy_success = sum(1 for r in policy_results if r['success'])
            if policy_results:
                print(f"  {policy}: {policy_success}/{len(policy_results)} successful")
        
        # Brand consistency analysis
        print("\n🏷️ Brand Consistency:")
        all_brands = {}
        for r in self.results:
            if r['success'] and 'brands' in r:
                key = f"{r['vendor']}-{r['grounded']}"
                if key not in all_brands:
                    all_brands[key] = []
                all_brands[key].extend(r['brands'])
        
        for key, brands in all_brands.items():
            unique_brands = list(set(brands))
            print(f"  {key}: {len(unique_brands)} unique brands found")
            
            # Show top 5 most common
            from collections import Counter
            brand_counts = Counter(brands)
            top_brands = brand_counts.most_common(5)
            if top_brands:
                print(f"    Top brands: {', '.join([f'{b}({c})' for b, c in top_brands])}")
    
    def save_results(self):
        """Save detailed results to file"""
        filename = f"longevity_brands_results_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "prompt": PROMPT,
                "total_tests": len(self.results),
                "successful": sum(1 for r in self.results if r['success']),
                "total_time_seconds": int(time.time() - self.start_time),
                "results": self.results
            }, f, indent=2, default=str)
        print(f"\n💾 Detailed results saved to: {filename}")


if __name__ == "__main__":
    suite = LongevityBrandsTestSuite()
    asyncio.run(suite.run_all_tests())