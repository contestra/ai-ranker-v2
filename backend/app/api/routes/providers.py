"""
Provider version API endpoints
Per PRD v2.7 Section 3
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.templates import ProviderVersionsResponse
from app.services.providers import ProviderVersionService
from app.api import errors


router = APIRouter(prefix="/v1/providers", tags=["providers"])


@router.get("/{provider}/versions", response_model=ProviderVersionsResponse)
async def get_provider_versions(
    provider: str,
    session: AsyncSession = Depends(get_session),
    force_refresh: bool = Query(False, description="Force refresh from provider API"),
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-Id")
):
    """
    Get available model versions for a provider.
    
    Features:
    - TTL-based caching (default 300s)
    - Single-flight protection to prevent thundering herd
    - ETag support for cache validation
    - Returns source indicator (cache|live)
    
    Args:
        provider: Provider name (openai|vertex|gemini)
        force_refresh: Bypass cache and fetch fresh data
        
    Returns:
        List of available versions with current/default version
    """
    if provider not in ["openai", "vertex"]:
        errors.bad_request(
            code="INVALID_PROVIDER",
            detail=f"Provider '{provider}' not supported",
            extra={"provider": provider, "supported": ["openai", "vertex"]}
        )
    
    service = ProviderVersionService()
    result = await service.get_versions(session, provider, force_refresh)
    
    return ProviderVersionsResponse(**result)