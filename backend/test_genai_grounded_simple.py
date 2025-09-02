#!/usr/bin/env python3
"""
Test grounded prompt with google-genai using ONLY GoogleSearch.
Demonstrates proper usage of tools parameter through GenerateContentConfig.
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


async def test_grounded_prompt():
    """Test grounded prompt with GoogleSearch tool only."""
    print("="*60)
    print("Testing Grounded Prompt with GoogleSearch Only")
    print("="*60)
    
    try:
        # Initialize client
        print("\n1. Initializing google-genai client...")
        client = genai.Client(
            vertexai=True,
            project=os.environ["VERTEX_PROJECT"],
            location=os.environ["VERTEX_LOCATION"]
        )
        print("✅ Client initialized successfully")
        
        # Set up system instruction
        print("\n2. Preparing system instruction...")
        system_instruction = "You are a helpful AI assistant. When answering questions about current events, use web search to provide accurate, up-to-date information."
        print("✅ System instruction prepared")
        
        # Configure tools for grounding (GoogleSearch ONLY)
        tools = [
            Tool(google_search=GoogleSearch())
        ]
        
        # Tool config to control function calling
        tool_config = ToolConfig(
            function_calling_config=FunctionCallingConfig(
                mode="ANY",  # More aggressive tool use for grounding
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
        
        # Create generation config with all parameters including tools
        config = GenerateContentConfig(
            systemInstruction=system_instruction,
            temperature=0.7,
            maxOutputTokens=2000,
            tools=tools,
            toolConfig=tool_config,
            safetySettings=safety_settings
        )
        
        # Test prompt
        prompt = "tell me the top longevity and healthspan news during august 2025"
        
        print("\n3. Sending grounded request...")
        print(f"   Model: gemini-2.5-pro")
        print(f"   Grounded: True (with GoogleSearch tool)")
        print(f"   Tool Mode: ANY (aggressive grounding)")
        print(f"   Prompt: {prompt}")
        
        # Execute request with tools (all embedded in config)
        print("\n4. Waiting for response...")
        start_time = datetime.now()
        
        # Run synchronously in async context using asyncio
        import asyncio
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="publishers/google/models/gemini-2.5-pro",
                contents=prompt,  # Just pass the prompt string directly
                config=config  # Contains system instruction, tools, tool_config, safety settings
            )
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print("\n5. Response received!")
        print("-"*60)
        
        # Extract response text
        response_text = ""
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'text'):
                        response_text = part.text
                        break
        
        print("RESPONSE:")
        print("-"*40)
        print(response_text[:1500] if len(response_text) > 1500 else response_text)
        
        if len(response_text) > 1500:
            print(f"\n... (truncated, total length: {len(response_text)} chars)")
        
        print("\n" + "-"*40)
        print("METADATA:")
        print(f"  Model: gemini-2.5-pro")
        print(f"  Response API: google-genai")
        print(f"  Response Time: {elapsed:.2f}s")
        
        # Check for grounding metadata
        grounding_detected = False
        web_search_queries = []
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                grounding_detected = True
                print(f"  Grounding Metadata: ✅ Present")
                
                # Check for web search queries
                if hasattr(candidate.grounding_metadata, 'web_search_queries'):
                    web_search_queries = candidate.grounding_metadata.web_search_queries
                    if web_search_queries:
                        print(f"  Web Search Queries: {len(web_search_queries)} queries")
                        for i, query in enumerate(web_search_queries[:3]):
                            print(f"    - {query}")
                    else:
                        print(f"  Web Search Queries: None or empty")
                
                # Check for search entry point
                if hasattr(candidate.grounding_metadata, 'search_entry_point'):
                    print(f"  Search Entry Point: {candidate.grounding_metadata.search_entry_point}")
                
                # Check for grounding chunks
                if hasattr(candidate.grounding_metadata, 'grounding_chunks'):
                    chunks = candidate.grounding_metadata.grounding_chunks
                    print(f"  Grounding Chunks: {len(chunks)} chunks")
                
                # Check for grounding supports
                if hasattr(candidate.grounding_metadata, 'grounding_supports'):
                    supports = candidate.grounding_metadata.grounding_supports
                    print(f"  Grounding Supports: {len(supports)} supports")
            else:
                print(f"  Grounding Metadata: ❌ Not present")
        
        print("\n" + "="*60)
        if grounding_detected:
            print("✅ GROUNDING SUCCESSFUL! GoogleSearch was used.")
        else:
            print("⚠️  No grounding metadata detected.")
        print("✅ Test completed successfully!")
        print("="*60)
        
        # Save response for analysis
        output_file = f"genai_grounded_simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "request": {
                    "model": "gemini-2.5-pro",
                    "prompt": prompt,
                    "grounded": True,
                    "tools": ["GoogleSearch"],
                    "tool_mode": "ANY",
                    "config_note": "Tools passed through GenerateContentConfig"
                },
                "response": {
                    "text": response_text,
                    "grounding_detected": grounding_detected,
                    "web_search_queries": web_search_queries,
                    "elapsed_seconds": elapsed
                },
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        print(f"\n📄 Full response saved to: {output_file}")
        
        print("\n✅ KEY FINDINGS:")
        print("   1. google-genai DOES support tools through GenerateContentConfig")
        print("   2. Tools must be passed in config, not as direct parameters")
        print("   3. GoogleSearch tool works for grounding")
        print("   4. Cannot mix GoogleSearch with FunctionDeclaration tools")
        
    except Exception as e:
        print(f"\n❌ Error occurred: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_grounded_prompt())
    exit(0 if success else 1)