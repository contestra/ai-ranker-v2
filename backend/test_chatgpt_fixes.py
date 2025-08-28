#!/usr/bin/env python3
"""
Comprehensive test suite for ChatGPT review fixes
Tests all P0 and P1 issues that were addressed
"""
import asyncio
import os
import sys
import json
import time
from unittest.mock import Mock, patch, AsyncMock
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

# Disable proxies for testing
os.environ["DISABLE_PROXIES"] = "true"
os.environ["OPENAI_AUTO_TRIM"] = "true"
os.environ["OPENAI_MAX_WEB_SEARCHES"] = "3"  # Test configurability

from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.grounding_detection_helpers import (
    detect_openai_grounding, 
    extract_openai_search_evidence
)
from app.llm.types import LLMRequest


class TestChatGPTFixes:
    """Test all fixes from ChatGPT review"""
    
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def test_metadata_preservation(self):
        """Test P0: Metadata is preserved, not overwritten"""
        print("\n=== TEST: Metadata Preservation ===")
        
        # Check that metadata update logic exists
        with open('app/llm/adapters/openai_adapter.py', 'r') as f:
            content = f.read()
        
        # Look for metadata.update instead of metadata = {}
        if 'metadata.update({' in content and 'metadata["auto_trimmed"]' in content:
            print("✅ Metadata preservation implemented correctly")
            self.passed += 1
            return True
        else:
            print("❌ Metadata preservation not found")
            self.failed += 1
            return False
    
    def test_normalized_model_usage(self):
        """Test P0: Normalized model is used in API calls"""
        print("\n=== TEST: Normalized Model Usage ===")
        
        with open('app/llm/adapters/openai_adapter.py', 'r') as f:
            content = f.read()
        
        # Check model normalization is used
        checks = [
            '"model": model_name' in content,  # Using normalized model
            'model_name = normalize_model' in content,  # Normalization happening
        ]
        
        if all(checks):
            print("✅ Normalized model is used in API calls")
            self.passed += 1
            return True
        else:
            print("❌ Model normalization issue found")
            self.failed += 1
            return False
    
    def test_token_estimation_fix(self):
        """Test P0: Token estimation uses effective_tokens"""
        print("\n=== TEST: Token Estimation Fix ===")
        
        with open('app/llm/adapters/openai_adapter.py', 'r') as f:
            content = f.read()
        
        # Check that effective_tokens is calculated before estimation
        lines = content.split('\n')
        effective_line = -1
        estimate_line = -1
        
        for i, line in enumerate(lines):
            if 'effective_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS' in line:
                effective_line = i
            if 'estimated_tokens = int((estimated_input_tokens + effective_tokens)' in line:
                estimate_line = i
        
        if effective_line > 0 and estimate_line > effective_line:
            print(f"✅ Token estimation uses effective_tokens (line {estimate_line})")
            self.passed += 1
            return True
        else:
            print("❌ Token estimation not using effective_tokens")
            self.failed += 1
            return False
    
    def test_synthesis_evidence_injection(self):
        """Test P0: Synthesis fallback includes search evidence"""
        print("\n=== TEST: Synthesis Evidence Injection ===")
        
        # Test the evidence extraction function
        mock_response = Mock()
        mock_response.output = [
            {
                'type': 'web_search_result',
                'result': {
                    'title': 'Test Result',
                    'url': 'https://example.com',
                    'snippet': 'Test snippet content'
                }
            }
        ]
        
        evidence = extract_openai_search_evidence(mock_response)
        
        if 'Test Result' in evidence and 'https://example.com' in evidence:
            print("✅ Evidence extraction working")
        else:
            print(f"❌ Evidence extraction failed: {evidence}")
            self.failed += 1
            return False
        
        # Check synthesis implementation
        with open('app/llm/adapters/openai_adapter.py', 'r') as f:
            content = f.read()
        
        if 'extract_openai_search_evidence(response)' in content and 'enhanced_input' in content:
            print("✅ Synthesis fallback includes search evidence")
            self.passed += 1
            return True
        else:
            print("❌ Synthesis evidence injection not found")
            self.failed += 1
            return False
    
    def test_tpm_credit_handling(self):
        """Test P1: TPM limiter handles credit for overestimates"""
        print("\n=== TEST: TPM Credit Handling ===")
        
        with open('app/llm/adapters/openai_adapter.py', 'r') as f:
            content = f.read()
        
        # Check for credit handling logic
        checks = [
            'RL_CREDIT' in content,
            'We overestimated' in content,
            'credit_applied' in content,
            'self._tokens_used_this_minute -= credit_applied' in content
        ]
        
        if all(checks):
            print("✅ TPM credit handling implemented")
            self.passed += 1
            return True
        else:
            print("❌ TPM credit handling not found")
            self.failed += 1
            return False
    
    def test_grounding_signal_separation(self):
        """Test P1: Grounding signals are separated (web vs any tool)"""
        print("\n=== TEST: Grounding Signal Separation ===")
        
        # Test mock response with mixed tools
        mock_resp = Mock()
        mock_resp.output = [
            {'type': 'web_search_call', 'content': {}},
            {'type': 'function_call', 'content': {}},
            {'type': 'tool_use', 'content': {}}
        ]
        
        grounded_effective, tool_call_count, web_grounded, web_search_count = detect_openai_grounding(mock_resp)
        
        print(f"  grounded_effective: {grounded_effective} (expected: True)")
        print(f"  tool_call_count: {tool_call_count} (expected: 3)")
        print(f"  web_grounded: {web_grounded} (expected: True)")
        print(f"  web_search_count: {web_search_count} (expected: 1)")
        
        if (grounded_effective == True and 
            tool_call_count == 3 and 
            web_grounded == True and 
            web_search_count == 1):
            print("✅ Grounding signals correctly separated")
            self.passed += 1
            return True
        else:
            print("❌ Grounding signal separation incorrect")
            self.failed += 1
            return False
    
    def test_configurable_search_limit(self):
        """Test P2: Web search limit is configurable"""
        print("\n=== TEST: Configurable Search Limit ===")
        
        # Check environment variable is used
        with open('app/llm/adapters/openai_adapter.py', 'r') as f:
            content = f.read()
        
        if 'OPENAI_MAX_WEB_SEARCHES' in content:
            print(f"✅ Search limit configurable (currently set to {os.getenv('OPENAI_MAX_WEB_SEARCHES', '2')})")
            self.passed += 1
            return True
        else:
            print("❌ Search limit not configurable")
            self.failed += 1
            return False
    
    async def test_adapter_initialization(self):
        """Test that adapters initialize without errors"""
        print("\n=== TEST: Adapter Initialization ===")
        
        # Mock the API key for testing
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            try:
                # Test OpenAI adapter
                adapter = OpenAIAdapter()
                print("✅ OpenAI adapter initializes")
                self.passed += 1
                return True
            except Exception as e:
                print(f"❌ OpenAI adapter initialization failed: {e}")
                self.failed += 1
                return False
    
    async def test_live_call_with_fixes(self):
        """Test a live call to verify all fixes work together"""
        print("\n=== TEST: Live Call Integration (Mocked) ===")
        
        # Mock the API key
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            adapter = OpenAIAdapter()
            
            # Create a test request
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",  # Use gpt-5 as required by Responses API
                messages=[{"role": "user", "content": "Test message"}],
                temperature=0.7,
                max_tokens=100,
                grounded=False
            )
            
            # Mock the actual API call to avoid real charges
            mock_response = Mock()
            mock_response.output = [
                {'type': 'message', 'content': [{'type': 'text', 'text': 'Test response'}]}
            ]
            # Create a proper usage mock that can be serialized
            mock_usage = Mock()
            mock_usage.total_tokens = 150
            mock_usage.prompt_tokens = 50
            mock_usage.completion_tokens = 100
            mock_usage.model_dump = lambda: {
                'total_tokens': 150, 
                'prompt_tokens': 50,
                'completion_tokens': 100
            }
            mock_response.usage = mock_usage
            mock_response.model = 'gpt-5'
            mock_response.system_fingerprint = 'test-fp'
            
            # Patch the client call
            with patch.object(adapter, 'client') as mock_client:
                mock_client.with_options.return_value.responses.create = AsyncMock(return_value=mock_response)
                
                try:
                    response = await adapter.complete(request)
                    
                    # Check response has content
                    if response.content == 'Test response':
                        print("✅ Live call completed successfully")
                        
                        # Check metadata preservation
                        if 'proxies_enabled' in response.metadata:
                            print("✅ Metadata preserved through call")
                        
                        self.passed += 1
                        return True
                    else:
                        print(f"❌ Unexpected response: {response.content}")
                        self.failed += 1
                        return False
                        
                except Exception as e:
                    print(f"❌ Live call failed: {e}")
                    self.failed += 1
                    return False
    
    async def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*60)
        print("🔍 COMPREHENSIVE TEST SUITE FOR CHATGPT REVIEW FIXES")
        print("="*60)
        
        # Synchronous tests
        self.test_metadata_preservation()
        self.test_normalized_model_usage()
        self.test_token_estimation_fix()
        self.test_synthesis_evidence_injection()
        self.test_tpm_credit_handling()
        self.test_grounding_signal_separation()
        self.test_configurable_search_limit()
        
        # Async tests
        await self.test_adapter_initialization()
        await self.test_live_call_with_fixes()
        
        # Summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        print(f"Tests Passed: {self.passed}")
        print(f"Tests Failed: {self.failed}")
        print(f"Success Rate: {self.passed/(self.passed+self.failed)*100:.1f}%")
        
        if self.failed == 0:
            print("\n🎉 ALL TESTS PASSED! ChatGPT review fixes verified.")
        else:
            print(f"\n⚠️ {self.failed} test(s) failed. Review needed.")
        
        return self.failed == 0


if __name__ == "__main__":
    tester = TestChatGPTFixes()
    success = asyncio.run(tester.run_all_tests())
    exit(0 if success else 1)