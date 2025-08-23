#!/bin/bash

# Script to switch between local and production environment configurations

set -e

if [ "$1" == "local" ]; then
    echo "Switching to LOCAL development environment (with SA key)..."
    cp .env.local .env
    echo "✅ Now using .env.local (Service Account authentication)"
    echo "   ENFORCE_VERTEX_WIF=false"
    echo "   Using SA key at: ~/.config/gcloud/keys/vertex-dev.json"
elif [ "$1" == "production" ]; then
    echo "Switching to PRODUCTION environment (with WIF)..."
    cp .env.production .env
    echo "✅ Now using .env.production (Workload Identity Federation)"
    echo "   ENFORCE_VERTEX_WIF=true"
    echo "   No SA keys will be used"
else
    echo "Usage: $0 [local|production]"
    echo ""
    echo "  local      - Use Service Account key for development"
    echo "  production - Use WIF for production deployment"
    echo ""
    echo "Current .env first lines:"
    head -n 2 .env 2>/dev/null || echo "No .env file found"
    exit 1
fi

echo ""
echo "Remember to restart the backend for changes to take effect!"