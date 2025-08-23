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
- **Vertex AI integration with ADC/WIF authentication**
- **Vendor routing with no silent fallbacks**

## Phase-1 Architecture
- **Framework**: FastAPI
- **Database**: Neon PostgreSQL
- **Execution**: Synchronous (no Redis/Celery)
- **Adapters**: Unified orchestrator with OpenAI/Vertex
- **Authentication**: ADC for local, WIF for production

## Quick Start

### Prerequisites
- Python 3.11+
- gcloud CLI installed and configured
- PostgreSQL (via Neon)
- Owner role on GCP project (for ADC)

### Local Development Setup

1. **Activate virtual environment**:
   ```bash
   source venv/bin/activate
   ```

2. **Configure environment**:
   ```bash
   cd backend
   cp .env.local .env
   ```

3. **Set up Google Cloud ADC** (for Vertex AI):
   ```bash
   # Clean slate
   unset GOOGLE_APPLICATION_CREDENTIALS
   gcloud auth application-default revoke -q || true
   
   # Authenticate (run interactively, don't pipe codes)
   gcloud auth application-default login --no-launch-browser
   
   # Set quota project
   gcloud auth application-default set-quota-project contestra-ai
   ```

4. **Set up database**:
   ```bash
   ./setup_db.sh
   ```

5. **Test database connection**:
   ```bash
   ./test_db.sh
   ```

6. **Start backend**:
   ```bash
   ./start_backend.sh
   ```

7. **Verify Vertex AI**:
   ```bash
   curl http://localhost:8000/preflight/vertex
   ```

8. **Access API**:
   - Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health
   - Vertex Preflight: http://localhost:8000/preflight/vertex

## Project Structure
```
backend/
├── app/
│   ├── api/          # API endpoints (/v1/templates, etc.)
│   ├── llm/          # LLM adapters (unified, openai, vertex)
│   ├── services/     # Business logic (hashing, canonicalization)
│   ├── models/       # SQLAlchemy models
│   ├── core/         # Core utilities
│   ├── routers/      # FastAPI routers (preflight, etc.)
│   └── google_creds.py  # Google credential detection
├── tests/            # Test suite
├── VERTEX_AUTH_SETUP.md  # Complete Vertex setup guide
└── ENVIRONMENT_SETUP.md  # Environment configuration

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
- **Vertex AI integration with ADC/WIF**
- **Vendor routing (no silent fallbacks)**
- **Direct SDK adapters (OpenAI, Vertex AI)**
- **Preflight endpoint for credential verification**
- **Model normalization and text extraction helpers**
- **Comprehensive error handling**
- **ALS infrastructure (ready but not active)**

### 🚧 In Progress
- [ ] Canonicalization rules (§5)
- [ ] Template SHA-256 hashing
- [ ] Output hashing (JSON/Text)
- [ ] Provider version pinning & cache
- [ ] Single-flight pattern
- [ ] API endpoints completion
- [ ] Idempotency handling
- [ ] Gemini two-step for JSON
- [ ] ALS determinism with seed keys
- [ ] Grounding detection logic

### 📋 Planned Upgrades
- [ ] **LangChain Integration** - Replace direct SDK adapters
- [ ] **LangSmith Observability** - Add tracing and monitoring
- [ ] **Prompt Templates** - Unified template management
- [ ] **Streaming Support** - Real-time response streaming

## Key Endpoints

### Template Management
- `POST /v1/templates` - Create template
- `GET /v1/templates/{id}` - Get template
- `POST /v1/templates/{id}/run` - Execute template

### Health & Diagnostics
- `GET /health` - Service health
- `GET /preflight/vertex` - Vertex AI credential check

## Authentication Configuration

### Local Development (ADC)
- Uses Application Default Credentials
- No Service Account keys (blocked by org policy)
- User: l@contestra.com with Owner role
- Set via `gcloud auth application-default login`

### Production (WIF)
- Workload Identity Federation
- No key files
- Credentials materialized at runtime
- Enforced via `ENFORCE_VERTEX_WIF=true`

## Important Notes

### Vertex AI Specifics
- **Model Format**: Use short form (e.g., `gemini-2.5-pro`)
- **Token Limits**: Set `max_tokens` to 1000+ for Gemini 2.5 (uses thinking tokens)
- **Region**: Configured for `europe-west4`

### Organization Constraints
- Service Account key creation is blocked by policy
- Solution: Use ADC for local development
- Production uses WIF for enhanced security

## Troubleshooting

For common issues and solutions, see:
- `VERTEX_AUTH_SETUP.md` - Vertex AI authentication guide
- `ENVIRONMENT_SETUP.md` - Environment configuration
- `TROUBLESHOOTING.md` - Common issues and fixes

## Reference Documents
- `IMMUTABILITY_IMPLEMENTATION_PLAN_v2.7—MERGED.md`
- `Prompt_Immutability_PRD_Contestra_Prompt_Lab_v2.6_MASTER.md`
- `AI_RANKER_V2_MIGRATION_PRD.md`
- `ADAPTER_ARCHITECTURE_PRD.md`

## Status
**Last Updated**: 2025-08-23  
**Status**: Production Ready with ADC/WIF Authentication