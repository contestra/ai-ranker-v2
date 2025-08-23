# Adapter Implementation Instructions - Phase 0

## IMPORTANT: This comes AFTER core immutability is working!

Based on PRD-Adapter-Layer-Phase0-FastAPI-Neon.md, here's what to implement:

## Architecture Overview

```
backend/app/llm/
  types.py                      # LLMRequest/LLMResponse dataclasses
  unified_llm_adapter.py        # Router + ALS + normalization
  adapters/
    openai_adapter.py          # All OpenAI logic (ungrounded + Responses API)
    vertex_adapter.py          # All Vertex/Gemini logic (NO Direct API fallback!)
```

## Key Requirements

### 1. NO DIRECT GEMINI API
- **DELETE** any Direct Gemini API fallback code
- **DELETE** `ALLOW_GEMINI_DIRECT` environment variables
- **ONLY** use Vertex AI for Gemini models
- Fail fast on auth errors with clear remediation steps

### 2. Unified Types (types.py)
```python
@dataclass
class LLMRequest:
    vendor: str              # "openai" | "vertex"
    model: str              # e.g., "gpt-4o", "gemini-2.5-pro"
    messages: List[Dict]    # Message array
    grounded: bool = False  # Enable web search
    json_mode: bool = False # Strict JSON output
    als_context: Optional[Dict] = None  # ALS signals
    temperature: float = 0.0
    seed: Optional[int] = None

@dataclass
class LLMResponse:
    content: str
    model_version: str
    model_fingerprint: Optional[str]
    grounded_effective: bool
    citations: Optional[List[Dict]]
    usage: Dict[str, int]
    latency_ms: int
    raw_response: Dict
```

### 3. Unified Orchestrator Responsibilities
- Route by vendor
- Apply ALS (once, before routing)
- Common timeout handling
- Normalize responses
- Emit Postgres telemetry row

### 4. OpenAI Adapter
- Ungrounded: Standard Chat Completions API
- Grounded: Use Responses API for citations
- Handle JSON mode
- Extract system_fingerprint

### 5. Vertex Adapter
- Use ADC/WIF authentication only
- Fail fast with clear error: "Run: gcloud auth application-default login"
- Grounding via GoogleSearch tool
- Two-step for JSON + grounding (when both required)
- Extract modelVersion as fingerprint

## Migration Steps

1. **Create types.py** with dataclasses
2. **Create unified_llm_adapter.py** as router
3. **Create adapters/openai_adapter.py** (merge all OpenAI logic)
4. **Create adapters/vertex_adapter.py** (Vertex only, no Direct API)
5. **Update imports** to use new unified adapter
6. **Add telemetry** to Postgres (one row per call)

## Telemetry Schema

Add to database:
```sql
CREATE TABLE llm_telemetry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vendor VARCHAR(50),
    model VARCHAR(100),
    grounded BOOLEAN,
    json_mode BOOLEAN,
    latency_ms INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    success BOOLEAN,
    error_type VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Testing Requirements

1. **Auth failure test**: Vertex should fail clearly without ADC
2. **Grounding test**: Both providers return citations when grounded=true
3. **JSON mode test**: Valid JSON output
4. **No fallback test**: Remove Direct API, ensure Vertex fails properly
5. **ALS test**: Verify ALS applied correctly

## What NOT to Do

- ❌ Don't create Direct Gemini API adapter
- ❌ Don't allow silent fallbacks
- ❌ Don't mix routing logic with provider logic
- ❌ Don't bypass SDK (use official clients)
- ❌ Don't implement Celery/Redis (Phase-0 is FastAPI+Neon only)

## Remember

This adapter work comes AFTER:
1. ✅ Canonicalization is working
2. ✅ Template hashing is implemented
3. ✅ API endpoints are functional
4. ✅ Provider version management is done

The adapters are just the LLM integration layer - the core immutability system must work first!