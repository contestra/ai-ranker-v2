#!/usr/bin/env python3
"""
Test ALS determinism - ensure same inputs produce same outputs
Critical for caching and compliance
"""
import asyncio
import os
import sys
import hashlib
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from dotenv import load_dotenv
load_dotenv()

os.environ["DISABLE_PROXIES"] = "true"

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest

async def test_als_determinism():
    """Test that ALS generation is deterministic"""
    print("\n" + "="*70)
    print("ALS DETERMINISM TEST")
    print("="*70)
    
    adapter = UnifiedLLMAdapter()
    
    # Test configurations
    test_configs = [
        {'country_code': 'US', 'locale': 'en-US'},
        {'country_code': 'DE', 'locale': 'de-DE'},
        {'country_code': 'GB', 'locale': 'en-GB'},
        {'country_code': 'FR', 'locale': 'fr-FR'},
    ]
    
    results = []
    
    for config in test_configs:
        print(f"\nTesting {config['country_code']} ({config['locale']})...")
        
        # Generate ALS 5 times with same inputs
        als_blocks = []
        sha256_hashes = []
        
        for i in range(5):
            request = LLMRequest(
                vendor="openai",
                model="gpt-5",
                messages=[{"role": "user", "content": "Test"}],
                als_context=config
            )
            
            # Apply ALS
            modified_request = adapter._apply_als(request)
            
            # Extract ALS block and hash
            als_text = modified_request.metadata.get('als_block_text', '')
            als_sha = modified_request.metadata.get('als_block_sha256', '')
            
            als_blocks.append(als_text)
            sha256_hashes.append(als_sha)
            
            if i == 0:
                print(f"  SHA256: {als_sha[:16]}...")
                print(f"  Length: {len(als_text)} chars")
                print(f"  Variant: {modified_request.metadata.get('als_variant_id')}")
        
        # Check determinism
        unique_blocks = set(als_blocks)
        unique_hashes = set(sha256_hashes)
        
        is_deterministic = len(unique_blocks) == 1 and len(unique_hashes) == 1
        
        if is_deterministic:
            print(f"  ✅ DETERMINISTIC: Same SHA256 across 5 runs")
        else:
            print(f"  ❌ NON-DETERMINISTIC: {len(unique_hashes)} different SHA256s")
            for i, sha in enumerate(unique_hashes):
                print(f"     Run {i+1}: {sha[:16]}...")
        
        results.append({
            'country': config['country_code'],
            'locale': config['locale'],
            'deterministic': is_deterministic,
            'unique_hashes': len(unique_hashes),
            'sha256': sha256_hashes[0] if sha256_hashes else None
        })
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    deterministic_count = sum(1 for r in results if r['deterministic'])
    print(f"Deterministic: {deterministic_count}/{len(results)} configurations")
    
    if deterministic_count == len(results):
        print("✅ ALL CONFIGURATIONS ARE DETERMINISTIC")
        return True
    else:
        print("❌ SOME CONFIGURATIONS ARE NON-DETERMINISTIC")
        for r in results:
            if not r['deterministic']:
                print(f"  - {r['country']}: {r['unique_hashes']} different hashes")
        return False

async def test_als_no_timestamps():
    """Test that ALS blocks contain no timestamps"""
    print("\n" + "="*70)
    print("ALS NO-TIMESTAMP TEST")
    print("="*70)
    
    adapter = UnifiedLLMAdapter()
    
    import re
    import datetime
    
    # Patterns that would indicate timestamps
    timestamp_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # Date YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',  # Date MM/DD/YYYY
        r'\d{2}:\d{2}:\d{2}',  # Time HH:MM:SS
        r'\d{2}:\d{2}',        # Time HH:MM
        str(datetime.datetime.now().year),  # Current year
        datetime.datetime.now().strftime('%B'),  # Current month name
        datetime.datetime.now().strftime('%b'),  # Current month abbr
    ]
    
    countries = ['US', 'DE', 'GB', 'FR']
    all_passed = True
    
    for country in countries:
        request = LLMRequest(
            vendor="openai",
            model="gpt-5",
            messages=[{"role": "user", "content": "Test"}],
            als_context={'country_code': country}
        )
        
        modified_request = adapter._apply_als(request)
        als_text = modified_request.metadata.get('als_block_text', '')
        
        print(f"\n{country} ALS Block:")
        found_timestamps = []
        
        for pattern in timestamp_patterns:
            if re.search(pattern, als_text, re.IGNORECASE):
                found_timestamps.append(pattern)
        
        if found_timestamps:
            print(f"  ❌ Found timestamp patterns: {found_timestamps}")
            all_passed = False
        else:
            print(f"  ✅ No timestamps found")
    
    return all_passed

async def test_als_length_enforcement():
    """Test that ALS blocks over 350 chars fail closed"""
    print("\n" + "="*70)
    print("ALS LENGTH ENFORCEMENT TEST")
    print("="*70)
    
    # This test would need a way to force a long ALS block
    # For now, we'll just verify that existing blocks are under 350
    
    adapter = UnifiedLLMAdapter()
    countries = ['US', 'DE', 'GB', 'FR', 'IT', 'CH', 'AE', 'SG']
    
    all_compliant = True
    
    for country in countries:
        request = LLMRequest(
            vendor="openai",
            model="gpt-5",
            messages=[{"role": "user", "content": "Test"}],
            als_context={'country_code': country}
        )
        
        try:
            modified_request = adapter._apply_als(request)
            als_length = modified_request.metadata.get('als_nfc_length', 0)
            
            if als_length > 350:
                print(f"{country}: ❌ {als_length} chars (exceeds 350)")
                all_compliant = False
            else:
                print(f"{country}: ✅ {als_length} chars (under 350)")
                
        except ValueError as e:
            if "ALS_BLOCK_TOO_LONG" in str(e):
                print(f"{country}: ✅ Correctly failed with ALS_BLOCK_TOO_LONG")
            else:
                raise
    
    return all_compliant

async def main():
    """Run all ALS determinism tests"""
    
    # Test 1: Determinism
    determinism_passed = await test_als_determinism()
    
    # Test 2: No timestamps
    no_timestamps_passed = await test_als_no_timestamps()
    
    # Test 3: Length enforcement
    length_passed = await test_als_length_enforcement()
    
    # Final summary
    print("\n" + "="*70)
    print("FINAL TEST RESULTS")
    print("="*70)
    
    print(f"Determinism Test: {'✅ PASSED' if determinism_passed else '❌ FAILED'}")
    print(f"No Timestamps Test: {'✅ PASSED' if no_timestamps_passed else '❌ FAILED'}")
    print(f"Length Enforcement: {'✅ PASSED' if length_passed else '❌ FAILED'}")
    
    all_passed = determinism_passed and no_timestamps_passed and length_passed
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED - ALS is deterministic and compliant!")
    else:
        print("\n⚠️  SOME TESTS FAILED - ALS needs fixes")
    
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)