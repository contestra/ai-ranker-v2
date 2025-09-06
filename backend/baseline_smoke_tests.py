#!/usr/bin/env python3
"""Baseline smoke tests for adapter telemetry - outputs JSON for diffing"""

import asyncio
import json
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.types import LLMRequest, ALSContext
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.services.als.als_builder import ALSBuilder


async def run_test(vendor: str, model: str, grounded: bool, prompt: str = "What is 2+2?"):
    """Run a single test and return result dict"""
    adapter = UnifiedLLMAdapter()
    als_builder = ALSBuilder()
    als_block = als_builder.build_als_block('DE')
    
    req = LLMRequest(
        vendor=vendor,
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        grounded=grounded,
        temperature=0.5,
        als_context=ALSContext(
            country_code='DE',
            locale='de-DE',
            als_block=als_block,
            als_variant_id='de_v1'
        )
    )
    
    try:
        result = await asyncio.wait_for(adapter.complete(req), timeout=60)
        
        return {
            "test": f"{vendor}_{model}_{'grounded' if grounded else 'ungrounded'}",
            "timestamp": datetime.utcnow().isoformat(),
            "success": result.success,
            "error": getattr(result, 'error', None),
            "content_length": len(result.content or ""),
            "content_preview": (result.content or "")[:100],
            "metadata": result.metadata or {},
            "citations_count": len(result.citations or []),
            "usage": result.usage or {}
        }
    except Exception as e:
        return {
            "test": f"{vendor}_{model}_{'grounded' if grounded else 'ungrounded'}",
            "timestamp": datetime.utcnow().isoformat(),
            "success": False,
            "error": str(e),
            "content_length": 0,
            "content_preview": "",
            "metadata": {},
            "citations_count": 0,
            "usage": {}
        }


async def main():
    """Run all baseline tests"""
    results = []
    
    # OpenAI tests
    print("Running OpenAI ungrounded...")
    results.append(await run_test("openai", "gpt-5-2025-08-07", False))
    
    print("Running OpenAI grounded...")
    results.append(await run_test("openai", "gpt-5-2025-08-07", True, "What is the capital of France?"))
    
    # Vertex tests
    print("Running Vertex ungrounded...")
    results.append(await run_test("vertex", "publishers/google/models/gemini-2.5-pro", False))
    
    print("Running Vertex grounded...")
    results.append(await run_test("vertex", "publishers/google/models/gemini-2.5-pro", True, "What is the capital of France?"))
    
    # Gemini Direct tests (need API key)
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        print("Running Gemini Direct ungrounded...")
        results.append(await run_test("gemini_direct", "gemini-2.5-pro", False))
        
        print("Running Gemini Direct grounded...")
        results.append(await run_test("gemini_direct", "gemini-2.5-pro", True, "What is the capital of France?"))
    else:
        print("Skipping Gemini Direct tests (no API key)")
    
    # Save individual results
    for result in results:
        test_name = result["test"].replace("/", "_").replace("publishers_google_models_", "")
        output_file = f"tmp/baseline/{test_name}.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Saved: {output_file}")
    
    # Save combined results
    combined_file = "tmp/baseline/all_tests.json"
    with open(combined_file, "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "tests": results,
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r["success"]),
                "failed": sum(1 for r in results if not r["success"])
            }
        }, f, indent=2)
    print(f"\nSaved combined: {combined_file}")
    
    # Print summary
    print("\n" + "="*60)
    print("BASELINE TEST SUMMARY")
    print("="*60)
    for result in results:
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"{status} - {result['test']}")
    print("="*60)
    
    failed = sum(1 for r in results if not r["success"])
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)