"""
Parametrized test suite for Vertex citation extraction.
Tests all canonical shapes and edge cases.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock

# Import the citation extractor and helpers
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm.adapters.vertex_adapter import _extract_vertex_citations
from tests.test_helpers import (
    create_vertex_response, 
    create_typed_none_dict_data_response,
    create_mixed_view_response
)


class TestVertexCitationsParametrized:
    """Comprehensive parametrized tests for citation extraction."""
    
    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory path."""
        return Path(__file__).parent / "fixtures"
    
    @pytest.mark.parametrize("fixture_file,expected_count,expected_urls,test_name", [
        # V1 JOIN pattern: citations with sourceIds → citedSources
        ("fixture1_v1_join.json", 3, [
            "https://docs.python.org/3/library/functions.html#sorted",
            "https://en.wikipedia.org/wiki/Timsort",
            "https://stackoverflow.com/questions/1517496"
        ], "v1_join"),
        
        # Legacy groundingAttributions
        ("fixture2_legacy_grounding.json", 2, [
            "https://react.dev/reference/react",
            "https://react.dev/reference/react/useState"
        ], "legacy_grounding"),
        
        # Loose harvest from multiple locations
        ("fixture3_loose_harvest.json", ">=2", [
            "https://go.dev/doc/effective_go#goroutines",
            "https://gobyexample.com/channels"
        ], "loose_harvest"),
        
        # Empty citations but tools called
        ("fixture4_empty_but_tools.json", 0, [], "empty_with_tools"),
        
        # Redirect URLs
        ("fixture5_redirect_only.json", 3, [
            "https://bit.ly/docker-intro",
            "https://tinyurl.com/k8s-basics",
            "http://short.link/container-guide"
        ], "redirect_urls"),
    ])
    def test_dict_only_path(self, fixtures_dir, fixture_file, expected_count, expected_urls, test_name):
        """Test extraction with dict-only path (no typed candidates)."""
        # Load fixture as pure dict
        with open(fixtures_dir / fixture_file) as f:
            data = json.load(f)
        
        # Use helper to create dict-only response
        mock_resp = create_vertex_response(dict_data=data)
        
        # Extract citations
        citations = _extract_vertex_citations(mock_resp)
        
        # Check count
        if isinstance(expected_count, str) and expected_count.startswith(">="):
            min_count = int(expected_count[2:])
            assert len(citations) >= min_count, f"{test_name}: Expected at least {min_count} citations, got {len(citations)}"
        else:
            assert len(citations) == expected_count, f"{test_name}: Expected {expected_count} citations, got {len(citations)}"
        
        # Check expected URLs are present
        actual_urls = [c["url"] for c in citations]
        for expected_url in expected_urls:
            assert expected_url in actual_urls, f"{test_name}: Missing expected URL: {expected_url}"
    
    def test_typed_candidates_with_dict_fallback(self, fixtures_dir):
        """Test extraction when typed candidates exist but have None metadata."""
        # Load v1 JOIN fixture
        with open(fixtures_dir / "fixture1_v1_join.json") as f:
            data = json.load(f)
        
        # Use helper to create response with typed None, dict data
        mock_resp = create_typed_none_dict_data_response(data)
        
        # Should still extract via model_dump
        citations = _extract_vertex_citations(mock_resp)
        assert len(citations) == 3
    
    def test_candidate_level_citation_metadata(self):
        """Test direct URIs in candidate.citationMetadata (no JOIN needed)."""
        data = {
            "candidates": [{
                "content": {"parts": [{"text": "Response text"}]},
                "citationMetadata": {
                    "citations": [
                        {"uri": "https://example.com/doc1", "title": "Doc 1"},
                        {"uri": "https://example.com/doc2", "title": "Doc 2"}
                    ]
                }
                # No groundingMetadata
            }]
        }
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []
        
        citations = _extract_vertex_citations(mock_resp)
        assert len(citations) == 2
        assert citations[0]["url"] == "https://example.com/doc1"
        assert citations[1]["url"] == "https://example.com/doc2"
    
    def test_camel_vs_snake_case(self):
        """Test both camelCase and snake_case field names work."""
        # Test camelCase
        data_camel = {
            "candidates": [{
                "citationMetadata": {
                    "citations": [{"uri": "https://camel.example.com"}]
                }
            }]
        }
        
        mock_camel = Mock()
        mock_camel.model_dump = Mock(return_value=data_camel)
        mock_camel.candidates = []
        
        citations_camel = _extract_vertex_citations(mock_camel)
        assert len(citations_camel) == 1
        assert citations_camel[0]["url"] == "https://camel.example.com"
        
        # Test snake_case
        data_snake = {
            "candidates": [{
                "citation_metadata": {
                    "citations": [{"uri": "https://snake.example.com"}]
                }
            }]
        }
        
        mock_snake = Mock()
        mock_snake.model_dump = Mock(return_value=data_snake)
        mock_snake.candidates = []
        
        citations_snake = _extract_vertex_citations(mock_snake)
        assert len(citations_snake) == 1
        assert citations_snake[0]["url"] == "https://snake.example.com"
    
    def test_deduplication(self):
        """Test that duplicate URLs are properly deduplicated."""
        data = {
            "candidates": [{
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
        mock_resp.candidates = []
        
        citations = _extract_vertex_citations(mock_resp)
        assert len(citations) == 2  # Deduplicated
        
        urls = [c["url"] for c in citations]
        assert "https://example.com/page" in urls
        assert "https://example.com/other" in urls
    
    def test_tools_called_but_no_citations(self, fixtures_dir):
        """Test forensics when tools>0 but citations=0."""
        with open(fixtures_dir / "fixture4_empty_but_tools.json") as f:
            data = json.load(f)
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []
        
        citations = _extract_vertex_citations(mock_resp)
        
        # Should return empty list
        assert len(citations) == 0
        
        # In production, this would trigger forensic audit
        # The metadata in fixture indicates tool_calls=4 but no citations
        # This is a valid case that should be handled gracefully
    
    def test_mixed_citation_sources(self):
        """Test extraction from both groundingMetadata and citationMetadata."""
        data = {
            "candidates": [{
                "groundingMetadata": {
                    "citedSources": [
                        {"id": "0", "uri": "https://from-grounding.com"}
                    ]
                },
                "citationMetadata": {
                    "citations": [
                        {"uri": "https://from-citation.com"}
                    ]
                }
            }]
        }
        
        mock_resp = Mock()
        mock_resp.model_dump = Mock(return_value=data)
        mock_resp.candidates = []
        
        citations = _extract_vertex_citations(mock_resp)
        assert len(citations) == 2
        
        urls = [c["url"] for c in citations]
        assert "https://from-grounding.com" in urls
        assert "https://from-citation.com" in urls
    
    def test_pure_dict_input(self, fixtures_dir):
        """Test that extractor can handle pure dict input (no Mock needed)."""
        with open(fixtures_dir / "fixture1_v1_join.json") as f:
            data = json.load(f)
        
        # Create minimal mock that only has model_dump
        mock_resp = type('Response', (), {'model_dump': lambda self: data, 'candidates': []})()
        
        citations = _extract_vertex_citations(mock_resp)
        assert len(citations) == 3
        
        # Verify all expected URLs present
        urls = [c["url"] for c in citations]
        assert "https://docs.python.org/3/library/functions.html#sorted" in urls
        assert "https://en.wikipedia.org/wiki/Timsort" in urls
        assert "https://stackoverflow.com/questions/1517496" in urls


if __name__ == "__main__":
    pytest.main([__file__, "-v"])