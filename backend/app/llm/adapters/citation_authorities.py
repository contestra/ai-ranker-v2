"""Citation authority domains configuration.

Defines tier-1 authority domains that should be preserved in citation deduplication.
"""

# Government and educational domains (always tier-1)
GOV_EDU_SUFFIXES = {
    ".gov",
    ".edu",
    ".gov.uk",
    ".gov.au",
    ".gov.ca",
    ".ac.uk",
}

# Major medical and scientific publishers
MEDICAL_AUTHORITIES = {
    "nejm.org",               # New England Journal of Medicine
    "thelancet.com",         # The Lancet
    "nature.com",            # Nature
    "science.org",           # Science
    "bmj.com",               # British Medical Journal
    "jamanetwork.com",       # JAMA Network
    "cell.com",              # Cell Press
    "plos.org",              # PLOS
    "springer.com",          # Springer
    "wiley.com",             # Wiley
    "elsevier.com",          # Elsevier
    "oxford.ac.uk",          # Oxford Academic
    "cambridge.org",         # Cambridge
}

# International health organizations
HEALTH_ORGS = {
    "who.int",               # World Health Organization
    "cdc.gov",               # CDC
    "nih.gov",               # NIH
    "fda.gov",               # FDA
    "ema.europa.eu",         # European Medicines Agency
    "pubmed.ncbi.nlm.nih.gov",  # PubMed
    "clinicaltrials.gov",    # Clinical Trials
    "cochrane.org",          # Cochrane Reviews
    "mayoclinic.org",        # Mayo Clinic
    "hopkinsmedicine.org",   # Johns Hopkins
    "clevelandclinic.org",   # Cleveland Clinic
}

# Tech and standards organizations (optional, extend as needed)
TECH_AUTHORITIES = {
    "ieee.org",              # IEEE
    "acm.org",               # ACM
    "w3.org",                # W3C
    "ietf.org",              # IETF
    "iso.org",               # ISO
}

# News authorities (major outlets)
NEWS_AUTHORITIES = {
    "reuters.com",           # Reuters
    "apnews.com",           # Associated Press
    "bbc.com",              # BBC
    "bbc.co.uk",            # BBC UK
    "npr.org",              # NPR
    "wsj.com",              # Wall Street Journal
    "nytimes.com",          # New York Times
    "washingtonpost.com",   # Washington Post
    "economist.com",        # The Economist
    "ft.com",               # Financial Times
}


def is_authority_domain(domain: str) -> bool:
    """Check if a domain is considered a tier-1 authority.
    
    Args:
        domain: The domain to check (e.g., "example.com")
        
    Returns:
        True if the domain is a recognized authority
    """
    if not domain:
        return False
    
    domain = domain.lower()
    
    # Check for gov/edu suffixes
    for suffix in GOV_EDU_SUFFIXES:
        if domain.endswith(suffix):
            return True
    
    # Check specific authority domains
    all_authorities = (
        MEDICAL_AUTHORITIES | 
        HEALTH_ORGS | 
        TECH_AUTHORITIES | 
        NEWS_AUTHORITIES
    )
    
    # Direct match
    if domain in all_authorities:
        return True
    
    # Check if it's a subdomain of an authority
    for auth in all_authorities:
        if domain.endswith("." + auth):
            return True
    
    return False


def get_all_authority_domains() -> set:
    """Get the complete set of authority domains.
    
    Returns:
        Set of all configured authority domains
    """
    return (
        MEDICAL_AUTHORITIES | 
        HEALTH_ORGS | 
        TECH_AUTHORITIES | 
        NEWS_AUTHORITIES
    )