#!/usr/bin/env python3
"""
Test health and wellness prompt with google-genai grounding.
"""
import asyncio
import os
import json
from datetime import datetime

# Set up environment
os.environ["VERTEX_PROJECT"] = os.getenv("VERTEX_PROJECT", os.getenv("GCP_PROJECT", "contestra-ai"))
os.environ["VERTEX_LOCATION"] = os.getenv("VERTEX_LOCATION", "europe-west4")

from google import genai
from google.genai.types import (
    GenerateContentConfig,
    Tool,
    GoogleSearch,
    ToolConfig,
    FunctionCallingConfig,
    SafetySetting,
    HarmCategory,
    HarmBlockThreshold
)


async def test_health_wellness_prompt():
    """Test health and wellness prompt with grounding."""
    print("="*60)
    print("Testing Health & Wellness Prompt - August 2025")
    print("="*60)
    
    try:
        # Initialize client
        print("\n1. Initializing google-genai client...")
        client = genai.Client(
            vertexai=True,
            project=os.environ["VERTEX_PROJECT"],
            location=os.environ["VERTEX_LOCATION"]
        )
        print("✅ Client initialized")
        
        # System instruction
        system_instruction = "You are a helpful AI assistant. Use web search to provide accurate, up-to-date information about current events."
        
        # Configure tools for grounding
        tools = [
            Tool(google_search=GoogleSearch())
        ]
        
        # Tool config for aggressive grounding
        tool_config = ToolConfig(
            function_calling_config=FunctionCallingConfig(
                mode="ANY"  # Aggressive tool use
            )
        )
        
        # Safety settings
        safety_settings = [
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.BLOCK_NONE
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.BLOCK_NONE
            )
        ]
        
        # Create generation config with tools embedded
        config = GenerateContentConfig(
            systemInstruction=system_instruction,
            temperature=0.7,
            maxOutputTokens=3000,
            tools=tools,
            toolConfig=tool_config,
            safetySettings=safety_settings
        )
        
        # Test prompt
        prompt = "give me a summary of health and wellness news during August 2025"
        
        print("\n2. Sending grounded request...")
        print(f"   Prompt: {prompt}")
        print(f"   Model: gemini-2.5-pro")
        print(f"   Grounding: Enabled (GoogleSearch)")
        
        # Execute request
        print("\n3. Waiting for response...")
        start_time = datetime.now()
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="publishers/google/models/gemini-2.5-pro",
                contents=prompt,
                config=config
            )
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print(f"\n✅ Response received in {elapsed:.1f} seconds")
        print("="*60)
        
        # Extract response text
        response_text = ""
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'text'):
                        response_text = part.text
                        break
        
        print("\nRESPONSE:")
        print("-"*60)
        print(response_text)
        print("-"*60)
        
        # Check grounding metadata
        grounding_info = {
            "detected": False,
            "queries": [],
            "chunks": 0,
            "supports": 0
        }
        
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                grounding_info["detected"] = True
                
                if hasattr(candidate.grounding_metadata, 'web_search_queries'):
                    queries = candidate.grounding_metadata.web_search_queries
                    if queries:
                        grounding_info["queries"] = list(queries)
                
                if hasattr(candidate.grounding_metadata, 'grounding_chunks'):
                    chunks = candidate.grounding_metadata.grounding_chunks
                    if chunks:
                        grounding_info["chunks"] = len(chunks)
                
                if hasattr(candidate.grounding_metadata, 'grounding_supports'):
                    supports = candidate.grounding_metadata.grounding_supports
                    if supports:
                        grounding_info["supports"] = len(supports)
        
        print("\nGROUNDING METADATA:")
        print("-"*60)
        if grounding_info["detected"]:
            print("✅ Grounding successful!")
            print(f"   Web searches performed: {len(grounding_info['queries'])}")
            if grounding_info["queries"]:
                print("   Search queries:")
                for q in grounding_info["queries"][:5]:
                    print(f"     - {q}")
            print(f"   Grounding chunks: {grounding_info['chunks']}")
            print(f"   Grounding supports: {grounding_info['supports']}")
        else:
            print("❌ No grounding metadata detected")
        
        print("\n" + "="*60)
        print("TEST COMPLETE")
        print("="*60)
        
        # Save results
        output_file = f"health_wellness_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "prompt": prompt,
                    "model": "gemini-2.5-pro",
                    "grounded": True
                },
                "response": {
                    "text": response_text,
                    "elapsed_seconds": elapsed
                },
                "grounding": grounding_info,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        print(f"\n📄 Results saved to: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_health_wellness_prompt())
    exit(0 if success else 1)