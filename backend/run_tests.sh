#!/bin/bash

# Script to run AI Ranker V2 tests

echo "🧪 Running AI Ranker V2 Tests"
echo "============================="

# Navigate to backend directory
cd "$(dirname "$0")"

# Activate virtual environment
source ../venv/bin/activate

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo "✅ Environment variables loaded"
else
    echo "⚠️  No .env file found - using defaults"
fi

# Run tests
echo ""
echo "Running test suite..."
echo ""

# Run specific test suites
echo "1️⃣ Canonicalization tests..."
python -m pytest tests/test_canonicalization.py -v --tb=short

echo ""
echo "2️⃣ Template service tests (requires DATABASE_URL)..."
if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  Skipping - DATABASE_URL not set"
else
    python -m pytest tests/test_template_service.py -v --tb=short
fi

echo ""
echo "============================="
echo "✅ Test run complete!"