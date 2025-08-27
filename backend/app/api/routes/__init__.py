"""
API route registration
"""

from fastapi import APIRouter

from .templates import router as templates_router
from .providers import router as providers_router
from .ops import router as ops_router
from .runs import router as runs_router
from .countries import router as countries_router


# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(templates_router)
api_router.include_router(providers_router)
api_router.include_router(ops_router)
api_router.include_router(runs_router)
api_router.include_router(countries_router)


__all__ = ['api_router']