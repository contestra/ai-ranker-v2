"""Test resolver budget enforcement."""
import pytest
from unittest.mock import patch, MagicMock
import time
from app.llm.citations.resolver import resolve_citations_with_budget


class TestResolverBudget:
    """Test that resolver respects budget limits."""
    
    def test_max_urls_budget(self):
        """Test that resolver stops at MAX_URLS_PER_REQUEST."""
        # Create 15 citations (more than budget of 8)
        citations = []
        for i in range(15):
            citations.append({
                "url": f"https://google.vertexaisearch.cloud.google.com/redirect?url={i}",
                "title": f"Citation {i}",
                "source_type": "web"
            })
        
        with patch('app.llm.citations.resolver.is_redirector', return_value=True):
            with patch('app.llm.citations.resolver.resolve_citation_url') as mock_resolve:
                # Mock resolution to track calls
                def resolve_side_effect(cit):
                    cit["resolved_url"] = f"https://example{cit['url'][-1]}.com"
                    return cit
                
                mock_resolve.side_effect = resolve_side_effect
                
                # Resolve with budget
                result = resolve_citations_with_budget(citations)
                
                # Should have all 15 citations returned
                assert len(result) == 15
                
                # Only first 8 should be resolved
                assert mock_resolve.call_count == 8
                
                # First 8 should have resolved_url
                for i in range(8):
                    assert "resolved_url" in result[i]
                
                # Remaining should be marked as truncated
                for i in range(8, 15):
                    assert result[i].get("source_type") == "redirect_only"
                    assert result[i].get("resolver_truncated") is True
    
    def test_stopwatch_budget(self):
        """Test that resolver stops when stopwatch expires."""
        # Create 10 citations
        citations = []
        for i in range(10):
            citations.append({
                "url": f"https://google.vertexaisearch.cloud.google.com/redirect?url={i}",
                "title": f"Citation {i}",
                "source_type": "web"
            })
        
        with patch('app.llm.citations.resolver.is_redirector', return_value=True):
            with patch('app.llm.citations.resolver.resolve_citation_url') as mock_resolve:
                with patch('app.llm.citations.resolver.RESOLVER_STOPWATCH_MS', 100):  # 100ms stopwatch
                    # Mock resolution to be slow
                    def slow_resolve(cit):
                        time.sleep(0.05)  # 50ms per resolution
                        cit["resolved_url"] = f"https://example.com/{cit['url'][-1]}"
                        return cit
                    
                    mock_resolve.side_effect = slow_resolve
                    
                    # Resolve with budget
                    result = resolve_citations_with_budget(citations)
                    
                    # Should have all 10 citations returned
                    assert len(result) == 10
                    
                    # Should have resolved only ~2 before stopwatch (100ms / 50ms = 2)
                    assert mock_resolve.call_count <= 3  # Allow some timing variance
                    
                    # Unresolved ones should be marked as truncated
                    truncated_count = sum(1 for c in result if c.get("resolver_truncated"))
                    assert truncated_count >= 7  # At least 7 should be truncated
    
    def test_non_redirector_skipped(self):
        """Test that non-redirector URLs are skipped."""
        citations = [
            {"url": "https://example.com/page1", "title": "Direct URL"},
            {"url": "https://google.vertexaisearch.cloud.google.com/redirect?url=2", "title": "Redirect"},
            {"url": "https://nature.com/article", "title": "Another direct"},
        ]
        
        with patch('app.llm.citations.resolver.is_redirector') as mock_is_redirector:
            with patch('app.llm.citations.resolver.resolve_citation_url') as mock_resolve:
                # Only middle one is a redirector
                mock_is_redirector.side_effect = [False, True, False]
                
                def resolve_side_effect(cit):
                    cit["resolved_url"] = "https://resolved.com"
                    cit["redirect"] = True  # resolve_citation_url would set this
                    return cit
                
                mock_resolve.side_effect = resolve_side_effect
                
                # Resolve with budget
                result = resolve_citations_with_budget(citations)
                
                # Only 1 should be resolved (the redirector)
                assert mock_resolve.call_count == 1
                
                # Non-redirectors should have redirect=False
                assert result[0].get("redirect") is False
                assert result[1].get("redirect") is True
                assert result[2].get("redirect") is False
    
    def test_empty_citations(self):
        """Test handling of empty citation list."""
        result = resolve_citations_with_budget([])
        assert result == []
        
        result = resolve_citations_with_budget(None)
        assert result is None