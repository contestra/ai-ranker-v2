#!/bin/bash
# AI Ranker V2 - Complete Bootstrap Script for WSL
# Run this from ~/ai-ranker-v2 to set up the entire v2 project

set -e  # Exit on error

echo "🚀 AI Ranker V2 - Complete Bootstrap for Prompter-Only Implementation"
echo "====================================================================="
echo ""

# Configuration
TEMP_REPO="$HOME/ai-ranker-v2/ai-ranker-temp"
PROJECT_DIR="$HOME/ai-ranker-v2"

# Neon Database Credentials (from NEON_DATABASE_SETUP_GUIDE.md)
export DB_HOST="ep-empty-frog-a2blbcz9-pooler.eu-central-1.aws.neon.tech"
export DB_NAME="neondb"
export DB_USER="neondb_owner"
export DB_PASSWORD="npg_nZ2RowvS0ODr"
export DB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}/${DB_NAME}?sslmode=require"

# Step 1: Verify we're in the right place
if [ "$PWD" != "$PROJECT_DIR" ]; then
    echo "⚠️  Switching to $PROJECT_DIR"
    cd "$PROJECT_DIR" || exit 1
fi

echo "✅ Running from: $PROJECT_DIR"

# Step 2: Create complete project structure
echo ""
echo "📁 Creating project structure..."
mkdir -p backend/{app/{api,llm/adapters,services/als,models,core,utils},tests,alembic/versions}
mkdir -p frontend/{src/{app,components,lib},public}
mkdir -p docs
echo "✅ Directories created"

# Step 3: Create .gitignore
echo ""
echo "📝 Creating .gitignore..."
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
ENV/
env/
.venv

# Environment
.env
.env.local
.env.*.local

# Database
*.db
*.sqlite
*.sqlite3

# Logs
*.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# Frontend
node_modules/
.next/
out/
build/
dist/
*.local

# OS
.DS_Store
Thumbs.db

# Testing
.coverage
htmlcov/
.pytest_cache/
.tox/

# Temp
*.tmp
*.bak
*~
EOF
echo "✅ .gitignore created"

# Step 4: Setup Python environment
echo ""
echo "🐍 Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "ℹ️  Virtual environment already exists"
fi

source venv/bin/activate
echo "✅ Virtual environment activated"

# Step 5: Create requirements.txt
echo ""
echo "📦 Creating requirements.txt..."
cat > backend/requirements.txt << 'EOF'
# Core Framework
fastapi==0.115.0
uvicorn[standard]==0.32.0
python-multipart==0.0.12

# Data Models & Validation
pydantic==2.9.0
pydantic-settings==2.5.0

# Database
sqlalchemy==2.0.35
asyncpg==0.30.0
psycopg2-binary==2.9.10
alembic==1.13.3

# LLM Providers
openai==1.54.0
google-generativeai==0.8.3
google-cloud-aiplatform==1.73.0

# Utilities
python-dotenv==1.0.1
httpx==0.27.2
structlog==24.4.0
python-json-logger==2.0.7

# Hashing & Crypto
cryptography==43.0.0

# Testing
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0

# Development
ipython==8.29.0
black==24.10.0
ruff==0.7.3
EOF
echo "✅ requirements.txt created"

# Step 6: Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r backend/requirements.txt
echo "✅ Dependencies installed"

# Step 7: Create .env file
echo ""
echo "⚙️  Creating environment configuration..."
cat > backend/.env << EOF
# Neon Database
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}/${DB_NAME}?ssl=require
DATABASE_SYNC_URL=${DB_URL}

# Phase-1 Configuration (No Redis/Celery)
EXECUTION_MODE=sync
USE_REDIS=false
USE_CELERY=false

# API Keys (add your own)
OPENAI_API_KEY=
GOOGLE_CLOUD_PROJECT=contestra-ai
VERTEX_LOCATION=europe-west4

# Server Settings
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=info

# Security
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
CORS_ORIGINS=["http://localhost:3001","http://localhost:3000"]

# Immutability Settings
ENFORCE_MODEL_VERSION=true
REQUIRE_GROUNDING_EVIDENCE=true
ENABLE_IDEMPOTENCY=true
PROVIDER_VERSION_CACHE_TTL=300
EOF
echo "✅ .env file created (remember to add your OPENAI_API_KEY)"

