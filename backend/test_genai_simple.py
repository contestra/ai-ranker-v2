#!/usr/bin/env python3
"""
Simple test of google-genai grounded request.
"""
import os
os.environ["VERTEX_PROJECT"] = os.getenv("VERTEX_PROJECT", os.getenv("GCP_PROJECT", "contestra-ai"))
os.environ["VERTEX_LOCATION"] = os.getenv("VERTEX_LOCATION", "europe-west4")

from google import genai
from google.genai.types import (
    GenerateContentConfig, 
    Tool, 
    GoogleSearch,
    Content,
    Part
)

# Initialize client
print("Initializing google-genai client...")
client = genai.Client(
    vertexai=True,
    project=os.environ["VERTEX_PROJECT"],
    location=os.environ["VERTEX_LOCATION"]
)

# Create request
contents = [
    Content(
        role="user",
        parts=[Part(text="tell me the top longevity and healthspan news during august 2025")]
    )
]

config = GenerateContentConfig(
    temperature=0.7,
    max_output_tokens=2000
)

# Add grounding tool
tools = [Tool(google_search=GoogleSearch())]

print("Sending grounded request...")
try:
    # Try with tools
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=config,
        tools=tools
    )
    print("Success with tools!")
except Exception as e:
    print(f"Failed with tools: {e}")
    # Try without tools
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=contents,
            config=config
        )
        print("Success without tools!")
    except Exception as e2:
        print(f"Failed without tools: {e2}")
        exit(1)

# Extract response
if hasattr(response, 'candidates'):
    for candidate in response.candidates:
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            for part in candidate.content.parts:
                if hasattr(part, 'text'):
                    print("\nResponse text:")
                    print(part.text[:500])
                    break

print("\nTest complete!")