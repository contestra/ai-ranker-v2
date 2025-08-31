"""
ALS Ambient Utilities
Helper functions for domain/language heuristics and leak detection
"""

import re
import hashlib
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from collections import Counter

# Location words that should NOT appear in prompts
LOCATION_LEAK_TOKENS = [
    "switzerland", "germany", "united states", "usa", "us", 
    "ch", "de", "eu", "europe", "zurich", "berlin", "new york",
    "swiss", "german", "american", "european", "zürich", "münchen",
    "france", "italy", "uk", "united kingdom", "london", "paris"
]

def check_prompt_leak(prompt: str) -> bool:
    """
    Check if prompt contains location words (case-insensitive)
    Returns True if leak detected, False if clean
    """
    prompt_lower = prompt.lower()
    for token in LOCATION_LEAK_TOKENS:
        # Use word boundaries to avoid false positives (e.g., "us" in "use")
        if re.search(r'\b' + re.escape(token) + r'\b', prompt_lower):
            return True
    return False

def check_assistant_location_mention(response: str) -> bool:
    """
    Check if assistant mentioned a country/location explicitly
    This is acceptable but should be noted
    """
    response_lower = response.lower()
    location_terms = ["switzerland", "germany", "united states", "swiss", "german", "american"]
    for term in location_terms:
        if term in response_lower:
            return True
    return False

def extract_tld_counts(citations: List[str]) -> Dict[str, int]:
    """
    Parse citation URLs and count TLD buckets.
    Enhanced to handle citations that may be dicts with source_domain field.
    """
    tld_counter = Counter()
    
    for item in citations:
        # Handle both string URLs and dict citations
        if isinstance(item, dict):
            # Prefer source_domain if available (actual domain from Vertex)
            if 'source_domain' in item and item['source_domain']:
                domain = item['source_domain'].lower()
            elif 'url' in item:
                url = item['url']
                if not url:
                    continue
                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                except:
                    continue
            else:
                continue
        elif isinstance(item, str):
            url = item
            if not url:
                continue
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
            except:
                continue
        else:
            continue
            
        # Extract TLD from domain
        if domain:
            parts = domain.split('.')
            if len(parts) >= 2:
                # Handle cases like .co.uk
                if len(parts) >= 3 and parts[-2] in ['co', 'ac', 'gov', 'edu', 'org']:
                    tld = f".{parts[-2]}.{parts[-1]}"
                else:
                    tld = f".{parts[-1]}"
                
                # Normalize common TLDs
                if tld in ['.ch', '.de', '.fr', '.it', '.uk', '.eu', '.com', '.org', '.gov', '.edu']:
                    tld_counter[tld] += 1
                else:
                    tld_counter['other'] += 1
    
    return dict(tld_counter)

def calculate_domain_diversity(citations: List[str]) -> int:
    """
    Count unique domains in citations
    """
    domains = set()
    for url in citations:
        if not url:
            continue
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                domains.add(parsed.netloc.lower())
        except:
            continue
    return len(domains)

def guess_language(response: str, tld_counts: Dict[str, int]) -> str:
    """
    Simple heuristic to guess language from response and TLD skew
    Returns 'de', 'en', or 'mixed'
    """
    # Check TLD skew
    german_tlds = tld_counts.get('.ch', 0) + tld_counts.get('.de', 0) + tld_counts.get('.at', 0)
    english_tlds = tld_counts.get('.com', 0) + tld_counts.get('.org', 0) + tld_counts.get('.uk', 0)
    
    # Check for language markers in text
    response_lower = response.lower()
    
    # German month names and common words
    german_markers = [
        'januar', 'februar', 'märz', 'april', 'mai', 'juni', 'juli', 'august',
        'september', 'oktober', 'november', 'dezember',
        'und', 'der', 'die', 'das', 'ist', 'sind', 'wurde', 'wurden'
    ]
    
    # English month names and common words  
    english_markers = [
        'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
        'september', 'october', 'november', 'december',
        'the', 'and', 'is', 'are', 'was', 'were', 'has', 'have'
    ]
    
    german_score = sum(1 for marker in german_markers if marker in response_lower)
    english_score = sum(1 for marker in english_markers if marker in response_lower)
    
    # Add TLD influence
    if german_tlds > english_tlds * 2:
        german_score += 3
    elif english_tlds > german_tlds * 2:
        english_score += 3
    
    # Determine language
    if german_score > english_score * 1.5:
        return 'de'
    elif english_score > german_score * 1.5:
        return 'en'
    else:
        return 'mixed'

def assess_result_quality(grounded_effective: bool, domain_diversity: int) -> bool:
    """
    Assess if grounded search produced quality results
    Returns True if quality threshold met
    """
    return grounded_effective and domain_diversity >= 3

def extract_unique_local_domains(citations: List[str], tld_filter: List[str]) -> List[str]:
    """
    Extract domains matching specific TLDs
    tld_filter: list of TLDs like ['.ch', '.de']
    """
    local_domains = []
    for url in citations:
        if not url:
            continue
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain:
                for tld in tld_filter:
                    if domain.endswith(tld):
                        if domain not in local_domains:
                            local_domains.append(domain)
                        break
        except:
            continue
    return local_domains

def calculate_als_hash(als_block: str) -> str:
    """
    Calculate SHA256 hash of ALS block for tracking
    """
    return hashlib.sha256(als_block.encode()).hexdigest()[:16]

def format_tld_summary(tld_counts: Dict[str, int], top_n: int = 3) -> str:
    """
    Format top TLDs with counts for report
    """
    if not tld_counts:
        return "none"
    
    sorted_tlds = sorted(tld_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return ", ".join([f"{tld}({count})" for tld, count in sorted_tlds])

def check_als_effect(
    baseline_tlds: Dict[str, int],
    als_tlds: Dict[str, int],
    expected_tld: str
) -> bool:
    """
    Check if ALS caused expected shift in TLD distribution
    """
    baseline_count = baseline_tlds.get(expected_tld, 0)
    als_count = als_tlds.get(expected_tld, 0)
    
    # ALS should increase local TLD presence
    return als_count > baseline_count