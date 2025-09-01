"""
Telemetry persistence module for Neon Postgres.

Handles writing LLM call telemetry to the llm_calls table
with rich metadata in JSONB for analytics and monitoring.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.llm.types import LLMResponse


async def persist_llm_telemetry(
    session: AsyncSession,
    request: Dict[str, Any],
    response: LLMResponse,
    latency_ms: int
) -> str:
    """
    Persist LLM call telemetry to Neon.
    
    Returns the ID of the inserted row.
    """
    # Generate ID if not provided
    call_id = str(uuid.uuid4())
    
    # Extract request metadata
    request_meta = request.get("meta", {})
    request_id = request_meta.get("request_id")
    tenant_id = request_meta.get("tenant_id")
    
    # Build complete metadata JSON
    meta = {
        **response.metadata,  # All response metadata
        "request_meta": request_meta,  # Original request metadata
        "request_messages": request.get("messages", [])[:3],  # First 3 messages for context
    }
    
    # Core fields for the row
    sql = text("""
        INSERT INTO llm_calls (
            id, ts, request_id, tenant_id,
            vendor, model, grounded, json_mode,
            latency_ms, tokens_in, tokens_out,
            cost_est_cents, success, error_code, meta
        ) VALUES (
            :id, :ts, :request_id, :tenant_id,
            :vendor, :model, :grounded, :json_mode,
            :latency_ms, :tokens_in, :tokens_out,
            :cost_est_cents, :success, :error_code, :meta
        )
        RETURNING id
    """)
    
    # Calculate token counts
    usage = response.usage or {}
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)
    
    # Estimate cost (simplified - would use actual pricing in production)
    cost_est_cents = estimate_cost_cents(
        request.get("vendor"),
        request.get("model"),
        tokens_in,
        tokens_out
    )
    
    params = {
        "id": call_id,
        "ts": datetime.utcnow(),
        "request_id": request_id,
        "tenant_id": tenant_id,
        "vendor": request.get("vendor"),
        "model": response.model_version or request.get("model"),
        "grounded": request.get("grounded", False),
        "json_mode": request.get("json_mode", False),
        "latency_ms": latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_est_cents": cost_est_cents,
        "success": response.success,
        "error_code": response.error_type,
        "meta": json.dumps(meta)  # JSONB requires JSON string
    }
    
    result = await session.execute(sql, params)
    await session.commit()
    
    return call_id


def estimate_cost_cents(
    vendor: str,
    model: str,
    tokens_in: int,
    tokens_out: int
) -> float:
    """
    Estimate cost in cents based on token usage.
    
    This is a simplified version - production would use
    actual pricing tables from each vendor.
    """
    # Simplified pricing per 1K tokens (cents)
    pricing = {
        "openai": {
            "gpt-5": {"input": 1.5, "output": 4.5},
            "gpt-5-chat-latest": {"input": 1.0, "output": 3.0},
        },
        "vertex": {
            "gemini-2.5-pro": {"input": 0.5, "output": 1.5},
            "gemini-2.0-flash": {"input": 0.1, "output": 0.3},
        }
    }
    
    # Get vendor pricing
    vendor_pricing = pricing.get(vendor, {})
    
    # Find model pricing (handle full model paths)
    model_pricing = None
    for model_key in vendor_pricing:
        if model_key in model:
            model_pricing = vendor_pricing[model_key]
            break
    
    if not model_pricing:
        # Default pricing if model not found
        model_pricing = {"input": 1.0, "output": 2.0}
    
    # Calculate cost
    input_cost = (tokens_in / 1000) * model_pricing["input"]
    output_cost = (tokens_out / 1000) * model_pricing["output"]
    
    return round(input_cost + output_cost, 4)


async def query_telemetry_by_request(
    session: AsyncSession,
    request_id: str
) -> Optional[Dict[str, Any]]:
    """
    Query telemetry for a specific request ID.
    Uses the analytics_runs view for flattened access.
    """
    sql = text("""
        SELECT 
            id, ts, vendor, model, grounded, grounded_effective,
            response_api, tool_call_count, anchored_citations_count,
            why_not_grounded, latency_ms, success
        FROM analytics_runs
        WHERE (meta->>'request_id') = :rid
        ORDER BY ts DESC
        LIMIT 1
    """)
    
    result = await session.execute(sql, {"rid": request_id})
    row = result.first()
    
    if not row:
        return None
    
    return {
        "id": str(row.id),
        "timestamp": row.ts.isoformat(),
        "vendor": row.vendor,
        "model": row.model,
        "grounded": row.grounded,
        "grounded_effective": row.grounded_effective,
        "response_api": row.response_api,
        "tool_call_count": row.tool_call_count,
        "anchored_citations_count": row.anchored_citations_count,
        "why_not_grounded": row.why_not_grounded,
        "latency_ms": row.latency_ms,
        "success": row.success
    }


async def get_telemetry_stats(
    session: AsyncSession,
    hours: int = 24
) -> Dict[str, Any]:
    """
    Get telemetry statistics for monitoring dashboards.
    """
    sql = text("""
        SELECT 
            COUNT(*) as total_calls,
            COUNT(*) FILTER (WHERE success = true) as successful_calls,
            COUNT(*) FILTER (WHERE grounded = true) as grounded_requested,
            COUNT(*) FILTER (WHERE grounded_effective = true) as grounded_effective,
            COUNT(*) FILTER (WHERE model_adjusted_for_grounding = true) as model_adjustments,
            AVG(latency_ms) as avg_latency_ms,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency_ms,
            SUM(tokens_in) as total_tokens_in,
            SUM(tokens_out) as total_tokens_out,
            SUM(cost_est_cents) as total_cost_cents
        FROM llm_calls
        WHERE ts > NOW() - INTERVAL ':hours hours'
    """)
    
    result = await session.execute(sql, {"hours": hours})
    row = result.first()
    
    if not row:
        return {}
    
    return {
        "total_calls": row.total_calls,
        "successful_calls": row.successful_calls,
        "grounded_requested": row.grounded_requested,
        "grounded_effective": row.grounded_effective,
        "model_adjustments": row.model_adjustments,
        "avg_latency_ms": float(row.avg_latency_ms) if row.avg_latency_ms else 0,
        "p95_latency_ms": float(row.p95_latency_ms) if row.p95_latency_ms else 0,
        "total_tokens_in": row.total_tokens_in or 0,
        "total_tokens_out": row.total_tokens_out or 0,
        "total_cost_cents": float(row.total_cost_cents) if row.total_cost_cents else 0
    }