# citations/domains.py
from urllib.parse import urlparse

# Try to use publicsuffix2 if available, otherwise fallback
try:
    from publicsuffix2 import PublicSuffixList
    _psl = PublicSuffixList()
    HAS_PSL = True
except ImportError:
    _psl = None
    HAS_PSL = False

def registrable_domain_from_url(url: str) -> str | None:
    """Extract registrable domain from URL using PSL if available."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc
        if not host:
            return None
        
        # Remove port if present
        host = host.split(':')[0].lower()
        
        # Remove www. prefix
        if host.startswith('www.'):
            host = host[4:]
        
        if HAS_PSL and _psl:
            # Use public suffix list for accurate extraction
            return _psl.get_sld(host) if host else None
        else:
            # Fallback to simple heuristic
            return _simple_registrable_domain(host)
    except Exception:
        return None

def registrable_domain_from_host(host: str) -> str | None:
    """Extract registrable domain from hostname using PSL if available."""
    try:
        if not host:
            return None
        
        # Remove port if present
        host = host.split(':')[0].lower()
        
        # Remove www. prefix
        if host.startswith('www.'):
            host = host[4:]
        
        if HAS_PSL and _psl:
            # Use public suffix list for accurate extraction
            return _psl.get_sld(host) if host else None
        else:
            # Fallback to simple heuristic
            return _simple_registrable_domain(host)
    except Exception:
        return None

def _simple_registrable_domain(host: str) -> str:
    """
    Simple fallback for registrable domain extraction.
    Keeps full domain for most cases, only strips for known 2-level TLDs.
    """
    if not host:
        return ""
    
    # For Vertex redirects, keep the full domain
    if 'vertexaisearch.cloud.google.com' in host:
        return host
    
    # For most domains, return as-is (keeps subdomains)
    # Only strip for known second-level TLDs
    parts = host.split('.')
    if len(parts) >= 3:
        # Check if it's a known second-level TLD pattern
        if parts[-2] in ['co', 'ac', 'gov', 'edu', 'org', 'net', 'com'] and parts[-1] in ['uk', 'jp', 'au', 'nz', 'za']:
            # e.g., example.co.uk -> return last 3 parts
            return '.'.join(parts[-3:])
    
    # For everything else, return full domain
    return host