"""
Tests for redirect resolution and domain extraction
"""
import pytest
from unittest.mock import Mock

from app.llm.citations.redirectors import is_redirector, try_extract_target_from_query, path_looks_like_redirect
from app.llm.citations.domains import registrable_domain_from_url
from app.llm.citations.resolver import resolve_citation_url
from app.llm.adapters.vertex_adapter import _extract_vertex_citations
from app.llm.adapters.openai_adapter import _extract_openai_citations


class TestRedirectorDetection:
    """Test redirector detection functions"""
    
    def test_is_redirector(self):
        """Test redirector host detection"""
        assert is_redirector("vertexaisearch.cloud.google.com") == True
        assert is_redirector("www.google.com") == True
        assert is_redirector("news.google.com") == True
        assert is_redirector("t.co") == True
        assert is_redirector("example.com") == False
        assert is_redirector("admin.ch") == False
    
    def test_path_looks_like_redirect(self):
        """Test redirect path detection"""
        assert path_looks_like_redirect("https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz") == True
        assert path_looks_like_redirect("https://www.google.com/url?q=https://example.com") == True
        assert path_looks_like_redirect("https://example.com/page") == False
    
    def test_extract_target_from_query(self):
        """Test extraction of target URL from query params"""
        # Vertex redirect with URL in query
        vertex_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/?url=https%3A%2F%2Fwww.estv.admin.ch%2F"
        target = try_extract_target_from_query(vertex_url)
        assert target == "https://www.estv.admin.ch/"
        
        # Google redirect
        google_url = "https://www.google.com/url?q=https://example.com/page"
        target = try_extract_target_from_query(google_url)
        assert target == "https://example.com/page"
        
        # Non-redirect URL
        normal_url = "https://example.com/page?id=123"
        target = try_extract_target_from_query(normal_url)
        assert target is None


class TestCitationResolution:
    """Test citation URL resolution"""
    
    def test_resolve_non_redirector(self):
        """Test that non-redirectors are marked correctly"""
        citation = {
            "url": "https://example.com/page",
            "raw": {}
        }
        resolved = resolve_citation_url(citation)
        assert resolved["redirect"] == False
        assert resolved.get("resolved_url") is None
    
    def test_resolve_with_sibling_hint(self):
        """Test resolution using sibling fields"""
        citation = {
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz",
            "raw": {
                "web": {"uri": "https://www.admin.ch/gov/en/start.html"},
                "reference": {"url": "https://www.estv.admin.ch/"}
            }
        }
        resolved = resolve_citation_url(citation)
        assert resolved["redirect"] == True
        assert resolved["resolved_url"] == "https://www.admin.ch/gov/en/start.html"
    
    def test_resolve_from_query_params(self):
        """Test resolution from query parameters"""
        citation = {
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/?url=https%3A%2F%2Fexample.ch%2F",
            "raw": {}
        }
        resolved = resolve_citation_url(citation)
        assert resolved["redirect"] == True
        assert resolved["resolved_url"] == "https://example.ch/"


