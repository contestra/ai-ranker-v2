"""
Database locking utilities for AI Ranker V2
Implements advisory locks for single-flight patterns
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import hashlib


def _hash_lock_key(s: str) -> int:
    """
    Generate a PostgreSQL advisory lock key from a string.
    Uses SHA-256 hash and takes lower 63 bits (positive BIGINT).
    """
    # Use SHA-256 for better distribution
    hash_bytes = hashlib.sha256(s.encode('utf-8')).digest()
    # Take first 8 bytes and convert to int, mask to 63 bits for positive BIGINT
    hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
    return hash_int & 0x7FFFFFFFFFFFFFFF  # 63 bits (positive)


@asynccontextmanager
async def pg_advisory_lock(
    session: AsyncSession, 
    key: str,
    timeout_ms: int = 5000
) -> AsyncGenerator[None, None]:
    """
    Acquire a PostgreSQL advisory lock for the duration of the context.
    
    Args:
        session: SQLAlchemy async session
        key: String key to lock on (will be hashed)
        timeout_ms: Lock acquisition timeout in milliseconds
        
    Usage:
        async with pg_advisory_lock(session, "provider:openai"):
            # Critical section - only one process can be here
            await fetch_provider_versions()
    """
    lock_id = _hash_lock_key(key)
    
    # Set lock timeout for this session
    await session.execute(
        text("SET LOCAL lock_timeout = :timeout"),
        {"timeout": f"{timeout_ms}ms"}
    )
    
    try:
        # Try to acquire the lock
        await session.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": lock_id}
        )
        
        yield
        
    finally:
        # Always release the lock
        await session.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": lock_id}
        )
        
        # Reset lock timeout
        await session.execute(text("RESET lock_timeout"))


@asynccontextmanager
async def pg_try_advisory_lock(
    session: AsyncSession,
    key: str
) -> AsyncGenerator[bool, None]:
    """
    Try to acquire a PostgreSQL advisory lock without blocking.
    
    Args:
        session: SQLAlchemy async session
        key: String key to lock on (will be hashed)
        
    Yields:
        bool: True if lock was acquired, False otherwise
        
    Usage:
        async with pg_try_advisory_lock(session, "batch:123") as locked:
            if locked:
                # Got the lock, proceed
                await process_batch()
            else:
                # Someone else has the lock
                return "BATCH_IN_PROGRESS"
    """
    lock_id = _hash_lock_key(key)
    
    # Try to acquire lock without blocking
    result = await session.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": lock_id}
    )
    locked = result.scalar()
    
    try:
        yield locked
    finally:
        if locked:
            # Only unlock if we actually got the lock
            await session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id}
            )