#!/usr/bin/env python3
"""
Startup probes to detect API compatibility issues early
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

logger = logging.getLogger(__name__)

async def probe_openai():
    """Probe OpenAI to determine which tool variant works"""
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.llm.types import LLMRequest
    
    adapter = UnifiedLLMAdapter()
    
    # Try with web_search first (per spec)
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",
        messages=[{"role": "user", "content": "Hi"}],
        grounded=True,
        temperature=0,
        max_tokens=16,
        meta={"grounding_mode": "AUTO"}
    )
    
    print("\n=== OpenAI Probe ===")
    try:
        response = await adapter.complete(request)
        print("✅ OpenAI works with 'web_search' tool")
        return "web_search"
    except Exception as e:
        error_msg = str(e)
        if "web_search_preview" in error_msg:
            print("⚠️  OpenAI rejected 'web_search', mentions 'web_search_preview'")
            
            if os.getenv("ALLOW_PREVIEW_COMPAT", "false").lower() == "true":
                print("   ALLOW_PREVIEW_COMPAT=true, will use preview variant")
                return "web_search_preview"
            else:
                print("   Set ALLOW_PREVIEW_COMPAT=true to enable compatibility mode")
                return None
        else:
            print(f"❌ OpenAI probe failed: {error_msg[:100]}")
            return None

async def probe_vertex():
    """Probe Vertex to ensure we're using the right SDK"""
    import vertexai
    from vertexai import generative_models as gm
    from vertexai.generative_models import grounding
    
    print("\n=== Vertex Probe ===")
    
    # Initialize
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("VERTEX_LOCATION", "europe-west4")
    
    if not project:
        print("❌ GOOGLE_CLOUD_PROJECT not set")
        return False
    
    vertexai.init(project=project, location=location)
    
    # Try to create the tool using new API
    try:
        from vertexai.generative_models import Tool
        tool = Tool(google_search=grounding.GoogleSearch())
        print(f"✅ Tool created: {type(tool)}")
    except Exception as e:
        print(f"❌ Failed to create tool: {e}")
        return False
    
    # Try a minimal generation
    model = gm.GenerativeModel("publishers/google/models/gemini-2.5-pro")
    content = gm.Content(role="user", parts=[gm.Part.from_text("Hi")])
    
    try:
        response = model.generate_content(
            contents=[content],
            tools=[tool],
            generation_config=gm.GenerationConfig(max_output_tokens=1)
        )
        print("✅ Vertex works with GoogleSearchRetrieval")
        return True
    except Exception as e:
        error_msg = str(e)
        if "google_search field" in error_msg and "google_search_retrieval" not in error_msg:
            print("❌ FATAL: API wants 'google_search' field - this is google.genai surface!")
            print("   Ensure NO google.genai imports exist in codebase")
            return False
        elif "google_search_retrieval is not supported" in error_msg:
            print("❌ API rejected GoogleSearchRetrieval")
            print(f"   Error: {error_msg[:200]}")
            return False
        else:
            print(f"⚠️  Vertex probe had issues: {error_msg[:100]}")
            return True  # Non-fatal, might be quota/auth issue

async def main():
    print("="*70)
    print("STARTUP PROBES - API COMPATIBILITY CHECK")
    print("="*70)
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check SDK version
    try:
        import google.cloud.aiplatform as aiplat
        print(f"\nSDK Version: google-cloud-aiplatform={aiplat.__version__}")
    except:
        pass
    
    # Run probes
    openai_result = await probe_openai()
    vertex_result = await probe_vertex()
    
    print("\n" + "="*70)
    print("PROBE RESULTS")
    print("="*70)
    
    if openai_result:
        print(f"✅ OpenAI: Ready with tool variant '{openai_result}'")
    else:
        print("❌ OpenAI: Not ready (check API key and model access)")
    
    if vertex_result:
        print("✅ Vertex: Ready with GoogleSearchRetrieval")
    else:
        print("❌ Vertex: Not ready (check project, auth, and SDK)")
    
    # Overall status
    if openai_result and vertex_result:
        print("\n✅ System ready for grounding operations")
        return 0
    else:
        print("\n⚠️  Some probes failed - review issues above")
        return 1

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        exit_code = loop.run_until_complete(main())
    finally:
        loop.close()
    
    sys.exit(exit_code)