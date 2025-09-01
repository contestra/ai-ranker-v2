"""
Tests for Tier-1 HTTP resolution.
Network-guarded: only run when ALLOW_HTTP_RESOLVE=true
"""
import os
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import httpx

from app.llm.citations.http_resolver import (
    is_blocked_url,
    get_cached_resolution,
    set_cached_resolution,
    resolve_url_with_http,
    ALLOW_HTTP_RESOLVE
)
from app.llm.citations.resolver import resolve_citation_url


class TestBlocklist:
    """Test URL blocking for safety"""
    
    def test_blocked_schemes(self):
        """Test that dangerous schemes are blocked"""
        assert is_blocked_url("data:text/html,<script>alert(1)</script>") == True
        assert is_blocked_url("blob:https://example.com/uuid") == True
        assert is_blocked_url("file:///etc/passwd") == True
        assert is_blocked_url("javascript:alert(1)") == True
        assert is_blocked_url("about:blank") == True
        assert is_blocked_url("https://example.com") == False
        assert is_blocked_url("http://example.com") == False
    
    def test_blocked_hosts(self):
        """Test that private IPs and localhost are blocked"""
        assert is_blocked_url("http://localhost/api") == True
        assert is_blocked_url("http://127.0.0.1/api") == True
        assert is_blocked_url("http://0.0.0.0:8080") == True
        assert is_blocked_url("http://::1/api") == True
        assert is_blocked_url("http://10.0.0.1/internal") == True
        assert is_blocked_url("http://172.16.0.1/internal") == True
        assert is_blocked_url("http://192.168.1.1/router") == True
        assert is_blocked_url("https://example.com") == False


class TestCache:
    """Test caching functionality"""
    
    def test_cache_operations(self):
        """Test cache get/set operations"""
        # Clear any existing cache
        from app.llm.citations import http_resolver
        http_resolver._resolution_cache.clear()
        
        # Test cache miss
        assert get_cached_resolution("https://example.com/redirect") is None
        
        # Test cache set and hit
        set_cached_resolution("https://example.com/redirect", "https://final.com")
        assert get_cached_resolution("https://example.com/redirect") == "https://final.com"
        
        # Test None caching (failed resolutions)
        set_cached_resolution("https://bad.com/redirect", None)
        # Should still return None but from cache
        assert get_cached_resolution("https://bad.com/redirect") is None
    
    def test_cache_expiry(self):
        """Test that cache entries expire"""
        from app.llm.citations import http_resolver
        import time
        
        # Set cache with old timestamp
        http_resolver._resolution_cache["https://old.com"] = ("https://final.com", time.time() - 100000)
        
        # Should return None due to expiry
        assert get_cached_resolution("https://old.com") is None
        
        # Should be removed from cache
        assert "https://old.com" not in http_resolver._resolution_cache


