#!/usr/bin/env python3
"""Test Google citation extraction with edge cases."""

import sys
from pathlib import Path
from urllib.parse import urlencode, quote

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.adapters._google_base_adapter import _normalize_url, _decode_vertex_redirect

def test_url_edge_cases():
    print("=" * 80)
    print("Testing Google Citation URL Edge Cases")
    print("=" * 80)
    
    print("\n1. Testing URL normalization with special characters:")
    print("-" * 60)
    
    # Test cases with special characters and multiple values
    test_urls = [
        # URL with spaces and special chars in params
        "https://example.com/search?q=health+news&category=medical&utm_source=google",
        
        # URL with multiple values for same param
        "https://example.com/page?tag=health&tag=wellness&tag=2025&utm_campaign=test",
        
        # URL with encoded characters
        "https://example.com/article?title=Health%20%26%20Wellness&author=John%20Doe",
        
        # URL with fragment and mixed case host
        "https://Example.COM/news#section2?utm_medium=social&topic=health",
        
        # URL with empty param values
        "https://example.com/search?q=&category=health&filter=",
        
        # URL with unicode characters (encoded)
        "https://example.com/search?q=" + quote("健康ニュース") + "&lang=ja",
    ]
    
    for url in test_urls:
        normalized = _normalize_url(url)
        print(f"Original:   {url}")
        print(f"Normalized: {normalized}")
        print()
    
    print("\n2. Testing Vertex redirect decoding:")
    print("-" * 60)
    
    # Simulate various redirect formats
    redirect_urls = [
        # Standard redirect with encoded URL
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG=" + 
        "?url=" + quote("https://health.com/article"),
        
        # Redirect with URL in path segment
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/" +
        quote("https://medical.org/news"),
        
        # Redirect with multiple encoding layers
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABC123" +
        "?target=" + quote(quote("https://wellness.com/2025")),
        
        # Redirect with complex query params
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/XYZ" +
        "?u=" + quote("https://example.com/page?id=123&type=health"),
    ]
    
    for redirect in redirect_urls:
        resolved, original = _decode_vertex_redirect(redirect)
        print(f"Redirect: {redirect[:80]}...")
        print(f"Resolved: {resolved}")
        if original:
            print(f"Original: {original[:80]}...")
        print()
    
    print("\n3. Testing proper URL encoding with urlencode:")
    print("-" * 60)
    
    # Test that urlencode properly handles edge cases
    query_params = [
        # Multiple values for same key
        {"tags": ["health", "wellness", "2025"], "author": "John Doe"},
        
        # Special characters
        {"search": "health & wellness", "filter": "type=article"},
        
        # Empty values
        {"q": "", "category": "medical", "empty": ""},
        
        # Unicode
        {"query": "健康", "lang": "ja", "region": "JP"},
    ]
    
    for params in query_params:
        # Convert lists to proper format for urlencode
        flat_params = {}
        for k, v in params.items():
            if isinstance(v, list):
                flat_params[k] = v
            else:
                flat_params[k] = [v] if v else []
        
        encoded = urlencode(flat_params, doseq=True)
        print(f"Params: {params}")
        print(f"Encoded: {encoded}")
        print()
    
    print("\n4. Testing deduplication after normalization:")
    print("-" * 60)
    
    # URLs that should deduplicate to the same normalized form
    duplicate_sets = [
        [
            "https://Example.com/article?utm_source=google",
            "https://example.com/article",
            "https://example.com/article#section1",
        ],
        [
            "https://health.org/news?id=123&utm_campaign=test",
            "https://Health.ORG/news?id=123",
            "https://health.org/news?utm_medium=email&id=123",
        ]
    ]
    
    for url_set in duplicate_sets:
        normalized_set = [_normalize_url(url) for url in url_set]
        print(f"Original URLs:")
        for url in url_set:
            print(f"  - {url}")
        print(f"Normalized (should be identical):")
        for norm in normalized_set:
            print(f"  - {norm}")
        print(f"Deduplicated: {len(set(normalized_set))} unique")
        print()

if __name__ == "__main__":
    test_url_edge_cases()