# Step 8: Copy prompter files from temp repo if it exists
if [ -d "$TEMP_REPO" ]; then
    echo ""
    echo "📋 Migrating prompter files from temp repo..."
    
    # Core API files
    if [ -f "$TEMP_REPO/backend/app/api/prompt_tracking.py" ]; then
        cp "$TEMP_REPO/backend/app/api/prompt_tracking.py" backend/app/api/ 2>/dev/null && echo "  ✅ Copied prompt_tracking.py" || echo "  ⚠️  Could not copy prompt_tracking.py"
    fi
    
    # Services
    if [ -f "$TEMP_REPO/backend/app/services/prompt_hasher.py" ]; then
        cp "$TEMP_REPO/backend/app/services/prompt_hasher.py" backend/app/services/ 2>/dev/null && echo "  ✅ Copied prompt_hasher.py" || echo "  ⚠️  Could not copy prompt_hasher.py"
    fi
    
    if [ -f "$TEMP_REPO/backend/app/services/background_runner.py" ]; then
        cp "$TEMP_REPO/backend/app/services/background_runner.py" backend/app/services/ 2>/dev/null && echo "  ✅ Copied background_runner.py" || echo "  ⚠️  Could not copy background_runner.py"
    fi
    
    # ALS templates
    if [ -d "$TEMP_REPO/backend/app/services/als" ]; then
        cp -r "$TEMP_REPO/backend/app/services/als/"*.py backend/app/services/als/ 2>/dev/null && echo "  ✅ Copied ALS templates" || echo "  ⚠️  Could not copy ALS templates"
    fi
else
    echo ""
    echo "ℹ️  Temp repo not found at $TEMP_REPO - skipping file migration"
fi

# Step 9: Create main.py
echo ""
echo "📝 Creating FastAPI application..."
cat > backend/app/main.py << 'EOF'
"""
AI Ranker V2 - Prompter Only
Phase-1: FastAPI + Neon (no Redis/Celery)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting AI Ranker V2 - Prompter")
    logger.info(f"Phase-1 Mode: FastAPI + Neon (no Redis/Celery)")
    logger.info(f"Execution Mode: {os.getenv('EXECUTION_MODE', 'sync')}")
    yield
    logger.info("Shutting down AI Ranker V2")

# Create app
app = FastAPI(
    title="AI Ranker V2 - Prompter",
    version="2.0.0",
    description="Prompt Immutability Testing System",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "AI Ranker V2",
        "version": "2.0.0",
        "phase": "1",
        "mode": os.getenv("EXECUTION_MODE", "sync"),
        "features": ["prompter", "immutability", "als"]
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "phase": "1",
        "database": "neon",
        "redis": False,
        "celery": False
    }

# TODO: Import routers once implemented
# from app.api import prompt_tracking_v2
# app.include_router(prompt_tracking_v2.router, prefix="/api/v2")
EOF
echo "✅ main.py created"

# Step 10: Create database schema SQL
echo ""
echo "📄 Creating database schema..."
cat > backend/create_schema.sql << 'EOF'
-- AI Ranker V2 - Prompter Schema
-- Phase-1: Core tables only (no legacy features)

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop existing tables (for clean setup)
DROP TABLE IF EXISTS runs CASCADE;
DROP TABLE IF EXISTS batches CASCADE;
DROP TABLE IF EXISTS prompt_templates CASCADE;
DROP TABLE IF EXISTS countries CASCADE;
DROP TABLE IF EXISTS provider_version_cache CASCADE;
DROP TABLE IF EXISTS idempotency_keys CASCADE;

-- Templates table with immutability
CREATE TABLE prompt_templates (
    template_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_name VARCHAR(255) NOT NULL,
    template_sha256 VARCHAR(64) NOT NULL,
    canonical_json JSONB NOT NULL,
    org_id VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    record_hmac VARCHAR(64),
    UNIQUE(org_id, template_sha256)
);

-- Runs table with full provenance
CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(template_id),
    batch_id UUID,
    batch_run_index INTEGER,
    run_sha256 VARCHAR(64) NOT NULL,
    locale_selected VARCHAR(10),
    grounding_mode VARCHAR(20),
    grounded_effective BOOLEAN,
    model_version_effective VARCHAR(100),
    model_fingerprint VARCHAR(255),
    output TEXT,
    response_output_sha256 VARCHAR(64),
    output_json_valid BOOLEAN,
    als_block_sha256 VARCHAR(64),
    als_block_text TEXT,
    als_variant_id VARCHAR(100),
    seed_key_id VARCHAR(20),
    provoker_value VARCHAR(100),
    usage JSONB,
    latency_ms INTEGER,
    why_not_grounded TEXT,
    step2_tools_invoked BOOLEAN,
    step2_source_ref VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Batches table
CREATE TABLE batches (
    batch_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(template_id),
    batch_sha256 VARCHAR(64),
    preflight_model_version VARCHAR(100),
    preflight_model_fingerprint VARCHAR(255),
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Countries for ALS
CREATE TABLE countries (
    id SERIAL PRIMARY KEY,
    code VARCHAR(2) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    emoji VARCHAR(10),
    vat_rate DECIMAL(5,2),
    plug_types VARCHAR(50),
    emergency_numbers VARCHAR(50),
    locale_code VARCHAR(10),
    is_active BOOLEAN DEFAULT true
);

-- Provider version cache with TTL
CREATE TABLE provider_version_cache (
    provider VARCHAR(50) PRIMARY KEY,
    versions JSONB,
    current VARCHAR(100),
    last_checked_utc TIMESTAMP WITH TIME ZONE,
    expires_at_utc TIMESTAMP WITH TIME ZONE,
    etag VARCHAR(100),
    source VARCHAR(20)
);

-- Idempotency keys
CREATE TABLE idempotency_keys (
    key VARCHAR(100) NOT NULL,
    org_id VARCHAR(255) NOT NULL,
    body_sha256 VARCHAR(64) NOT NULL,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (org_id, key)
);

-- Indexes
CREATE INDEX idx_template_runs ON runs(template_id, created_at DESC);
CREATE INDEX idx_output_hash ON runs(response_output_sha256);
CREATE INDEX idx_batch_status ON batches(status, created_at DESC);
CREATE INDEX idx_batch_runs ON runs(batch_id, batch_run_index);
CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

-- Insert countries
INSERT INTO countries (code, name, emoji, vat_rate, plug_types, emergency_numbers, locale_code) VALUES
('US', 'United States', '🇺🇸', 0, 'A,B', '911', 'en-US'),
('GB', 'United Kingdom', '🇬🇧', 20, 'G', '999,112', 'en-GB'),
('DE', 'Germany', '🇩🇪', 19, 'F,C', '112,110', 'de-DE'),
('CH', 'Switzerland', '🇨🇭', 8.1, 'J,C', '112,117,118', 'de-CH'),
('FR', 'France', '🇫🇷', 20, 'E,F,C', '112,15,17,18', 'fr-FR'),
('IT', 'Italy', '🇮🇹', 22, 'L,F,C', '112,113,115,118', 'it-IT'),
('AE', 'UAE', '🇦🇪', 5, 'G,C,D', '999,997,998', 'ar-AE'),
('SG', 'Singapore', '🇸🇬', 9, 'G', '999,995', 'en-SG')
ON CONFLICT (code) DO NOTHING;
EOF
echo "✅ Database schema created"

# Step 11: Create startup scripts
echo ""
echo "🚀 Creating helper scripts..."

cat > start_backend.sh << 'EOF'
#!/bin/bash
cd backend
source ../venv/bin/activate
echo "Starting AI Ranker V2 Backend..."
echo "API Docs will be available at: http://localhost:8000/docs"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
EOF
chmod +x start_backend.sh

cat > setup_db.sh << 'EOF'
#!/bin/bash
echo "Setting up Neon database..."
source venv/bin/activate
cd backend

# Load environment variables
export $(grep -v '^#' .env | xargs)

# Run schema
psql "$DATABASE_SYNC_URL" < create_schema.sql
echo "✅ Database schema applied"
EOF
chmod +x setup_db.sh

cat > test_db.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
cd backend

# Load environment variables
export $(grep -v '^#' .env | xargs)

# Test connection
python3 << 'PYTHON'
import asyncio
import asyncpg
import os

async def test():
    try:
        db_url = os.getenv('DATABASE_SYNC_URL')
        conn = await asyncpg.connect(db_url)
        version = await conn.fetchval('SELECT version()')
        print(f"✅ Connected to PostgreSQL")
        
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public' 
            ORDER BY tablename
        """)
        print(f"✅ Found {len(tables)} tables:")
        for table in tables:
            print(f"   - {table['tablename']}")
        
        await conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

