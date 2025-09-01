"""
SQLAlchemy models for AI Ranker V2
Based on PRD v2.7 and schema from create_schema.sql
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    String, Text, UniqueConstraint, Index, JSON, Numeric
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class PromptTemplate(Base):
    """
    Templates table with immutability per PRD §8
    """
    __tablename__ = 'prompt_templates'
    
    # Primary key
    template_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Template identity
    template_name = Column(String(255), nullable=False)
    template_sha256 = Column(String(64), nullable=False, index=True)
    canonical_json = Column(JSON, nullable=False)
    
    # Organization
    org_id = Column(String(255), nullable=False, default='default')
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    created_by = Column(String(255))
    
    # Tamper detection per PRD
    record_hmac = Column(String(64))
    
    # Relationships
    runs = relationship("Run", back_populates="template", cascade="all, delete-orphan")
    batches = relationship("Batch", back_populates="template", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('org_id', 'template_sha256', name='uq_template_org_hash'),
        Index('idx_template_created', 'created_at'),
    )
    
    def __repr__(self):
        return f"<PromptTemplate(id={self.template_id}, name={self.template_name})>"


class Run(Base):
    """
    Runs table with complete Phase-1 columns for run persistence
    """
    __tablename__ = 'runs'
    
    # Primary key
    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign keys
    template_id = Column(UUID(as_uuid=True), ForeignKey('prompt_templates.template_id'))
    batch_id = Column(UUID(as_uuid=True), ForeignKey('batches.batch_id'), nullable=True)
    
    # Run identity
    batch_run_index = Column(Integer)
    run_sha256 = Column(String(64), nullable=False)
    
    # Core execution fields
    vendor = Column(Text)
    model = Column(Text)
    grounded_requested = Column(Boolean, nullable=False, default=False)
    grounded_effective = Column(Boolean, nullable=False, default=False)
    json_mode = Column(Boolean, nullable=False, default=False)
    
    # Request/Response tracking
    request_json = Column(JSON, nullable=False, default={})
    output_text = Column(Text, nullable=False, default='')
    response_json = Column(JSON, nullable=False, default={})
    response_output_sha256 = Column(String(64), index=True)
    output_json_valid = Column(Boolean)
    
    # Performance metrics
    latency_ms = Column(Integer, nullable=False, default=0)
    tokens_input = Column(Integer, nullable=False, default=0)
    tokens_output = Column(Integer, nullable=False, default=0)
    tokens_reasoning = Column(Integer, nullable=False, default=0)
    usage = Column(JSON)
    
    # Status tracking
    status = Column(Text, nullable=False, default='succeeded')
    error_message = Column(Text)
    why_not_grounded = Column(Text)
    
    # Model versioning
    model_version_effective = Column(String(100))
    model_fingerprint = Column(String(255))
    
    # Locale/ALS fields
    locale_selected = Column(String(10))
    grounding_mode = Column(String(20))
    als_block_sha256 = Column(String(64))
    als_block_text = Column(Text)
    als_variant_id = Column(String(100))
    seed_key_id = Column(String(20))
    provoker_value = Column(String(100))
    
    # Gemini two-step attestation
    step2_tools_invoked = Column(Boolean)
    step2_source_ref = Column(String(64))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    template = relationship("PromptTemplate", back_populates="runs")
    batch = relationship("Batch", back_populates="runs")
    
    # Indexes
    __table_args__ = (
        Index('idx_template_runs', 'template_id', 'created_at'),
        Index('idx_batch_runs', 'batch_id', 'batch_run_index'),
    )
    
    def __repr__(self):
        return f"<Run(id={self.run_id}, template={self.template_id})>"


class Batch(Base):
    """
    Batches table for batch execution tracking
    """
    __tablename__ = 'batches'
    
    # Primary key
    batch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign key
    template_id = Column(UUID(as_uuid=True), ForeignKey('prompt_templates.template_id'))
    
    # Batch identity
    batch_sha256 = Column(String(64))
    
    # Preflight lock per PRD §8
    preflight_model_version = Column(String(100))
    preflight_model_fingerprint = Column(String(255))
    
    # Configuration
    parameters = Column(JSON)
    
    # Status
    status = Column(String(20), default='pending')
    
    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    template = relationship("PromptTemplate", back_populates="batches")
    runs = relationship("Run", back_populates="batch", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_batch_status', 'status', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Batch(id={self.batch_id}, status={self.status})>"


class Country(Base):
    """
    Countries table for ALS (Ambient Location Signals)
    """
    __tablename__ = 'countries'
    
    # Primary key
    id = Column(Integer, primary_key=True)
    
    # Country data
    code = Column(String(2), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    emoji = Column(String(10))
    vat_rate = Column(Numeric(5, 2))
    plug_types = Column(String(50))
    emergency_numbers = Column(String(50))
    locale_code = Column(String(10))
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<Country(code={self.code}, name={self.name})>"


class ProviderVersionCache(Base):
    """
    Provider version cache with TTL per PRD §3
    """
    __tablename__ = 'provider_version_cache'
    
    # Primary key
    provider = Column(String(50), primary_key=True)
    
    # Version data
    versions = Column(JSON)
    current = Column(String(100))
    
    # Cache management
    last_checked_utc = Column(DateTime(timezone=True))
    expires_at_utc = Column(DateTime(timezone=True), index=True)
    etag = Column(String(100))
    source = Column(String(20))  # 'cache' or 'live'
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        if not self.expires_at_utc:
            return True
        return datetime.utcnow() > self.expires_at_utc
    
    def __repr__(self):
        return f"<ProviderVersionCache(provider={self.provider}, current={self.current})>"


class IdempotencyKey(Base):
    """
    Idempotency keys table per PRD §7
    """
    __tablename__ = 'idempotency_keys'
    
    # Composite primary key
    key = Column(String(100), primary_key=True)
    org_id = Column(String(255), primary_key=True)
    
    # Request tracking
    body_sha256 = Column(String(64), nullable=False)
    result = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    expires_at = Column(DateTime(timezone=True), index=True)
    
    def is_expired(self) -> bool:
        """Check if idempotency key is expired"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f"<IdempotencyKey(key={self.key}, org={self.org_id})>"


class LLMTelemetry(Base):
    """
    Telemetry for LLM API calls - one row per call
    Tracks vendor, model, performance, and token usage
    """
    __tablename__ = 'llm_telemetry'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    vendor = Column(String(50), nullable=False)  # openai, vertex
    model = Column(String(100), nullable=False)  # gpt-4o, gemini-1.5-pro
    grounded = Column(Boolean, nullable=False, default=False)
    grounded_effective = Column(Boolean, nullable=False, default=False)  # Whether grounding actually happened
    json_mode = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Integer)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    success = Column(Boolean, nullable=False, default=True)
    error_type = Column(String(100))
    template_id = Column(UUID(as_uuid=True))  # Optional link to template
    run_id = Column(String(255))  # Optional run identifier
    meta = Column(JSON)  # Rich metadata: ALS, grounding, citations, feature flags
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Indexes for analysis
    __table_args__ = (
        Index('idx_llm_telemetry_vendor_model', 'vendor', 'model'),
        Index('idx_llm_telemetry_created_at', 'created_at'),
        Index('idx_llm_telemetry_template_id', 'template_id'),
    )
    
    def __repr__(self):
        return f"<LLMTelemetry(id={self.id}, vendor={self.vendor}, model={self.model})>"