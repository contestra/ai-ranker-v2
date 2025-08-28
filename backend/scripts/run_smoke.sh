#!/usr/bin/env bash
# Run adapter smoke tests
# Fast, network-free validation of critical paths

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Running adapter smoke tests..."
echo "================================"

# Change to backend directory
cd "$(dirname "$0")/.."

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}⚠️  pytest not found. Installing...${NC}"
    pip install pytest pytest-asyncio
fi

# Run the tests
if pytest -q tests/test_adapters_smoke.py; then
    echo -e "\n${GREEN}✅ All smoke tests passed!${NC}"
    echo "================================"
    echo "Validated:"
    echo "  • OpenAI: ungrounded, grounded (AUTO/REQUIRED), preview retry"
    echo "  • Vertex: Step-1 grounded, Step-2 JSON reshape, attestation"
    echo "  • Rate limiter: adaptive multipliers, auto-trim"
    exit 0
else
    echo -e "\n${RED}❌ Some tests failed${NC}"
    echo "================================"
    echo "Run with verbose output:"
    echo "  pytest -v tests/test_adapters_smoke.py"
    exit 1
fi