# Neon PostgreSQL Setup Guide for AI Ranker V2

**Purpose:** Complete guide for setting up Neon PostgreSQL for v2 migration  
**Status:** Ready for implementation  
**Parent Document:** [AI_RANKER_V2_MIGRATION_PRD.md](./AI_RANKER_V2_MIGRATION_PRD.md)

---

## 1. Understanding the Migration

### Current State (V1)
- **Database**: SQLite (local files)
- **Files**: Multiple .db files (ai_ranker.db, prompter.db, etc.)
- **Issues**: Not suitable for production, no concurrent writes, file-based

### Target State (V2)
- **Database**: Neon PostgreSQL (serverless Postgres)
- **Benefits**: Cloud-hosted, auto-scaling, branching for dev/test, connection pooling
- **Cost**: Free tier includes 0.5 GB storage (enough for MVP)

---

## 2. Neon Account Setup

### Step 1: Create Neon Account
1. Go to https://neon.tech
2. Sign up with GitHub or email
3. Verify email if needed

### Step 2: Create Project
1. Click "Create Project"
2. **Project Name**: `ai-ranker-v2`
3. **Region**: Choose closest to your users (e.g., `us-east-1` or `eu-central-1`)
4. **Postgres Version**: 15 (latest stable)
5. Click "Create Project"

### Step 3: Get Connection Details
Your Neon project details:
```
Host: ep-empty-frog-a2blbcz9-pooler.eu-central-1.aws.neon.tech
Database: neondb
Username: neondb_owner
Password: npg_nZ2RowvS0ODr
Region: eu-central-1

Pooled Connection String:
postgresql://neondb_owner:npg_nZ2RowvS0ODr@ep-empty-frog-a2blbcz9-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require

Direct Connection String (non-pooled):
postgresql://neondb_owner:npg_nZ2RowvS0ODr@ep-empty-frog-a2blbcz9.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

Note: Using the pooled connection (-pooler) is recommended for web applications.

---

## 3. Database Schema Creation

### Option A: Direct SQL (Recommended for V2)

Connect to Neon via their web SQL editor or psql:

```sql
-- Create schema for prompter-only functionality
-- No brand/entity tables needed for V2!

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Templates table
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

-- Runs table (formerly prompt_results)
CREATE TABLE runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(template_id),
    run_sha256 VARCHAR(64) NOT NULL,
    
    -- Execution details
    locale_selected VARCHAR(10),
    grounding_mode VARCHAR(20),
    grounded_effective BOOLEAN,
    
    -- Model info
    model_version_effective VARCHAR(100),
    model_fingerprint VARCHAR(255),
    
    -- Output
    output TEXT,
    response_output_sha256 VARCHAR(64),
    output_json_valid BOOLEAN,
    
    -- ALS
    als_block_sha256 VARCHAR(64),
    als_block_text TEXT,
    als_variant_id VARCHAR(100),
    seed_key_id VARCHAR(20),
    
    -- Metadata
    usage JSONB,
    latency_ms INTEGER,
    why_not_grounded TEXT,
    
    -- Gemini Step-2 attestation
    step2_tools_invoked BOOLEAN,
    step2_source_ref VARCHAR(64),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes
    INDEX idx_template_runs (template_id, created_at),
    INDEX idx_output_hash (response_output_sha256)
);

-- Batches table
CREATE TABLE batches (
    batch_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_id UUID REFERENCES prompt_templates(template_id),
    batch_sha256 VARCHAR(64),
    
    -- Preflight lock
    preflight_model_version VARCHAR(100),
    preflight_model_fingerprint VARCHAR(255),
    
    -- Configuration
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    
    -- Metadata
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    INDEX idx_batch_status (status, created_at)
);

-- Countries table (for ALS)
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

-- Provider version cache
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
    key VARCHAR(100) PRIMARY KEY,
    org_id VARCHAR(255) NOT NULL,
    body_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(org_id, key)
);

-- Initial country data
INSERT INTO countries (code, name, emoji, vat_rate, plug_types, emergency_numbers, locale_code) VALUES
('US', 'United States', '🇺🇸', 0, 'A,B', '911', 'en-US'),
('GB', 'United Kingdom', '🇬🇧', 20, 'G', '999,112', 'en-GB'),
('DE', 'Germany', '🇩🇪', 19, 'F,C', '112,110', 'de-DE'),
('CH', 'Switzerland', '🇨🇭', 8.1, 'J,C', '112,117,118', 'de-CH'),
('FR', 'France', '🇫🇷', 20, 'E,F,C', '112,15,17,18', 'fr-FR'),
('IT', 'Italy', '🇮🇹', 22, 'L,F,C', '112,113,115,118', 'it-IT'),
('AE', 'UAE', '🇦🇪', 5, 'G,C,D', '999,997,998', 'ar-AE'),
('SG', 'Singapore', '🇸🇬', 9, 'G', '999,995', 'en-SG');
```

### Option B: Using Alembic (If you have existing migrations)

```bash
# In WSL
cd ~/ai-ranker-v2/backend

# Install alembic
pip install alembic asyncpg

# Initialize alembic (if not already done)
alembic init alembic

# Configure alembic.ini with Neon connection string
# sqlalchemy.url = postgresql+asyncpg://user:pass@xxx.neon.tech/neondb

# Create migration
alembic revision -m "Initial v2 schema"

