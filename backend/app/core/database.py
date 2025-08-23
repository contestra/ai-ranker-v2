"""
Database connection and session management for AI Ranker V2
Uses async SQLAlchemy with Neon PostgreSQL
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

from app.models.base import Base

# Load environment variables
load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost/airanker"
)

# Create async engine
# NullPool is recommended for serverless/edge environments like Neon
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    poolclass=NullPool,  # Important for Neon
    future=True
)

# Create async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session.
    Usage in FastAPI:
        @app.get("/")
        async def root(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session.
    Usage:
        async with get_db_context() as db:
            ...
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    Should be called on application startup.
    """
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.
    Should be called on application shutdown.
    """
    await engine.dispose()


class DatabaseService:
    """
    Service class for database operations.
    Provides high-level database utilities.
    """
    
    @staticmethod
    async def health_check() -> bool:
        """
        Check database connectivity.
        Returns True if database is accessible.
        """
        try:
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception:
            return False
    
    @staticmethod
    async def get_table_counts() -> dict:
        """
        Get row counts for all tables.
        Useful for monitoring and debugging.
        """
        async with async_session() as session:
            tables = {
                'templates': "SELECT COUNT(*) FROM prompt_templates",
                'runs': "SELECT COUNT(*) FROM runs",
                'batches': "SELECT COUNT(*) FROM batches",
                'countries': "SELECT COUNT(*) FROM countries",
                'provider_cache': "SELECT COUNT(*) FROM provider_version_cache",
                'idempotency_keys': "SELECT COUNT(*) FROM idempotency_keys"
            }
            
            counts = {}
            for name, query in tables.items():
                result = await session.execute(query)
                counts[name] = result.scalar()
            
            return counts