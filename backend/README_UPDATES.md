# Recent Updates - September 1, 2025

## Major Improvements

### 1. Citation Extraction Fixes
- Fixed Gemini grounded models returning 0 citations despite multiple tool calls
- Implemented index-driven union-of-views for typed vs dict candidates
- Added budget-limited citation resolution (max 8 URLs, 3s stopwatch)
- Fixed unlinked sources not being emitted when anchored citations existed

### 2. Telemetry Persistence Enhancement
- Added `meta` JSONB column to store rich telemetry metadata
- Added `grounded_effective` field to track actual grounding status
- Implemented comprehensive metadata persistence (40+ fields)
- Created indexes for efficient JSONB queries
- Added SQL queries for telemetry analysis and monitoring

### 3. OpenAI Adapter Improvements
- Removed duplicate `GroundingNotSupportedError` class
- Added token reservation rollback on failures
- Improved rate limiter with adaptive multipliers
- Fixed model routing for grounded vs ungrounded requests

### 4. Post-Deploy Verification
- Created SQL assertions for telemetry contract enforcement
- Added CI script for automated contract checks
- Implemented 10 comprehensive health checks
- Added remediation guidance for failures

## Files Changed

### Core Adapters
- `app/llm/adapters/openai_adapter.py` - Rate limiter fixes, exception cleanup
- `app/llm/adapters/vertex_adapter.py` - Citation extraction improvements
- `app/llm/unified_llm_adapter.py` - Telemetry persistence, metadata enrichment

### Database
- `app/models/models.py` - Added meta and grounded_effective fields
- `alembic/versions/20250901_add_telemetry_meta.py` - Migration for new fields
- `alembic/versions/20250901_analytics_view_check.py` - Analytics views

### Testing & Verification
- `tests/test_citations.py` - Comprehensive citation tests
- `tests/test_telemetry_contract_neon.py` - Contract verification
- `sql/check_telemetry_contracts.sql` - SQL assertions
- `sql/query_telemetry_meta.sql` - Telemetry analysis queries
- `scripts/check_telemetry_contracts.sh` - CI integration

### Documentation
- `CHATGPT_REVIEW_RESPONSES.md` - Response to code review
- `TELEMETRY_PERSISTENCE_COMPLETE.md` - Telemetry implementation details
- `E2E_TEST_RESULTS_SUMMARY.md` - Test results summary
- `docs/ENVIRONMENT_SETUP.md` - Environment configuration guide

## Key Features

### Telemetry Metadata
The system now persists comprehensive metadata for every LLM call:
- ALS provenance (SHA256, variant, country)
- Grounding details (mode, effectiveness, failures)
- API versioning (response_api, provider version)
- Model routing (adjustments, original model)
- Feature flags for A/B testing
- Citation metrics (total, anchored, unlinked)
- Performance metrics (latency, tokens)

### Contract Enforcement
Post-deploy checks ensure:
- All grounded calls have response_api labels
- OpenAI grounded calls use 'responses_http'
- Vertex grounded calls use 'vertex_genai'
- Failed calls include error codes
- REQUIRED mode failures explain why grounding failed

### Monitoring Support
New queries enable:
- Grounding effectiveness analysis
- Feature flag distribution tracking
- Citation extraction metrics
- Model routing verification
- Performance analysis by configuration

## Migration Instructions

1. Run database migrations:
```bash
alembic upgrade head
```

2. Verify telemetry contract:
```bash
./scripts/check_telemetry_contracts.sh
```

3. Check telemetry flow:
```sql
psql $DATABASE_URL -f sql/query_telemetry_meta.sql
```

## Environment Variables

Required for full functionality:
```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Vertex AI
export GOOGLE_CLOUD_PROJECT="your-project"
export VERTEX_LOCATION="us-central1"

# Database
export DATABASE_URL="postgresql://..."

# Feature Flags (optional)
export CITATION_EXTRACTOR_V2="1.0"
export ENFORCE_RESOLVER_BUDGETS="1.0"
```

## Next Steps

1. Deploy migrations to production
2. Enable telemetry monitoring dashboards
3. Configure alerts based on contract violations
4. Gradually roll out feature flags
5. Monitor citation extraction effectiveness