#!/usr/bin/env python3
"""
CI Guard: Validates production allowlist configuration.
Fails if production environment has non-pinned models.
"""

import os
import sys

def check_prod_allowlist():
    """
    Check that production allowlist contains only gpt-5-2025-08-07.
    
    Returns:
        Exit code 0 if valid, 1 if invalid
    """
    
    # Get environment and allowlist
    environment = os.getenv("ENVIRONMENT", "development")
    allowed_models = os.getenv("ALLOWED_OPENAI_MODELS", "")
    
    print("=" * 60)
    print("CI GUARD: Production Allowlist Check")
    print("=" * 60)
    print(f"Environment: {environment}")
    print(f"Allowed Models: {allowed_models}")
    print("-" * 60)
    
    # Check if we're in production
    if environment.lower() != "production":
        print("✅ PASS: Not production environment, skipping check")
        return 0
    
    # Production environment - enforce strict allowlist
    PROD_ALLOWED = "gpt-5-2025-08-07"
    
    # Parse allowlist
    models = [m.strip() for m in allowed_models.split(",") if m.strip()]
    
    # Check exact match
    if len(models) != 1 or models[0] != PROD_ALLOWED:
        print("❌ FAIL: Production allowlist violation!")
        print(f"  Expected: {PROD_ALLOWED}")
        print(f"  Found: {', '.join(models) if models else '(empty)'}")
        print("")
        print("DEPLOYMENT BLOCKED")
        print("Production must use only the pinned model: gpt-5-2025-08-07")
        print("")
        print("To fix:")
        print("  1. Set ALLOWED_OPENAI_MODELS=gpt-5-2025-08-07")
        print("  2. Remove any dev/test models from production config")
        print("=" * 60)
        return 1
    
    print("✅ PASS: Production allowlist valid")
    print(f"  Using pinned model: {PROD_ALLOWED}")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    exit_code = check_prod_allowlist()
    sys.exit(exit_code)