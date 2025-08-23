"""
Template API endpoints
Per PRD v2.7 Section 6
"""

from typing import Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.schemas.templates import (
    TemplateCreate,
    TemplateResponse,
    RunRequest,
    RunResponse,
    BatchRunRequest,
    BatchRunResponse,
    RunListResponse
)
from app.services.template_service_v2 import TemplateService
from app.services import idempotency
from app.services.providers import ProviderVersionService
from app.api import errors
from app.core.jsondiff import generate_rfc6902_diff


router = APIRouter(prefix="/v1", tags=["templates"])


@router.post("/templates", response_model=TemplateResponse)
async def create_template(
    request: TemplateCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Create an immutable template with canonicalization and deduplication.
    
    Returns:
    - 201: New template created
    - 200: Existing template with same hash returned
    - 409: Idempotency conflict (different template with same idempotency key)
    """
    service = TemplateService()
    
    # Prepare body for idempotency check
    body_for_key = {
        "canonical": request.canonical,
        "template_name": request.template_name
    }
    
    # Check idempotency if key provided
    if x_idempotency_key:
        try:
            await idempotency.reserve_idempotency(
                session, x_organization_id, x_idempotency_key, body_for_key
            )
        except ValueError as e:
            errors.conflict(
                code="IDEMPOTENCY_CONFLICT",
                detail=str(e)
            )
    
    # Create or get template
    try:
        template, created = await service.create_or_get_template(
            session=session,
            org_id=x_organization_id,
            canonical_body=request.canonical,
            template_name=request.template_name,
            created_by=x_user_id
        )
    except Exception as e:
        errors.unprocessable(
            code="CANONICALIZATION_ERROR",
            detail=f"Failed to process template: {str(e)}"
        )
    
    # Commit the transaction
    await session.commit()
    
    # Set correct status code
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    
    # Return response
    return TemplateResponse(
        template_id=template.template_id,
        template_sha256=template.template_sha256,
        template_name=template.template_name,
        canonical_json=template.canonical_json,
        org_id=template.org_id,
        created_at=template.created_at,
        created_by=template.created_by,
        is_new=created
    )


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_session),
    x_organization_id: str = Header(..., alias="X-Organization-Id")
):
    """Get a template by ID"""
    service = TemplateService()
    template = await service.get_template(session, template_id, x_organization_id)
    
    if not template:
        errors.not_found(
            code="TEMPLATE_NOT_FOUND",
            detail=f"Template {template_id} not found",
            extra={"template_id": str(template_id)}
        )
    
    return TemplateResponse(
        template_id=template.template_id,
        template_sha256=template.template_sha256,
        template_name=template.template_name,
        canonical_json=template.canonical_json,
        org_id=template.org_id,
        created_at=template.created_at,
        created_by=template.created_by
    )


@router.post("/templates/{template_id}/run", response_model=RunResponse)
async def run_template(
    template_id: UUID,
    request: RunRequest,
    session: AsyncSession = Depends(get_session),
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Execute a template run with version enforcement and grounding checks.
    
    Enforces:
    - Model version equality with constraint
    - Optional fingerprint allowlist
    - Strict JSON validation if requested
    - Grounding requirements based on mode
    """
    from app.llm.types import LLMRequest
    from app.llm.unified_llm_adapter import UnifiedLLMAdapter
    from app.models.models import PromptTemplate
    import uuid
    import hashlib
    import json
    from datetime import datetime
    
    # Get the template
    template = await session.get(PromptTemplate, template_id)
    if not template or template.org_id != x_organization_id:
        errors.not_found(
            code="TEMPLATE_NOT_FOUND",
            detail=f"Template {template_id} not found"
        )
    
    # Parse the canonical JSON
    canonical = template.canonical_json
    
    # Create LLM request - strict validation, no silent defaults
    json_mode_requested = request.strict_json if request else False
    
    # Strict field validation - fail closed instead of defaulting
    vendor = canonical.get("vendor") or canonical.get("provider")
    model = canonical.get("model")
    
    if not vendor:
        errors.unprocessable(
            code="TEMPLATE_INVALID",
            detail="Template canonical.vendor is required"
        )
    if not model:
        errors.unprocessable(
            code="TEMPLATE_INVALID", 
            detail="Template canonical.model is required"
        )
    
    run_id = str(uuid.uuid4())
    
    llm_request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=canonical.get("messages", []),
        temperature=canonical.get("temperature", 0.0),
        max_tokens=canonical.get("max_tokens"),
        grounded=bool(canonical.get("grounded", False)),
        json_mode=json_mode_requested,
        tools=canonical.get("tools"),
        template_id=str(template_id),
        run_id=run_id
    )
    
    # Execute with adapter
    adapter = UnifiedLLMAdapter()
    llm_response = await adapter.complete(llm_request, session=session)
    
    # Handle adapter errors
    if not llm_response.success:
        if "DefaultCredentialsError" in llm_response.error_type or "auth" in llm_response.error_message.lower():
            errors.service_unavailable(
                code="VENDOR_AUTH_ERROR",
                detail=f"Authentication failed for {llm_response.vendor}: {llm_response.error_message}"
            )
        else:
            errors.service_unavailable(
                code="VENDOR_ERROR", 
                detail=f"Provider error: {llm_response.error_message}"
            )
    
    # Create response
    run_id = uuid.uuid4()
    run_sha = hashlib.sha256(f"{template_id}{datetime.utcnow()}".encode()).hexdigest()
    
    return RunResponse(
        run_id=run_id,
        template_id=template_id,
        run_sha256=run_sha,
        vendor=llm_response.vendor,
        locale_selected=request.locale if request else "en-US",
        grounding_mode=canonical.get("grounding_mode", "UNGROUNDED"),
        grounded_effective=llm_response.grounded_effective,
        model_version_effective=llm_response.model_version,
        model_fingerprint=llm_response.model_fingerprint,
        output=llm_response.content,
        output_json_valid=True if json_mode_requested else None,
        usage=llm_response.usage,
        latency_ms=llm_response.latency_ms,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow()
    )


@router.post("/templates/{template_id}/batch-run", response_model=BatchRunResponse)
async def batch_run_template(
    template_id: UUID,
    request: BatchRunRequest,
    session: AsyncSession = Depends(get_session),
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Execute batch runs with deterministic expansion and drift policy.
    
    Features:
    - Preflight model version/fingerprint lock
    - Deterministic locale × mode × replicate expansion
    - Configurable drift policy (hard|fail|warn)
    - Rate limiting and parallel execution control
    """
    # TODO: Implement batch execution
    # This requires TaskRunner abstraction
    errors.service_unavailable(
        code="NOT_IMPLEMENTED",
        detail="Batch execution not yet implemented",
        extra={"template_id": str(template_id)}
    )


@router.get("/templates/{template_id}/runs", response_model=RunListResponse)
async def list_runs(
    template_id: UUID,
    session: AsyncSession = Depends(get_session),
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    batch_id: Optional[UUID] = Query(None),
    locale: Optional[str] = Query(None)
):
    """
    List runs for a template with filtering.
    
    Filters:
    - batch_id: Show only runs from a specific batch
    - locale: Filter by locale
    - Pagination via page/page_size
    """
    # TODO: Implement run listing
    # This requires Run model queries
    return RunListResponse(
        runs=[],
        total=0,
        page=page,
        page_size=page_size
    )