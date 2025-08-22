"""
Ambient Location Signals (ALS) Service
A standalone service for geographic location inference through minimal civic signals
"""

from .als_builder import ALSBuilder
from .als_templates import ALSTemplates
from .als_harvester import ALSHarvester

__all__ = ['ALSBuilder', 'ALSTemplates', 'ALSHarvester']

# Singleton instance for easy access
als_service = ALSBuilder()