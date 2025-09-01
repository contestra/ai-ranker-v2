#!/usr/bin/env python3
"""
Longevity E2E Validation Test
Verifies citation extraction fixes work end-to-end for MVP deployment.

MVP Requirements:
1. Grounded → JSON two-step: anchored_citations ≥ 1 in Step-1
2. Step-2 purity: two_step_used=true, step2_tools_invoked=false
3. Ungrounded: non-empty output, retry_max_tokens ≥ first_attempt_max_tokens
4. Baseline citations_shape_set distribution recorded
"""

import os
import sys
import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter
from app.llm.types import LLMRequest

# Test prompts designed to trigger grounding and citations
TEST_PROMPTS = [
    {
        "id": "longevity_brands",
        "content": "List the most trusted longevity supplement brands with scientific backing. Include specific products and research citations.",
        "expected_grounding": True,
        "expected_citations": True,
    },
    {
        "id": "climate_data",
        "content": "What are the latest 2024 global temperature anomalies and climate change statistics? Cite authoritative sources.",
        "expected_grounding": True,
        "expected_citations": True,
    },
    {
        "id": "tech_news",
        "content": "What are the most recent AI breakthroughs in December 2024? Include links to announcements.",
        "expected_grounding": True,
        "expected_citations": True,
    },
    {
        "id": "creative_story",
        "content": "Write a creative short story about a robot learning to paint. Make it entirely fictional.",
        "expected_grounding": False,
        "expected_citations": False,
    },
]

