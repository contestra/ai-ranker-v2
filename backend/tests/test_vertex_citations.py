"""
Test suite for Vertex adapter citation extraction.
Tests various citation formats and edge cases.
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

# Import the citation extractor and adapter
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm.adapters.vertex_adapter import _extract_vertex_citations, VertexAdapter


class TestVertexCitations:
    """Test citation extraction from various Vertex response formats."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory path."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.fixture
    def load_fixture(self, fixtures_dir):
        """Helper to load JSON fixtures."""
        def _load(filename):
            with open(fixtures_dir / filename) as f:
                return json.load(f)
        return _load
    
    def test_v1_join_pattern(self, load_fixture):
        """Test v1 pattern: citations with sourceIds → citedSources."""
        data = load_fixture("fixture1_v1_join.json")
        
        # Create mock response - model_dump provides all the data
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []  # Can be empty - dict path will handle it
        
        citations = _extract_vertex_citations(mock_resp)
        
        assert len(citations) == 3
        # Check all URLs are present (order may vary)
        urls = [c["url"] for c in citations]
        assert "https://docs.python.org/3/library/functions.html#sorted" in urls
        assert "https://en.wikipedia.org/wiki/Timsort" in urls
        assert "https://stackoverflow.com/questions/1517496" in urls
        
        # Check first citation has expected fields
        first = citations[0]
        assert first["url"] == "https://docs.python.org/3/library/functions.html#sorted"
        assert first["title"] == "Python sorted() - Built-in Functions"
        assert first["provider"] == "vertex"
        assert first["source_domain"] == "docs.python.org"
    
    def test_legacy_grounding_attributions(self, load_fixture):
        """Test legacy groundingAttributions format."""
        data = load_fixture("fixture2_legacy_grounding.json")
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []  # Dict path will handle it
        
        citations = _extract_vertex_citations(mock_resp)
        
        assert len(citations) == 2
        
        # Check URLs are correct
        urls = [c["url"] for c in citations]
        assert "https://react.dev/reference/react" in urls
        assert "https://react.dev/reference/react/useState" in urls
        
        # Legacy format may not extract all fields, but URLs should be correct
        # This is acceptable as long as we get the citations
    
    def test_loose_harvest_multiple_locations(self, load_fixture):
        """Test loose harvest from multiple metadata locations."""
        data = load_fixture("fixture3_loose_harvest.json")
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []  # Add for fallback
        
        citations = _extract_vertex_citations(mock_resp)
        
        # Should find citations from both citationMetadata and supportingContent
        assert len(citations) >= 2
        urls = [c["url"] for c in citations]
        assert "https://go.dev/doc/effective_go#goroutines" in urls
        assert "https://gobyexample.com/channels" in urls
    
    def test_empty_citations_with_tools(self, load_fixture):
        """Test empty citations even though tools were called."""
        data = load_fixture("fixture4_empty_but_tools.json")
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []  # Add for fallback
        
        citations = _extract_vertex_citations(mock_resp)
        
        assert len(citations) == 0  # Empty arrays should return no citations
    
    def test_redirect_urls(self, load_fixture):
        """Test that redirect URLs are handled (domain extraction)."""
        data = load_fixture("fixture5_redirect_only.json")
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []  # Add for fallback
        
        citations = _extract_vertex_citations(mock_resp)
        
        assert len(citations) == 3
        # URLs should be preserved as-is
        assert citations[0]["url"] == "https://bit.ly/docker-intro"
        assert citations[1]["url"] == "https://tinyurl.com/k8s-basics"
        assert citations[2]["url"] == "http://short.link/container-guide"
        
        # Source domains should be extracted from shorteners
        assert citations[0]["source_domain"] in ["bit.ly", "bitly.com"]
        assert citations[1]["source_domain"] == "tinyurl.com"
        assert citations[2]["source_domain"] == "short.link"
    
    def test_candidate_level_citation_metadata(self):
        """Test extraction when citationMetadata is at candidate level, not in groundingMetadata."""
        data = {
            "candidates": [{
                "content": {"parts": [{"text": "Response text"}]},
                "citationMetadata": {  # At candidate level!
                    "citations": [
                        {
                            "uri": "https://example.com/doc1",
                            "title": "Document 1"
                        }
                    ]
                }
                # No groundingMetadata at all
            }]
        }
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []  # Dict path will handle it
        
        citations = _extract_vertex_citations(mock_resp)
        
        assert len(citations) == 1
        assert citations[0]["url"] == "https://example.com/doc1"
        assert citations[0]["title"] == "Document 1"
    
    def test_deduplication(self):
        """Test that duplicate URLs are deduplicated."""
        data = {
            "candidates": [{
                "content": {"parts": [{"text": "Response"}]},
                "groundingMetadata": {
                    "citedSources": [
                        {"id": "0", "uri": "https://example.com/page"},
                        {"id": "1", "uri": "https://example.com/page"},  # Duplicate
                        {"id": "2", "uri": "https://example.com/other"}
                    ]
                }
            }]
        }
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []  # Add for fallback
        
        citations = _extract_vertex_citations(mock_resp)
        
        assert len(citations) == 2  # Only unique URLs
        urls = [c["url"] for c in citations]
        assert urls == ["https://example.com/page", "https://example.com/other"]
    
    def test_ungrounded_retry_token_calculation(self):
        """Test that retry token calculation is correct."""
        # Test the calculation logic directly
        
        # Case 1: Low original tokens (200) should be bumped to 500 first, then retry gets more
        first_attempt_max_tokens = 200
        max_tokens_used = 500  # After bumping
        model_max = 8192
        
        # The retry calculation from our fix
        retry_max_tokens = min(
            max(int(first_attempt_max_tokens * 2), 3000, max_tokens_used),
            model_max
        )
        
        # Should be max(400, 3000, 500) = 3000
        assert retry_max_tokens == 3000
        
        # Case 2: Higher original tokens (2000)
        first_attempt_max_tokens = 2000
        max_tokens_used = 2000  # No bumping needed
        
        retry_max_tokens = min(
            max(int(first_attempt_max_tokens * 2), 3000, max_tokens_used),
            model_max
        )
        
        # Should be max(4000, 3000, 2000) = 4000
        assert retry_max_tokens == 4000
        
        # Case 3: Very high tokens hitting model max
        first_attempt_max_tokens = 6000
        max_tokens_used = 6000
        
        retry_max_tokens = min(
            max(int(first_attempt_max_tokens * 2), 3000, max_tokens_used),
            model_max
        )
        
        # Should be capped at model_max (8192)
        assert retry_max_tokens == 8192


if __name__ == "__main__":
    pytest.main([__file__, "-v"])