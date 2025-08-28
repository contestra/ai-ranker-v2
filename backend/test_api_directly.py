#!/usr/bin/env python3
"""Test OpenAI and Vertex APIs directly to debug issues"""
import os
from dotenv import load_dotenv
load_dotenv()

print("Testing API compatibility...")

# Test 1: Check if OpenAI supports web_search_preview with gpt-5-chat-latest
print("\n1. Testing OpenAI with web_search_preview...")
from openai import OpenAI
client = OpenAI()

models_to_try = ["gpt-4.1", "gpt-5", "gpt-5-chat-latest"]
for model in models_to_try:
    try:
        print(f"\n  Trying model: {model}")
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search_preview"}],
            input="What is 2+2?",
            max_output_tokens=50
        )
        print(f"    ✅ Success with {model}")
        break
    except Exception as e:
        error_msg = str(e)[:150]
        if "not supported" in error_msg:
            print(f"    ❌ Tool not supported with {model}")
        else:
            print(f"    ❌ Error: {error_msg}")

# Test 2: Check what Vertex actually expects
print("\n2. Testing Vertex grounding approaches...")
import vertexai
from vertexai import generative_models as gm
from vertexai.generative_models import grounding

project = os.getenv("GOOGLE_CLOUD_PROJECT", "test-project")
location = os.getenv("VERTEX_LOCATION", "europe-west4")
vertexai.init(project=project, location=location)

model = gm.GenerativeModel("publishers/google/models/gemini-2.5-pro")

# Try the documented approach
print("\n  Trying GoogleSearchRetrieval approach...")
try:
    google_search = grounding.GoogleSearchRetrieval()
    tools = [gm.Tool.from_google_search_retrieval(google_search)]
    
    content = gm.Content(
        role="user",
        parts=[gm.Part.from_text("What is the capital of France?")]
    )
    
    response = model.generate_content(
        contents=[content],
        tools=tools,
        generation_config=gm.GenerationConfig(temperature=0.7, max_output_tokens=100)
    )
    print("    ✅ GoogleSearchRetrieval works!")
except Exception as e:
    error_msg = str(e)[:200]
    print(f"    ❌ Failed: {error_msg}")
    
    # If it mentions google_search field, that's a different API
    if "google_search field" in error_msg:
        print("\n  Note: The API wants 'google_search' field, which is from google.genai client")
        print("        But we're using vertexai SDK which has different API surface")

print("\nConclusion:")
print("- OpenAI: Check if gpt-5-chat-latest actually supports web search tools")
print("- Vertex: The error suggests API mismatch between vertexai SDK and backend service")