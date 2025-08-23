"""
Tests for template service - deduplication and HMAC
"""

import pytest
import asyncio
import os
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.models.base import Base
from app.models.models import PromptTemplate
from app.services.template_service import TemplateService
from app.core.config import settings


@pytest.fixture(scope="function")
async def test_db():
    """
    Create a test database session using Neon PostgreSQL.
    Uses a test schema to isolate test data.
    """
    # Use the same Neon database but with a test schema
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set - skipping database tests")
    
    # Create engine
    engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=NullPool  # Important for Neon
    )
    
    # Create a test schema for isolation
    test_schema = f"test_{uuid4().hex[:8]}"
    
    async with engine.begin() as conn:
        # Create test schema
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {test_schema}"))
        await conn.execute(text(f"SET search_path TO {test_schema}"))
        
        # Create tables in test schema
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session with test schema
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        # Set search path for session
        await session.execute(text(f"SET search_path TO {test_schema}"))
        
        try:
            yield session
            await session.rollback()
        finally:
            # Clean up test schema
            await session.execute(text(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE"))
            await session.commit()
    
    await engine.dispose()


class TestTemplateService:
    """Test template service functionality"""
    
    @pytest.mark.asyncio
    async def test_create_template(self, test_db):
        """Test basic template creation"""
        template_config = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7
        }
        
        template, is_new, conflict = await TemplateService.create_template(
            test_db,
            template_name="Test Template",
            template_config=template_config,
            org_id="test_org",
            created_by="test_user"
        )
        
        assert template is not None
        assert is_new is True
        assert conflict is None
        assert template.template_name == "Test Template"
        assert template.org_id == "test_org"
        assert template.created_by == "test_user"
        assert template.template_sha256 is not None
        assert template.record_hmac is not None
    
    @pytest.mark.asyncio
    async def test_template_deduplication(self, test_db):
        """Test that identical templates are deduplicated"""
        template_config = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7
        }
        
        # Create first template
        template1, is_new1, _ = await TemplateService.create_template(
            test_db,
            template_name="Template 1",
            template_config=template_config,
            org_id="test_org"
        )
        
        assert is_new1 is True
        
        # Create second template with same config
        template2, is_new2, _ = await TemplateService.create_template(
            test_db,
            template_name="Template 2",  # Different name
            template_config=template_config,  # Same config
            org_id="test_org"
        )
        
        assert is_new2 is False  # Should be deduplicated
        assert template1.template_id == template2.template_id
        assert template1.template_sha256 == template2.template_sha256
    
    @pytest.mark.asyncio
    async def test_template_canonicalization(self, test_db):
        """Test that templates are canonicalized before hashing"""
        # These configs should canonicalize to the same value
        config1 = {
            "temperature": 0.7000000,  # Extra decimals
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        config2 = {
            "model": "gpt-4",  # Different key order
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7
        }
        
        template1, _, _ = await TemplateService.create_template(
            test_db,
            template_name="Template 1",
            template_config=config1,
            org_id="test_org"
        )
        
        template2, is_new, _ = await TemplateService.create_template(
            test_db,
            template_name="Template 2",
            template_config=config2,
            org_id="test_org"
        )
        
        # Should be the same template due to canonicalization
        assert is_new is False
        assert template1.template_id == template2.template_id
        assert template1.template_sha256 == template2.template_sha256
    
    @pytest.mark.asyncio
    async def test_hmac_verification(self, test_db):
        """Test HMAC verification for tamper detection"""
        template_config = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Test"}]
        }
        
        template, _, _ = await TemplateService.create_template(
            test_db,
            template_name="HMAC Test",
            template_config=template_config,
            org_id="test_org"
        )
        
        # Verify HMAC is correct
        assert TemplateService.verify_record_hmac(template) is True
        
        # Tamper with the template
        original_hmac = template.record_hmac
        template.template_name = "Tampered Name"
        
        # HMAC should no longer verify
        template.record_hmac = original_hmac  # Keep old HMAC
        assert TemplateService.verify_record_hmac(template) is False
        
        # Recompute HMAC after change
        template.record_hmac = TemplateService.compute_record_hmac(template)
        assert TemplateService.verify_record_hmac(template) is True
    
    @pytest.mark.asyncio
    async def test_get_template_by_hash(self, test_db):
        """Test retrieving template by hash"""
        template_config = {
            "model": "gpt-4",
            "prompt": "Test prompt"
        }
        
        created_template, _, _ = await TemplateService.create_template(
            test_db,
            template_name="Hash Lookup Test",
            template_config=template_config,
            org_id="test_org"
        )
        
        # Retrieve by hash
        found_template = await TemplateService.get_template_by_hash(
            test_db,
            template_sha256=created_template.template_sha256,
            org_id="test_org"
        )
        
        assert found_template is not None
        assert found_template.template_id == created_template.template_id
        
        # Try with non-existent hash
        not_found = await TemplateService.get_template_by_hash(
            test_db,
            template_sha256="nonexistent_hash",
            org_id="test_org"
        )
        
        assert not_found is None
    
    @pytest.mark.asyncio  
    async def test_org_isolation(self, test_db):
        """Test that templates are isolated by organization"""
        template_config = {
            "model": "gpt-4",
            "prompt": "Shared config"
        }
        
        # Create template for org1
        template_org1, _, _ = await TemplateService.create_template(
            test_db,
            template_name="Org1 Template",
            template_config=template_config,
            org_id="org1"
        )
        
        # Create same template for org2
        template_org2, is_new, _ = await TemplateService.create_template(
            test_db,
            template_name="Org2 Template",
            template_config=template_config,
            org_id="org2"
        )
        
        # Should be a new template despite same config
        assert is_new is True
        assert template_org1.template_id != template_org2.template_id
        assert template_org1.template_sha256 == template_org2.template_sha256  # Same hash
        assert template_org1.org_id != template_org2.org_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])