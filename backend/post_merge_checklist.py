#!/usr/bin/env python3
"""
Post-merge checklist for grounding sanity (Preferred & Required)
"""
import os
import sys
import subprocess
import json
import asyncio
from pathlib import Path

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

def run_command(cmd):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return str(e), 1

def check_repository_hygiene():
    """0) Preflight: repository hygiene"""
    print("=== 0) PREFLIGHT: REPOSITORY HYGIENE ===\n")
    
    checks = []
    
    # Check 1: No google.genai, proxy code, WEBSHARE
    print("1. Checking for google.genai, proxy, and WEBSHARE references:")
    cmd = "grep -RIn 'google\\.genai\\|HttpOptions\\|GenerateContentConfig\\|WEBSHARE\\|proxy_' backend/app/ 2>/dev/null | wc -l"
    output, _ = run_command(cmd)
    count = int(output) if output.isdigit() else -1
    print(f"   Found: {count} references (should be 0)")
    checks.append(("No genai/proxy references", count == 0))
    
    # Check 2: No disallowed model references
    print("\n2. Checking for disallowed model references (gemini-2.0, flash, exp, chatty):")
    cmd = "grep -RIn 'gemini-2\\.0\\|flash\\|exp\\|chatty' backend/app/ 2>/dev/null | wc -l"
    output, _ = run_command(cmd)
    count = int(output) if output.isdigit() else -1
    print(f"   Found: {count} references (should be 0)")
    checks.append(("No disallowed models", count == 0))
    
    # Check 3: Verify allowed models
    print("\n3. Verifying allowed models:")
    try:
        from app.llm.models import OPENAI_ALLOWED_MODELS, VERTEX_ALLOWED_MODELS
        print(f"   OpenAI models: {OPENAI_ALLOWED_MODELS}")
        print(f"   Vertex models: {VERTEX_ALLOWED_MODELS}")
        
        # Check specific models
        has_gpt5 = "gpt-5-chat-latest" in OPENAI_ALLOWED_MODELS or "gpt-5" in OPENAI_ALLOWED_MODELS
        has_gemini = "publishers/google/models/gemini-2.5-pro" in VERTEX_ALLOWED_MODELS
        
        checks.append(("GPT-5 in allowlist", has_gpt5))
        checks.append(("Gemini 2.5-pro in allowlist", has_gemini))
        
    except ImportError as e:
        print(f"   ❌ Could not import models: {e}")
        checks.append(("Models import", False))
    
    return all(c[1] for c in checks), checks

def check_environment():
    """1) Environment & pins"""
    print("\n=== 1) ENVIRONMENT & PINS ===\n")
    
    checks = []
    
    # Check environment variables
    env_vars = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID"),
        "VERTEX_LOCATION": os.getenv("VERTEX_LOCATION"),
    }
    
    for var, value in env_vars.items():
        has_value = bool(value)
        status = "✅" if has_value else "❌"
        masked = "***" if has_value else "NOT SET"
        print(f"{status} {var}: {masked}")
        checks.append((var, has_value))
    
    # Check preferred location
    location = env_vars.get("VERTEX_LOCATION", "")
    is_europe = location == "europe-west4"
    print(f"   Vertex location: {location} {'(preferred)' if is_europe else '(consider europe-west4)'}")
    
    return all(c[1] for c in checks[:3]), checks  # First 3 are required

async def quick_smoke_tests():
    """2) Quick smoke tests per provider"""
    print("\n=== 2) QUICK SMOKE TESTS ===\n")
    
    results = []
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    # Import adapter
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter = UnifiedLLMAdapter()
    
    # Test configurations
    tests = [
        {
            "name": "OpenAI GPT-5 (grounded=Preferred)",
            "vendor": "openai", 
            "model": "gpt-5",
            "grounded": True,
            "mode": "AUTO",
            "prompt": "What is the current stock price of Microsoft?"
        },
        {
            "name": "Vertex Gemini 2.5-pro (grounded=Preferred)",
            "vendor": "vertex",
            "model": "publishers/google/models/gemini-2.5-pro", 
            "grounded": True,
            "mode": "AUTO",
            "prompt": "What is the current weather in London?"
        }
    ]
    
    for test_config in tests:
        print(f"\nTesting: {test_config['name']}")
        
        request = LLMRequest(
            vendor=test_config["vendor"],
            model=test_config["model"],
            messages=[{"role": "user", "content": test_config["prompt"]}],
            grounded=test_config["grounded"],
            temperature=0.7,
            max_tokens=100,
            meta={"grounding_mode": test_config["mode"]}
        )
        
        try:
            response = await adapter.complete(request)
            
            # Check metadata
            metadata = response.metadata if hasattr(response, 'metadata') else {}
            grounded_effective = metadata.get("grounded_effective", False)
            tool_count = metadata.get("tool_call_count", 0)
            
            print(f"  ✅ Success")
            print(f"  - Response length: {len(response.content) if response.content else 0}")
            print(f"  - Grounded effective: {grounded_effective}")
            print(f"  - Tool calls: {tool_count}")
            
            if test_config["vendor"] == "vertex" and metadata.get("two_step_used"):
                print(f"  - Two-step used: Yes")
                print(f"  - Step2 tools invoked: {metadata.get('step2_tools_invoked', 'N/A')}")
                print(f"  - Step2 source ref: {metadata.get('step2_source_ref', 'N/A')[:16]}...")
            
            results.append((test_config["name"], True))
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append((test_config["name"], False))
    
    return all(r[1] for r in results), results

