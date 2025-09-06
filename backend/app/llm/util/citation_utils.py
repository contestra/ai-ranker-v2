"""Citation normalization and deduplication utilities."""

import re
from typing import Dict, List, Tuple, Optional, Set, Any
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def get_etld_plus_one(url: str) -> str:
    """Extract the eTLD+1 (effective top-level domain plus one) from a URL.
    
    Examples:
        https://www.example.com/page -> example.com
        https://blog.github.io/post -> github.io
        https://www.bbc.co.uk/news -> bbc.co.uk
    """
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path.split('/')[0]
        
        # Remove www. prefix
        if host.startswith('www.'):
            host = host[4:]
        
        # Remove port if present
        if ':' in host:
            host = host.split(':')[0]
        
        # Lowercase
        host = host.lower()
        
        # Handle common multi-level TLDs
        parts = host.split('.')
        if len(parts) >= 2:
            # Check for known multi-level TLDs
            multi_tlds = {
                'co.uk', 'co.jp', 'co.kr', 'co.in', 'co.id', 'co.il', 'co.za',
                'com.au', 'com.br', 'com.cn', 'com.mx', 'com.tw', 'com.ar', 'com.sg',
                'net.au', 'net.br', 'net.cn', 'net.mx', 'net.tw', 'net.ar',
                'org.uk', 'org.au', 'org.br', 'org.cn', 'org.mx', 'org.tw',
                'gov.uk', 'gov.au', 'gov.br', 'gov.cn', 'gov.mx', 'gov.in',
                'edu.au', 'edu.br', 'edu.cn', 'edu.mx', 'edu.sg', 'edu.tw',
                'ac.uk', 'ac.jp', 'ac.kr', 'ac.in', 'ac.il', 'ac.za',
                'nih.gov', 'europa.eu'
            }
            
            # Check if last two parts form a known multi-level TLD
            if len(parts) >= 3:
                potential_tld = '.'.join(parts[-2:])
                if potential_tld in multi_tlds:
                    # Return domain + multi-level TLD
                    return '.'.join(parts[-3:])
            
            # Default: return last two parts
            return '.'.join(parts[-2:])
        
        return host
        
    except Exception:
        return ""


def normalize_url(url: str, resolved_url: Optional[str] = None) -> Tuple[str, str, str]:
    """Normalize a URL and extract its domain key.
    
    Args:
        url: The original URL
        resolved_url: Optional pre-resolved URL (e.g., from redirect resolution)
        
    Returns:
        Tuple of (normalized_url, original_url, domain_key)
    """
    if not url:
        return "", "", ""
    
    original_url = url
    
    # Use resolved URL if provided, otherwise use original
    working_url = resolved_url or url
    
    try:
        parsed = urlparse(working_url.lower())
        
        # Normalize scheme
        scheme = parsed.scheme or 'https'
        
        # Normalize host
        host = parsed.netloc
        if not host and parsed.path:
            # Handle URLs without scheme
            parts = parsed.path.split('/', 1)
            host = parts[0]
            path = '/' + parts[1] if len(parts) > 1 else '/'
        else:
            path = parsed.path or '/'
        
        # Remove common tracking parameters
        if parsed.query:
            params = parse_qs(parsed.query)
            # Remove common tracking params
            tracking_params = {
                'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
                'fbclid', 'gclid', 'msclkid', 'ref', 'source', 'sr_share'
            }
            cleaned_params = {k: v for k, v in params.items() if k not in tracking_params}
            query = urlencode(cleaned_params, doseq=True) if cleaned_params else ''
        else:
            query = ''
        
        # Reconstruct normalized URL (without fragment)
        normalized = urlunparse((scheme, host, path, '', query, ''))
        
        # Get domain key (eTLD+1)
        domain_key = get_etld_plus_one(normalized)
        
        return normalized, original_url, domain_key
        
    except Exception:
        # If normalization fails, return originals
        domain_key = get_etld_plus_one(url)
        return url, url, domain_key


