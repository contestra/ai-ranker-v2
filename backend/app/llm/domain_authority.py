"""
Domain Authority Scoring System
Implements tiered authority scoring for grounding citations
"""

from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse
import re

# Tier 1: Premium authoritative sources (highest trust)
TIER_1_DOMAINS = {
    # Major News Agencies
    'reuters.com',
    'apnews.com',
    'bloomberg.com',
    
    # Premium Financial Publications
    'wsj.com',
    'ft.com',
    'barrons.com',
    'economist.com',
    
    # Major Business News
    'cnbc.com',
    'businessinsider.com',
    'forbes.com',
    'fortune.com',
    
    # Major Newspapers
    'nytimes.com',
    'washingtonpost.com',
    'theguardian.com',
    'bbc.com',
    'bbc.co.uk',
    
    # Tech Authority
    'techcrunch.com',
    'theverge.com',
    'arstechnica.com',
    'wired.com',
    
    # Scientific/Medical
    'nature.com',
    'science.org',
    'nejm.org',
    'thelancet.com',
    'nih.gov',
    'cdc.gov',
    
    # Government/Official
    'sec.gov',
    'federalreserve.gov',
    'ecb.europa.eu',
    'imf.org',
    'worldbank.org',
}

# Tier 2: Reputable but specialized sources
TIER_2_DOMAINS = {
    # Business/Finance
    'marketwatch.com',
    'seekingalpha.com',
    'morningstar.com',
    'investopedia.com',
    
    # Tech News
    'engadget.com',
    'zdnet.com',
    'cnet.com',
    'venturebeat.com',
    
    # Regional News
    'latimes.com',
    'chicagotribune.com',
    'usatoday.com',
    'sfchronicle.com',
    
    # Industry Specific
    'industryweek.com',
    'supplychaindive.com',
    'autoblog.com',
}

# Tier 3: General/User-generated/Lower authority
TIER_3_PATTERNS = [
    r'.*\.substack\.com',
    r'.*\.medium\.com',
    r'.*\.blogspot\.com',
    r'.*\.wordpress\.com',
    r'reddit\.com',
    r'quora\.com',
    r'.*\.wiki.*',
]

# Penalty domains (low credibility or known issues)
PENALTY_DOMAINS = {
    'watcher.guru',
    'webpronews.com',
    'marketbeat.com',  # Often promotional
    'benzinga.com',     # Mixed quality
    'zacks.com',        # Often promotional
}


class DomainAuthority:
    """Evaluates and scores domain authority for citations"""
    
    def __init__(self):
        self.tier_1 = TIER_1_DOMAINS
        self.tier_2 = TIER_2_DOMAINS
        self.tier_3_patterns = [re.compile(p) for p in TIER_3_PATTERNS]
        self.penalty_domains = PENALTY_DOMAINS
    
    def get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url.lower())
            domain = parsed.netloc or parsed.path
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return ''
    
    def get_tier(self, url: str) -> int:
        """
        Get tier for a URL/domain
        Returns: 1 (highest), 2 (good), 3 (acceptable), 4 (penalty)
        """
        domain = self.get_domain(url)
        
        if not domain:
            return 4
        
        # Check penalty list first
        if domain in self.penalty_domains:
            return 4
        
        # Check Tier 1
        if domain in self.tier_1:
            return 1
        
        # Check Tier 2
        if domain in self.tier_2:
            return 2
        
        # Check Tier 3 patterns
        for pattern in self.tier_3_patterns:
            if pattern.match(domain):
                return 3
        
        # Default to Tier 3 for unknown
        return 3
    
    def score_citations(self, citations: List[Dict]) -> Dict:
        """
        Score a list of citations
        Returns metrics about authority distribution
        """
        if not citations:
            return {
                'total_citations': 0,
                'tier_1_count': 0,
                'tier_2_count': 0,
                'tier_3_count': 0,
                'tier_4_count': 0,
                'authority_score': 0.0,
                'tier_1_percentage': 0.0,
                'premium_percentage': 0.0,  # Tier 1 + 2
                'penalty_percentage': 0.0,
                'domains': {},
                'tier_breakdown': []
            }
        
        tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        domains = {}
        tier_breakdown = []
        
        for citation in citations:
            url = citation.get('url', '')
            if not url:
                continue
            
            domain = self.get_domain(url)
            tier = self.get_tier(url)
            
            tier_counts[tier] += 1
            domains[domain] = tier
            
            tier_breakdown.append({
                'url': url,
                'domain': domain,
                'tier': tier,
                'title': citation.get('title', ''),
            })
        
        total = sum(tier_counts.values())
        
        # Calculate authority score (weighted average)
        # Tier 1: 100 points, Tier 2: 70 points, Tier 3: 40 points, Tier 4: 0 points
        weights = {1: 100, 2: 70, 3: 40, 4: 0}
        total_score = sum(tier_counts[tier] * weights[tier] for tier in tier_counts)
        authority_score = total_score / total if total > 0 else 0
        
        return {
            'total_citations': total,
            'tier_1_count': tier_counts[1],
            'tier_2_count': tier_counts[2],
            'tier_3_count': tier_counts[3],
            'tier_4_count': tier_counts[4],
            'authority_score': round(authority_score, 1),
            'tier_1_percentage': round(100 * tier_counts[1] / total, 1) if total > 0 else 0,
            'premium_percentage': round(100 * (tier_counts[1] + tier_counts[2]) / total, 1) if total > 0 else 0,
            'penalty_percentage': round(100 * tier_counts[4] / total, 1) if total > 0 else 0,
            'domains': domains,
            'tier_breakdown': tier_breakdown
        }
    
    def resolve_redirect_url(self, url: str) -> str:
        """
        Resolve redirect URLs to final destination
        Specifically handles vertexaisearch.cloud.google.com redirects
        """
        if 'vertexaisearch.cloud.google.com/grounding-api-redirect' in url:
            # For now, return as-is but mark for resolution
            # In production, this would follow the redirect
            return url  # TODO: Implement actual redirect resolution
        return url
    
    def format_authority_summary(self, metrics: Dict) -> str:
        """Format authority metrics as a readable summary"""
        if metrics['total_citations'] == 0:
            return "No citations"
        
        parts = []
        
        # Overall score
        parts.append(f"Authority: {metrics['authority_score']}/100")
        
        # Tier distribution
        if metrics['tier_1_count'] > 0:
            parts.append(f"Tier-1: {metrics['tier_1_percentage']}%")
        
        if metrics['premium_percentage'] > 0:
            parts.append(f"Premium: {metrics['premium_percentage']}%")
        
        if metrics['penalty_percentage'] > 0:
            parts.append(f"⚠️ Low-quality: {metrics['penalty_percentage']}%")
        
        return " • ".join(parts)


# Singleton instance
authority_scorer = DomainAuthority()