#!/usr/bin/env python3
"""Test model normalization for failover scenarios."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter
from app.llm.adapters.gemini_adapter import GeminiAdapter

def test_model_normalization():
    print("=" * 80)
    print("Testing Model Normalization for Failover")
    print("=" * 80)
    
    # Initialize adapters
    router = UnifiedLLMAdapter()
    vertex = VertexAdapter()
    gemini = GeminiAdapter()
    
    # Test cases with various model formats
    test_models = [
        "gemini-2.5-pro",
        "models/gemini-2.5-pro",
        "publishers/google/models/gemini-2.5-pro",
        "gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "publishers/google/models/gemini-1.5-pro",
        "gemini-1.5-pro-002",
        "models/gemini-2.5-pro-experimental",
    ]
    
    print("\n1. Vertex Adapter Normalization (_normalize_for_validation):")
    print("-" * 60)
    for model in test_models:
        normalized = vertex._normalize_for_validation(model)
        print(f"  {model:45} -> {normalized}")
    
    print("\n2. Gemini Adapter Normalization (_normalize_for_sdk):")
    print("-" * 60)
    for model in test_models:
        normalized = gemini._normalize_for_sdk(model)
        print(f"  {model:45} -> {normalized}")
    
    print("\n3. Router's _get_bare_model_name for Vertex:")
    print("-" * 60)
    for model in test_models:
        bare = router._get_bare_model_name(model, "vertex")
        print(f"  {model:45} -> {bare}")
    
    print("\n4. Router's _get_bare_model_name for Gemini Direct:")
    print("-" * 60)
    for model in test_models:
        bare = router._get_bare_model_name(model, "gemini_direct")
        print(f"  {model:45} -> {bare}")
    
    print("\n5. Failover Scenario (Gemini Direct -> Vertex):")
    print("-" * 60)
    print("Simulating failover model transformation using Vertex adapter normalization:")
    for model in test_models:
        # This is what happens during failover
        vertex_model = vertex._normalize_for_validation(model)
        print(f"  Gemini: {model:35} -> Vertex: {vertex_model}")
    
    # Test edge cases
    print("\n6. Edge Cases:")
    print("-" * 60)
    edge_cases = [
        "gemini",  # Missing version
        "2.5-pro",  # Missing 'gemini' prefix
        "publishers/google/models/bison-001",  # Non-gemini model
        "",  # Empty string
    ]
    
    for model in edge_cases:
        try:
            vertex_norm = vertex._normalize_for_validation(model)
            gemini_norm = gemini._normalize_for_sdk(model)
            print(f"  {model:30} -> Vertex: {vertex_norm:35} Gemini: {gemini_norm}")
        except Exception as e:
            print(f"  {model:30} -> Error: {str(e)[:50]}")

if __name__ == "__main__":
    test_model_normalization()