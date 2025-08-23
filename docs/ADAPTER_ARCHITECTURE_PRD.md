# Adapter Architecture PRD - AI Ranker V2

**Document Type:** Technical Design Document  
**Version:** 1.0  
**Status:** Ready for Implementation  
**Owner:** Backend Engineering  
**Parent Document:** [AI_RANKER_V2_MIGRATION_PRD.md](./AI_RANKER_V2_MIGRATION_PRD.md)  
**Created:** 2025-08-22  
**Source:** ChatGPT architectural review + Claude implementation analysis

---

## Executive Summary

This document specifies the adapter layer architecture for AI Ranker V2, implementing a clean two-layer design with a unified orchestrator and per-provider adapters. This architecture replaces the current inconsistent hybrid model with a predictable, testable, and maintainable solution.

**Key Decision:** Phase-0 uses FastAPI + Neon only. Celery/Redis/Fly.io scaling added later without changing interfaces.

---

## 1. Current State Problems

### Architectural Inconsistencies
- **OpenAI**: Logic split between `langchain_adapter.py` (inline) and `openai_responses_adapter.py` (external)
- **Vertex**: Fully external in `vertex_genai_adapter.py`
- **Gemini Direct**: Dangerous fallback that masks authentication issues
- **Result**: Confusing codebase with multiple patterns

### Operational Issues
- Silent degradation when Vertex auth fails (falls back to limited Direct API)
- Duplicate code paths to maintain
- Unclear error sources
- Inconsistent telemetry

---

## 2. Target Architecture

### Two-Layer Design

```
Layer 1: Orchestrator (thin routing layer)
└── unified_llm_adapter.py
    ├── Route by vendor
    ├── Apply ALS (Ambient Location Signals)
    ├── Common retry/timeout logic
    └── Normalize responses

Layer 2: Provider Adapters (vendor-specific logic)
├── adapters/openai_adapter.py (ALL OpenAI logic)
└── adapters/vertex_adapter.py (ALL Vertex logic)
```

### Design Principles
1. **Fail Fast**: No fallbacks - clear errors with remediation
2. **Consistent Interfaces**: Same request/response shapes
3. **Single Responsibility**: Each adapter owns ONE provider
4. **Clean Separation**: Orchestrator routes, adapters implement

---

## 3. Interface Specification

### 3.1 Type Definitions

```python
# backend/app/llm/types.py
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

@dataclass
class LLMRequest:
    vendor: str                    # "openai" | "vertex"
    model: str                     # e.g., "gpt-4o", "gemini-2.5-pro"
    messages: List[Dict[str, Any]] # Message array
    grounded: bool = False         # Enable web search
    json_mode: bool = False        # Strict JSON output
    tools: Optional[List[Dict[str, Any]]] = None
    als: Optional[Dict[str, Any]] = None  # ALS context
    meta: Optional[Dict[str, Any]] = None # Request metadata

@dataclass
class LLMResponse:
    text: str                      # Response text
    tool_calls: List[Dict[str, Any]] = None
    raw: Dict[str, Any] = None    # Raw provider response
    provider: str = None          # Provider name
    model: str = None             # Model used
    usage: Dict[str, Any] = None  # Token usage
    meta: Dict[str, Any] = None   # Response metadata

class BaseAdapter(Protocol):
    async def analyze(self, req: LLMRequest) -> LLMResponse: ...
```

### 3.2 Orchestrator Interface

```python
# backend/app/llm/unified_llm_adapter.py
class UnifiedLLMAdapter:
    def __init__(self, openai: OpenAIAdapter, vertex: VertexAdapter):
        self.openai = openai
        self.vertex = vertex
        self.telemetry = TelemetryService()
    
    async def analyze(self, req: LLMRequest) -> LLMResponse:
        # 1. Apply ALS if present
        req = self._apply_als(req)
        
        # 2. Route to provider
        if req.vendor == "openai":
            response = await self._with_retry(self.openai.analyze, req)
        elif req.vendor in ("vertex", "gemini", "google"):
            response = await self._with_retry(self.vertex.analyze, req)
        else:
            raise ValueError(f"Unknown vendor: {req.vendor}")
        
        # 3. Emit telemetry
        await self.telemetry.record(req, response)
        
        return response
```

---

## 4. Implementation Plan (4 Independent PRs)

### PR1: Kill Gemini Direct Fallback (Day 1)
**Impact: High | Risk: Low | Dependencies: None**

