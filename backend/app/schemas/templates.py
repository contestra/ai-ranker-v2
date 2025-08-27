"""
Pydantic schemas for template and run API endpoints
Per PRD v2.7 Section 6
"""

from datetime import datetime
from typing import Any, Dict, Optional, List, Literal
from uuid import UUID
from pydantic import BaseModel, Field, AliasChoices

# Enums
GroundingMode = Literal["UNGROUNDED", "PREFERRED", "REQUIRED"]
DriftPolicy = Literal["hard", "fail", "warn"]
ProviderType = Literal["openai", "vertex", "gemini"]


class TemplateCreate(BaseModel):
    """Request body for POST /v1/templates"""
    
    template_name: str = Field(..., description="Human-readable template name")
    canonical: Dict[str, Any] = Field(
        ..., 
        description="Template canonical JSON per PRD §4/§5 - will be canonicalized server-side"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_name": "Product Description Generator",
                "canonical": {
                    "provider": "openai",
                    "model_version_constraint": "gpt-4o-2024-08-06",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Generate a product description for {product}"}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500,
                    "grounding_mode": "PREFERRED",
                    "seed_key_id": "k1"
                }
            }
        }


class TemplateResponse(BaseModel):
    """Response for template creation and retrieval"""
    
    template_id: UUID
    template_sha256: str
    template_name: str
    canonical_json: Dict[str, Any]
    org_id: str
    created_at: datetime
    created_by: Optional[str] = None
    is_new: Optional[bool] = Field(None, description="True if newly created, False if already existed")
    conflict_diff: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="RFC-6902 JSON patch if template existed with different config"
    )
    
    class Config:
        from_attributes = True


class RunTemplateRequest(BaseModel):
    """Simplified request to execute a template - Phase 1"""
    variables: Dict[str, Any] = Field(default_factory=dict)
    grounded: bool = False
    json_mode: bool = False
    vendor: Optional[str] = None
    model: Optional[str] = None
    idempotency_key: Optional[str] = None
    als_context: Optional[Dict[str, Any]] = None

class RunTemplateResponse(BaseModel):
    """Simplified response from template execution - Phase 1"""
    run_id: str
    template_id: str
    output_text: str
    grounded_requested: bool
    grounded_effective: bool
    vendor: str
    model: str
    latency_ms: int
    usage: Dict[str, Any] = {}
    created_at: str
    metadata: Dict[str, Any] = {}

class RunRequest(BaseModel):
    """Request body for POST /v1/templates/{id}/run"""
    
    grounding_mode: Optional[GroundingMode] = Field(
        None,
        description="Override template's grounding mode"
    )
    locale: Optional[str] = Field(
        None,
        description="Locale for ALS (e.g., 'en-US', 'de-DE')"
    )
    als_params: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional ALS parameters"
    )
    model_fingerprint_allowlist: Optional[List[str]] = Field(
        None,
        description="Optional allowlist of acceptable model fingerprints"
    )
    strict_json: bool = Field(
        False,
        description="Enforce strict JSON output validation",
        validation_alias=AliasChoices("strict_json", "json_mode")
    )
    client_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Client-provided context for tracking"
    )


class RunResponse(BaseModel):
    """Response for template run execution"""
    
    run_id: UUID
    template_id: UUID
    run_sha256: str
    
    # Output
    output: Optional[str] = None
    response_output_sha256: Optional[str] = None
    output_json_valid: Optional[bool] = None
    
    # Model tracking
    vendor: ProviderType
    model_version_effective: str
    model_fingerprint: Optional[str] = None
    
    # Grounding
    grounding_mode: str
    grounded_effective: Optional[bool] = None
    why_not_grounded: Optional[str] = None
    
    # ALS
    locale_selected: Optional[str] = None
    als_block_sha256: Optional[str] = None
    als_block_text: Optional[str] = None
    als_variant_id: Optional[str] = None
    seed_key_id: Optional[str] = None
    
    # Gemini two-step attestation
    step2_tools_invoked: Optional[bool] = None
    step2_source_ref: Optional[str] = None
    
    # Metadata
    usage: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class BatchRunRequest(BaseModel):
    """Request body for POST /v1/templates/{id}/batch-run"""
    
    models: List[str] = Field(
        ...,
        description="List of model names to run template against"
    )
    locales: List[str] = Field(
        ...,
        description="List of locales to run (e.g., ['en-US', 'de-DE'])"
    )
    grounding_modes: List[GroundingMode] = Field(
        default=["UNGROUNDED"],
        description="List of grounding modes to test"
    )
    replicates: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of replicates per model/locale/mode combination",
        alias="replicate_count"
    )
    drift_policy: DriftPolicy = Field(
        default="fail",
        description="Policy for handling version drift: hard|fail|warn"
    )
    max_parallel: Optional[int] = Field(
        None,
        ge=1,
        le=50,
        description="Maximum parallel executions"
    )
    inputs: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Template input variables"
    )


class BatchRunResponse(BaseModel):
    """Response for batch run creation"""
    
    batch_id: UUID
    template_id: UUID
    batch_sha256: str
    status: str
    preflight_model_version: Optional[str] = None
    preflight_model_fingerprint: Optional[str] = None
    total_runs: int
    successful_runs: Optional[int] = None
    failed_runs: Optional[int] = None
    created_at: datetime
    run_ids: Optional[List[str]] = None
    
    class Config:
        from_attributes = True


class ProviderVersionsResponse(BaseModel):
    """Response for GET /v1/providers/{provider}/versions"""
    
    provider: str
    versions: List[str]
    current: str
    last_checked_utc: datetime
    expires_at_utc: datetime
    source: Literal["cache", "live"]
    etag: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "provider": "openai",
                "versions": [
                    "gpt-4o-2024-08-06",
                    "gpt-4o-2024-05-13",
                    "gpt-4-turbo-2024-04-09"
                ],
                "current": "gpt-4o-2024-08-06",
                "last_checked_utc": "2024-08-22T10:30:00Z",
                "expires_at_utc": "2024-08-22T10:35:00Z",
                "source": "cache",
                "etag": "W/\"xyz123\""
            }
        }


class RunListResponse(BaseModel):
    """Response for GET /v1/templates/{id}/runs"""
    
    runs: List[RunResponse]
    total: int
    page: int
    page_size: int
    
    class Config:
        from_attributes = True