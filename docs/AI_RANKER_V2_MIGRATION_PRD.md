# AI Ranker V2 Migration PRD

**Document Type:** Product Requirements Document  
**Version:** 1.0  
**Status:** Ready for Review  
**Owner:** Platform Engineering  
**Created:** 2025-08-22  
**Target Completion:** 2025-09-06 (2 weeks)

---

## 1. Executive Summary

### 1.1 Purpose
Migrate AI Ranker from a monolithic multi-tool platform to a focused, clean prompt immutability testing system. This migration involves creating a new repository (ai-ranker-v2), dropping ~92% of legacy code, and moving development from Windows/PowerShell to WSL2/Linux.

### 1.2 Key Decisions
- **New Repository**: `github.com/contestra/ai-ranker-v2` (not a fork)
- **Single Focus**: Prompter functionality only (drop all other tools)
- **Clean Architecture**: No backward compatibility or migration shims
- **WSL Development**: Eliminate Windows-specific issues permanently
- **Fresh Start**: No historical data migration (optional selective import)

### 1.3 Success Metrics
- Codebase reduction: From ~500+ files to ~40 files (92% reduction)
- Zero Windows encoding errors post-migration
- Single unified LLM adapter architecture
- All tests passing in WSL environment
- Clean git history starting from commit #1

---

## 2. Problem Statement

### 2.1 Current State Problems
1. **Feature Sprawl**: 35+ API endpoints, only 5-6 are prompter-related
2. **File Chaos**: 200+ MD files, 150+ test files, 10+ database files scattered
3. **Windows Issues**: Daily Unicode/encoding errors requiring constant workarounds
4. **Architecture Inconsistency**: Mixed adapter patterns, dangerous fallbacks
5. **Technical Debt**: 92% of codebase is legacy experiments and failed attempts

### 2.2 Impact
- **Development Velocity**: Slowed by navigating 500+ files
- **Reliability**: Windows encoding issues cause daily failures
- **Maintainability**: Unclear which code is actually used
- **Testing**: 150+ test files with unclear purpose
- **Onboarding**: New developers overwhelmed by complexity

---

## 3. Solution Overview

### 3.1 Core Strategy
Create a new, clean repository containing ONLY the prompter functionality, developed natively in WSL2 to match the production Linux environment.

### 3.2 What We Keep (Prompter Core)
```
Backend:
- Prompt template management
- Immutable execution with SHA-256 hashing
- Multi-provider LLM support (OpenAI, Vertex)
- Ambient Location Signals (ALS)
- Background execution service

Frontend:
- PromptTracking.tsx component
- Template CRUD operations
- Results viewing and analytics

Database:
- prompt_templates
- prompt_runs
- countries (for ALS)
```

### 3.3 What We Drop (Everything Else)
```
Features Removed:
- Brand entity strength analysis
- Concordance analysis
- Crawler monitoring
- Entity extraction
- Weekly tracking
- Embedding analysis
- All experimental tools

Files Removed:
- 200+ documentation files
- 150+ test files
- 30+ API endpoint files
- 20+ frontend components
- 50+ PowerShell scripts
- All Windows workarounds
```

---

## 4. Technical Requirements

### 4.1 Development Environment

#### Required Setup
- **OS**: WSL2 with Ubuntu 22.04 LTS
- **Python**: 3.11+ (native Linux version)
- **Node.js**: 20+ LTS
- **Database**: Neon PostgreSQL (cloud)
- **Git**: Configured for Linux line endings

#### Authentication
- Google Cloud SDK installed in WSL
- ADC configured: `gcloud auth application-default login`
- Project set: `gcloud config set project contestra-ai`

### 4.2 Architecture Requirements

#### Backend Structure
```
backend/
├── app/
│   ├── api/
│   │   ├── prompt_tracking.py    # Main prompter API
│   │   ├── prompter_v7.py        # V7 implementation
│   │   └── health.py              # Health checks
│   ├── llm/
│   │   ├── unified_adapter.py    # Routing and ALS
│   │   └── adapters/
│   │       ├── openai_adapter.py # All OpenAI logic
│   │       └── vertex_adapter.py  # All Vertex logic
│   ├── services/
│   │   ├── prompt_hasher.py      # SHA-256 hashing
│   │   ├── background_runner.py  # Async execution
│   │   └── als/                  # ALS templates
│   └── models/
│       └── prompt_models.py      # SQLAlchemy models
```

#### Frontend Structure
```
frontend/
└── src/
    ├── app/
    │   └── page.tsx              # Single-page app
    └── components/
        └── PromptTracking.tsx    # Main UI component
```

### 4.3 Adapter Architecture

#### Design Principles
1. **No Fallbacks**: Vertex auth failure = hard error
2. **Consistent Interfaces**: Same request/response types
3. **Clear Separation**: Orchestrator vs provider logic
4. **Fail Fast**: Immediate errors with fix instructions

