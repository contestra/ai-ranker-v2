"""
Template service for AI Ranker V2 - Clean implementation
Per PRD v2.7 with proper deduplication and status codes
"""

from typing import Dict, Any, Tuple, Optional
from datetime import datetime
from uuid import UUID
import hashlib
import hmac
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from sqlalchemy.exc import IntegrityError

from app.models.models import PromptTemplate
from app.core.canonicalization import canonicalize_json, compute_template_hash
from app.core.config import get_settings


settings = get_settings()


class TemplateService:
    """Service for managing prompt templates with immutability guarantees"""
    
    @staticmethod
    def compute_record_hmac(
        org_id: str,
        template_sha256: str,
        canonical_json: Dict[str, Any]
    ) -> str:
        """Compute HMAC for tamper detection"""
        hmac_data = {
            'org_id': org_id,
            'template_sha256': template_sha256,
            'canonical_json': canonical_json
        }
        hmac_payload = json.dumps(hmac_data, sort_keys=True, separators=(',', ':'))
        
        h = hmac.new(
            settings.secret_key.encode('utf-8'),
            hmac_payload.encode('utf-8'),
            hashlib.sha256
        )
        return h.hexdigest()
    
    async def get_by_hash(
        self,
        session: AsyncSession,
        org_id: str,
        template_sha256: str
    ) -> Optional[PromptTemplate]:
        """Get template by its SHA-256 hash"""
        result = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.org_id == org_id,
                PromptTemplate.template_sha256 == template_sha256
            )
        )
        return result.scalar_one_or_none()
    
    async def create_or_get_template(
        self,
        session: AsyncSession,
        org_id: str,
        canonical_body: Dict[str, Any],
        template_name: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> Tuple[PromptTemplate, bool]:
        """
        Create a new template or return existing one with same hash.
        
        Returns:
            Tuple of (template, created) where created is True if newly created
        """
        # 1) Canonicalize and hash
        canonical_json = canonicalize_json(canonical_body, for_hashing=True)
        template_sha256 = compute_template_hash(canonical_json)
        
        # 2) Check for existing template with same hash
        existing = await self.get_by_hash(session, org_id, template_sha256)
        if existing:
            return existing, False  # Not created, already exists
        
        # 3) Compute HMAC for new template
        record_hmac = self.compute_record_hmac(
            org_id=org_id,
            template_sha256=template_sha256,
            canonical_json=canonical_json
        )
        
        # 4) Create new template
        new_template = PromptTemplate(
            org_id=org_id,
            template_sha256=template_sha256,
            canonical_json=canonical_json,
            template_name=template_name or "Untitled Template",
            record_hmac=record_hmac,
            created_by=created_by
        )
        
        session.add(new_template)
        
        try:
            await session.flush()  # Get the ID without committing
            return new_template, True  # Created
        except IntegrityError:
            # Race condition - another request created it
            await session.rollback()
            existing = await self.get_by_hash(session, org_id, template_sha256)
            if existing:
                return existing, False
            raise  # Unexpected error
    
    async def get_template(
        self,
        session: AsyncSession,
        template_id: UUID,
        org_id: str
    ) -> Optional[PromptTemplate]:
        """Get template by ID"""
        result = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.template_id == template_id,
                PromptTemplate.org_id == org_id
            )
        )
        return result.scalar_one_or_none()
    
    def verify_record_hmac(self, template: PromptTemplate) -> bool:
        """Verify template hasn't been tampered with"""
        if not template.record_hmac:
            return False
        
        expected = self.compute_record_hmac(
            org_id=template.org_id,
            template_sha256=template.template_sha256,
            canonical_json=template.canonical_json
        )
        return hmac.compare_digest(template.record_hmac, expected)