class LongevityValidator:
    def __init__(self):
        self.results = []
        self.summary = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "citation_shapes": {},
            "grounding_stats": {},
        }
        
    def extract_metadata(self, response: Any) -> Dict[str, Any]:
        """Extract all relevant metadata from response."""
        metadata = {}
        
        # Handle different response types
        if hasattr(response, '__dict__'):
            resp_dict = response.__dict__
        elif isinstance(response, dict):
            resp_dict = response
        else:
            resp_dict = {}
            
        # Extract core metrics
        metadata['grounded_effective'] = resp_dict.get('grounded_effective', False)
        metadata['tool_call_count'] = resp_dict.get('tool_call_count', 0)
        metadata['anchored_citations_count'] = resp_dict.get('anchored_citations_count', 0)
        metadata['unlinked_sources_count'] = resp_dict.get('unlinked_sources_count', 0)
        
        # Extract shape distribution
        shapes = resp_dict.get('citations_shape_set', [])
        if isinstance(shapes, list):
            metadata['citations_shape_set'] = shapes
        elif isinstance(shapes, str):
            metadata['citations_shape_set'] = [shapes]
        else:
            metadata['citations_shape_set'] = []
            
        # Two-step metadata
        metadata['two_step_used'] = resp_dict.get('two_step_used', False)
        metadata['step2_tools_invoked'] = resp_dict.get('step2_tools_invoked', False)
        metadata['step2_source_ref'] = resp_dict.get('step2_source_ref', None)
        
        # Retry metadata
        metadata['retry_max_tokens'] = resp_dict.get('retry_max_tokens', 0)
        metadata['first_attempt_max_tokens'] = resp_dict.get('first_attempt_max_tokens', 0)
        metadata['max_tokens_used'] = resp_dict.get('max_tokens_used', 0)
        
        # Failure analysis
        metadata['why_not_grounded'] = resp_dict.get('why_not_grounded', '')
        
        # Extract text output
        if hasattr(response, 'text'):
            metadata['output_text'] = response.text[:500]
        elif hasattr(response, 'output_text'):
            metadata['output_text'] = response.output_text[:500]
        elif isinstance(response, dict) and 'text' in response:
            metadata['output_text'] = response['text'][:500]
        else:
            metadata['output_text'] = str(response)[:500]
            
        # Extract usage
        usage = resp_dict.get('usage', {})
        if hasattr(response, 'usage'):
            usage = response.usage if hasattr(response.usage, '__dict__') else usage
        metadata['input_tokens'] = usage.get('input_tokens', 0) if isinstance(usage, dict) else 0
        metadata['output_tokens'] = usage.get('output_tokens', 0) if isinstance(usage, dict) else 0
        
        return metadata
        
    def validate_grounded_response(self, metadata: Dict[str, Any], prompt_id: str) -> List[str]:
        """Validate grounded response requirements."""
        failures = []
        
        # Check anchored citations requirement
        if metadata['grounded_effective'] and metadata['tool_call_count'] > 0:
            if metadata['anchored_citations_count'] < 1:
                failures.append(f"FAIL: {prompt_id} - Grounded with {metadata['tool_call_count']} tools but 0 anchored citations")
                
        # Check two-step purity (Gemini specific)
        if metadata['two_step_used']:
            if metadata['step2_tools_invoked']:
                failures.append(f"FAIL: {prompt_id} - Step 2 invoked tools (should be pure reshape)")
            if not metadata['step2_source_ref']:
                failures.append(f"WARN: {prompt_id} - Step 2 missing source reference")
                
        return failures
        
    def validate_ungrounded_response(self, metadata: Dict[str, Any], prompt_id: str) -> List[str]:
        """Validate ungrounded response requirements."""
        failures = []
        
        # Check output not empty
        if not metadata['output_text'] or len(metadata['output_text'].strip()) < 10:
            failures.append(f"FAIL: {prompt_id} - Ungrounded produced empty response")
            
        # Check retry token budget
        if metadata['retry_max_tokens'] > 0:  # Only if retry was attempted
            if metadata['retry_max_tokens'] < metadata['first_attempt_max_tokens']:
                failures.append(f"FAIL: {prompt_id} - Retry tokens ({metadata['retry_max_tokens']}) < first attempt ({metadata['first_attempt_max_tokens']})")
                
        return failures
        
    async def run_test(self, vendor: str, model: str, prompt: Dict, grounded: bool, timeout: int) -> Dict[str, Any]:
        """Run a single test case."""
        test_id = f"{vendor}_{model}_{prompt['id']}_gr{grounded}"
        
        req = LLMRequest(
            vendor=vendor,
            model=model,
            grounded=grounded,
            json_mode=False,
            messages=[{"role": "user", "content": prompt['content']}],
            temperature=0.2,
            max_tokens=4000,
        )
        
        t0 = time.perf_counter()
        result = {
            "test_id": test_id,
            "vendor": vendor,
            "model": model,
            "prompt_id": prompt['id'],
            "grounded_requested": grounded,
            "timestamp": datetime.now().isoformat(),
        }
        
        try:
            if vendor == "openai":
                adapter = OpenAIAdapter()
            else:
                adapter = VertexAdapter()
                
            resp = await adapter.complete(req, timeout=timeout)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            
            metadata = self.extract_metadata(resp)
            result.update({
                "status": "success",
                "latency_ms": latency_ms,
                **metadata
            })
            
            # Validate based on grounding mode
            if grounded:
                failures = self.validate_grounded_response(metadata, test_id)
            else:
                failures = self.validate_ungrounded_response(metadata, test_id)
                
            result["validation_failures"] = failures
            result["validation_passed"] = len(failures) == 0
            
        except Exception as e:
            result.update({
                "status": "error",
                "error": str(e),
                "validation_passed": False,
                "validation_failures": [f"ERROR: {test_id} - {str(e)}"]
            })
            
        return result
        
    async def run_validation_suite(self):
        """Run the complete validation suite."""
        print("\n" + "="*80)
        print("LONGEVITY E2E VALIDATION TEST - Citation Extraction MVP")
        print("="*80)
        print(f"Started: {datetime.now().isoformat()}\n")
        
        # Configuration
        t_un = int(os.getenv("LLM_TIMEOUT_UN", "60"))
        t_gr = int(os.getenv("LLM_TIMEOUT_GR", "180"))
        model_openai = os.getenv("TEST_OPENAI_MODEL", "gpt-5-chat-latest")
        model_vertex = os.getenv("TEST_VERTEX_MODEL", "publishers/google/models/gemini-2.5-pro")
        
        # Build test matrix
        test_cases = []
        for prompt in TEST_PROMPTS:
            # OpenAI tests
            if prompt['expected_grounding']:
                test_cases.append(("openai", model_openai, prompt, True, t_gr))
            test_cases.append(("openai", model_openai, prompt, False, t_un))
            
            # Vertex tests
            if prompt['expected_grounding']:
                test_cases.append(("vertex", model_vertex, prompt, True, t_gr))
            test_cases.append(("vertex", model_vertex, prompt, False, t_un))
            
        print(f"Running {len(test_cases)} test cases...\n")
        
        # Run tests in parallel batches to avoid overwhelming the APIs
        batch_size = 4
        all_results = []
        
        for i in range(0, len(test_cases), batch_size):
            batch = test_cases[i:i+batch_size]
            print(f"Running batch {i//batch_size + 1}/{(len(test_cases) + batch_size - 1)//batch_size}...")
            
            batch_results = await asyncio.gather(
                *[self.run_test(*tc) for tc in batch],
                return_exceptions=True
            )
            
            for result in batch_results:
                if isinstance(result, Exception):
                    print(f"  ✗ Batch exception: {result}")
                else:
                    all_results.append(result)
                    status_icon = "✓" if result.get("validation_passed") else "✗"
                    print(f"  {status_icon} {result['test_id']}: {result.get('status')}")
                    
            # Small delay between batches
            await asyncio.sleep(2)
            
        self.results = all_results
        self.generate_summary()
        
    def generate_summary(self):
        """Generate validation summary."""
        print("\n" + "="*80)
        print("VALIDATION SUMMARY")
        print("="*80)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get("validation_passed"))
        failed = total - passed
        
        self.summary.update({
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
        })
        
        print(f"\nOverall: {passed}/{total} passed ({self.summary['pass_rate']:.1f}%)")
        
        # Analyze grounded calls
        grounded_results = [r for r in self.results if r.get("grounded_effective")]
        if grounded_results:
            anchored_rate = sum(1 for r in grounded_results if r.get("anchored_citations_count", 0) > 0) / len(grounded_results) * 100
            avg_anchored = sum(r.get("anchored_citations_count", 0) for r in grounded_results) / len(grounded_results)
            print(f"\nGrounded Calls ({len(grounded_results)} total):")
            print(f"  - Anchored citation rate: {anchored_rate:.1f}%")
            print(f"  - Avg anchored citations: {avg_anchored:.1f}")
            
            # Check critical metric: tools>0 & anchored==0
            critical_failures = [r for r in grounded_results 
                                if r.get("tool_call_count", 0) > 0 
                                and r.get("anchored_citations_count", 0) == 0]
            if critical_failures:
                critical_rate = len(critical_failures) / len(grounded_results) * 100
                print(f"  - ⚠️  CRITICAL: Tools>0 & Anchored==0 rate: {critical_rate:.1f}% ({len(critical_failures)} cases)")
                for cf in critical_failures[:3]:  # Show first 3
                    print(f"      {cf['test_id']}")
                    
        # Analyze citation shapes
        all_shapes = []
        for r in self.results:
            shapes = r.get("citations_shape_set", [])
            all_shapes.extend(shapes if isinstance(shapes, list) else [shapes])
            
        if all_shapes:
            from collections import Counter
            shape_counts = Counter(all_shapes)
            print(f"\nCitation Shapes Distribution:")
            for shape, count in shape_counts.most_common():
                print(f"  - {shape}: {count} ({count/len(all_shapes)*100:.1f}%)")
                
        # Analyze two-step usage (Vertex specific)
        vertex_results = [r for r in self.results if r.get("vendor") == "vertex"]
        two_step_results = [r for r in vertex_results if r.get("two_step_used")]
        if two_step_results:
            print(f"\nVertex Two-Step Analysis ({len(two_step_results)} cases):")
            step2_pure = sum(1 for r in two_step_results if not r.get("step2_tools_invoked"))
            print(f"  - Step 2 purity rate: {step2_pure}/{len(two_step_results)} ({step2_pure/len(two_step_results)*100:.1f}%)")
            
        # Show failures
        failed_results = [r for r in self.results if not r.get("validation_passed")]
        if failed_results:
            print(f"\n⚠️  Validation Failures ({len(failed_results)} total):")
            for r in failed_results[:5]:  # Show first 5
                print(f"\n  {r['test_id']}:")
                for failure in r.get("validation_failures", [])[:2]:  # Show first 2 failures per test
                    print(f"    - {failure}")
                    
        # MVP Go/No-Go Decision
        print("\n" + "="*80)
        print("MVP GO/NO-GO DECISION")
        print("="*80)
        
        go_decision = True
        decision_reasons = []
        
        # Check critical thresholds
        if grounded_results:
            critical_rate = len([r for r in grounded_results 
                                if r.get("tool_call_count", 0) > 0 
                                and r.get("anchored_citations_count", 0) == 0]) / len(grounded_results) * 100
            if critical_rate > 2:
                go_decision = False
                decision_reasons.append(f"Tools>0 & Anchored==0 rate ({critical_rate:.1f}%) exceeds 2% threshold")
                
            anchored_rate = sum(1 for r in grounded_results if r.get("anchored_citations_count", 0) > 0) / len(grounded_results) * 100
            if anchored_rate < 70:
                go_decision = False
                decision_reasons.append(f"Anchored citation rate ({anchored_rate:.1f}%) below 70% threshold")
                
        if self.summary['pass_rate'] < 80:
            go_decision = False
            decision_reasons.append(f"Overall pass rate ({self.summary['pass_rate']:.1f}%) below 80% threshold")
            
        if go_decision:
            print("✅ GO - All MVP criteria met")
        else:
            print("❌ NO-GO - MVP criteria not met:")
            for reason in decision_reasons:
                print(f"  - {reason}")
                
        # Save results
        output_file = f"longevity_e2e_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "summary": self.summary,
                "results": self.results,
                "decision": {
                    "go": go_decision,
                    "reasons": decision_reasons
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2, default=str)
            
        print(f"\nResults saved to: {output_file}")
        
async def main():
    validator = LongevityValidator()
    await validator.run_validation_suite()
    
if __name__ == "__main__":
    asyncio.run(main())