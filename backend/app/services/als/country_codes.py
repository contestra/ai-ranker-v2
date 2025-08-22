"""
Numeric country code mapping to prevent AI models from interpreting ISO codes.
Using numeric IDs makes it impossible for models to recognize them as locations.
"""

# Bidirectional mapping between numeric codes and ISO codes
COUNTRY_TO_NUM = {
    'DE': 1,  # Germany
    'FR': 2,  # France
    'IT': 3,  # Italy
    'GB': 4,  # United Kingdom
    'US': 5,  # United States
    'CH': 6,  # Switzerland
    'AE': 7,  # United Arab Emirates
    'SG': 8,  # Singapore
    'NONE': 0,  # No country (base model)
}

NUM_TO_COUNTRY = {v: k for k, v in COUNTRY_TO_NUM.items()}

def country_to_num(country_code: str) -> int:
    """Convert ISO country code to numeric ID"""
    return COUNTRY_TO_NUM.get(country_code.upper(), 0)

def num_to_country(num_id: int) -> str:
    """Convert numeric ID to ISO country code"""
    return NUM_TO_COUNTRY.get(num_id, 'NONE')

def is_valid_country(country_code: str) -> bool:
    """Check if country code is supported"""
    return country_code.upper() in COUNTRY_TO_NUM

def is_valid_num(num_id: int) -> bool:
    """Check if numeric ID is valid"""
    return num_id in NUM_TO_COUNTRY

def get_all_countries() -> list:
    """Get list of all supported country codes"""
    return [k for k in COUNTRY_TO_NUM.keys() if k != 'NONE']

def get_all_nums() -> list:
    """Get list of all numeric IDs"""
    return [v for v in COUNTRY_TO_NUM.values() if v != 0]