# Apply migration
alembic upgrade head
```

---

## 4. Environment Configuration

### Create .env file in WSL:
```bash
cd ~/ai-ranker-v2/backend

cat > .env << 'EOF'
# Database - Using your actual Neon credentials
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_nZ2RowvS0ODr@ep-empty-frog-a2blbcz9-pooler.eu-central-1.aws.neon.tech/neondb?ssl=require
DATABASE_SYNC_URL=postgresql://neondb_owner:npg_nZ2RowvS0ODr@ep-empty-frog-a2blbcz9-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require

# Direct connection (for migrations)
DATABASE_DIRECT_URL=postgresql://neondb_owner:npg_nZ2RowvS0ODr@ep-empty-frog-a2blbcz9.eu-central-1.aws.neon.tech/neondb?sslmode=require

# Connection pool settings
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30

# Phase indicator
EXECUTION_MODE=sync  # Phase-1: sync, Phase-2: celery
USE_REDIS=false      # Phase-1: false, Phase-2: true
EOF
```

---

## 5. Connection Code

### SQLAlchemy Setup (backend/app/database.py):
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Async engine for FastAPI
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set True for debugging
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Verify connections before using
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

---

## 6. Data Migration Strategy

### Decision: Start Fresh (Recommended)
Since you're dropping 92% of features, migrating old data adds complexity with little value.

**Approach:**
1. Start with clean schema
2. No data migration from SQLite
3. Keep v1 running as read-only archive if needed

### Alternative: Selective Migration (If Required)
If you must migrate some templates:

```python
# migrate_templates.py
import asyncio
import sqlite3
import asyncpg
from datetime import datetime

async def migrate_templates():
    # Connect to old SQLite
    sqlite_conn = sqlite3.connect('/mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/backend/prompter.db')
    sqlite_cur = sqlite_conn.cursor()
    
    # Connect to new Neon
    neon_conn = await asyncpg.connect('postgresql://user:pass@xxx.neon.tech/neondb')
    
    # Migrate only recent templates
    templates = sqlite_cur.execute("""
        SELECT * FROM prompt_templates 
        WHERE created_at > '2024-01-01'
    """).fetchall()
    
    for template in templates:
        await neon_conn.execute("""
            INSERT INTO prompt_templates 
            (template_name, template_sha256, canonical_json, org_id, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT DO NOTHING
        """, template['name'], template['sha256'], template['json'], 
            'default', template['created_at'])
    
    print(f"Migrated {len(templates)} templates")
    
    await neon_conn.close()
    sqlite_conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_templates())
```

---

## 7. Testing the Connection

### Quick Test Script:
```python
# test_neon.py
import asyncio
import asyncpg

async def test_connection():
    conn = await asyncpg.connect(
        'postgresql://neondb_owner:npg_nZ2RowvS0ODr@ep-empty-frog-a2blbcz9-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require'
    )
    
    # Test query
    version = await conn.fetchval('SELECT version()')
    print(f"Connected to: {version}")
    
    # Test tables
    tables = await conn.fetch("""
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public'
    """)
    print(f"Tables: {[t['tablename'] for t in tables]}")
    
    await conn.close()

asyncio.run(test_connection())
```

---

## 8. Neon-Specific Features to Leverage

### 1. Branching (Great for Testing)
```bash
# Create a branch for testing
neon branches create --name testing --project-id xxx

# Get connection string for branch
neon connection-string --branch testing
```

### 2. Connection Pooling
Neon provides built-in connection pooling. Use the pooled connection string:
```
postgresql://user:pass@xxx-pooler.neon.tech/neondb
```

### 3. Auto-suspend
Neon automatically suspends inactive databases (free tier: after 5 minutes).
First query after suspension takes ~1 second to wake up.

### 4. Point-in-Time Recovery
Available even on free tier (7 days retention).

---

## 9. Migration Checklist

- [ ] Create Neon account
- [ ] Create project and database
- [ ] Save connection credentials securely
- [ ] Create schema using SQL or Alembic
- [ ] Configure .env with connection string
- [ ] Test connection from WSL
- [ ] Update SQLAlchemy models to match schema
- [ ] Verify FastAPI can connect
- [ ] Run a test create/read operation
- [ ] Document connection details for team

---

## 10. Common Issues and Solutions

### Issue: Connection timeout
**Solution**: Check if database is suspended. First connection wakes it up.

### Issue: SSL required error
**Solution**: Add `?sslmode=require` to connection string.

### Issue: Too many connections
**Solution**: Use pooled connection endpoint or reduce pool_size.

### Issue: Permission denied
**Solution**: Ensure user has correct permissions. Neon users have full access by default.

---

## Cost Considerations

### Free Tier Limits:
- 0.5 GB storage
- 3 databases per project
- Unlimited compute (auto-suspend after 5 min)
- 7-day point-in-time recovery

### For AI Ranker V2:
The free tier is MORE than sufficient for Phase-1 development and early production.

---

## Summary

Moving from SQLite to Neon PostgreSQL provides:
1. **Production-ready database** from day 1
2. **No local database files** to manage
3. **Cloud-native** with auto-scaling
4. **Free tier** sufficient for MVP
5. **Easy branching** for dev/test environments

This setup aligns perfectly with the v2 migration strategy of starting simple (FastAPI + Neon) and adding complexity later (Celery + Redis).