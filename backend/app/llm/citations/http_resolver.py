# citations/http_resolver.py
"""
Tier-1 HTTP resolver for following redirects when sibling hints unavailable.
Optional, disabled by default for deterministic testing.
"""
from __future__ import annotations
import os
import time
import asyncio
import logging
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse, urljoin
import httpx
from .redirectors import is_redirector

logger = logging.getLogger(__name__)

# Feature flags and configuration
ALLOW_HTTP_RESOLVE = os.getenv("ALLOW_HTTP_RESOLVE", "false").lower() == "true"
HTTP_RESOLVE_TIMEOUT_MS = int(os.getenv("HTTP_RESOLVE_TIMEOUT_MS", "2000"))
HTTP_RESOLVE_MAX_HOPS = int(os.getenv("HTTP_RESOLVE_MAX_HOPS", "3"))
CACHE_TTL_SECONDS = int(os.getenv("HTTP_RESOLVE_CACHE_TTL", "86400"))  # 24 hours

# Simple in-memory cache (could be replaced with LRU or Redis)
_resolution_cache: Dict[str, Tuple[Optional[str], float]] = {}

# Blocklist patterns - never resolve to these
BLOCKED_SCHEMES = {"data", "blob", "file", "javascript", "about"}
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
PRIVATE_IP_PREFIXES = ["10.", "172.16.", "172.17.", "172.18.", "172.19.", 
                       "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                       "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                       "172.30.", "172.31.", "192.168."]

def is_blocked_url(url: str) -> bool:
    """Check if URL should not be resolved for safety reasons."""
    try:
        p = urlparse(url)
        
        # Check scheme
        if p.scheme in BLOCKED_SCHEMES:
            return True
        
        # Check for private IPs
        host = p.hostname or p.netloc or ""
        # Remove port from netloc if present
        if ':' in host and not host.startswith('['):
            host = host.split(':')[0]
        
        if host in BLOCKED_HOSTS or p.netloc in BLOCKED_HOSTS:
            return True
        
        # Check private IP ranges
        for prefix in PRIVATE_IP_PREFIXES:
            if host.startswith(prefix):
                return True
        
        # Check for IP-based hosts that might be private
        if host and all(c.isdigit() or c == '.' for c in host):
            # It's an IP address - be cautious
            parts = host.split('.')
            if len(parts) == 4:
                try:
                    first_octet = int(parts[0])
                    # Block private ranges
                    if first_octet in [10, 127] or (first_octet == 172 and 16 <= int(parts[1]) <= 31):
                        return True
                    if first_octet == 192 and int(parts[1]) == 168:
                        return True
                except ValueError:
                    pass
        
        return False
    except Exception:
        # On any parsing error, block for safety
        return True

def get_cached_resolution(url: str) -> Optional[str]:
    """Get cached resolution if still valid."""
    if url in _resolution_cache:
        resolved_url, cached_at = _resolution_cache[url]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            logger.debug(f"[HTTP_RESOLVE] Cache hit for {url[:50]}...")
            return resolved_url
        else:
            # Expired, remove from cache
            del _resolution_cache[url]
    return None

def set_cached_resolution(url: str, resolved_url: Optional[str]):
    """Store resolution in cache."""
    _resolution_cache[url] = (resolved_url, time.time())
    # Simple cache size limit - remove oldest if too large
    if len(_resolution_cache) > 1000:
        # Remove oldest 100 entries
        sorted_items = sorted(_resolution_cache.items(), key=lambda x: x[1][1])
        for key, _ in sorted_items[:100]:
            del _resolution_cache[key]

async def resolve_url_with_http(url: str) -> Optional[str]:
    """
    Follow HTTP redirects to find the final URL.
    Returns None if resolution fails or is not allowed.
    """
    if not ALLOW_HTTP_RESOLVE:
        return None
    
    if is_blocked_url(url):
        logger.debug(f"[HTTP_RESOLVE] Blocked URL: {url[:50]}...")
        return None
    
    # Check cache first
    cached = get_cached_resolution(url)
    if cached is not None:
        return cached
    
    timeout = httpx.Timeout(HTTP_RESOLVE_TIMEOUT_MS / 1000.0)
    visited_urls = set()
    current_url = url
    resolved_url = None
    
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,  # Manual redirect following
        limits=httpx.Limits(max_connections=5)
    ) as client:
        
        for hop in range(HTTP_RESOLVE_MAX_HOPS):
            if current_url in visited_urls:
                logger.debug(f"[HTTP_RESOLVE] Redirect loop detected at hop {hop}")
                break
            
            visited_urls.add(current_url)
            
            try:
                # Try HEAD first (less bandwidth)
                try:
                    response = await client.head(current_url)
                except httpx.RequestError:
                    # Some servers don't support HEAD, try GET with minimal range
                    headers = {"Range": "bytes=0-0"}
                    response = await client.get(current_url, headers=headers)
                
                # Check for redirect
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if location:
                        # Handle relative redirects
                        next_url = urljoin(current_url, location)
                        
                        # Check if we should continue
                        if is_blocked_url(next_url):
                            logger.debug(f"[HTTP_RESOLVE] Blocked redirect target at hop {hop}")
                            break
                        
                        p = urlparse(next_url)
                        if p.scheme not in ("http", "https"):
                            logger.debug(f"[HTTP_RESOLVE] Non-HTTP scheme at hop {hop}: {p.scheme}")
                            break
                        
                        # Check if we've reached a non-redirector
                        if not is_redirector(p.netloc):
                            resolved_url = next_url
                            logger.debug(f"[HTTP_RESOLVE] Resolved after {hop + 1} hops: {url[:30]}... -> {next_url[:30]}...")
                            break
                        
                        current_url = next_url
                    else:
                        # No location header, stop
                        break
                else:
                    # Not a redirect, we've reached the final URL
                    p = urlparse(current_url)
                    if not is_redirector(p.netloc):
                        resolved_url = current_url
                        logger.debug(f"[HTTP_RESOLVE] Final URL after {hop} hops: {resolved_url[:50]}...")
                    break
                    
            except httpx.TimeoutException:
                logger.debug(f"[HTTP_RESOLVE] Timeout at hop {hop} for {current_url[:50]}...")
                break
            except httpx.RequestError as e:
                logger.debug(f"[HTTP_RESOLVE] Request error at hop {hop}: {e}")
                break
            except Exception as e:
                logger.debug(f"[HTTP_RESOLVE] Unexpected error at hop {hop}: {e}")
                break
    
    # Cache the result (even if None to avoid repeated failures)
    set_cached_resolution(url, resolved_url)
    
    if not resolved_url:
        logger.debug(f"[HTTP_RESOLVE] Failed to resolve {url[:50]}... after {hop + 1} hops")
    
    return resolved_url

def resolve_url_with_http_sync(url: str) -> Optional[str]:
    """Synchronous wrapper for HTTP resolution."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context, can't use run_until_complete
            # Return None to avoid blocking
            logger.debug("[HTTP_RESOLVE] Cannot perform sync resolution in async context")
            return None
        return loop.run_until_complete(resolve_url_with_http(url))
    except Exception as e:
        logger.debug(f"[HTTP_RESOLVE] Sync wrapper error: {e}")
        return None