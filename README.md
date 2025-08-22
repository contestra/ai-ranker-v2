# AI Ranker V2 - Prompter Implementation

## Overview
Clean implementation of prompt immutability testing system based on PRD v2.7.

### Key Features
- Template hashing with SHA-256
- Canonicalization rules (numeric normalization, JSON ordering)
- Provider version pinning
- ALS (Ambient Location Signals) determinism
- Grounding enforcement
- Full execution provenance
- Idempotency with RFC-6902 diffs

## Phase-1 Architecture
- **Framework**: FastAPI
- **Database**: Neon PostgreSQL
- **Execution**: Synchronous (no Redis/Celery)
- **Adapters**: Unified orchestrator with OpenAI/Vertex

## Quick Start

1. **Activate virtual environment**:
   ```bash
   source venv/bin/activate
   ```

2. **Add API keys to `backend/.env`**:
   ```
   OPENAI_API_KEY=your_key_here
   ```

3. **Set up database**:
   ```bash
   ./setup_db.sh
   ```

4. **Test database connection**:
   ```bash
   ./test_db.sh
   ```

5. **Configure Google Cloud** (for Vertex AI):
   ```bash
   gcloud auth application-default login
   gcloud config set project contestra-ai
   ```

6. **Start backend**:
   ```bash
   ./start_backend.sh
   ```

7. **Access API**:
   - Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health

## Project Structure
```
backend/
├── app/
│   ├── api/          # API endpoints (/v1/templates, etc.)
│   ├── llm/          # LLM adapters (unified, openai, vertex)
│   ├── services/     # Business logic (hashing, canonicalization)
│   ├── models/       # SQLAlchemy models
│   └── core/         # Core utilities
└── tests/            # Test suite

frontend/
└── src/
    └── components/   # React components (PromptTracking.tsx)
```

## Implementation Status

### ✅ Completed
- Project structure
- Database schema (Phase-1 tables)
- Environment configuration
- Basic FastAPI app

### 🚧 TODO (from PRD v2.7)
- [ ] Canonicalization rules (§5)
- [ ] Template SHA-256 hashing
- [ ] Output hashing (JSON/Text)
- [ ] Provider version pinning & cache
- [ ] Single-flight pattern
- [ ] API endpoints (/v1/templates, /v1/templates/{id}/run, etc.)
- [ ] Idempotency handling
- [ ] Gemini two-step for JSON
- [ ] ALS determinism with seed keys
- [ ] Grounding detection logic

## Reference Documents
- `IMMUTABILITY_IMPLEMENTATION_PLAN_v2.7—MERGED.md`
- `Prompt_Immutability_PRD_Contestra_Prompt_Lab_v2.6_MASTER.md`
- `AI_RANKER_V2_MIGRATION_PRD.md`
- `ADAPTER_ARCHITECTURE_PRD.md`
