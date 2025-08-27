"""
Template execution service with run persistence
Phase-1 implementation for storing all runs to database
"""

import time
import json
import hashlib
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Run, PromptTemplate
from app.llm.types import LLMRequest
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.schemas.templates import RunTemplateRequest, RunTemplateResponse
from app.core.canonicalization import compute_sha256
from app.services.als_constants import get_system_prompt, ALS_SYSTEM_PROMPT
from app.services.als.als_builder import ALSBuilder

# Initialize adapter
adapter = UnifiedLLMAdapter()


def render_template(template: PromptTemplate, variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    Render template with variables.
    For Phase-1, we'll do simple string replacement in messages.
    """
    canonical = template.canonical_json
    messages = canonical.get("messages", [])
    
    # Simple variable substitution
    rendered_messages = []
    for msg in messages:
        rendered_msg = msg.copy()
        if "content" in rendered_msg and isinstance(rendered_msg["content"], str):
            content = rendered_msg["content"]
            for key, value in variables.items():
                placeholder = f"{{{key}}}"
                if placeholder in content:
                    content = content.replace(placeholder, str(value))
            rendered_msg["content"] = content
        rendered_messages.append(rendered_msg)
    
    return rendered_messages


async def execute_template_run(
    session: AsyncSession,
    template_id: str,
    request: RunTemplateRequest,
    org_id: str,
    user_id: Optional[str] = None
) -> RunTemplateResponse:
    """
    Execute a template and persist the run to database.
    
    Args:
        session: Database session
        template_id: Template UUID
        request: Run request with variables and options
        org_id: Organization ID
        user_id: Optional user ID
        
    Returns:
        RunTemplateResponse with execution results
        
    Raises:
        ValueError: Template not found
        RuntimeError: Execution error
    """
    
    # Get the template
    result = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.template_id == template_id,
            PromptTemplate.org_id == org_id
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise ValueError(f"Template {template_id} not found")
    
    # TODO: Implement idempotency check if idempotency_key provided
    # This would check the idempotency_keys table for existing runs
    
    # Render the template with variables
    rendered_messages = render_template(template, request.variables)
    
    # Get model and vendor from template or request
    canonical = template.canonical_json
    model = request.model or canonical.get("model", "gpt-5")
    vendor = request.vendor or canonical.get("vendor") or canonical.get("provider", "openai")
    
    # Generate run ID for this execution
    run_id = uuid4()
    
    # CRITICAL: Handle ALS message ordering if ALS context is provided
    final_messages = []
    als_context_dict = request.als_context or {}
    
    if als_context_dict and als_context_dict.get('als_enabled'):
        # MISSION-CRITICAL: Message ordering for ALS (DO NOT MODIFY)
        # 1. System prompt with EXACT ALS prompt
        final_messages.append({
            "role": "system",
            "content": ALS_SYSTEM_PROMPT
        })
        
        # 2. ALS context as SEPARATE user message (ambient signals)
        if 'als_block' in als_context_dict:
            final_messages.append({
                "role": "user", 
                "content": als_context_dict['als_block']
            })
        
        # 3. User's actual question (NAKED, unmodified) - filter out any system messages
        for msg in rendered_messages:
            if msg.get('role') == 'user':
                final_messages.append(msg)
                break  # Only take the first user message as the actual question
    else:
        # Non-ALS run: inject default system prompt if no system message exists
        has_system = any(msg.get('role') == 'system' for msg in rendered_messages)
        if not has_system:
            final_messages.append({
                "role": "system",
                "content": get_system_prompt(use_als=False)
            })
        final_messages.extend(rendered_messages)
    
    # Build LLM request with properly ordered messages
    llm_request = LLMRequest(
        vendor=vendor,
        model=model,
        messages=final_messages,  # Use the properly ordered messages
        grounded=request.grounded,
        json_mode=request.json_mode,
        als_context={},  # Don't pass ALS context since we've already injected it in messages
        temperature=canonical.get("temperature", 0.7),
        max_tokens=canonical.get("max_tokens", 6000),
        template_id=str(template_id),
        run_id=str(run_id)
    )
    
    # Execute with timing
    t0 = time.perf_counter()
    
    try:
        # Call the adapter (now with grounding support!)
        llm_response = await adapter.complete(llm_request, session)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Extract results
        output_text = llm_response.content or ""
        grounded_effective = llm_response.grounded_effective
        usage = llm_response.usage or {}
        
        # Normalize token counts
        tokens_input = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        tokens_output = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
        tokens_reasoning = usage.get("reasoning_tokens", 0)
        
        status = "succeeded"
        error_message = None
        
    except Exception as e:
        # Handle execution errors
        latency_ms = int((time.perf_counter() - t0) * 1000)
        output_text = ""
        grounded_effective = False
        usage = {}
        tokens_input = 0
        tokens_output = 0
        tokens_reasoning = 0
        status = "failed"
        error_message = str(e)
    
    # Compute run hash for deduplication
    run_data = {
        "template_id": str(template_id),
        "variables": request.variables,
        "vendor": vendor,
        "model": model,
        "grounded": request.grounded,
        "json_mode": request.json_mode
    }
    run_sha256 = compute_sha256(run_data)
    
    # Build request JSON for storage
    request_json = {
        "messages": rendered_messages,
        "variables": request.variables,
        "vendor": vendor,
        "model": model,
        "grounded": request.grounded,
        "json_mode": request.json_mode,
        "temperature": canonical.get("temperature", 0.7),
        "max_tokens": canonical.get("max_tokens", 500)
    }
    
    # Build response JSON for storage
    response_json = {
        "content": output_text,
        "grounded_effective": grounded_effective,
        "usage": usage,
    }
    
    # Add model version info only if successful
    if status == "succeeded" and 'llm_response' in locals():
        response_json.update({
            "model_version": getattr(llm_response, 'model_version', model),
            "model_fingerprint": getattr(llm_response, 'model_fingerprint', None)
        })
    else:
        response_json.update({
            "model_version": model,
            "model_fingerprint": None
        })
    
    # Create Run record
    run = Run(
        run_id=run_id,
        template_id=template_id,
        run_sha256=run_sha256,
        vendor=vendor,
        model=model,
        grounded_requested=request.grounded,
        grounded_effective=grounded_effective,
        json_mode=request.json_mode,
        grounding_mode="GR" if request.grounded else "UN",
        request_json=request_json,
        output_text=output_text,
        response_json=response_json,
        response_output_sha256=compute_sha256(output_text) if output_text else None,
        output_json_valid=None,  # TODO: Validate if json_mode
        usage=usage,
        latency_ms=latency_ms,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_reasoning=tokens_reasoning,
        status=status,
        error_message=error_message,
        model_version_effective=getattr(llm_response, 'model_version', model) if 'llm_response' in locals() else model,
        model_fingerprint=getattr(llm_response, 'model_fingerprint', None) if 'llm_response' in locals() else None,
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow() if status == "succeeded" else None
    )
    
    # Add error tracking if failed
    if error_message:
        run.why_not_grounded = error_message
    
    # Save to database
    session.add(run)
    await session.commit()
    await session.refresh(run)
    
    # Build response
    return RunTemplateResponse(
        run_id=str(run.run_id),
        template_id=str(run.template_id),
        output_text=run.output_text or "",
        grounded_requested=run.grounded_requested,
        grounded_effective=run.grounded_effective or False,
        vendor=run.vendor,
        model=run.model,
        latency_ms=run.latency_ms,
        usage={
            "input_tokens": run.tokens_input,
            "output_tokens": run.tokens_output,
            "reasoning_tokens": run.tokens_reasoning,
            "total_tokens": run.tokens_input + run.tokens_output + run.tokens_reasoning
        },
        created_at=run.created_at.isoformat(),
        metadata={
            "template_name": template.template_name,
            "status": run.status,
            "run_sha256": run.run_sha256,
            "model_fingerprint": run.model_fingerprint
        }
    )