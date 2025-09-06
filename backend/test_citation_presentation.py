#!/usr/bin/env python3
"""Test citation presentation for UI domain capping."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.unified_llm_adapter import present_citations_for_ui, _domain_key, _is_tier1


def test_domain_key_extraction():
    """Test eTLD+1 domain key extraction."""
    print("Test 1: Domain key extraction...")
    
    # Test normal domains
    assert _domain_key("https://example.com/path") == "example.com"
    assert _domain_key("https://www.example.com/path") == "example.com"
    assert _domain_key("https://subdomain.example.com/path") == "example.com"
    
    # Test edge cases
    assert _domain_key("https://localhost:8080/path") == "localhost:8080"
    assert _domain_key("invalid-url") == "unknown"
    assert _domain_key("") == "unknown"
    
    print("✅ Domain key extraction works correctly")


def test_tier1_detection():
    """Test tier-1 authority domain detection."""
    print("\nTest 2: Tier-1 domain detection...")
    
    # Test tier-1 domains
    assert _is_tier1("https://who.int/health") == True
    assert _is_tier1("https://nih.gov/research") == True
    assert _is_tier1("https://nejm.org/articles") == True
    assert _is_tier1("https://nature.com/articles") == True
    
    # Test .gov/.edu suffixes
    assert _is_tier1("https://cdc.gov/data") == True
    assert _is_tier1("https://harvard.edu/info") == True
    
    # Test non-tier1 domains
    assert _is_tier1("https://example.com/page") == False
    assert _is_tier1("https://blog.example.org/post") == False
    
    print("✅ Tier-1 domain detection works correctly")


def test_same_domain_spam_scenario():
    """Test A: Same-domain spam (UI) scenario."""
    print("\nTest 3: Same-domain spam scenario...")
    
    # Input: deduped citations with 3 from example.com, 2 from example.org, 1 from who.int
    final_citations = [
        {"url": "https://example.com/page1", "title": "Page 1"},
        {"url": "https://example.com/page2", "title": "Page 2"},
        {"url": "https://example.com/page3", "title": "Page 3"},
        {"url": "https://example.org/article1", "title": "Article 1"},
        {"url": "https://example.org/article2", "title": "Article 2"},
        {"url": "https://who.int/health-data", "title": "WHO Health Data"},
    ]
    
    # UI list should return ≤1 per domain by default
    presented = present_citations_for_ui(final_citations)
    
    # Check domain distribution
    domains = [_domain_key(c.get("url", "")) for c in presented]
    domain_counts = {}
    for d in domains:
        domain_counts[d] = domain_counts.get(d, 0) + 1
    
    print(f"Presented citations: {len(presented)}")
    print(f"Domain distribution: {domain_counts}")
    
    # Should have at most 1 per domain (with tier-1 preservation)
    for domain, count in domain_counts.items():
        if domain != "who.int":  # who.int might get preserved as tier-1
            assert count <= 1, f"Domain {domain} has {count} citations (expected ≤1)"
    
    # Ensure who.int appears (tier-1 authority)
    who_present = any("who.int" in c.get("url", "") for c in presented)
    assert who_present, "WHO (tier-1) should be preserved"
    
    print("✅ Same-domain spam scenario handled correctly")


def test_official_tier1_preservation():
    """Test B: Ensure official + tier-1 presence (when available)."""
    print("\nTest 4: Official + tier-1 preservation...")
    
    # Test with official domain
    citations_with_official = [
        {"url": "https://example.com/page1", "title": "Page 1"},
        {"url": "https://example.com/page2", "title": "Page 2"},
        {"url": "https://brand.com/official", "title": "Official Brand", "is_official_domain": True},
        {"url": "https://another.com/page", "title": "Another Page"},
    ]
    
    presented = present_citations_for_ui(citations_with_official, per_domain_cap=1)
    
    # Should include official domain even with per-domain cap
    official_present = any(c.get("is_official_domain") for c in presented)
    assert official_present, "Official domain should be preserved"
    
    print("✅ Official domain preserved")
    
    # Test with tier-1 authority
    citations_with_tier1 = [
        {"url": "https://example.com/page1", "title": "Page 1"},
        {"url": "https://example.com/page2", "title": "Page 2"},
        {"url": "https://example.com/page3", "title": "Page 3"},
        {"url": "https://nih.gov/research", "title": "NIH Research"},
    ]
    
    presented = present_citations_for_ui(citations_with_tier1, per_domain_cap=1)
    
    # Should include tier-1 domain
    tier1_present = any(_is_tier1(c.get("url", "")) for c in presented)
    assert tier1_present, "Tier-1 domain should be preserved"
    
    print("✅ Tier-1 domain preserved")
    
    # Test with both official and tier-1
    citations_mixed = [
        {"url": "https://example.com/page1", "title": "Page 1"},
        {"url": "https://brand.com/official", "title": "Official Brand", "is_official_domain": True},
        {"url": "https://who.int/health", "title": "WHO Health"},
        {"url": "https://random.org/page", "title": "Random Page"},
    ]
    
    presented = present_citations_for_ui(citations_mixed, per_domain_cap=1)
    
    official_present = any(c.get("is_official_domain") for c in presented)
    tier1_present = any(_is_tier1(c.get("url", "")) for c in presented)
    
    assert official_present, "Official domain should be preserved in mixed scenario"
    assert tier1_present, "Tier-1 domain should be preserved in mixed scenario"
    
    print("✅ Both official and tier-1 domains preserved in mixed scenario")


def test_ranking_order():
    """Test citation ranking: official → tier1 → others."""
    print("\nTest 5: Citation ranking order...")
    
    citations = [
        {"url": "https://random.com/page", "title": "Random Page"},
        {"url": "https://who.int/health", "title": "WHO Health"},  # tier-1
        {"url": "https://brand.com/official", "title": "Official Brand", "is_official_domain": True},  # official
        {"url": "https://another.com/page", "title": "Another Page"},
    ]
    
    presented = present_citations_for_ui(citations, per_domain_cap=4, max_total=4)
    
    # First should be official
    assert presented[0].get("is_official_domain") == True, "First should be official domain"
    
    # Second should be tier-1 (WHO)
    assert _is_tier1(presented[1].get("url", "")), "Second should be tier-1 domain"
    
    print("✅ Citation ranking works correctly (official → tier-1 → others)")


def test_max_total_limit():
    """Test global max_total limit."""
    print("\nTest 6: Max total limit...")
    
    citations = [{"url": f"https://example{i}.com/page", "title": f"Page {i}"} for i in range(15)]
    
    presented = present_citations_for_ui(citations, per_domain_cap=5, max_total=8)
    
    assert len(presented) <= 8, f"Should respect max_total=8, got {len(presented)}"
    
    print("✅ Max total limit respected")


def test_empty_input():
    """Test edge case: empty input."""
    print("\nTest 7: Empty input...")
    
    presented = present_citations_for_ui([])
    assert presented == [], "Empty input should return empty list"
    
    print("✅ Empty input handled correctly")


if __name__ == "__main__":
    test_domain_key_extraction()
    test_tier1_detection()
    test_same_domain_spam_scenario()
    test_official_tier1_preservation()
    test_ranking_order()
    test_max_total_limit()
    test_empty_input()
    
    print("\n" + "="*60)
    print("✅ ALL CITATION PRESENTATION TESTS PASSED")
    print("="*60)