#### Implementation Requirements
```python
# Required error handling
class VertexAuthError(Exception):
    def __init__(self, original_error):
        super().__init__(
            f"Vertex AI authentication failed: {original_error}\n\n"
            "To fix this, run:\n"
            "  gcloud auth application-default login\n"
            "  gcloud config set project contestra-ai\n"
        )

# NO direct Gemini API fallback
# NO mixed inline/external implementations
# NO backward compatibility shims
```

### 4.4 Database Requirements

#### Schema (Prompter Only)
```sql
-- Core tables only
CREATE TABLE prompt_templates (...);
CREATE TABLE prompt_runs (...);
CREATE TABLE countries (...);

-- No brand tables
-- No entity tables
-- No tracking tables
-- No concordance tables
```

#### Connection
- Use Neon PostgreSQL from day 1
- Connection string in environment variables
- No SQLite files

---

## 5. Implementation Phases

### 5.1 Phase 1: Environment Setup (Day 1-2)
**Owner:** DevOps/Platform

**Tasks:**
1. Install WSL2 + Ubuntu 22.04
2. Configure Python 3.11 environment
3. Install Node.js 20+
4. Set up Google Cloud SDK
5. Configure ADC authentication
6. Create new GitHub repository

**Acceptance Criteria:**
- [ ] WSL2 running Ubuntu 22.04
- [ ] Python/Node environments working
- [ ] `gcloud auth application-default login` successful
- [ ] New repository created at github.com/contestra/ai-ranker-v2

### 5.2 Phase 2: Code Extraction (Day 3-4)
**Owner:** Backend Engineering

**Tasks:**
1. Copy prompter-related files only
2. Remove all Windows-specific code
3. Remove all encoding workarounds
4. Clean up imports and dependencies
5. Create minimal requirements.txt

**Acceptance Criteria:**
- [ ] Only prompter files copied
- [ ] No `PYTHONUTF8` references
- [ ] No Windows path separators
- [ ] requirements.txt < 20 packages

### 5.3 Phase 3: Adapter Refactoring (Day 5-7)
**Owner:** Backend Engineering

**Detailed Specification:** See [ADAPTER_ARCHITECTURE_PRD.md](./ADAPTER_ARCHITECTURE_PRD.md)

**Tasks:**
1. Implement unified_adapter.py per adapter PRD
2. Create clean openai_adapter.py (merge grounded path)
3. Create clean vertex_adapter.py (no fallbacks)
4. Remove ALL Gemini Direct fallback logic
5. Add clear error messages with remediation

**Acceptance Criteria:**
- [ ] No gemini_direct_adapter.py exists
- [ ] Vertex auth errors show fix instructions
- [ ] All adapters follow consistent interface per PRD
- [ ] No backward compatibility code
- [ ] Telemetry recording all LLM calls

### 5.4 Phase 4: Frontend Simplification (Day 8-9)
**Owner:** Frontend Engineering

**Tasks:**
1. Extract PromptTracking.tsx
2. Create single-page application
3. Remove all non-prompter UI
4. Update API endpoints
5. Test in WSL environment

