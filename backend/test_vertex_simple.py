#!/usr/bin/env python3
"""
Simple Vertex test without ADC
"""
import asyncio
import os
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

# Ensure no ADC is set
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
os.environ["GOOGLE_CLOUD_PROJECT"] = "contestra-ai"
os.environ["VERTEX_LOCATION"] = "europe-west4"
os.environ["DISABLE_PROXIES"] = "true"

print(f"Testing Vertex with:")
print(f"  PROJECT: {os.environ.get('GOOGLE_CLOUD_PROJECT')}")
print(f"  LOCATION: {os.environ.get('VERTEX_LOCATION')}")
print(f"  GOOGLE_APPLICATION_CREDENTIALS: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'NOT SET')}")

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_vertex():
    """Test Vertex without ADC"""
    
    adapter = UnifiedLLMAdapter()
    
    request = LLMRequest(
        vendor="vertex",
        model="publishers/google/models/gemini-2.5-pro",
        messages=[{"role": "user", "content": "Say 'hello' in one word"}],
        temperature=0.1,
        max_tokens=10
    )
    
    try:
        print("\nCalling Vertex API...")
        response = await adapter.complete(request)
        
        print(f"✅ Success!")
        print(f"Response: {response.content}")
        print(f"Vendor: {response.vendor}")
        print(f"Latency: {response.latency_ms}ms")
        
        if response.usage:
            print(f"Tokens: {response.usage}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        
        # Try to diagnose the auth issue
        import google.auth
        try:
            credentials, project = google.auth.default()
            print(f"\nAuth diagnostics:")
            print(f"  Credentials type: {type(credentials)}")
            print(f"  Project from auth: {project}")
        except Exception as auth_e:
            print(f"  Auth error: {auth_e}")
        
        return False

if __name__ == "__main__":
    success = asyncio.run(test_vertex())
    sys.exit(0 if success else 1)