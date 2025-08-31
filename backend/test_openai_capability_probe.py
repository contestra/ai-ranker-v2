#!/usr/bin/env venv/bin/python
"""
Simplified OpenAI web_search capability probe
Tests if the org/model combination supports web_search tools
"""

import asyncio
import os
import json
from datetime import datetime
from openai import AsyncOpenAI

# Enable debug output
os.environ["OPENAI_WIRE_DEBUG"] = "true"

async def test_tool_support():
    """Test which web_search variants are supported"""
    
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": "gpt-5-chat-latest",
        "org": os.getenv("OPENAI_ORG_ID", "default"),
        "tools_tested": {}
    }
    
    print("\n" + "="*80)
    print("OpenAI Web Search Capability Probe")
    print("="*80)
    print(f"\nModel: gpt-5-chat-latest")
    print(f"Org: {results['org']}")
    print(f"Testing tool support...\n")
    
    # Test each tool variant
    for tool_type in ["web_search", "web_search_preview"]:
        print(f"\nTesting {tool_type}...")
        
        try:
            # Minimal request with tool attached
            response = await client.chat.completions.create(
                model="gpt-5-chat-latest",
                messages=[{"role": "user", "content": "test"}],
                tools=[{"type": tool_type}],
                tool_choice="auto",
                max_tokens=10
            )
            
            results["tools_tested"][tool_type] = {
                "status": "SUPPORTED",
                "response_id": response.id if hasattr(response, 'id') else None
            }
            print(f"  ✓ {tool_type} SUPPORTED")
            
        except Exception as e:
            error_str = str(e)
            
            # Check for specific error patterns
            if "not supported" in error_str.lower() or "400" in error_str:
                results["tools_tested"][tool_type] = {
                    "status": "NOT_SUPPORTED",
                    "error": error_str[:200]  # First 200 chars
                }
                print(f"  ✗ {tool_type} NOT SUPPORTED")
            else:
                results["tools_tested"][tool_type] = {
                    "status": "ERROR",
                    "error": error_str[:200]
                }
                print(f"  ✗ {tool_type} ERROR: {error_str[:100]}")
    
    # Now test Responses API
    print(f"\n\nTesting Responses API with tools...")
    
    for tool_type in ["web_search", "web_search_preview"]:
        print(f"\nTesting Responses API with {tool_type}...")
        
        try:
            # Test responses endpoint
            import httpx
            
            headers = {
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                "Content-Type": "application/json"
            }
            
            if os.getenv("OPENAI_ORG_ID"):
                headers["OpenAI-Organization"] = os.getenv("OPENAI_ORG_ID")
            
            payload = {
                "model": "gpt-5-chat-latest",
                "input": "test",
                "instructions": "Reply with 'ok'",
                "tools": [{"type": tool_type}],
                "tool_choice": "auto",
                "max_output_tokens": 16
            }
            
            async with httpx.AsyncClient() as http_client:
                response = await http_client.post(
                    "https://api.openai.com/v1/responses",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    results["tools_tested"][f"responses_{tool_type}"] = {
                        "status": "SUPPORTED",
                        "response_id": response.json().get("id")
                    }
                    print(f"  ✓ Responses API + {tool_type} SUPPORTED")
                else:
                    error_body = response.text[:500]
                    results["tools_tested"][f"responses_{tool_type}"] = {
                        "status": "NOT_SUPPORTED" if response.status_code == 400 else "ERROR",
                        "status_code": response.status_code,
                        "error": error_body
                    }
                    print(f"  ✗ Responses API + {tool_type} returned {response.status_code}")
                    
        except Exception as e:
            results["tools_tested"][f"responses_{tool_type}"] = {
                "status": "ERROR",
                "error": str(e)[:200]
            }
            print(f"  ✗ Responses API + {tool_type} ERROR: {str(e)[:100]}")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    chat_web_search = results["tools_tested"].get("web_search", {}).get("status")
    chat_preview = results["tools_tested"].get("web_search_preview", {}).get("status")
    resp_web_search = results["tools_tested"].get("responses_web_search", {}).get("status")
    resp_preview = results["tools_tested"].get("responses_web_search_preview", {}).get("status")
    
    print(f"\nChat Completions API:")
    print(f"  web_search: {chat_web_search}")
    print(f"  web_search_preview: {chat_preview}")
    
    print(f"\nResponses API:")
    print(f"  web_search: {resp_web_search}")
    print(f"  web_search_preview: {resp_preview}")
    
    # Determine if ANY tool works
    any_supported = any(
        status == "SUPPORTED" 
        for test in results["tools_tested"].values() 
        if isinstance(test, dict) and test.get("status") == "SUPPORTED"
    )
    
    if not any_supported:
        print("\n" + "🚨"*40)
        print("\n🚨 NO WEB SEARCH TOOLS ARE SUPPORTED ON THIS ORG/MODEL")
        print("🚨 This is an ENTITLEMENT issue, not a code issue")
        print("🚨 Action: Open ticket with OpenAI for web_search enablement")
        print(f"🚨 Reference: Org={results['org']}, Model=gpt-5-chat-latest")
        print("\n" + "🚨"*40)
    else:
        print("\n✅ At least one web search variant is supported")
        print("   The adapter should be able to use grounding")
    
    # Save results
    filename = f"OPENAI_CAPABILITY_PROBE_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📁 Results saved to: {filename}\n")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_tool_support())