**Acceptance Criteria:**
- [ ] Single component application
- [ ] No brand/entity UI elements
- [ ] All API calls to /api/prompt-tracking/*
- [ ] Hot reload working in WSL

### 5.5 Phase 5: Testing & Documentation (Day 10-12)
**Owner:** QA/Documentation

**Tasks:**
1. Write focused test suite (10-15 tests)
2. Create clean README.md
3. Document WSL setup process
4. Test complete flow in WSL
5. Archive old repository

**Acceptance Criteria:**
- [ ] All tests passing in WSL
- [ ] README includes WSL setup
- [ ] Old repo marked as deprecated
- [ ] No Windows-specific instructions

---

## 6. Non-Functional Requirements

### 6.1 Performance
- API response time < 200ms (excluding LLM calls)
- Frontend bundle size < 500KB
- Database queries < 50ms

### 6.2 Security
- All API keys in environment variables
- No secrets in code
- ADC authentication for Vertex
- CORS properly configured

### 6.3 Developer Experience
- Single command setup: `./setup.sh`
- Hot reload for frontend and backend
- Clear error messages with fixes
- No Windows-specific tooling

### 6.4 Code Quality
- Python: Follow PEP 8
- TypeScript: ESLint + Prettier
- No commented-out code
- No TODO comments without tickets

---

## 7. Migration Execution

### 7.1 Data Migration Strategy
**Decision: Clean Start (No Migration)**

Rationale:
- Historical data has limited value
- Schema changes would require complex migration
- Can reference old system if needed
- Cleaner to start fresh

Optional: Selective migration script for recent templates only

### 7.2 Cutover Plan
1. Complete v2 development in parallel
2. Test thoroughly in WSL environment
3. Deploy v2 to new Fly.io instance
4. Update DNS/routing when ready
5. Archive v1 repository

### 7.3 Rollback Plan
- V1 remains untouched during development
- Can continue using v1 if issues arise
- No shared resources between v1 and v2

---

## 8. Success Criteria

### 8.1 Technical Metrics
- [ ] Codebase: ~40 files (from 500+)
- [ ] Dependencies: ~20 packages (from 100+)
- [ ] Test files: ~15 (from 150+)
- [ ] API endpoints: 3 (from 35)
- [ ] Frontend components: 1 (from 20+)

### 8.2 Quality Metrics
- [ ] Zero Windows encoding errors
- [ ] All tests passing
- [ ] No fallback adapters
- [ ] Clean git history
- [ ] No legacy code

### 8.3 Operational Metrics
- [ ] WSL development environment working
- [ ] ADC authentication configured
- [ ] Deployment to Fly.io successful
- [ ] Monitoring configured
- [ ] Documentation complete

---

## 9. Risks and Mitigations

### 9.1 Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| WSL setup issues | High | Detailed setup guide, test on multiple machines |
| ADC authentication problems | High | Clear error messages, troubleshooting guide |
| Missing functionality | Medium | Keep v1 running, can add if needed |
| Data loss | Low | V1 remains as archive, optional migration |

### 9.2 Timeline Risks
- **Risk**: 2-week timeline aggressive
- **Mitigation**: Focus on MVP, defer nice-to-haves

### 9.3 Adoption Risks
- **Risk**: Team unfamiliar with WSL
- **Mitigation**: Training session, pair programming

---

## 10. Future Considerations

### 10.1 Phase 2 Features (Post-Migration)
- Add Redis caching (when needed)
- Add Celery for async jobs (when scale requires)
- Implement batch processing UI
- Add comprehensive analytics

### 10.2 Excluded from Scope
- Data migration from v1
- Backward compatibility
- Windows support
- Non-prompter features
- Multi-tenant support (initially)

---

## 11. Related Documentation

### Key Technical Specifications
- **[ADAPTER_ARCHITECTURE_PRD.md](./ADAPTER_ARCHITECTURE_PRD.md)** - Detailed adapter layer design and implementation
- **[IMMUTABILITY_IMPLEMENTATION_PLAN_v2.8.md](./IMMUTABILITY_IMPLEMENTATION_PLAN_v2.8—MERGED.md)** - Prompt immutability implementation (v2.8)
- **[Prompt_Immutability_PRD_v2.7_MASTER.md](./Prompt_Immutability_PRD_Contestra_Prompt_Lab_v2.7_MASTER.md)** - Immutability requirements (v2.7)
- **[NEON_DATABASE_SETUP_GUIDE.md](./NEON_DATABASE_SETUP_GUIDE.md)** - Complete Neon PostgreSQL setup with connection details

### 11.1 File Migration Checklist

#### Files to Migrate
```
✓ backend/app/api/prompt_tracking.py
✓ backend/app/api/prompter_v7.py
✓ backend/app/services/prompt_hasher.py
✓ backend/app/services/als/*
✓ frontend/src/components/PromptTracking.tsx
✓ Key sections of CLAUDE.md
✓ Immutability PRD and implementation plans
```

#### Files to Archive (NOT migrate)
```
✗ 200+ MD documentation files
✗ 150+ test files
✗ 30+ non-prompter API files
✗ 20+ non-prompter frontend components
✗ All PowerShell scripts
✗ All Windows batch files
✗ All entity/brand analysis code
```

### 11.2 Dependencies Comparison

#### Current (v1) - 100+ packages
```
langchain, langchain-openai, langchain-google-genai, 
langchain-anthropic, langsmith, sqlalchemy, alembic,
celery, redis, pandas, numpy, scikit-learn, ...
```

#### Target (v2) - ~20 packages
```
fastapi, uvicorn, pydantic, sqlalchemy, asyncpg,
openai, google-generativeai, httpx, python-dotenv, ...
```

### 11.3 WSL Setup Commands

```bash
# One-time setup
wsl --install -d Ubuntu-22.04

# In WSL
sudo apt update && sudo apt upgrade
sudo apt install python3.11 python3.11-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Google Cloud SDK
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo tee /usr/share/keyrings/cloud.google.asc
sudo apt-get update && sudo apt-get install google-cloud-cli

# Authentication
gcloud auth application-default login
gcloud config set project contestra-ai
```

---

## 12. Approval and Sign-off

### Required Approvals
- [ ] Engineering Lead - Technical approach
- [ ] Product Owner - Scope and timeline
- [ ] DevOps - Infrastructure requirements
- [ ] QA Lead - Testing strategy

### Decision Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-08-22 | No data migration | Clean start preferred |
| 2025-08-22 | WSL2 required | Eliminate Windows issues |
| 2025-08-22 | New repository | Avoid legacy contamination |
| 2025-08-22 | Drop all non-prompter features | Focus on core value |

---

**Document Status:** This PRD represents the complete requirements for AI Ranker v2 migration. Any changes require approval from Engineering Lead and Product Owner.

**Next Steps:**
1. Review and approve PRD
2. Create project tracking tickets
3. Begin Phase 1 (WSL setup)
4. Daily standups during migration
5. Go/No-Go decision at end of each phase