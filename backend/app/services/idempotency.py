"""
Idempotency key management for AI Ranker V2
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.models import IdempotencyKey
from app.core.config import get_settings


settings = get_settings()


async def compute_body_hash(body: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of request body"""
    body_str = json.dumps(body, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(body_str.encode()).hexdigest()


async def check_idempotency(
    session: AsyncSession,
    org_id: str,
    idempotency_key: str
) -> tuple[bool, str | None]:
    """
    Check if idempotency key exists and return its body hash.
    
    Returns:
        (exists, body_sha256) where exists is True if key found
    """
    # Clean up expired keys first
    expire_cutoff = datetime.utcnow()
    await session.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.expires_at < expire_cutoff
        )
    )
    
    # Check for existing key
    result = await session.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.org_id == org_id,
            IdempotencyKey.key == idempotency_key
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        return True, existing.body_sha256
    return False, None


async def reserve_idempotency(
    session: AsyncSession,
    org_id: str,
    idempotency_key: str,
    body: Dict[str, Any]
) -> None:
    """
    Reserve an idempotency key for the given request.
    
    Raises:
        ValueError: If key already exists with different body
    """
    body_hash = await compute_body_hash(body)
    
    # Check if key exists
    exists, existing_hash = await check_idempotency(session, org_id, idempotency_key)
    
    if exists:
        if existing_hash != body_hash:
            raise ValueError(f"Idempotency key already used with different request body")
        # Same body, idempotent request - OK
        return
    
    # Reserve the key
    expires_at = datetime.utcnow() + timedelta(seconds=settings.idempotency_ttl_seconds)
    
    new_key = IdempotencyKey(
        key=idempotency_key,
        org_id=org_id,
        body_sha256=body_hash,
        expires_at=expires_at
    )
    
    session.add(new_key)
    await session.flush()