def dedupe_citations(
    citations: List[Dict[str, Any]], 
    official_domains: Optional[Set[str]] = None,
    authority_domains: Optional[Set[str]] = None,
    per_domain_cap: int = 2
) -> List[Dict[str, Any]]:
    """Deduplicate citations by domain with authority exceptions.
    
    Args:
        citations: List of citation dicts with at least 'url' and optionally 'title', 'type'
        official_domains: Set of official/brand domains to preserve
        authority_domains: Set of tier-1 authority domains to preserve
        per_domain_cap: Maximum citations per domain (default 2)
        
    Returns:
        Deduplicated list of citations
    """
    if not citations:
        return []
    
    official_domains = official_domains or set()
    authority_domains = authority_domains or set()
    
    # Group citations by domain
    domain_groups = {}
    
    for citation in citations:
        url = citation.get('url', '')
        if not url:
            continue
            
        # Normalize URL and get domain key
        resolved_url = citation.get('resolved_url', '')
        normalized, original, domain_key = normalize_url(url, resolved_url)
        
        if not domain_key:
            continue
        
        # Enhanced citation with normalized data
        enhanced_citation = dict(citation)
        enhanced_citation['normalized_url'] = normalized
        enhanced_citation['domain_key'] = domain_key
        
        if domain_key not in domain_groups:
            domain_groups[domain_key] = []
        domain_groups[domain_key].append(enhanced_citation)
    
    # Apply retention rules
    deduped = []
    
    for domain_key, group in domain_groups.items():
        # Check if this is an official or authority domain
        is_official = domain_key in official_domains
        is_authority = False
        
        # Check if domain is an authority
        if authority_domains:
            is_authority = domain_key in authority_domains
        
        # Also check using the citation_authorities module if available
        try:
            from app.llm.adapters.citation_authorities import is_authority_domain
            if not is_authority:
                is_authority = is_authority_domain(domain_key)
        except ImportError:
            pass
        
        # Sort group by quality signals
        # Prefer: 1) PDFs/whitepapers, 2) longer titles, 3) first seen
        def citation_quality(c):
            score = 0
            url_lower = c.get('url', '').lower()
            title = c.get('title', '')
            
            # Prefer PDFs and clinical/research content
            if '.pdf' in url_lower:
                score += 100
            if any(term in url_lower for term in ['clinical', 'research', 'whitepaper', 'study']):
                score += 50
            if any(term in title.lower() for term in ['clinical', 'research', 'study', 'trial']):
                score += 25
                
            # Prefer longer, more descriptive titles
            score += min(len(title), 100)
            
            return -score  # Negative for reverse sort
        
        sorted_group = sorted(group, key=citation_quality)
        
        # Determine how many to keep
        keep_count = 1  # Default: keep one per domain
        
        # Exception rules for keeping 2 from same domain
        if len(sorted_group) > 1:
            # Check if we have different document types
            has_pdf = any('.pdf' in c.get('url', '').lower() for c in sorted_group)
            has_html = any('.pdf' not in c.get('url', '').lower() for c in sorted_group)
            
            # Check if we have significantly different paths/content
            urls = [c.get('url', '') for c in sorted_group]
            paths = [urlparse(u).path for u in urls]
            unique_paths = len(set(paths))
            
            # Exception criteria
            if is_official and (has_pdf and has_html):
                # Official domain with mixed content types
                keep_count = min(2, per_domain_cap)
            elif is_authority:
                # Authority domains can keep 2 if diverse content
                if unique_paths > 1:
                    keep_count = min(2, per_domain_cap)
            elif is_official or is_authority:
                # Always try to keep at least 1 from official/authority
                keep_count = 1
        
        # Apply cap
        keep_count = min(keep_count, len(sorted_group), per_domain_cap)
        
        # Add selected citations
        for citation in sorted_group[:keep_count]:
            # Remove temporary fields we added
            clean_citation = {k: v for k, v in citation.items() 
                            if k not in ['normalized_url', 'domain_key']}
            deduped.append(clean_citation)
    
    return deduped


def recompute_citation_counts(citations: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Recompute anchored and unlinked citation counts.
    
    Args:
        citations: List of citations with 'type' field
        
    Returns:
        Tuple of (anchored_count, unlinked_count)
    """
    anchored = 0
    unlinked = 0
    
    for citation in citations:
        citation_type = citation.get('type', 'anchored')
        if citation_type == 'unlinked':
            unlinked += 1
        else:
            # Default to anchored if type is missing or unknown
            anchored += 1
    
    return anchored, unlinked