asyncio.run(test())
PYTHON
EOF
chmod +x test_db.sh

# Step 12: Create README
echo ""
echo "📚 Creating README..."
cat > README.md << 'EOF'
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
EOF
echo "✅ README created"

# Step 13: Initialize git
echo ""
echo "🔧 Initializing git repository..."
if [ ! -d ".git" ]; then
    git init
    git config core.autocrlf false
    git add .
    git commit -m "Initial AI Ranker V2 setup - Phase 1 (FastAPI + Neon)"
    echo "✅ Git repository initialized"
else
    echo "ℹ️  Git repository already exists"
fi

# Step 14: Final summary
echo ""
echo "=========================================="
echo "✨ AI Ranker V2 Bootstrap Complete! ✨"
echo "=========================================="
echo ""
echo "✅ Project structure created"
echo "✅ Python environment set up"
echo "✅ Dependencies installed"
echo "✅ Configuration files created"
echo "✅ Database schema ready"
echo "✅ Helper scripts created"
echo ""
echo "📋 Next Steps:"
echo "1. Add your OpenAI API key to backend/.env"
echo "2. Run: ./setup_db.sh (to create database tables)"
echo "3. Run: ./test_db.sh (to verify connection)"
echo "4. Run: gcloud auth application-default login (for Vertex AI)"
echo "5. Run: ./start_backend.sh (to start the server)"
echo ""
echo "📚 To implement immutability features:"
echo "- Review the TODO list in README.md"
echo "- See reference PRDs in ai-ranker-temp/"
echo ""
echo "🚀 Ready to implement v2.7 features!"