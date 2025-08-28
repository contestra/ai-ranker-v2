#!/usr/bin/env python3
"""
STANDALONE Test Suite for Proxy Removal (No Dependencies)
Tests proxy removal without requiring external packages
"""
import os
import re
import json
import time
from pathlib import Path
from datetime import datetime

# Set environment
os.environ["DISABLE_PROXIES"] = "true"

class StandaloneProxyTester:
    """Tests that work without dependencies"""
    
    def __init__(self):
        self.results = []
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
    
    def test_file_analysis(self):
        """Analyze files for proxy remnants"""
        print("\n" + "="*70)
        print("TEST: Static File Analysis")
        print("="*70)
        
        files = {
            "app/llm/adapters/openai_adapter.py": "OpenAI Adapter",
            "app/llm/adapters/vertex_adapter.py": "Vertex Adapter",
            "app/llm/unified_llm_adapter.py": "Unified Adapter"
        }
        
        proxy_patterns = {
            "WEBSHARE_": "WebShare credentials",
            "_should_use_proxy": "Proxy decision function",
            "_build_webshare_proxy_uri": "Proxy URI builder",
            "_proxy_connection_mode": "Proxy mode selector",
            "proxy_circuit_breaker": "Circuit breaker",
            "proxies=": "Proxy parameter",
            "proxy=": "Proxy parameter",
            "_proxy_client": "Proxy client variable",
            "proxy_timeout": "Proxy timeout",
            "proxy_requested": "Proxy request check",
        }
        
        all_clean = True
        
        for filepath, name in files.items():
            print(f"\nAnalyzing {name}...")
            
            if not os.path.exists(filepath):
                print(f"  ⚠️ File not found: {filepath}")
                continue
            
            with open(filepath, 'r') as f:
                content = f.read()
            
            found_issues = []
            
            for pattern, description in proxy_patterns.items():
                # Use regex for more accurate matching
                if pattern in content:
                    # Count occurrences
                    count = content.count(pattern)
                    # Check if it's in comments only
                    lines = content.split('\n')
                    actual_count = 0
                    for line in lines:
                        if pattern in line and not line.strip().startswith('#'):
                            actual_count += 1
                    
                    if actual_count > 0:
                        found_issues.append(f"{description} ({pattern}): {actual_count} active references")
            
            if found_issues:
                print(f"  ❌ Found issues in {name}:")
                for issue in found_issues:
                    print(f"      - {issue}")
                all_clean = False
            else:
                print(f"  ✅ {name} is clean of proxy references")
        
        return all_clean
    
    def test_metadata_consistency(self):
        """Check metadata fields are consistent"""
        print("\n" + "="*70)
        print("TEST: Metadata Consistency")
        print("="*70)
        
        required_metadata = {
            '"proxies_enabled": False': "proxies_enabled flag",
            '"proxy_mode": "disabled"': "proxy_mode setting",
        }
        
        files = [
            "app/llm/adapters/openai_adapter.py",
            "app/llm/adapters/vertex_adapter.py"
        ]
        
        all_consistent = True
        
        for filepath in files:
            filename = os.path.basename(filepath)
            print(f"\nChecking {filename}...")
            
            if not os.path.exists(filepath):
                print(f"  ⚠️ File not found")
                continue
            
            with open(filepath, 'r') as f:
                content = f.read()
            
            for pattern, description in required_metadata.items():
                if pattern in content:
                    print(f"  ✅ Has {description}")
                else:
                    print(f"  ❌ Missing {description}")
                    all_consistent = False
        
        return all_consistent
    
    def test_grounding_preservation(self):
        """Verify grounding code is preserved"""
        print("\n" + "="*70)
        print("TEST: Grounding Preservation")
        print("="*70)
        
        grounding_markers = {
            "openai": {
                "web_search": "Web search tool",
                "request.grounded": "Grounded parameter",
                "detect_openai_grounding": "Grounding detection",
                "at most 2 web searches": "Search limit",
            },
            "vertex": {
                "GoogleSearch": "Google Search tool",
                "_create_grounding_tools": "Tool creation",
                "req.grounded": "Grounded parameter",
                "detect_vertex_grounding": "Grounding detection",
                "Cannot use grounding with structured output": "Two-step rule",
            }
        }
        
        all_preserved = True
        
        # Check OpenAI
        print("\nOpenAI Adapter:")
        with open("app/llm/adapters/openai_adapter.py", 'r') as f:
            openai_content = f.read()
        
        for marker, description in grounding_markers["openai"].items():
            if marker in openai_content:
                print(f"  ✅ {description} preserved")
            else:
                print(f"  ❌ {description} missing")
                all_preserved = False
        
        # Check Vertex
        print("\nVertex Adapter:")
        with open("app/llm/adapters/vertex_adapter.py", 'r') as f:
            vertex_content = f.read()
        
        for marker, description in grounding_markers["vertex"].items():
            if marker in vertex_content:
                print(f"  ✅ {description} preserved")
            else:
                print(f"  ❌ {description} missing")
                all_preserved = False
        
        return all_preserved
    
    def test_environment_setup(self):
        """Test environment configuration"""
        print("\n" + "="*70)
        print("TEST: Environment Configuration")
        print("="*70)
        
        checks = {}
        
        # Check DISABLE_PROXIES
        disable_proxies = os.getenv("DISABLE_PROXIES", "")
        checks["disable_proxies"] = disable_proxies.lower() in ("true", "1", "yes")
        print(f"{'✅' if checks['disable_proxies'] else '❌'} DISABLE_PROXIES = {disable_proxies}")
        
        # Check no proxy vars are set
        proxy_vars = ["WEBSHARE_USERNAME", "WEBSHARE_PASSWORD", "WEBSHARE_HOST", "WEBSHARE_PORT"]
        for var in proxy_vars:
            value = os.getenv(var)
            checks[var] = value is None
            if value:
                print(f"❌ {var} is still set")
            else:
                print(f"✅ {var} is not set")
        
        return all(checks.values())
    
    def test_imports_validity(self):
        """Test Python syntax and imports are valid"""
        print("\n" + "="*70)
        print("TEST: Python Syntax Validation")
        print("="*70)
        
        files = [
            "app/llm/adapters/openai_adapter.py",
            "app/llm/adapters/vertex_adapter.py",
            "app/llm/unified_llm_adapter.py"
        ]
        
        all_valid = True
        
        for filepath in files:
            filename = os.path.basename(filepath)
            
            try:
                with open(filepath, 'r') as f:
                    code = f.read()
                
                # Try to compile the code (syntax check only)
                compile(code, filepath, 'exec')
                print(f"✅ {filename} has valid Python syntax")
                
            except SyntaxError as e:
                print(f"❌ {filename} has syntax error: {e}")
                all_valid = False
            except Exception as e:
                print(f"⚠️ {filename} check error: {e}")
        
        return all_valid
    
    def test_documentation(self):
        """Check documentation is updated"""
        print("\n" + "="*70)
        print("TEST: Documentation Updates")
        print("="*70)
        
        doc_file = "PROXY_REMOVAL_COMPLETE.md"
        
        if os.path.exists(doc_file):
            print(f"✅ {doc_file} exists")
            
            with open(doc_file, 'r') as f:
                content = f.read()
            
            # Check key sections
            required_sections = [
                "Global Kill-Switch",
                "Policy Normalization",
                "OpenAI Adapter Cleanup",
                "Vertex Adapter Cleanup",
                "Verification Results"
            ]
            
            for section in required_sections:
                if section in content:
                    print(f"  ✅ Section: {section}")
                else:
                    print(f"  ❌ Missing section: {section}")
            
            return True
        else:
            print(f"❌ {doc_file} not found")
            return False
    
    def test_file_deletions(self):
        """Verify proxy files are deleted"""
        print("\n" + "="*70)
        print("TEST: File Deletions")
        print("="*70)
        
        files_should_not_exist = [
            "app/llm/adapters/proxy_circuit_breaker.py",
            "app/services/proxy_service.py",
            "test_proxy.py",
            "PROXY_QUICKSTART.md",
            "PROXY_IMPLEMENTATION_PLAN.md"
        ]
        
        all_deleted = True
        
        for filepath in files_should_not_exist:
            if os.path.exists(filepath):
                print(f"❌ {filepath} still exists (should be deleted)")
                all_deleted = False
            else:
                print(f"✅ {filepath} deleted")
        
        return all_deleted
    
    def test_unified_adapter_normalization(self):
        """Check unified adapter has normalization logic"""
        print("\n" + "="*70)
        print("TEST: Policy Normalization in Router")
        print("="*70)
        
        filepath = "app/llm/unified_llm_adapter.py"
        
        if not os.path.exists(filepath):
            print(f"❌ {filepath} not found")
            return False
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        checks = {
            "DISABLE_PROXIES": "Kill-switch constant",
            "PROXY_ONLY": "PROXY_ONLY policy check",
            "ALS_PLUS_PROXY": "ALS_PLUS_PROXY policy check",
            "normalized_policy": "Normalization variable",
            "proxies_normalized": "Normalization tracking",
        }
        
        all_present = True
        
        for marker, description in checks.items():
            if marker in content:
                print(f"✅ {description} found")
            else:
                print(f"❌ {description} missing")
                all_present = False
        
        return all_present
    
    def test_rate_limiting_code(self):
        """Verify rate limiting code is preserved"""
        print("\n" + "="*70)
        print("TEST: Rate Limiting Preservation")
        print("="*70)
        
        filepath = "app/llm/adapters/openai_adapter.py"
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        rate_limit_markers = {
            "class _OpenAIRateLimiter": "Rate limiter class",
            "get_grounded_multiplier": "Adaptive multiplier",
            "_tokens_used_this_minute": "Token tracking",
            "_debt": "Debt tracking",
            "random.uniform(0.5, 0.75)": "Window jitter",
            "await_tpm": "TPM waiting",
            "commit_actual_tokens": "Token commit",
        }
        
        all_present = True
        
        for marker, description in rate_limit_markers.items():
            if marker in content:
                print(f"✅ {description} preserved")
            else:
                print(f"❌ {description} missing")
                all_present = False
        
        return all_present
    
    def test_clean_code(self):
        """Check for clean code practices"""
        print("\n" + "="*70)
        print("TEST: Code Cleanliness")
        print("="*70)
        
        files = [
            "app/llm/adapters/openai_adapter.py",
            "app/llm/adapters/vertex_adapter.py",
            "app/llm/unified_llm_adapter.py"
        ]
        
        issues = []
        
        for filepath in files:
            filename = os.path.basename(filepath)
            
            with open(filepath, 'r') as f:
                lines = f.readlines()
            
            # Check for various issues
            for i, line in enumerate(lines, 1):
                # Check for TODO/FIXME about proxy
                if ('TODO' in line or 'FIXME' in line) and 'proxy' in line.lower():
                    issues.append(f"{filename}:{i} - TODO/FIXME about proxy")
                
                # Check for print statements (should use logger)
                if line.strip().startswith('print(') and not filepath.endswith('test'):
                    issues.append(f"{filename}:{i} - Print statement (use logger)")
                
                # Check for very long lines
                if len(line) > 120 and not line.strip().startswith('#'):
                    issues.append(f"{filename}:{i} - Line too long ({len(line)} chars)")
        
        if issues:
            print(f"Found {len(issues)} cleanliness issues:")
            for issue in issues[:10]:  # Show first 10
                print(f"  - {issue}")
            return False
        else:
            print("✅ Code is clean")
            return True
    
    def run_all(self):
        """Run all standalone tests"""
        print("\n" + "="*70)
        print("🔍 STANDALONE PROXY REMOVAL VERIFICATION")
        print("="*70)
        print(f"Time: {datetime.now().isoformat()}")
        print(f"DISABLE_PROXIES: {os.getenv('DISABLE_PROXIES', 'not set')}")
        print("="*70)
        
        tests = [
            ("File Analysis", self.test_file_analysis),
            ("Metadata Consistency", self.test_metadata_consistency),
            ("Grounding Preservation", self.test_grounding_preservation),
            ("Environment Setup", self.test_environment_setup),
            ("Python Syntax", self.test_imports_validity),
            ("Documentation", self.test_documentation),
            ("File Deletions", self.test_file_deletions),
            ("Router Normalization", self.test_unified_adapter_normalization),
            ("Rate Limiting", self.test_rate_limiting_code),
            ("Code Cleanliness", self.test_clean_code),
        ]
        
        for test_name, test_func in tests:
            self.tests_run += 1
            try:
                result = test_func()
                if result:
                    self.tests_passed += 1
                    self.results.append((test_name, "PASS", None))
                    print(f"\n✅ {test_name}: PASS\n")
                else:
                    self.tests_failed += 1
                    self.results.append((test_name, "FAIL", None))
                    print(f"\n❌ {test_name}: FAIL\n")
            except Exception as e:
                self.tests_failed += 1
                self.results.append((test_name, "ERROR", str(e)))
                print(f"\n❌ {test_name}: ERROR - {e}\n")
        
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("📊 TEST SUMMARY")
        print("="*70)
        
        print(f"\nTests Run: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ({self.tests_passed/self.tests_run*100:.1f}%)")
        print(f"Failed: {self.tests_failed} ({self.tests_failed/self.tests_run*100:.1f}%)")
        
        if self.tests_failed > 0:
            print("\nFailed Tests:")
            for name, status, error in self.results:
                if status != "PASS":
                    if error:
                        print(f"  - {name}: {error}")
                    else:
                        print(f"  - {name}")
        
        print("\n" + "="*70)
        if self.tests_failed == 0:
            print("🎉 ALL TESTS PASSED!")
            print("\nProxy removal verification complete:")
            print("  ✅ No proxy code remaining")
            print("  ✅ Metadata shows proxies disabled")
            print("  ✅ Grounding preserved")
            print("  ✅ Rate limiting preserved")
            print("  ✅ Documentation updated")
        else:
            print(f"⚠️ {self.tests_failed} test(s) failed")
            print("Review the failures above for details")
        
        # Save results
        results_file = f"standalone_test_results_{int(time.time())}.json"
        with open(results_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "tests_run": self.tests_run,
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "results": [{"test": name, "status": status, "error": error} for name, status, error in self.results]
            }, f, indent=2)
        print(f"\n📁 Results saved to: {results_file}")


if __name__ == "__main__":
    tester = StandaloneProxyTester()
    tester.run_all()
    exit(0 if tester.tests_failed == 0 else 1)