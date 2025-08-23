"""
Template service for AI Ranker V2
Implements template creation, deduplication, and HMAC signing per PRD
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.canonicalization import canonicalize_json, compute_template_hash
from app.core.config import settings
from app.models.models import PromptTemplate, IdempotencyKey


class TemplateService:
    """
    Service for managing prompt templates with immutability guarantees.
    """
    
    @staticmethod
    def compute_record_hmac(template: PromptTemplate) -> str:
        """
        Compute HMAC for tamper detection per PRD.
        Signs: template_id + template_sha256 + canonical_json + created_at
        """
        # Prepare data for HMAC
        hmac_data = {
            'template_id': str(template.template_id),
            'template_sha256': template.template_sha256,
            'canonical_json': template.canonical_json,
            'created_at': template.created_at.isoformat() if template.created_at else ''
        }
        
        # Serialize deterministically
        hmac_payload = json.dumps(hmac_data, sort_keys=True, separators=(',', ':'))
        
        # Compute HMAC using secret key
        h = hmac.new(
            settings.secret_key.encode('utf-8'),
            hmac_payload.encode('utf-8'),
            hashlib.sha256
        )
        
        return h.hexdigest()
    
    @staticmethod
    def verify_record_hmac(template: PromptTemplate) -> bool:
        """
        Verify template record hasn't been tampered with.
        """
        if not template.record_hmac:
            return False
        
        expected_hmac = TemplateService.compute_record_hmac(template)
        return hmac.compare_digest(template.record_hmac, expected_hmac)
    
    async def create_template(
        self,
        session: AsyncSession,
        org_id: str,
        template_name: str,
        canonical: Dict[str, Any],
        brand_name: Optional[str] = None,
        created_by: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new template with deduplication and idempotency.
        
        Args:
            db: Database session
            template_name: Human-readable template name
            template_config: Template configuration to canonicalize
            org_id: Organization ID
            created_by: User who created the template
            idempotency_key: Optional idempotency key
            
        Returns:
            Tuple of (template, is_new, conflict_diff)
            - template: The created or existing template
            - is_new: True if newly created, False if already existed
            - conflict_diff: RFC-6902 diff if template existed with different config
        """
        
        # Step 1: Canonicalize and hash the template
        canonical_json = canonicalize_json(canonical, for_hashing=True)
        template_sha256 = compute_template_hash(canonical_json)
        
        # Step 2: Check idempotency if key provided
        if idempotency_key and settings.enable_idempotency:
            idempotent_result = await TemplateService._check_idempotency(
                db, org_id, idempotency_key, template_sha256
            )
            if idempotent_result:
                return idempotent_result
        
        # Step 3: Check for existing template with same hash
        existing = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.org_id == org_id,
                PromptTemplate.template_sha256 == template_sha256
            )
        )
        existing_template = existing.scalar_one_or_none()
        
        if existing_template:
            # Template already exists - return it with deduplication flag
            return (existing_template, False, None)
        
        # Step 4: Create new template
        new_template = PromptTemplate(
            template_name=template_name,
            template_sha256=template_sha256,
            canonical_json=canonical,
            org_id=org_id,
            created_by=created_by
        )
        
        # Step 5: Compute and set HMAC (needs template_id first)
        db.add(new_template)
        await db.flush()  # Get the template_id
        
        new_template.record_hmac = TemplateService.compute_record_hmac(new_template)
        
        # Step 6: Store idempotency result if key provided
        if idempotency_key and settings.enable_idempotency:
            await TemplateService._store_idempotency(
                db, org_id, idempotency_key, template_sha256, new_template
            )
        
        try:
            await db.commit()
            return (new_template, True, None)
        except IntegrityError:
            # Race condition - another request created it
            await db.rollback()
            existing = await db.execute(
                select(PromptTemplate).where(
                    PromptTemplate.org_id == org_id,
                    PromptTemplate.template_sha256 == template_sha256
                )
            )
            return (existing.scalar_one(), False, None)
    
    @staticmethod
    async def get_template(
        db: AsyncSession,
        template_id: UUID,
        org_id: str = 'default',
        verify_hmac: bool = True
    ) -> Optional[PromptTemplate]:
        """
        Get a template by ID with optional HMAC verification.
        """
        result = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.template_id == template_id,
                PromptTemplate.org_id == org_id
            )
        )
        template = result.scalar_one_or_none()
        
        if template and verify_hmac:
            if not TemplateService.verify_record_hmac(template):
                raise ValueError(f"Template {template_id} failed HMAC verification - possible tampering")
        
        return template
    
    @staticmethod
    async def get_template_by_hash(
        db: AsyncSession,
        template_sha256: str,
        org_id: str = 'default'
    ) -> Optional[PromptTemplate]:
        """
        Get a template by its SHA-256 hash.
        """
        result = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.org_id == org_id,
                PromptTemplate.template_sha256 == template_sha256
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def _check_idempotency(
        db: AsyncSession,
        org_id: str,
        idempotency_key: str,
        body_sha256: str
    ) -> Optional[Tuple[PromptTemplate, bool, Optional[Dict]]]:
        """
        Check if an idempotent request was already processed.
        """
        result = await session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.org_id == org_id,
                IdempotencyKey.key == idempotency_key
            )
        )
        existing_key = result.scalar_one_or_none()
        
        if existing_key:
            # Check if expired
            if existing_key.is_expired():
                # Delete expired key
                await db.delete(existing_key)
                await db.flush()
                return None
            
            # Check if body matches
            if existing_key.body_sha256 != body_sha256:
                # Different request with same idempotency key
                return None  # Could raise an error instead
            
            # Return cached result
            if existing_key.result:
                template_id = existing_key.result.get('template_id')
                if template_id:
                    template = await TemplateService.get_template(
                        db, UUID(template_id), org_id
                    )
                    if template:
                        return (template, False, None)
        
        return None
    
    @staticmethod
    async def _store_idempotency(
        db: AsyncSession,
        org_id: str,
        idempotency_key: str,
        body_sha256: str,
        template: PromptTemplate
    ) -> None:
        """
        Store idempotency key result for future requests.
        """
        expires_at = datetime.utcnow() + timedelta(seconds=getattr(settings, 'idempotency_ttl_seconds', 86400))
        
        idempotent_key = IdempotencyKey(
            key=idempotency_key,
            org_id=org_id,
            body_sha256=body_sha256,
            result={'template_id': str(template.template_id)},
            expires_at=expires_at
        )
        
        session.add(idempotent_key)
        await session.flush()
    
    async def get_by_idempotency_key(
        self,
        session: AsyncSession,
        org_id: str,
        idempotency_key: str
    ) -> Optional[PromptTemplate]:
        """
        Get template by idempotency key if it exists and is not expired.
        """
        result = await session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.org_id == org_id,
                IdempotencyKey.key == idempotency_key
            )
        )
        existing_key = result.scalar_one_or_none()
        
        if existing_key:
            # Check if expired
            if datetime.utcnow() > existing_key.expires_at:
                return None
            
            if existing_key.result:
                template_id = existing_key.result.get('template_id')
                if template_id:
                    return await self.get_template(
                        session, UUID(template_id), org_id
                    )
        return None