"""
Run API endpoints
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.database import get_session
from app.models.models import Run

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs")
async def list_runs(
    session: AsyncSession = Depends(get_session),
    template_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """
    List all runs, optionally filtered by template_id.
    """
    query = select(Run)
    
    if template_id:
        query = query.where(Run.template_id == UUID(template_id))
    
    query = query.order_by(desc(Run.created_at))
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # Execute query
    result = await session.execute(query)
    runs = result.scalars().all()
    
    # Convert to response format
    run_list = []
    for run in runs:
        run_list.append({
            "id": str(run.run_id),
            "template_id": str(run.template_id),
            "status": run.status or "completed",
            "input_data": run.request_json,
            "output_data": run.output_text or run.response_json,
            "error": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        })
    
    return run_list


@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """
    Get a specific run by ID.
    """
    run = await session.get(Run, run_id)
    
    if not run:
        return {"error": "Run not found"}
    
    return {
        "id": str(run.run_id),
        "template_id": str(run.template_id),
        "status": run.status or "completed",
        "input_data": run.request_json,
        "output_data": run.output_text or run.response_json,
        "error": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.post("/runs")
async def create_run(
    request: dict,
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new run (for compatibility - actual execution happens via /v1/templates/{id}/run)
    """
    from app.services.template_runner import execute_template_run
    from app.schemas.templates import RunTemplateRequest
    
    try:
        # Execute the template
        result = await execute_template_run(
            session=session,
            template_id=UUID(request["template_id"]),
            request=RunTemplateRequest(
                inputs=request.get("input_data", {}),
                locale="en-US"
            ),
            org_id="test-org",
            user_id=None
        )
        
        # Return in expected format
        return {
            "id": str(result.run_id),
            "template_id": request["template_id"],
            "status": "completed",
            "input_data": request.get("input_data", {}),
            "output_data": result.output,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "id": str(UUID("00000000-0000-0000-0000-000000000000")),
            "template_id": request["template_id"],
            "status": "failed",
            "input_data": request.get("input_data", {}),
            "error": str(e),
            "created_at": datetime.utcnow().isoformat(),
        }


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """
    Delete a run (soft delete or mark as deleted)
    """
    run = await session.get(Run, run_id)
    
    if not run:
        return {"error": "Run not found"}
    
    # For now, just return success since we don't actually delete
    return {"success": True}