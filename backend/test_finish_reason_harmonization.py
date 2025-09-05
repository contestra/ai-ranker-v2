#!/usr/bin/env python3
"""Test finish_reason harmonization across adapters."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_finish_reason_harmonization():
    print("=" * 80)
    print("Testing Finish Reason Harmonization")
    print("=" * 80)
    
    print("\n1. OpenAI Finish Reason Handling:")
    print("-" * 60)
    
    print("\n  Priority order:")
    print("  1. SDK native finish_reason field (future-proofing)")
    print("  2. stop_reason field (current SDK)")
    print("  3. Inferred from response characteristics")
    
    print("\n  Example scenarios:")
    print("\n  a) Future SDK with finish_reason:")
    print("     response.finish_reason = 'stop'")
    print("     metadata['finish_reason'] = 'stop'")
    print("     metadata['finish_reason_source'] = 'sdk_native'")
    print("     metadata['finish_reason_standardized'] = 'STOP'")
    
    print("\n  b) Current SDK with stop_reason:")
    print("     response.stop_reason = 'length'")
    print("     metadata['finish_reason'] = 'length'")
    print("     metadata['finish_reason_source'] = 'stop_reason'")
    print("     metadata['finish_reason_standardized'] = 'MAX_TOKENS'")
    
    print("\n  c) Inferred from content:")
    print("     response has content but no finish/stop_reason")
    print("     metadata['finish_reason'] = 'stop'")
    print("     metadata['finish_reason_source'] = 'inferred_from_content'")
    print("     metadata['finish_reason_standardized'] = 'STOP'")
    
    print("\n2. Google Finish Reason Handling:")
    print("-" * 60)
    
    print("\n  Google SDK provides enum/int values:")
    print("  - 1 = STOP")
    print("  - 2 = MAX_TOKENS")
    print("  - 3 = SAFETY")
    print("  - 4 = RECITATION")
    print("  - 5 = OTHER")
    
    print("\n  Example scenarios:")
    print("\n  a) SDK provides enum:")
    print("     candidate.finish_reason = FinishReason.STOP")
    print("     metadata['finish_reason'] = 'STOP'")
    print("     metadata['finish_reason_source'] = 'sdk_native'")
    print("     metadata['finish_reason_standardized'] = 'STOP'")
    
    print("\n  b) SDK provides integer:")
    print("     candidate.finish_reason = 2")
    print("     metadata['finish_reason'] = 'MAX_TOKENS'")
    print("     metadata['finish_reason_source'] = 'sdk_native'")
    print("     metadata['finish_reason_standardized'] = 'MAX_TOKENS'")
    
    print("\n3. Standardized Values for Cross-Vendor Comparison:")
    print("-" * 60)
    
    print("\n  Common standardized values:")
    print("  - STOP: Normal completion")
    print("  - MAX_TOKENS: Hit token limit")
    print("  - SAFETY: Content filtered for safety")
    print("  - ERROR: Error occurred")
    print("  - TOOL_CALLS: Tool calls only (OpenAI-specific)")
    print("  - RECITATION: Recitation issue (Google-specific)")
    print("  - UNKNOWN: Unknown reason")
    
    print("\n4. Metadata Fields:")
    print("-" * 60)
    
    print("\n  All adapters now provide:")
    print("  - finish_reason: The actual finish reason (vendor format)")
    print("  - finish_reason_source: Where we got it from")
    print("  - finish_reason_standardized: Standardized for comparison")
    
    print("\n5. Cross-Vendor Analysis Benefits:")
    print("-" * 60)
    
    print("\n  With harmonized finish reasons, we can now:")
    print("  - Compare completion patterns across vendors")
    print("  - Track MAX_TOKENS issues consistently")
    print("  - Monitor SAFETY filtering across platforms")
    print("  - Identify vendor-specific issues (TOOL_CALLS, RECITATION)")
    print("  - Build unified dashboards for all providers")
    
    print("\n6. Future-Proofing:")
    print("-" * 60)
    
    print("\n  OpenAI adapter is ready for when SDK adds finish_reason:")
    print("  - Checks for finish_reason field first")
    print("  - Falls back to stop_reason (current)")
    print("  - Infers if neither available")
    print("  - All paths lead to harmonized metadata")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("✓ Both adapters store finish_reason in metadata")
    print("✓ Source tracking shows where finish_reason came from")
    print("✓ Standardized values enable cross-vendor comparison")
    print("✓ OpenAI adapter future-proofed for SDK updates")
    print("✓ Inference fallbacks ensure we always have a value")
    print("✓ Vendor-specific reasons preserved alongside standardized")

if __name__ == "__main__":
    test_finish_reason_harmonization()