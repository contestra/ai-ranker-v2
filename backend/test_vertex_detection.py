#!/usr/bin/env python3
"""
Test the Vertex/Gemini two-step grounding detection.
"""

import sys
import json

# Add backend to path
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.llm.tool_detection import (
    detect_vertex_grounding_usage,
    extract_vertex_sources,
    attest_two_step_vertex,
    normalize_tool_detection
)

def test_vertex_source_extraction():
    """Test URL extraction from various Vertex response shapes"""
    
    print("=" * 60)
    print("Testing Vertex Source Extraction")
    print("=" * 60)
    
    # Test case 1: Standard groundingMetadata with web sources
    response1 = {
        "groundingMetadata": {
            "sources": [
                {"web": {"uri": "https://example1.com"}},
                {"web": {"uri": "https://example2.com"}}
            ]
        }
    }
    
    urls = extract_vertex_sources(response1)
    print(f"\nTest 1 - Standard groundingMetadata:")
    print(f"  URLs: {urls}")
    assert len(urls) == 2
    assert "https://example1.com" in urls
    
    # Test case 2: Citations format
    response2 = {
        "citations": [
            {"url": "https://example3.com", "title": "Source 3"},
            {"uri": "https://example4.com", "title": "Source 4"},
            {"link": "https://example5.com"}
        ]
    }
    
    urls = extract_vertex_sources(response2)
    print(f"\nTest 2 - Citations format:")
    print(f"  URLs: {urls}")
    assert len(urls) == 3
    
    # Test case 3: Nested grounding_chunks
    response3 = {
        "grounding_metadata": {
            "grounding_chunks": [
                {"web": {"uri": "https://example6.com", "domain": "example6.com"}},
                {"web": {"url": "https://example7.com"}}
            ]
        }
    }
    
    urls = extract_vertex_sources(response3)
    print(f"\nTest 3 - Grounding chunks:")
    print(f"  URLs: {urls}")
    assert len(urls) == 2
    
    print("\n✅ Source extraction tests passed!")

def test_vertex_detection():
    """Test Vertex grounding detection"""
    
    print("\n" + "=" * 60)
    print("Testing Vertex Grounding Detection")
    print("=" * 60)
    
    # Test case 1: Response with grounding_metadata
    response1 = {
        "grounding_metadata": {
            "grounding_chunks": [
                {"web": {"uri": "https://example.com"}}
            ]
        },
        "content": "Response text"
    }
    
    tools_used, signal_count, signals, source_urls = detect_vertex_grounding_usage(response=response1)
    print(f"\nTest 1 - With grounding_metadata:")
    print(f"  Tools used: {tools_used}")
    print(f"  Signal count: {signal_count}")
    print(f"  Signals: {signals}")
    print(f"  Sources: {source_urls}")
    assert tools_used == True
    assert "grounding_metadata" in signals
    assert len(source_urls) == 1
    
    # Test case 2: Response with citations
    response2 = {
        "candidates": [{
            "citations": [
                {"uri": "https://example.com"},
                {"url": "https://example2.com"}
            ]
        }]
    }
    
    tools_used, signal_count, signals, source_urls = detect_vertex_grounding_usage(response=response2)
    print(f"\nTest 2 - With citations:")
    print(f"  Tools used: {tools_used}")
    print(f"  Signals: {signals}")
    print(f"  Sources: {source_urls}")
    assert tools_used == True
    assert "citations" in signals
    
    # Test case 3: No grounding
    response3 = {
        "content": "Simple response without grounding"
    }
    
    tools_used, signal_count, signals, source_urls = detect_vertex_grounding_usage(response=response3)
    print(f"\nTest 3 - No grounding:")
    print(f"  Tools used: {tools_used}")
    print(f"  Signals: {signals}")
    print(f"  Sources: {source_urls}")
    assert tools_used == False
    assert len(signals) == 0
    
    print("\n✅ Detection tests passed!")

def test_two_step_attestation():
    """Test two-step contract validation"""
    
    print("\n" + "=" * 60)
    print("Testing Two-Step Attestation")
    print("=" * 60)
    
    # Test case 1: Valid two-step (Step 1 has grounding, Step 2 doesn't)
    step1 = {
        "grounding_metadata": {
            "grounding_chunks": [
                {"web": {"uri": "https://example.com"}}
            ]
        }
    }
    step2 = {
        "content": '{"result": "processed"}'
    }
    
    attestation = attest_two_step_vertex(
        step1_response=step1,
        step2_response=step2
    )
    
    print(f"\nTest 1 - Valid two-step:")
    print(f"  {json.dumps(attestation, indent=2)}")
    assert attestation["contract_ok"] == True
    assert attestation["step1_tools_used"] == True
    assert attestation["step2_tools_used"] == False
    
    # Test case 2: Invalid - Step 2 has grounding
    step2_bad = {
        "grounding_metadata": {"chunks": []},
        "content": '{"result": "processed"}'
    }
    
    attestation = attest_two_step_vertex(
        step1_response=step1,
        step2_response=step2_bad
    )
    
    print(f"\nTest 2 - Invalid (Step 2 has grounding):")
    print(f"  Contract OK: {attestation['contract_ok']}")
    print(f"  Step 2 tools: {attestation['step2_tools_used']}")
    assert attestation["contract_ok"] == False
    assert attestation["step2_tools_used"] == True
    
    # Test case 3: Invalid - Step 1 has no sources
    step1_no_sources = {
        "grounding_metadata": {
            "grounding_chunks": []
        }
    }
    
    attestation = attest_two_step_vertex(
        step1_response=step1_no_sources,
        step2_response=step2
    )
    
    print(f"\nTest 3 - Invalid (Step 1 no sources):")
    print(f"  Contract OK: {attestation['contract_ok']}")
    print(f"  Step 1 sources: {attestation['step1_sources_count']}")
    assert attestation["contract_ok"] == False
    assert attestation["step1_sources_count"] == 0
    
    print("\n✅ Two-step attestation tests passed!")

def test_normalized_vertex():
    """Test normalized detection for Vertex"""
    
    print("\n" + "=" * 60)
    print("Testing Normalized Vertex Detection")
    print("=" * 60)
    
    response = {
        "grounding_metadata": {
            "grounding_chunks": [
                {"web": {"uri": "https://example1.com"}},
                {"web": {"uri": "https://example2.com"}}
            ]
        }
    }
    
    result = normalize_tool_detection("vertex", response=response)
    print(f"  {json.dumps(result, indent=2)}")
    
    assert result["tools_used"] == True
    assert result["vendor_specific"]["source_count"] == 2
    assert "grounding_metadata" in result["vendor_specific"]["signals"]
    
    print("\n✅ Normalized detection test passed!")

if __name__ == "__main__":
    test_vertex_source_extraction()
    test_vertex_detection()
    test_two_step_attestation()
    test_normalized_vertex()
    
    print("\n" + "=" * 60)
    print("🎉 All Vertex detection tests passed!")
    print("=" * 60)