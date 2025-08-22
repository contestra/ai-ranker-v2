"""
Ambient Block Builder - Main service for generating Ambient Location Signals
Uses the new corrected templates with proper render_block method
"""

from typing import Dict, List, Optional, Tuple
# Use Unicode-safe templates with proper escape sequences
from .als_templates import ALSTemplates

class ALSBuilder:
    """
    Builds minimal ALS blocks from pre-harvested templates.
    This is the main interface used by prompt tracker and other features.
    """
    
    def __init__(self):
        self.templates = ALSTemplates()
        
    def build_als_block(
        self, 
        country: str, 
        max_chars: int = 350,
        include_weather: bool = True,
        randomize: bool = True
    ) -> str:
        """
        Build an ALS block for a specific country using the new renderer.
        
        Args:
            country: Country code (DE, CH, US, GB, AE, SG, IT, FR)
            max_chars: Maximum characters (default 350)
            include_weather: Include weather line
            randomize: Randomize selections for variety
            
        Returns:
            Formatted ALS block string
        """
        
        try:
            # Use the new render_block method with proper phrase rotation
            import random
            # Get the actual number of phrases for this country
            tpl = ALSTemplates.TEMPLATES.get(country.upper())
            if tpl and tpl.phrases:
                max_idx = len(tpl.phrases) - 1
                phrase_idx = random.randint(0, max_idx) if randomize else 0
            else:
                phrase_idx = 0
            
            return ALSTemplates.render_block(
                code=country,
                phrase_idx=phrase_idx,
                include_weather=include_weather
            )
        except (KeyError, ValueError) as e:
            # Return empty string if country not supported or block too long
            print(f"Warning: Could not generate ALS block for {country}: {e}")
            return ""
    
    def build_minimal_als(self, country: str) -> str:
        """
        Build an ultra-minimal ALS (≤200 chars).
        Just timezone, one civic term, and currency.
        """
        
        try:
            # Use render_block without weather for minimal version
            return ALSTemplates.render_block(
                code=country,
                phrase_idx=0,
                include_weather=False
            )
        except (KeyError, ValueError):
            return ""
    
    def validate_als_block(self, als_block: str) -> Tuple[bool, List[str]]:
        """
        Validate an ALS block for potential issues.
        
        Returns:
            (is_valid, list_of_issues)
        """
        
        issues = []
        
        # Check length
        if len(als_block) > 350:
            issues.append(f"Too long: {len(als_block)} chars (max 350)")
        
        # Check for URLs
        if 'http://' in als_block or 'https://' in als_block or 'www.' in als_block:
            issues.append("Contains URLs (should be domain hints only)")
        
        # Check for commercial brands
        commercial_brands = ['amazon', 'google', 'microsoft', 'apple', 'facebook']
        als_lower = als_block.lower()
        for brand in commercial_brands:
            if brand in als_lower:
                issues.append(f"Contains commercial brand: {brand}")
        
        # Check for industry terms (supplements, etc)
        industry_terms = ['supplement', 'vitamin', 'pharma', 'drug', 'medicine']
        for term in industry_terms:
            if term in als_lower:
                issues.append(f"Contains industry term: {term}")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def detect_leakage(self, als_block: str, response: str) -> List[str]:
        """
        Check if response leaked phrases from ALS block.
        
        Args:
            als_block: The ALS block sent
            response: Model's response
            
        Returns:
            List of leaked phrases
        """
        
        # Extract 2-3 word phrases from ALS
        als_words = als_block.lower().replace('\n', ' ').replace('-', ' ').split()
        
        # Build n-grams
        bigrams = set()
        trigrams = set()
        
        for i in range(len(als_words) - 1):
            bigrams.add(' '.join(als_words[i:i+2]))
            if i < len(als_words) - 2:
                trigrams.add(' '.join(als_words[i:i+3]))
        
        # Check for leaks
        response_lower = response.lower()
        leaked = []
        
        # Skip common/expected phrases
        skip_phrases = {
            'do not', 'not cite', 'ambient context', 
            'localization only', 'national weather',
            'lokaler kontext', 'contexte local', 'contesto locale'
        }
        
        for phrase in bigrams.union(trigrams):
            if phrase in skip_phrases:
                continue
            if len(phrase) < 6:  # Skip very short phrases
                continue
            if phrase in response_lower:
                leaked.append(phrase)
        
        return leaked
    
    def get_supported_countries(self) -> List[str]:
        """Get list of supported country codes."""
        return ALSTemplates.supported_countries()