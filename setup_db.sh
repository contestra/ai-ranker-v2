#!/bin/bash
echo "Setting up Neon database..."
source venv/bin/activate
cd backend

# Load environment variables
export $(grep -v '^#' .env | xargs)

# Run schema
psql "$DATABASE_SYNC_URL" < create_schema.sql
echo "✅ Database schema applied"
