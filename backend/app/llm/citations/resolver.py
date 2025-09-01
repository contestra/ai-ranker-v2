# citations/resolver.py
import os
import time
from urllib.parse import urlparse
from typing import List, Dict
from .redirectors import is_redirector, try_extract_target_from_query, path_looks_like_redirect
from .http_resolver import resolve_url_with_http_sync, ALLOW_HTTP_RESOLVE
import logging

logger = logging.getLogger(__name__)

# Resolver budget limits (configurable via environment)
MAX_URLS_PER_REQUEST = int(os.getenv("CITATION_RESOLVER_MAX_URLS", "8"))
MAX_RESOLVE_TIME_MS = int(os.getenv("CITATION_RESOLVER_MAX_TIME_MS", "2000"))
RESOLVER_STOPWATCH_MS = int(os.getenv("CITATION_RESOLVER_STOPWATCH_MS", "3000"))

def resolve_citations_with_budget(citations: List[Dict]) -> List[Dict]:
    """
    Resolve multiple citations with budget enforcement.
    
    Budgets:
    - Max URLs: 8 (configurable via CITATION_RESOLVER_MAX_URLS)
    - Max time per URL: 2s (configurable via CITATION_RESOLVER_MAX_TIME_MS)
    - Total stopwatch: 3s (configurable via CITATION_RESOLVER_STOPWATCH_MS)
    
    Returns: citations with resolved_url added where possible
    """
    if not citations:
        return citations
    
    start_time = time.time() * 1000  # Convert to milliseconds
    resolved_count = 0
    truncated = False
    
    # Process up to MAX_URLS_PER_REQUEST citations
    for i, cit in enumerate(citations):
        # Check stopwatch
        elapsed_ms = (time.time() * 1000) - start_time
        if elapsed_ms > RESOLVER_STOPWATCH_MS:
            logger.warning(f"[RESOLVER_BUDGET] Stopwatch exceeded ({elapsed_ms:.0f}ms > {RESOLVER_STOPWATCH_MS}ms), "
                         f"truncating at citation {i+1}/{len(citations)}")
            truncated = True
            # Mark remaining as truncated
            for j in range(i, len(citations)):
                citations[j]["source_type"] = "redirect_only"
                citations[j]["resolver_truncated"] = True
            break
        
        # Check URL count budget
        if resolved_count >= MAX_URLS_PER_REQUEST:
            logger.info(f"[RESOLVER_BUDGET] Max URLs reached ({MAX_URLS_PER_REQUEST}), "
                       f"marking remaining {len(citations)-i} as redirect_only")
            truncated = True
            # Mark remaining as truncated
            for j in range(i, len(citations)):
                citations[j]["source_type"] = "redirect_only"
                citations[j]["resolver_truncated"] = True
            break
        
        # Check if this needs resolution
        url = cit.get("url") or ""
        host = urlparse(url).netloc.lower()
        
        # Skip if not a redirector
        if not is_redirector(host):
            cit["redirect"] = False
            continue
        
        # Track time for this resolution
        url_start = time.time() * 1000
        
        # Apply single resolution with time budget
        citations[i] = resolve_citation_url(cit)
        
        url_elapsed = (time.time() * 1000) - url_start
        if url_elapsed > MAX_RESOLVE_TIME_MS:
            logger.warning(f"[RESOLVER_BUDGET] URL resolution took {url_elapsed:.0f}ms > {MAX_RESOLVE_TIME_MS}ms")
        
        resolved_count += 1
    
    # Add metadata about truncation if it occurred
    if truncated:
        logger.info(f"[RESOLVER_BUDGET] Resolved {resolved_count}/{len(citations)} citations before budget limits")
    
    return citations


def resolve_citation_url(cit: dict) -> dict:
    """
    Resolve redirector URLs to their true destinations.
    Keeps original URL unchanged, adds resolved_url when confident.
    """
    url = cit.get("url") or ""
    host = urlparse(url).netloc.lower()
    
    # Assume non-redirectors are final unless proven otherwise
    if not is_redirector(host):
        cit["redirect"] = False
        cit.setdefault("resolved_url", None)
        return cit

    # Mark and try cheap recoveries
    cit["redirect"] = True

    # 1) Prefer sibling end-site fields the extractor placed into raw
    raw = cit.get("raw") or {}
    sibling_candidates = []
    for key in ("web", "reference", "source", "support"):
        obj = raw.get(key)
        if isinstance(obj, dict):
            sibling_candidates += [obj.get("uri"), obj.get("url")]
    sibling_candidates = [u for u in sibling_candidates if isinstance(u, str)]

    for candidate in sibling_candidates:
        cp = urlparse(candidate)
        if cp.scheme in ("http", "https") and cp.netloc and not is_redirector(cp.netloc.lower()):
            cit["resolved_url"] = candidate
            return cit

    # 2) Heuristic from redirector query/path
    if path_looks_like_redirect(url):
        target = try_extract_target_from_query(url)
        if target:
            cit["resolved_url"] = target
            return cit

    # 3) Tier-1 HTTP resolution (if enabled and still unresolved)
    if ALLOW_HTTP_RESOLVE and not cit.get("resolved_url"):
        try:
            resolved = resolve_url_with_http_sync(url)
            if resolved:
                cit["resolved_url"] = resolved
                logger.debug(f"[RESOLVER] HTTP resolved {url[:50]}... to {resolved[:50]}...")
        except Exception as e:
            logger.debug(f"[RESOLVER] HTTP resolution failed: {e}")
    
    # 4) Leave unresolved if all methods failed
    cit.setdefault("resolved_url", None)
    return cit