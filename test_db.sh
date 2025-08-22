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
