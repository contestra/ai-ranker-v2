"""
Database connection and session management for AI Ranker V2
Uses async SQLAlchemy with Neon PostgreSQL
Per PRD v2.7 Phase-1
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.models.base import Base
from app.core.config import get_settings


settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,  # Recommended for Neon
    future=True
)

# Create async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get database session.
    
    Usage:
        @app.get("/")
        async def endpoint(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session.
    
    Usage:
        async with get_session_context() as session:
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
    Called on application startup.
    """
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def health_check() -> bool:
    """
    Check database connectivity.
    Returns True if database is accessible.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


async def close_db() -> None:
    """
    Close database connections.
    Called on application shutdown.
    """
    await engine.dispose()