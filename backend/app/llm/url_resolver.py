"""
URL Resolution for redirect handling
Specifically handles Vertex AI search redirects
"""

import re
import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs
import asyncio
import httpx

logger = logging.getLogger(__name__)

class URLResolver:
    """Resolves redirect URLs to their final destinations"""
    
    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.vertex_redirect_pattern = re.compile(
            r'https?://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/'
        )
    
    def is_vertex_redirect(self, url: str) -> bool:
        """Check if URL is a Vertex AI search redirect"""
        return bool(self.vertex_redirect_pattern.search(url))
    
    async def resolve_url(self, url: str, timeout: int = 5) -> str:
        """
        Resolve a URL to its final destination
        Returns original URL if resolution fails
        """
        # Check cache
        if url in self.cache:
            return self.cache[url]
        
        # Only resolve Vertex redirects for now
        if not self.is_vertex_redirect(url):
            return url
        
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                # Use HEAD request to avoid downloading content
                response = await client.head(url)
                final_url = str(response.url)
                
                # Cache the result
                self.cache[url] = final_url
                
                logger.debug(f"Resolved redirect: {url[:60]}... -> {final_url[:60]}...")
                return final_url
                
        except Exception as e:
            logger.warning(f"Failed to resolve URL {url[:60]}...: {e}")
            # Return original URL on failure
            return url
    
    async def resolve_citations(self, citations: List[Dict]) -> List[Dict]:
        """
        Resolve all URLs in a list of citations
        Returns updated citations with resolved URLs
        """
        if not citations:
            return citations
        
        resolved_citations = []
        
        for citation in citations:
            url = citation.get('url', '')
            
            if url and self.is_vertex_redirect(url):
                # Resolve the redirect
                resolved_url = await self.resolve_url(url)
                
                # Create updated citation with both URLs
                updated_citation = dict(citation)
                updated_citation['url'] = resolved_url
                updated_citation['original_url'] = url  # Keep original for forensics
                resolved_citations.append(updated_citation)
            else:
                resolved_citations.append(citation)
        
        return resolved_citations
    
    def extract_vertex_redirect_info(self, url: str) -> Optional[Dict]:
        """
        Extract information from Vertex redirect URL
        Returns metadata about the redirect
        """
        if not self.is_vertex_redirect(url):
            return None
        
        try:
            parsed = urlparse(url)
            
            # Extract the encoded target from the path
            # Format: /grounding-api-redirect/[encoded_data]
            path_parts = parsed.path.split('/')
            
            info = {
                'is_vertex_redirect': True,
                'redirect_service': 'vertexaisearch.cloud.google.com',
                'path': parsed.path,
            }
            
            # Try to extract query parameters if any
            if parsed.query:
                params = parse_qs(parsed.query)
                info['query_params'] = params
            
            return info
            
        except Exception as e:
            logger.debug(f"Failed to extract redirect info: {e}")
            return None


# Singleton instance
url_resolver = URLResolver()