#### Changes:
1. Delete `backend/app/llm/gemini_direct_adapter.py`
2. Remove `ALLOW_GEMINI_DIRECT` environment variable
3. Replace fallback logic with fail-fast error:
```python
if vertex_auth_failed:
    raise VertexAuthError(
        "Vertex AI authentication failed.\n"
        "Run: gcloud auth application-default login\n"
        "See: VERTEX_SETUP.md"
    )
```
4. Add preflight endpoint:
```python
@router.get("/ops/vertex-preflight")
async def vertex_preflight():
    # Check ADC and return status with fix instructions
```

#### Testing:
- Verify Vertex calls fail with clear error when ADC missing
- Confirm no references to `ALLOW_GEMINI_DIRECT`
- Test preflight endpoint

### PR2: Extract OpenAI Adapter (Day 2)
**Impact: Medium | Risk: Low | Dependencies: None**

#### Changes:
1. Create `backend/app/llm/adapters/openai_adapter.py`
2. Move inline OpenAI logic from `langchain_adapter.py`
3. Merge `openai_responses_adapter.py` (grounded path)
4. Implement unified interface:
```python
class OpenAIAdapter:
    async def analyze(self, req: LLMRequest) -> LLMResponse:
        if req.grounded:
            return await self._analyze_with_responses(req)
        else:
            return await self._analyze_with_chat(req)
```

#### Testing:
- Verify both grounded and ungrounded paths work
- Check GPT-5 special handling preserved
- Ensure response normalization correct

### PR3: Standardize Vertex Adapter (Day 3)
**Impact: Low | Risk: Low | Dependencies: PR1**

#### Changes:
1. Rename `vertex_genai_adapter.py` → `vertex_adapter.py`
2. Implement consistent interface
3. Add clear error handling:
```python
class VertexAdapter:
    async def analyze(self, req: LLMRequest) -> LLMResponse:
        try:
            # Vertex implementation
        except AuthenticationError as e:
            raise VertexAuthError(self._get_fix_instructions())
```

#### Testing:
- Verify grounding works via GoogleSearch tool
- Test auth error messages
- Check two-step JSON+grounding process

### PR4: Unified Orchestrator (Day 4-5)
**Impact: High | Risk: Medium | Dependencies: PR2, PR3**

#### Changes:
1. Create `backend/app/llm/types.py` with type definitions
2. Create `backend/app/llm/unified_llm_adapter.py`
3. Update all imports to use new orchestrator
4. Add deprecation shim for `langchain_adapter.py`:
```python
# Temporary backward compatibility
import warnings
warnings.warn("Use UnifiedLLMAdapter", DeprecationWarning)
```

#### Testing:
- All existing endpoints work via compatibility shim
- ALS injection works correctly
- Telemetry records all calls

---

## 5. Telemetry (Phase-0: Postgres Only)

### Database Schema
```sql
CREATE TABLE llm_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id TEXT,
    tenant_id TEXT,
    vendor TEXT NOT NULL,
    model TEXT NOT NULL,
    grounded BOOLEAN NOT NULL DEFAULT FALSE,
    json_mode BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms INT,
    tokens_in INT,
    tokens_out INT,
    cost_est_cents NUMERIC(10,4),
    success BOOLEAN NOT NULL,
    error_code TEXT,
    meta JSONB,
    INDEX idx_ts (ts),
    INDEX idx_vendor_grounded (vendor, grounded)
);
```

### Emission Pattern
- One row per LLM call
- Emitted from orchestrator (not adapters)
- Phase-0: Direct INSERT to Postgres
- Phase-1: Dual-write to Redis stream

---

## 6. Configuration

### Environment Variables (Phase-0)
```bash
# Provider Selection
LLM_VENDOR_DEFAULT=openai|vertex

# OpenAI Configuration
OPENAI_API_KEY=sk-...

# Vertex Configuration
VERTEX_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4
# Uses ADC: gcloud auth application-default login

# REMOVED
# ALLOW_GEMINI_DIRECT - deleted
# GEMINI_API_KEY - not needed
```

### Feature Flags (Future)
- `GROUNDING_STRATEGY`: responses|google_search
- `RETRY_POLICY`: exponential|fixed
- `TELEMETRY_SINK`: postgres|redis|both

---

## 7. Error Handling