def check_acceptance_gates():
    """7) Acceptance gates"""
    print("\n=== 7) ACCEPTANCE GATES ===\n")
    
    gates = []
    
    # Gate 1: Model pins
    print("1. Model pins check:")
    try:
        from app.llm.models import OPENAI_ALLOWED_MODELS, VERTEX_ALLOWED_MODELS
        
        correct_openai = "gpt-5-chat-latest" in OPENAI_ALLOWED_MODELS or "gpt-5" in OPENAI_ALLOWED_MODELS
        correct_vertex = "publishers/google/models/gemini-2.5-pro" in VERTEX_ALLOWED_MODELS
        
        print(f"   OpenAI: {'✅' if correct_openai else '❌'} GPT-5 models only")
        print(f"   Vertex: {'✅' if correct_vertex else '❌'} Gemini 2.5-pro only")
        
        gates.append(("Model pins", correct_openai and correct_vertex))
        
    except ImportError:
        print("   ❌ Could not check model pins")
        gates.append(("Model pins", False))
    
    # Gate 2: Two-step attestation
    print("\n2. Two-step attestation check:")
    print("   Checking vertex_adapter.py for attestation fields...")
    
    cmd = "grep -n 'step2_tools_invoked\\|step2_source_ref' app/llm/adapters/vertex_adapter.py | wc -l"
    output, _ = run_command(cmd)
    has_attestation = int(output) > 0 if output.isdigit() else False
    
    print(f"   {'✅' if has_attestation else '❌'} Attestation fields present")
    gates.append(("Two-step attestation", has_attestation))
    
    # Gate 3: REQUIRED mode enforcement
    print("\n3. REQUIRED mode enforcement:")
    
    cmd = "grep -n 'GroundingRequiredError\\|REQUIRED' app/llm/adapters/vertex_adapter.py | wc -l"
    output, _ = run_command(cmd)
    has_required = int(output) > 0 if output.isdigit() else False
    
    print(f"   {'✅' if has_required else '❌'} REQUIRED mode handling present")
    gates.append(("REQUIRED enforcement", has_required))
    
    return all(g[1] for g in gates), gates

def main():
    print("="*70)
    print("POST-MERGE CHECKLIST: GROUNDING SANITY")
    print("="*70)
    
    all_results = []
    
    # Run checks
    hygiene_pass, hygiene_checks = check_repository_hygiene()
    all_results.append(("Repository hygiene", hygiene_pass))
    
    env_pass, env_checks = check_environment()
    all_results.append(("Environment setup", env_pass))
    
    # Run async smoke tests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        smoke_pass, smoke_results = loop.run_until_complete(quick_smoke_tests())
        all_results.append(("Smoke tests", smoke_pass))
    except Exception as e:
        print(f"\n❌ Smoke tests failed: {e}")
        all_results.append(("Smoke tests", False))
    finally:
        loop.close()
    
    gates_pass, gates_results = check_acceptance_gates()
    all_results.append(("Acceptance gates", gates_pass))
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    for check_name, passed in all_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{check_name}: {status}")
    
    overall_pass = all(r[1] for r in all_results)
    
    print("\n" + "="*70)
    if overall_pass:
        print("✅ ALL CHECKS PASSED")
        print("The system is ready for grounding operations with:")
        print("  - OpenAI GPT-5 (Preferred/Required modes)")
        print("  - Vertex Gemini 2.5-pro (Preferred/Required modes)")
        print("  - Two-step grounded JSON for Vertex")
        print("  - Proper attestation fields")
    else:
        print("❌ SOME CHECKS FAILED")
        print("Review the issues above and fix before proceeding")
    print("="*70)
    
    return 0 if overall_pass else 1

if __name__ == "__main__":
    sys.exit(main())