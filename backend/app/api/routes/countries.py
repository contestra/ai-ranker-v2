"""
Countries API endpoints for ALS configuration
"""

from typing import List, Optional
from fastapi import APIRouter, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.database import get_session
from app.services.als.country_codes import COUNTRY_TO_NUM, get_all_countries

router = APIRouter(prefix="/api", tags=["countries"])


class Country(BaseModel):
    """Country model for ALS"""
    id: int
    code: str
    name: str
    emoji: str
    locale_code: str
    is_active: bool
    vat_rate: Optional[float] = None
    plug_types: Optional[str] = None
    emergency_numbers: Optional[str] = None


# Hardcoded ALS-supported countries
ALS_COUNTRIES = [
    Country(
        id=1,
        code="DE",
        name="Germany",
        emoji="🇩🇪",
        locale_code="de-DE",
        is_active=True,
        vat_rate=19,
        plug_types="C, F",
        emergency_numbers="110, 112"
    ),
    Country(
        id=2,
        code="FR",
        name="France", 
        emoji="🇫🇷",
        locale_code="fr-FR",
        is_active=True,
        vat_rate=20,
        plug_types="C, E",
        emergency_numbers="15, 17, 18, 112"
    ),
    Country(
        id=3,
        code="IT",
        name="Italy",
        emoji="🇮🇹",
        locale_code="it-IT",
        is_active=True,
        vat_rate=22,
        plug_types="C, F, L",
        emergency_numbers="112, 113, 115, 118"
    ),
    Country(
        id=4,
        code="GB",
        name="United Kingdom",
        emoji="🇬🇧",
        locale_code="en-GB",
        is_active=True,
        vat_rate=20,
        plug_types="G",
        emergency_numbers="999, 112"
    ),
    Country(
        id=5,
        code="US",
        name="United States",
        emoji="🇺🇸",
        locale_code="en-US",
        is_active=True,
        vat_rate=0,
        plug_types="A, B",
        emergency_numbers="911"
    ),
    Country(
        id=6,
        code="CH",
        name="Switzerland",
        emoji="🇨🇭",
        locale_code="de-CH",
        is_active=True,
        vat_rate=7.7,
        plug_types="C, J",
        emergency_numbers="112, 117, 118, 144"
    ),
    Country(
        id=7,
        code="AE",
        name="United Arab Emirates",
        emoji="🇦🇪",
        locale_code="ar-AE",
        is_active=True,
        vat_rate=5,
        plug_types="C, D, G",
        emergency_numbers="999, 997, 998"
    ),
    Country(
        id=8,
        code="SG",
        name="Singapore",
        emoji="🇸🇬",
        locale_code="en-SG",
        is_active=True,
        vat_rate=8,
        plug_types="G",
        emergency_numbers="999, 995"
    )
]


@router.get("/countries", response_model=List[Country])
async def list_countries(
    session: AsyncSession = Depends(get_session),
    active_only: bool = False
):
    """
    Get list of countries configured for ALS.
    These are the only supported countries for Ambient Location Signals.
    """
    if active_only:
        return [c for c in ALS_COUNTRIES if c.is_active]
    return ALS_COUNTRIES


@router.get("/countries/{country_code}", response_model=Country)
async def get_country(
    country_code: str,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific country by code"""
    country = next((c for c in ALS_COUNTRIES if c.code == country_code.upper()), None)
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")
    return country