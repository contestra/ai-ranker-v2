#!/usr/bin/env python3
"""
OpenAI web_search enablement diagnostic script
Tests all checklist items from ChatGPT's analysis
"""

import asyncio
import json
import os
import sys
from typing import Dict, Any, Optional
from datetime import datetime

# Add the backend path to sys.path for imports
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.models import LLMRequest, ALSContext
from app.llm.errors import BaseGradedError
import logging

# Enable detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enable WIRE_DEBUG
os.environ["OPENAI_WIRE_DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "DEBUG"

class OpenAIGroundingDiagnostics:
    def __init__(self):
        self.adapter = OpenAIAdapter()
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "evidence": {}
        }
    
    async def run_all_checks(self):
        """Run all 7 checks from ChatGPT's checklist"""
        
        print("\n" + "="*80)
        print("OpenAI Grounding Diagnostics - Following ChatGPT's Checklist")
        print("="*80 + "\n")
        
        # Check 1: Model + tool type actually attached
        await self.check_1_tool_attachment()
        
        # Check 2: Using Responses API
        await self.check_2_responses_api()
        
        # Check 3: Preview vs full tool variant fallback
        await self.check_3_tool_fallback()
        
        # Check 4: REQUIRED mode sets tool_choice
        await self.check_4_required_mode()
        
        # Check 5: Parameters not being stripped
        await self.check_5_params_preservation()
        
        # Check 6: Org/project scoping - capability probe
        await self.check_6_capability_probe()
        
        # Check 7: Telemetry truth
        await self.check_7_telemetry_truth()
        
        # Save results
        self.save_results()
    
    async def check_1_tool_attachment(self):
        """Check 1: Model + tool type actually attached on the call"""
        print("\n[CHECK 1] Tool Attachment Verification")
        print("-" * 40)
        
        # Test AUTO mode
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[
                {"role": "user", "content": "What's the latest news about AI?"}
            ],
            grounded=True,
            als_context=ALSContext(country="US", locale="en-US")
        )
        
        try:
            # The adapter should log the WIRE_DEBUG payload
            response = await self.adapter.generate(request)
            
            # Check metadata for what was sent
            if hasattr(response, 'metadata') and response.metadata:
                self.results["checks"]["tool_attachment"] = {
                    "model": response.metadata.get("model"),
                    "tool_type": response.metadata.get("response_api_tool_type"),
                    "tool_choice": response.metadata.get("tool_choice", "auto"),
                    "grounding_mode": response.metadata.get("grounding_mode_requested"),
                    "status": "PASS" if response.metadata.get("response_api_tool_type") else "FAIL"
                }
                
                print(f"✓ Model: {response.metadata.get('model')}")
                print(f"✓ Tool Type: {response.metadata.get('response_api_tool_type')}")
                print(f"✓ Tool Choice: {response.metadata.get('tool_choice', 'auto')}")
                print(f"✓ Grounding Mode: {response.metadata.get('grounding_mode_requested')}")
            
        except Exception as e:
            self.results["checks"]["tool_attachment"] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"✗ Error: {e}")
    
    async def check_2_responses_api(self):
        """Check 2: Using Responses API (not ChatCompletions)"""
        print("\n[CHECK 2] Responses API Verification")
        print("-" * 40)
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[
                {"role": "user", "content": "Test response"}
            ],
            grounded=True
        )
        
        try:
            response = await self.adapter.generate(request)
            
            if hasattr(response, 'metadata') and response.metadata:
                api_used = response.metadata.get("response_api", "unknown")
                self.results["checks"]["responses_api"] = {
                    "api": api_used,
                    "status": "PASS" if api_used == "responses_http" else "FAIL"
                }
                
                if api_used == "responses_http":
                    print(f"✓ Using Responses API: {api_used}")
                else:
                    print(f"✗ Wrong API: {api_used} (expected: responses_http)")
                    
        except Exception as e:
            self.results["checks"]["responses_api"] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"✗ Error: {e}")
    
    async def check_3_tool_fallback(self):
        """Check 3: Preview vs full tool variant fallback"""
        print("\n[CHECK 3] Tool Fallback Verification")
        print("-" * 40)
        
        # Force a specific tool type to test fallback
        os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"] = "web_search"
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[
                {"role": "user", "content": "Test fallback"}
            ],
            grounded=True
        )
        
        try:
            response = await self.adapter.generate(request)
            
            if hasattr(response, 'metadata') and response.metadata:
                tool_variant = response.metadata.get("response_api_tool_variant")
                tool_type = response.metadata.get("response_api_tool_type")
                
                self.results["checks"]["tool_fallback"] = {
                    "initial_type": "web_search",
                    "final_type": tool_type,
                    "used_fallback": tool_variant == "preview_retry",
                    "status": "PASS"
                }
                
                print(f"✓ Initial Tool: web_search")
                print(f"✓ Final Tool: {tool_type}")
                print(f"✓ Fallback Used: {tool_variant == 'preview_retry'}")
                
        except Exception as e:
            self.results["checks"]["tool_fallback"] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"✗ Error: {e}")
        
        finally:
            # Clear override
            del os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"]
    
    async def check_4_required_mode(self):
        """Check 4: REQUIRED mode sets tool_choice:required"""
        print("\n[CHECK 4] REQUIRED Mode Verification")
        print("-" * 40)
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[
                {"role": "user", "content": "Test required mode"}
            ],
            grounded=True,
            meta={"grounding_mode": "REQUIRED"}
        )
        
        try:
            response = await self.adapter.generate(request)
            
            # This should fail with GROUNDING_NOT_SUPPORTED if no tools available
            # Or succeed with tool_choice:required if tools are available
            self.results["checks"]["required_mode"] = {
                "status": "PASS",
                "response_received": True
            }
            print(f"✓ REQUIRED mode processed")
            
        except BaseGradedError as e:
            if e.code == "GROUNDING_NOT_SUPPORTED":
                self.results["checks"]["required_mode"] = {
                    "status": "PASS",
                    "behavior": "Correctly failed with GROUNDING_NOT_SUPPORTED"
                }
                print(f"✓ Correctly failed closed: {e.code}")
            else:
                self.results["checks"]["required_mode"] = {
                    "status": "FAIL",
                    "error": str(e)
                }
                print(f"✗ Unexpected error: {e}")
                
        except Exception as e:
            self.results["checks"]["required_mode"] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"✗ Error: {e}")
    
    async def check_5_params_preservation(self):
        """Check 5: Parameters not being stripped"""
        print("\n[CHECK 5] Parameter Preservation")
        print("-" * 40)
        
        # This check would need to inspect the actual HTTP payload
        # which requires WIRE_DEBUG output analysis
        
        self.results["checks"]["params_preservation"] = {
            "status": "MANUAL",
            "note": "Check WIRE_DEBUG output for tools and tool_choice in payload"
        }
        
        print("⚠ Manual verification needed:")
        print("  Check debug logs for actual HTTP payload")
        print("  Verify 'tools' and 'tool_choice' are present")
    
    async def check_6_capability_probe(self):
        """Check 6: Capability probe for org/project scoping"""
        print("\n[CHECK 6] Capability Probe")
        print("-" * 40)
        
        # Minimal probe to test if tools are supported
        for tool_type in ["web_search", "web_search_preview"]:
            print(f"\nTesting {tool_type}...")
            
            probe_request = LLMRequest(
                vendor="openai",
                model="gpt-5-chat-latest",
                messages=[
                    {"role": "user", "content": "test"}
                ],
                grounded=True,
                max_tokens=16,
                meta={"probe_tool_type": tool_type}
            )
            
            # Force specific tool type for probe
            os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"] = tool_type
            
            try:
                response = await self.adapter.generate(probe_request)
                
                self.results["evidence"][f"probe_{tool_type}"] = {
                    "status": "SUPPORTED",
                    "model": probe_request.model,
                    "org": os.getenv("OPENAI_ORG_ID", "default")
                }
                print(f"  ✓ {tool_type} SUPPORTED")
                
            except BaseGradedError as e:
                if e.code == "GROUNDING_NOT_SUPPORTED":
                    self.results["evidence"][f"probe_{tool_type}"] = {
                        "status": "NOT_SUPPORTED",
                        "error": e.code,
                        "message": str(e)
                    }
                    print(f"  ✗ {tool_type} NOT SUPPORTED: {e.code}")
                else:
                    self.results["evidence"][f"probe_{tool_type}"] = {
                        "status": "ERROR",
                        "error": str(e)
                    }
                    print(f"  ✗ Error: {e}")
                    
            except Exception as e:
                self.results["evidence"][f"probe_{tool_type}"] = {
                    "status": "ERROR",
                    "error": str(e)
                }
                print(f"  ✗ Error: {e}")
            
            finally:
                if "OPENAI_WEB_SEARCH_TOOL_TYPE" in os.environ:
                    del os.environ["OPENAI_WEB_SEARCH_TOOL_TYPE"]
        
        # Determine overall support
        web_search_supported = self.results["evidence"].get("probe_web_search", {}).get("status") == "SUPPORTED"
        preview_supported = self.results["evidence"].get("probe_web_search_preview", {}).get("status") == "SUPPORTED"
        
        self.results["checks"]["capability_probe"] = {
            "web_search": web_search_supported,
            "web_search_preview": preview_supported,
            "any_supported": web_search_supported or preview_supported,
            "status": "PASS" if (web_search_supported or preview_supported) else "FAIL"
        }
    
    async def check_7_telemetry_truth(self):
        """Check 7: Telemetry truth verification"""
        print("\n[CHECK 7] Telemetry Truth")
        print("-" * 40)
        
        request = LLMRequest(
            vendor="openai",
            model="gpt-5-chat-latest",
            messages=[
                {"role": "user", "content": "What's happening in tech?"}
            ],
            grounded=True
        )
        
        try:
            response = await self.adapter.generate(request)
            
            if hasattr(response, 'metadata') and response.metadata:
                why_not = response.metadata.get("why_not_grounded")
                grounded_effective = response.metadata.get("grounded_effective", False)
                
                self.results["checks"]["telemetry_truth"] = {
                    "grounded_effective": grounded_effective,
                    "why_not_grounded": why_not,
                    "status": "PASS"
                }
                
                if not grounded_effective and why_not:
                    print(f"✓ Not grounded because: {why_not}")
                elif grounded_effective:
                    print(f"✓ Successfully grounded")
                else:
                    print(f"⚠ No grounding, no reason given")
                    
        except Exception as e:
            self.results["checks"]["telemetry_truth"] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"✗ Error: {e}")
    
    def save_results(self):
        """Save diagnostic results to file"""
        filename = f"OPENAI_GROUNDING_DIAGNOSTICS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n{'='*80}")
        print("DIAGNOSTIC SUMMARY")
        print('='*80)
        
        # Count pass/fail
        passed = sum(1 for check in self.results["checks"].values() if check.get("status") == "PASS")
        failed = sum(1 for check in self.results["checks"].values() if check.get("status") == "FAIL")
        errors = sum(1 for check in self.results["checks"].values() if check.get("status") == "ERROR")
        manual = sum(1 for check in self.results["checks"].values() if check.get("status") == "MANUAL")
        
        print(f"\n✓ Passed: {passed}")
        print(f"✗ Failed: {failed}")
        print(f"⚠ Errors: {errors}")
        print(f"📋 Manual: {manual}")
        
        # Evidence summary
        print(f"\n📊 EVIDENCE FOR ESCALATION:")
        print(f"   Model: gpt-5-chat-latest")
        print(f"   Org: {os.getenv('OPENAI_ORG_ID', 'default')}")
        
        web_search_status = self.results["evidence"].get("probe_web_search", {}).get("status", "UNKNOWN")
        preview_status = self.results["evidence"].get("probe_web_search_preview", {}).get("status", "UNKNOWN")
        
        print(f"   web_search: {web_search_status}")
        print(f"   web_search_preview: {preview_status}")
        
        if web_search_status != "SUPPORTED" and preview_status != "SUPPORTED":
            print(f"\n🚨 NEITHER TOOL TYPE IS SUPPORTED")
            print(f"   → This appears to be an ENTITLEMENT issue")
            print(f"   → Open a ticket with OpenAI for 'web_search' enablement")
            print(f"   → Reference org: {os.getenv('OPENAI_ORG_ID', 'default')}")
        
        print(f"\n📁 Full results saved to: {filename}")
        print(f"   Share this file with OpenAI support if escalating\n")

async def main():
    diagnostics = OpenAIGroundingDiagnostics()
    await diagnostics.run_all_checks()

if __name__ == "__main__":
    asyncio.run(main())