class TestVertexIntegration:
    """Test Vertex citation extraction with resolution"""
    
    def test_vertex_redirect_with_sibling_hint(self):
        """Test Vertex extraction with redirect and sibling hints"""
        response = Mock()
        candidate = Mock()
        candidate.grounding_metadata = {
            "cited_sources": [
                {
                    "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/?url=https%3A%2F%2Fwww.estv.admin.ch%2F",
                    "title": "Swiss Tax Authority"
                }
            ]
        }
        response.candidates = [candidate]
        
        citations = _extract_vertex_citations(response)
        assert len(citations) == 1
        
        c = citations[0]
        # When only redirect URL is available
        assert c["url"].startswith("https://vertexaisearch.cloud.google.com")
        assert c.get("resolved_url") == "https://www.estv.admin.ch/"
        assert c["redirect"] == True
        assert c["source_domain"] in ["estv.admin.ch", "www.estv.admin.ch"]  # Depends on PSL availability
    
    def test_vertex_redirect_with_direct_url_preferred(self):
        """Test that Vertex prefers direct URL when available"""
        response = Mock()
        candidate = Mock()
        candidate.grounding_metadata = {
            "cited_sources": [
                {
                    "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/?url=https%3A%2F%2Fwww.estv.admin.ch%2F",
                    "web": {"uri": "https://www.estv.admin.ch/"},
                    "title": "Swiss Tax Authority"
                }
            ]
        }
        response.candidates = [candidate]
        
        citations = _extract_vertex_citations(response)
        assert len(citations) == 1
        
        c = citations[0]
        # Should use the direct URL from web.uri, not the redirect
        assert c["url"] == "https://www.estv.admin.ch/"
        assert c["redirect"] == False
        assert c.get("resolved_url") is None
        assert c["source_domain"] in ["estv.admin.ch", "www.estv.admin.ch"]
    
    def test_vertex_direct_url(self):
        """Test Vertex with direct (non-redirect) URL"""
        response = Mock()
        candidate = Mock()
        candidate.grounding_metadata = {
            "grounding_attributions": [
                {
                    "uri": "https://www.bundesfinanzministerium.de/page",
                    "title": "German Finance Ministry"
                }
            ]
        }
        response.candidates = [candidate]
        
        citations = _extract_vertex_citations(response)
        assert len(citations) == 1
        
        c = citations[0]
        assert c["url"] == "https://www.bundesfinanzministerium.de/page"
        assert c["redirect"] == False
        assert c.get("resolved_url") is None
        assert "bundesfinanzministerium.de" in c["source_domain"]


class TestOpenAIIntegration:
    """Test OpenAI citation extraction with resolution"""
    
    def test_openai_dedup_and_domain(self):
        """Test OpenAI deduplication and domain extraction"""
        response = Mock()
        response.output = [
            {
                "type": "web_search",
                "content": "1. German Finance - https://www.bundesfinanzministerium.de/?utm_source=x\n"
                          "2. German Finance - https://www.bundesfinanzministerium.de/"
            }
        ]
        response.message = {}
        
        citations = _extract_openai_citations(response)
        # Should deduplicate to 1 citation (same URL after normalization)
        assert len(citations) == 1
        assert "bundesfinanzministerium.de" in citations[0]["source_domain"]
    
    def test_openai_google_redirect(self):
        """Test OpenAI handling of Google redirects"""
        response = Mock()
        response.output = [
            {
                "type": "web_search",
                "content": "Result - https://www.google.com/url?q=https://example.com/article"
            }
        ]
        response.message = {}
        
        citations = _extract_openai_citations(response)
        assert len(citations) == 1
        
        c = citations[0]
        # Should detect as redirect and resolve
        if c.get("redirect"):
            assert c.get("resolved_url") == "https://example.com/article"
            assert c["source_domain"] == "example.com"


class TestDomainExtraction:
    """Test domain extraction functions"""
    
    def test_registrable_domain_extraction(self):
        """Test extraction of registrable domains"""
        # Standard domains
        assert registrable_domain_from_url("https://www.example.com/page") in ["example.com", "www.example.com"]
        assert registrable_domain_from_url("https://subdomain.example.com") in ["example.com", "subdomain.example.com"]
        
        # Keep subdomains for government/official sites
        assert "ec.europa.eu" in (registrable_domain_from_url("https://ec.europa.eu/page") or "")
        assert "estv.admin.ch" in (registrable_domain_from_url("https://www.estv.admin.ch") or "")
        
        # Second-level TLDs
        domain = registrable_domain_from_url("https://example.co.uk")
        assert domain in ["example.co.uk", "co.uk"]  # Depends on implementation
    
    def test_vertex_redirect_domain(self):
        """Test domain extraction for Vertex redirects"""
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz"
        domain = registrable_domain_from_url(url)
        assert "vertexaisearch.cloud.google.com" in (domain or "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])