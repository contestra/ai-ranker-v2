"""
Proxy Service for managing Webshare.io residential proxies
Handles per-run proxy configuration based on vantage policy
"""

import os
import httpx
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from app.llm.types import VantagePolicy

logger = logging.getLogger(__name__)


class ProxyClass(str, Enum):
    """Proxy infrastructure class"""
    DATACENTER = "datacenter"
    RESIDENTIAL = "residential"
    ISP = "isp"


class ConnectionType(str, Enum):
    """Proxy connection type"""
    ROTATING = "rotating"      # New IP per request
    BACKBONE = "backbone"      # Stable gateway


@dataclass
class ProxyConfig:
    """Configuration for a proxy connection"""
    url: str                           # Full proxy URL with auth
    country_code: str                  # ISO country code
    proxy_class: ProxyClass           # datacenter/residential/isp
    connection: ConnectionType        # rotating/backbone
    username_suffix: str              # The constructed username with country
    

class ProxyService:
    """Service for managing proxy configurations and connections"""
    
    def __init__(self):
        self.base_username = os.getenv('WEBSHARE_USERNAME')
        self.password = os.getenv('WEBSHARE_PASSWORD')
        self.host = os.getenv('WEBSHARE_HOST', 'p.webshare.io')
        self.port = os.getenv('WEBSHARE_PORT', '80')
        self.download_key = os.getenv('WEBSHARE_DOWNLOAD_KEY')
        self.plan_id = os.getenv('WEBSHARE_PLAN_ID')
        self.enabled = os.getenv('PROXY_ENABLED', 'false').lower() == 'true'
        self._proxy_cache = {}  # Cache proxy list by country
        
        if self.enabled and not (self.base_username and self.password):
            logger.warning("Proxy enabled but Webshare credentials not configured")
            self.enabled = False
    
    def normalize_country_code(self, country_code: str) -> str:
        """Normalize country codes (e.g., UK -> GB)"""
        if not country_code:
            return "US"
        
        country_code = country_code.strip().upper()
        
        # Critical normalizations
        mappings = {
            "UK": "GB",      # United Kingdom
            "USA": "US",     # United States
            "UAE": "AE",     # United Arab Emirates
        }
        
        return mappings.get(country_code, country_code)
    
    def get_proxy_config(
        self,
        country_code: str,
        vantage_policy: VantagePolicy,
        proxy_class: ProxyClass = ProxyClass.DATACENTER,
        connection: ConnectionType = ConnectionType.ROTATING
    ) -> Optional[ProxyConfig]:
        """
        Get proxy configuration based on policy and country.
        Returns None if proxy not needed or not configured.
        """
        
        # Check if proxy should be used based on vantage policy
        if vantage_policy not in [VantagePolicy.PROXY_ONLY, VantagePolicy.ALS_PLUS_PROXY]:
            logger.debug(f"Proxy not needed for vantage_policy={vantage_policy}")
            return None
        
        if not self.enabled:
            logger.warning("Proxy requested but not enabled/configured")
            return None
        
        # Normalize country code
        country_code = self.normalize_country_code(country_code)
        
        # Build username based on connection type
        # Webshare requires numbered suffixes for backbone (e.g., US-1, US-2)
        # For rotating, it uses -rotate suffix
        if connection == ConnectionType.ROTATING:
            username_suffix = f"{self.base_username}-{country_code}-rotate"
        else:  # BACKBONE
            # Use -1 as default proxy number (you could randomize 1-100 for load balancing)
            username_suffix = f"{self.base_username}-{country_code}-1"
        
        # Build proxy URL
        proxy_url = f"http://{username_suffix}:{self.password}@{self.host}:{self.port}"
        
        config = ProxyConfig(
            url=proxy_url,
            country_code=country_code,
            proxy_class=proxy_class,
            connection=connection,
            username_suffix=username_suffix
        )
        
        logger.info(
            f"Proxy configured: country={country_code}, "
            f"class={proxy_class.value}, connection={connection.value}"
        )
        
        return config
    
    async def fetch_proxy_list(
        self, 
        countries: List[str], 
        connection: str = 'backbone'
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch proxy list from Webshare API for specific countries.
        This can be used to pre-validate proxy availability.
        """
        if not (self.download_key and self.plan_id):
            logger.warning("Cannot fetch proxy list: missing download_key or plan_id")
            return None
        
        countries_str = '-'.join([self.normalize_country_code(c) for c in countries])
        url = (
            f"https://proxy.webshare.io/api/v2/proxy/list/download/"
            f"{self.download_key}/{countries_str}/any/username/{connection}/-/"
            f"?plan_id={self.plan_id}"
        )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch proxy list: {e}")
            return None
    
    async def verify_proxy_connection(
        self, 
        proxy_config: ProxyConfig
    ) -> Optional[Dict[str, str]]:
        """
        Verify proxy connection by checking IP address.
        Returns IP info if successful, None if failed.
        """
        if not proxy_config:
            return None
        
        # Use ipinfo.io to check the proxy's external IP
        check_url = "https://ipinfo.io/json"
        
        try:
            async with httpx.AsyncClient(
                proxy=proxy_config.url,
                timeout=10.0
            ) as client:
                response = await client.get(check_url)
                response.raise_for_status()
                ip_info = response.json()
                
                logger.info(
                    f"Proxy verified: IP={ip_info.get('ip')}, "
                    f"Country={ip_info.get('country')}, "
                    f"City={ip_info.get('city')}"
                )
                
                return ip_info
        except Exception as e:
            logger.error(f"Proxy verification failed: {e}")
            return None
    
    def should_use_residential(self, grounded: bool, vendor: str) -> ProxyClass:
        """
        Determine whether to use residential or datacenter proxy.
        Can implement logic like: use residential for grounded, datacenter for ungrounded.
        """
        # Default strategy: residential for grounded requests, datacenter otherwise
        if grounded:
            return ProxyClass.RESIDENTIAL
        return ProxyClass.DATACENTER
    
    def should_use_backbone(self, vendor: str, streaming: bool = False) -> ConnectionType:
        """
        Determine whether to use backbone or rotating connection.
        Backbone is better for streaming/long connections.
        """
        # Use backbone for streaming or when stability is needed
        if streaming or vendor == "vertex":  # Vertex may benefit from stable connection
            return ConnectionType.BACKBONE
        return ConnectionType.ROTATING


# Singleton instance
_proxy_service = None

def get_proxy_service() -> ProxyService:
    """Get or create the singleton proxy service instance"""
    global _proxy_service
    if _proxy_service is None:
        _proxy_service = ProxyService()
    return _proxy_service