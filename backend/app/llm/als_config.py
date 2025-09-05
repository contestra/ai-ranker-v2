"""
Centralized ALS (Ambient Location Signals) Configuration
Ensures consistent seed key handling across all adapters and the router.
"""

import os
from typing import Optional, Dict, Any
from app.core.config import settings


class ALSConfig:
    """Centralized ALS configuration to prevent drift."""
    
    # Production seed key - all components should use this
    PRODUCTION_SEED_KEY_ID = "v1_2025"
    
    # Fallback/default for development
    DEVELOPMENT_SEED_KEY_ID = "k1"
    
    @classmethod
    def get_seed_key_id(cls, vendor: Optional[str] = None) -> str:
        """
        Get the appropriate ALS seed key ID.
        
        Args:
            vendor: Optional vendor name for vendor-specific overrides
            
        Returns:
            The seed key ID to use
        """
        # Check for vendor-specific environment overrides
        if vendor == "openai":
            env_key = os.getenv("OPENAI_SEED_KEY_ID")
            if env_key:
                return env_key
        
        # Check for global override
        global_override = os.getenv("ALS_SEED_KEY_ID")
        if global_override:
            return global_override
        
        # Use production key in production, development key otherwise
        if settings.is_production:
            return cls.PRODUCTION_SEED_KEY_ID
        else:
            # Use configured default or fallback
            return settings.default_seed_key_id or cls.DEVELOPMENT_SEED_KEY_ID
    
    @classmethod
    def get_seed_key(cls, key_id: Optional[str] = None, vendor: Optional[str] = None) -> str:
        """
        Get the actual seed key value for a given ID.
        
        Args:
            key_id: Specific key ID to lookup (if None, uses default)
            vendor: Optional vendor name for vendor-specific logic
            
        Returns:
            The seed key value
        """
        if key_id is None:
            key_id = cls.get_seed_key_id(vendor)
        
        # Look up the key in settings
        return settings.get_als_seed(key_id)
    
    @classmethod
    def mark_als_metadata(cls, metadata: Dict[str, Any], seed_key_id: str, vendor: Optional[str] = None) -> None:
        """
        Mark ALS metadata with provenance information.
        
        Args:
            metadata: Response metadata dictionary to update
            seed_key_id: The seed key ID that was used
            vendor: Optional vendor name for context
        """
        # Mark the seed key used
        metadata["als_seed_key_id"] = seed_key_id
        
        # Mark if this is a default/placeholder
        if seed_key_id == cls.DEVELOPMENT_SEED_KEY_ID:
            metadata["als_seed_is_default"] = True
            metadata["als_seed_warning"] = "Using development default seed key"
        elif seed_key_id == cls.PRODUCTION_SEED_KEY_ID:
            metadata["als_seed_is_production"] = True
        
        # Mark if this came from an environment override
        if vendor == "openai" and os.getenv("OPENAI_SEED_KEY_ID") == seed_key_id:
            metadata["als_seed_source"] = "openai_env_override"
        elif os.getenv("ALS_SEED_KEY_ID") == seed_key_id:
            metadata["als_seed_source"] = "global_env_override"
        else:
            metadata["als_seed_source"] = "config_default"