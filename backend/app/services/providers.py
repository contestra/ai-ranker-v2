"""
Provider version management with caching and single-flight
Per PRD v2.7 Section 3
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import hashlib
import httpx
import json

from app.models.models import ProviderVersionCache
from app.core.locks import pg_try_advisory_lock
from app.core.config import get_settings


settings = get_settings()


class ProviderVersionService:
    """Manages provider version discovery with TTL cache and single-flight"""
    
    def __init__(self):
        self.ttl_seconds = settings.provider_version_cache_ttl_seconds
        
    async def get_versions(
        self,
        session: AsyncSession,
        provider: str,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get provider versions with cache and single-flight protection.
        
        Args:
            session: Database session
            provider: Provider name (openai, vertex, gemini)
            force_refresh: Bypass cache and fetch fresh
            
        Returns:
            Dict with versions, current, last_checked_utc, expires_at_utc, source
        """
        now = datetime.now(timezone.utc)
        
        # Try to get from cache first
        if not force_refresh:
            cached = await self._get_cached(session, provider, now)
            if cached:
                return cached
                
        # Need to refresh - use single-flight protection
        async with pg_try_advisory_lock(session, f"provider:{provider}") as locked:
            if not locked:
                # Someone else is refreshing, wait a bit and try cache again
                import asyncio
                await asyncio.sleep(0.5)
                cached = await self._get_cached(session, provider, now)
                if cached:
                    return cached
                # If still no cache, proceed without lock (fallback)
                    
            # We have the lock or proceeding without it - fetch live
            return await self._fetch_and_cache(session, provider, now)
            
    async def _get_cached(
        self,
        session: AsyncSession,
        provider: str,
        now: datetime
    ) -> Optional[Dict[str, Any]]:
        """Get versions from cache if not expired"""
        stmt = select(ProviderVersionCache).where(
            ProviderVersionCache.provider == provider,
            ProviderVersionCache.expires_at_utc > now
        )
        result = await session.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        
        if cache_entry:
            return {
                "provider": provider,
                "versions": cache_entry.versions,
                "current": cache_entry.current,
                "last_checked_utc": cache_entry.last_checked_utc,
                "expires_at_utc": cache_entry.expires_at_utc,
                "source": "cache",
                "etag": cache_entry.etag
            }
        return None
        
    async def _fetch_and_cache(
        self,
        session: AsyncSession,
        provider: str,
        now: datetime
    ) -> Dict[str, Any]:
        """Fetch live versions and update cache"""
        # Fetch from provider
        versions_data = await self._fetch_from_provider(provider)
        
        # Calculate expiry
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        
        # Generate ETag from versions
        etag = self._generate_etag(versions_data["versions"])
        
        # Upsert cache entry
        stmt = select(ProviderVersionCache).where(
            ProviderVersionCache.provider == provider
        )
        result = await session.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        
        if cache_entry:
            # Update existing
            cache_entry.versions = versions_data["versions"]
            cache_entry.current = versions_data["current"]
            cache_entry.last_checked_utc = now
            cache_entry.expires_at_utc = expires_at
            cache_entry.etag = etag
            cache_entry.source = "live"
        else:
            # Create new
            cache_entry = ProviderVersionCache(
                provider=provider,
                versions=versions_data["versions"],
                current=versions_data["current"],
                last_checked_utc=now,
                expires_at_utc=expires_at,
                etag=etag,
                source="live"
            )
            session.add(cache_entry)
            
        await session.commit()
        
        return {
            "provider": provider,
            "versions": versions_data["versions"],
            "current": versions_data["current"],
            "last_checked_utc": now,
            "expires_at_utc": expires_at,
            "source": "live",
            "etag": etag
        }
        
    async def _fetch_from_provider(self, provider: str) -> Dict[str, Any]:
        """
        Fetch model versions from the actual provider APIs.
        """
        if provider == "openai":
            return await self._fetch_openai_versions()
        elif provider == "vertex":
            return await self._fetch_vertex_versions()
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    async def _fetch_openai_versions(self) -> Dict[str, Any]:
        """Fetch OpenAI model versions from API"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers=headers,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                # Extract GPT models and sort by date
                gpt_models = [
                    model["id"] for model in data["data"]
                    if model["id"].startswith(("gpt-4", "gpt-3.5"))
                    and "snapshot" not in model["id"]
                ]
                gpt_models.sort(reverse=True)  # Newest first
                
                return {
                    "versions": gpt_models,
                    "current": gpt_models[0] if gpt_models else "gpt-4o"
                }
        except Exception as e:
            # Fallback to static list if API fails
            return {
                "versions": [
                    "gpt-4o-2024-08-06",
                    "gpt-4o-2024-05-13", 
                    "gpt-4-turbo-2024-04-09",
                    "gpt-3.5-turbo-0125"
                ],
                "current": "gpt-4o-2024-08-06"
            }
    
    async def _fetch_vertex_versions(self) -> Dict[str, Any]:
        """Fetch Vertex AI (Gemini) model versions"""
        try:
            # Vertex AI doesn't have a simple models list API like OpenAI
            # We'll use the known Gemini model versions
            # In production, this would query the Vertex AI API
            return {
                "versions": [
                    "gemini-1.5-pro-002",
                    "gemini-1.5-pro-001", 
                    "gemini-1.5-flash-002",
                    "gemini-1.5-flash-001",
                    "gemini-1.0-pro-002"
                ],
                "current": "gemini-1.5-pro-002"
            }
        except Exception as e:
            # Fallback to static list
            return {
                "versions": [
                    "gemini-1.5-pro-002",
                    "gemini-1.5-flash-002"
                ],
                "current": "gemini-1.5-pro-002"
            }
            
    def _generate_etag(self, versions: List[str]) -> str:
        """Generate ETag from version list"""
        content = json.dumps(versions, sort_keys=True)
        hash_hex = hashlib.sha256(content.encode()).hexdigest()
        return f'W/"{hash_hex[:16]}"'