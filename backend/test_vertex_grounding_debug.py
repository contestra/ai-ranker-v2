#!/usr/bin/env python3
"""
Deep debug of Vertex grounding metadata structure.
"""

import asyncio
import os
import sys
import json

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Vertex SDK directly
import vertexai
from vertexai.generative_models import GenerativeModel, Tool
from google.cloud import aiplatform
import google.generativeai as genai

async def test_vertex_sdk_direct():
    """Test Vertex SDK directly to see grounding metadata structure."""
    print("\n" + "="*60)
    print("TESTING VERTEX SDK DIRECTLY")
    print("="*60)
    
    # Initialize Vertex AI
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID")
    location = os.getenv("VERTEX_LOCATION", "us-central1")
    
    if not project_id:
        print("ERROR: No Google Cloud project configured")
        return
        
    vertexai.init(project=project_id, location=location)
    
    # Create model with grounding
    model = GenerativeModel("gemini-2.5-pro")
    
    # Enable grounding with Google Search
    from vertexai.generative_models import grounding
    google_search_grounding = grounding.Grounding(
        sources=[grounding.GoogleSearchRetrieval()]
    )
    
    try:
        # Generate with grounding
        response = model.generate_content(
            "What are the latest AI developments in December 2024?",
            tools=[google_search_grounding],
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 300
            }
        )
        
        print(f"Response generated successfully")
        
        # Examine the response structure
        if hasattr(response, 'candidates') and response.candidates:
            print(f"Number of candidates: {len(response.candidates)}")
            
            candidate = response.candidates[0]
            print(f"\nCandidate attributes: {[attr for attr in dir(candidate) if not attr.startswith('_')]}")
            
            # Check for grounding metadata
            if hasattr(candidate, 'grounding_metadata'):
                gm = candidate.grounding_metadata
                print(f"\nGrounding metadata found!")
                print(f"Type: {type(gm)}")
                print(f"Attributes: {[attr for attr in dir(gm) if not attr.startswith('_')]}")
                
                # Check for various citation fields
                for attr_name in ['grounding_attributions', 'grounding_chunks', 'web_search_queries', 
                                  'search_entry_point', 'grounding_supports', 'citations']:
                    if hasattr(gm, attr_name):
                        attr_val = getattr(gm, attr_name)
                        print(f"\n{attr_name}: {type(attr_val)}")
                        if attr_val:
                            if isinstance(attr_val, list):
                                print(f"  Length: {len(attr_val)}")
                                if len(attr_val) > 0:
                                    first_item = attr_val[0]
                                    print(f"  First item type: {type(first_item)}")
                                    if hasattr(first_item, '__dict__'):
                                        print(f"  First item attrs: {[a for a in dir(first_item) if not a.startswith('_')]}")
                                        
                                        # Check for web/uri fields
                                        if hasattr(first_item, 'web'):
                                            web = first_item.web
                                            print(f"  Web attrs: {[a for a in dir(web) if not a.startswith('_')]}")
                                            if hasattr(web, 'uri'):
                                                print(f"  Web URI: {web.uri[:100]}...")
                            else:
                                print(f"  Value: {str(attr_val)[:200]}...")
                
                # Try to convert to dict
                try:
                    gm_dict = gm.to_dict() if hasattr(gm, 'to_dict') else dict(gm)
                    print(f"\nGrounding metadata as dict:")
                    print(json.dumps(gm_dict, indent=2, default=str)[:1000])
                except Exception as e:
                    print(f"Could not convert to dict: {e}")
                    
            else:
                print("\nNo grounding_metadata attribute found")
                
        else:
            print("No candidates in response")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def test_genai_direct():
    """Test Google GenAI directly."""
    print("\n" + "="*60)
    print("TESTING GOOGLE GENAI DIRECTLY")
    print("="*60)
    
    api_key = os.getenv("GOOGLE_GENAI_API_KEY")
    if not api_key:
        print("Skipping - no GOOGLE_GENAI_API_KEY")
        return
        
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel("gemini-2.5-pro")
    
    try:
        # Generate with grounding using search
        response = model.generate_content(
            "What are the latest AI developments?",
            tools="google_search_retrieval",
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 300
            }
        )
        
        print(f"Response generated successfully")
        
        # Examine structure
        if hasattr(response, 'candidates') and response.candidates:
            print(f"Number of candidates: {len(response.candidates)}")
            
            candidate = response.candidates[0]
            print(f"\nCandidate attributes: {[attr for attr in dir(candidate) if not attr.startswith('_')]}")
            
            # Check for grounding metadata
            if hasattr(candidate, 'grounding_metadata'):
                gm = candidate.grounding_metadata
                print(f"\nGrounding metadata found!")
                print(f"Type: {type(gm)}")
                print(f"Attributes: {[attr for attr in dir(gm) if not attr.startswith('_')]}")
            else:
                print("\nNo grounding_metadata attribute found")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Run all tests."""
    await test_vertex_sdk_direct()
    await test_genai_direct()

if __name__ == "__main__":
    asyncio.run(main())