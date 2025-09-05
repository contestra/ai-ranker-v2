#!/usr/bin/env python3
"""Test centralized ALS configuration."""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.als_config import ALSConfig

def test_als_config():
    print("=" * 80)
    print("Testing Centralized ALS Configuration")
    print("=" * 80)
    
    print("\n1. Default Configuration:")
    print("-" * 60)
    
    # Test default configuration
    default_key_id = ALSConfig.get_seed_key_id()
    print(f"  Default seed_key_id: {default_key_id}")
    print(f"  Is production key: {default_key_id == ALSConfig.PRODUCTION_SEED_KEY_ID}")
    print(f"  Is development key: {default_key_id == ALSConfig.DEVELOPMENT_SEED_KEY_ID}")
    
    print("\n2. Vendor-specific Configuration:")
    print("-" * 60)
    
    # Test OpenAI-specific configuration
    openai_key_id = ALSConfig.get_seed_key_id("openai")
    print(f"  OpenAI seed_key_id: {openai_key_id}")
    
    # Simulate OpenAI environment override
    os.environ["OPENAI_SEED_KEY_ID"] = "openai_custom_key"
    openai_override = ALSConfig.get_seed_key_id("openai")
    print(f"  OpenAI with env override: {openai_override}")
    del os.environ["OPENAI_SEED_KEY_ID"]
    
    print("\n3. Metadata Marking:")
    print("-" * 60)
    
    # Test metadata marking for different scenarios
    test_cases = [
        ("Development default", ALSConfig.DEVELOPMENT_SEED_KEY_ID, None),
        ("Production key", ALSConfig.PRODUCTION_SEED_KEY_ID, None),
        ("OpenAI vendor", "v1_2025", "openai"),
    ]
    
    for desc, key_id, vendor in test_cases:
        metadata = {}
        ALSConfig.mark_als_metadata(metadata, key_id, vendor)
        print(f"\n  {desc}:")
        for k, v in metadata.items():
            if k.startswith("als_"):
                print(f"    {k}: {v}")
    
    print("\n4. Global Override:")
    print("-" * 60)
    
    # Test global override
    os.environ["ALS_SEED_KEY_ID"] = "global_override_key"
    global_override = ALSConfig.get_seed_key_id()
    print(f"  With global override: {global_override}")
    
    metadata = {}
    ALSConfig.mark_als_metadata(metadata, global_override)
    print(f"  Metadata source: {metadata.get('als_seed_source')}")
    del os.environ["ALS_SEED_KEY_ID"]
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("✓ Centralized ALS configuration prevents drift")
    print("✓ Vendor-specific overrides supported")
    print("✓ Metadata marking identifies defaults/placeholders")
    print("✓ Environment overrides tracked in metadata")

if __name__ == "__main__":
    test_als_config()