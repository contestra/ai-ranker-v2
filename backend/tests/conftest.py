"""
Pytest configuration and shared fixtures for AI Ranker V2 tests
"""

import os
import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Set test environment variables
os.environ["ENVIRONMENT"] = "testing"
os.environ["SECRET_KEY"] = "test_secret_key_for_hmac_testing"

# Ensure we're using the test database configuration
if "DATABASE_URL" not in os.environ:
    # If DATABASE_URL is not set, tests requiring database will be skipped
    print("Warning: DATABASE_URL not set - database tests will be skipped")

import pytest
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

# Make async fixtures available
pytest_plugins = ['pytest_asyncio']


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()