### Error Types
```python
class LLMError(Exception): pass

class VertexAuthError(LLMError):
    """Vertex authentication failed"""
    
class ModelNotAvailableError(LLMError):
    """Requested model not available"""
    
class GroundingNotSupportedError(LLMError):
    """Grounding not supported for this configuration"""
```

### Error Responses
```json
{
    "error": "VertexAuthError",
    "message": "Vertex AI authentication failed",
    "remediation": "Run: gcloud auth application-default login",
    "docs": "/docs/vertex-setup"
}
```

---

## 8. Testing Strategy

### Unit Tests
- Each adapter tested in isolation
- Mock provider SDKs
- Verify response normalization
- Test error conditions

### Integration Tests
- End-to-end via FastAPI
- Both providers, both grounding modes
- Telemetry recording
- Error propagation

### Regression Tests
- No references to `gemini_direct_adapter`
- All imports use `UnifiedLLMAdapter`
- Vertex auth failures are explicit
- ALS applied consistently

---

## 9. Migration Checklist

### Pre-Migration
- [ ] All tests passing on current codebase
- [ ] Backup current adapter files
- [ ] Document current API contracts

### During Migration
- [ ] PR1: Remove Gemini Direct
- [ ] PR2: Extract OpenAI adapter
- [ ] PR3: Standardize Vertex adapter
- [ ] PR4: Create unified orchestrator

### Post-Migration
- [ ] All endpoints using new orchestrator
- [ ] Telemetry recording all calls
- [ ] No legacy imports remaining
- [ ] Documentation updated

---

## 10. Phase-Next: Adding Scale (Not in Phase-0)

### When to Add Celery/Redis
Triggers for Phase-1:
- Request volume > 100/minute
- Need for job queuing
- Requirement for distributed caching
- Multiple FastAPI instances

### How to Add Without Breaking Changes
1. Keep adapter interfaces unchanged
2. Add queue abstraction in orchestrator
3. Dual-write telemetry to Redis
4. Use same `LLMRequest`/`LLMResponse` types

### Architecture with Celery/Redis
```
FastAPI → Queue (Celery) → Orchestrator → Adapters
                ↓
            Redis (cache/events)
                ↓
            Postgres (storage)
```

---

## 11. Success Metrics

### Phase-0 Completion
- [ ] Zero references to Direct Gemini API
- [ ] All LLM calls use unified orchestrator
- [ ] Clear errors for auth failures
- [ ] Telemetry for 100% of calls
- [ ] All tests passing

### Quality Metrics
- Code coverage > 80%
- p95 latency < 4s (grounded)
- Zero silent failures
- 100% backward compatible (via shim)

---

## 12. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Hidden Gemini Direct dependencies | High | Medium | CI grep guard, smoke tests |
| Breaking existing APIs | High | Low | Compatibility shim, gradual migration |
| Vertex auth complexity | Medium | High | Clear docs, preflight endpoint |
| Performance regression | Medium | Low | Benchmark before/after |

---

## Appendix A: File Mapping

### Files to Delete
```
✗ backend/app/llm/gemini_direct_adapter.py
✗ backend/app/llm/openai_responses_adapter.py (merge into openai_adapter)
✗ backend/app/llm/google_adapter.py (obsolete)
✗ backend/app/llm/openai_tools_adapter.py (unused)
```

### Files to Create
```
✓ backend/app/llm/types.py
✓ backend/app/llm/unified_llm_adapter.py
✓ backend/app/llm/adapters/openai_adapter.py
✓ backend/app/llm/adapters/vertex_adapter.py
```

### Files to Modify
```
→ backend/app/llm/langchain_adapter.py (add deprecation)
→ All API endpoints (update imports)
```

---

## Appendix B: Code Examples

### Example: Using the New Architecture
```python
# backend/app/api/prompt_tracking.py
from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

adapter = UnifiedLLMAdapter()

async def run_prompt(template, context):
    request = LLMRequest(
        vendor="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": template}],
        grounded=True,
        als=context
    )
    
    response = await adapter.analyze(request)
    return response.text
```

### Example: Error Handling
```python
try:
    response = await adapter.analyze(request)
except VertexAuthError as e:
    return JSONResponse(
        status_code=503,
        content={
            "error": "authentication_required",
            "message": str(e),
            "fix": e.remediation_steps
        }
    )
```

---

**This PRD provides the complete technical specification for the adapter architecture. It should be read in conjunction with the main [AI_RANKER_V2_MIGRATION_PRD.md](./AI_RANKER_V2_MIGRATION_PRD.md) which covers the overall migration strategy.**