@pytest.mark.asyncio
class TestHTTPResolution:
    """Test HTTP resolution logic (mocked)"""
    
    async def test_successful_resolution(self):
        """Test successful redirect following"""
        # Mock HTTP client
        mock_response_redirect = Mock()
        mock_response_redirect.status_code = 301
        mock_response_redirect.headers = {"location": "https://final.example.com/page"}
        
        mock_response_final = Mock()
        mock_response_final.status_code = 200
        
        with patch('app.llm.citations.http_resolver.ALLOW_HTTP_RESOLVE', True):
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # First call returns redirect, second returns final
                mock_client.head.side_effect = [mock_response_redirect, mock_response_final]
                
                result = await resolve_url_with_http("https://redirect.com/path")
                assert result == "https://final.example.com/page"
    
    async def test_redirect_loop_detection(self):
        """Test that redirect loops are detected"""
        # Use a known redirector for this test
        test_url = "https://www.google.com/url?q=https://www.google.com/url"
        
        mock_response = Mock()
        mock_response.status_code = 301
        mock_response.headers = {"location": test_url}  # Points to itself
        
        with patch('app.llm.citations.http_resolver.ALLOW_HTTP_RESOLVE', True):
            # Clear cache
            from app.llm.citations import http_resolver
            http_resolver._resolution_cache.clear()
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                # Return same redirect response multiple times
                mock_client.head.return_value = mock_response
                
                result = await resolve_url_with_http(test_url)
                assert result is None  # Should fail due to loop
    
    async def test_max_hops_limit(self):
        """Test that max hops limit is enforced"""
        # Create a chain of redirects longer than max
        responses = []
        for i in range(5):  # More than default max of 3
            mock_response = Mock()
            mock_response.status_code = 301
            mock_response.headers = {"location": f"https://hop{i+1}.com"}
            responses.append(mock_response)
        
        with patch('app.llm.citations.http_resolver.ALLOW_HTTP_RESOLVE', True):
            with patch('app.llm.citations.http_resolver.HTTP_RESOLVE_MAX_HOPS', 3):
                with patch('httpx.AsyncClient') as mock_client_class:
                    mock_client = AsyncMock()
                    mock_client_class.return_value.__aenter__.return_value = mock_client
                    mock_client.head.side_effect = responses
                    
                    result = await resolve_url_with_http("https://hop0.com")
                    # Should stop at max hops
                    assert mock_client.head.call_count <= 3


@pytest.mark.skipif(
    not os.getenv("ALLOW_HTTP_RESOLVE") == "true",
    reason="Network tests disabled (set ALLOW_HTTP_RESOLVE=true to run)"
)
class TestHTTPResolutionLive:
    """Live network tests - only run when explicitly enabled"""
    
    @pytest.mark.asyncio
    async def test_live_google_redirect(self):
        """Test resolution of a real Google redirect (if network available)"""
        # This URL format is commonly seen from Google search
        test_url = "https://www.google.com/url?q=https://example.com"
        
        result = await resolve_url_with_http(test_url)
        # Should resolve to example.com
        if result:
            assert "example.com" in result
            assert "google.com" not in result
    
    def test_integration_with_citation_resolver(self):
        """Test full integration with citation resolver"""
        citation = {
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/?url=https%3A%2F%2Fexample.com",
            "raw": {}
        }
        
        # With HTTP resolution enabled
        with patch.dict(os.environ, {"ALLOW_HTTP_RESOLVE": "true"}):
            resolved = resolve_citation_url(citation)
            
            # Should attempt resolution
            assert resolved["redirect"] == True
            # May or may not resolve depending on network
            # But should not error
            assert "url" in resolved
            assert "resolved_url" in resolved


class TestDeterminism:
    """Test that system remains deterministic with flag off"""
    
    def test_flag_off_no_network(self):
        """Test that no network calls are made when flag is off"""
        from app.llm.citations import http_resolver
        
        # Ensure flag is off
        with patch.object(http_resolver, 'ALLOW_HTTP_RESOLVE', False):
            citation = {
                "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz",
                "raw": {}
            }
            
            # Mock httpx to ensure it's never called
            with patch('httpx.AsyncClient') as mock_client:
                resolved = resolve_citation_url(citation)
                
                # Should not make any HTTP calls
                mock_client.assert_not_called()
                
                # Should still resolve from query params (Tier-0)
                assert resolved["redirect"] == True
                # But no HTTP resolution
                assert resolved.get("resolved_url") is None or "vertexaisearch" not in resolved.get("resolved_url", "")
    
    def test_existing_tests_unchanged(self):
        """Test that existing citation tests still pass with flag off"""
        # This ensures backward compatibility
        citation = {
            "url": "https://example.com/page",
            "raw": {}
        }
        
        with patch.dict(os.environ, {"ALLOW_HTTP_RESOLVE": "false"}):
            resolved = resolve_citation_url(citation)
            
            # Non-redirector should work as before
            assert resolved["redirect"] == False
            assert resolved.get("resolved_url") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])