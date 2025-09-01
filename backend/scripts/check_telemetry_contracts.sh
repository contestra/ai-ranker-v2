#!/usr/bin/env bash
# Post-deploy telemetry contract verification for CI
# Runs SQL assertions against Neon to ensure telemetry contract is maintained

set -euo pipefail

# Colors for output (works in most CI environments)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "════════════════════════════════════════════════════════════════"
echo "🔍 TELEMETRY CONTRACT VERIFICATION"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check required environment variables
if [ -z "${DATABASE_URL:-}" ] && [ -z "${NEON_DATABASE_URL:-}" ]; then
    echo -e "${RED}❌ ERROR: DATABASE_URL or NEON_DATABASE_URL must be set${NC}"
    exit 1
fi

# Use DATABASE_URL if set, otherwise NEON_DATABASE_URL
DB_URL="${DATABASE_URL:-${NEON_DATABASE_URL}}"

# For Neon, ensure SSL mode is set
if [[ "$DB_URL" == *"neon"* ]] && [[ "$DB_URL" != *"sslmode"* ]]; then
    DB_URL="${DB_URL}?sslmode=require"
fi

echo "📊 Database: Neon Postgres"
echo "🔗 Connection: ${DB_URL%%@*}@..." # Hide password in output
echo ""

# Function to run SQL file and capture result
run_sql_checks() {
    local sql_file="$1"
    local temp_output="/tmp/telemetry_check_$$.out"
    local temp_error="/tmp/telemetry_check_$$.err"
    
    echo "Running contract checks..."
    echo ""
    
    # Run psql and capture output
    if psql "$DB_URL" -f "$sql_file" -v ON_ERROR_STOP=1 > "$temp_output" 2> "$temp_error"; then
        # Success - show the notices
        cat "$temp_output"
        rm -f "$temp_output" "$temp_error"
        return 0
    else
        # Failure - show the error
        echo -e "${RED}❌ CONTRACT VIOLATION DETECTED${NC}"
        echo ""
        cat "$temp_error"
        cat "$temp_output"
        rm -f "$temp_output" "$temp_error"
        return 1
    fi
}

# Find the SQL file
SQL_FILE=""
if [ -f "sql/check_telemetry_contracts.sql" ]; then
    SQL_FILE="sql/check_telemetry_contracts.sql"
elif [ -f "backend/sql/check_telemetry_contracts.sql" ]; then
    SQL_FILE="backend/sql/check_telemetry_contracts.sql"
elif [ -f "../sql/check_telemetry_contracts.sql" ]; then
    SQL_FILE="../sql/check_telemetry_contracts.sql"
else
    echo -e "${RED}❌ ERROR: Cannot find check_telemetry_contracts.sql${NC}"
    echo "Searched in: sql/, backend/sql/, ../sql/"
    exit 1
fi

echo "📄 Using SQL file: $SQL_FILE"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

# Run the checks
if run_sql_checks "$SQL_FILE"; then
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo -e "${GREEN}✅ ALL TELEMETRY CONTRACT CHECKS PASSED${NC}"
    echo "════════════════════════════════════════════════════════════════"
    echo ""
    echo "The Phase-0 telemetry contract is verified:"
    echo "  • Grounded calls have response_api labels"
    echo "  • Model routing is correct"
    echo "  • Error tracking is complete"
    echo "  • Analytics views are functional"
    echo ""
    echo "Dashboards and monitoring can rely on this data quality."
    exit 0
else
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo -e "${RED}❌ TELEMETRY CONTRACT VIOLATION${NC}"
    echo "════════════════════════════════════════════════════════════════"
    echo ""
    echo "One or more contract checks failed."
    echo "This means telemetry data quality issues that will break dashboards."
    echo ""
    echo "Common fixes:"
    echo "  1. Ensure adapters set meta.response_api for grounded calls"
    echo "  2. Verify OpenAI grounded uses 'responses_http'"
    echo "  3. Verify Vertex grounded uses 'vertex_genai'"
    echo "  4. Check that failed calls include error_code"
    echo "  5. Ensure REQUIRED mode failures include why_not_grounded"
    echo ""
    echo "Run locally: psql \$DATABASE_URL -f sql/check_telemetry_contracts.sql"
    exit 1
fi