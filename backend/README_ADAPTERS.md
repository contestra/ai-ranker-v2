# LLM Adapters Documentation

## Overview
Custom LLM adapters for OpenAI and Google Vertex with PRD-compliant grounding, authority scoring, and ALS propagation.

## Documentation Structure

### Core Documentation
1. **[GROUNDING_IMPLEMENTATION.md](./GROUNDING_IMPLEMENTATION.md)** - Complete implementation guide with configuration, testing, and troubleshooting
2. **[ADAPTER_ENGINEERING_RATIONALE.md](./ADAPTER_ENGINEERING_RATIONALE.md)** - Why custom adapters were required (provider issues & solutions)
3. **[ADAPTER_FIXES_20250831.md](./ADAPTER_FIXES_20250831.md)** - Detailed fixes applied for PRD compliance

### Key Features

#### ✅ Grounding
- **Modes**: AUTO (model decides), REQUIRED (must ground or fail), NONE (disabled)
- **OpenAI**: Adaptive tool selection (`web_search` vs `web_search_preview`)
- **Vertex**: GoogleSearch tool with two-step pipeline for JSON+grounded

#### ✅ Authority Scoring
- **4-tier domain classification** (Tier 1: Premium, Tier 4: Penalty)
- **Authority score**: 0-100 weighted average
- **Metrics**: tier percentages, premium percentage, penalty percentage
- **Configuration**: Edit `app/llm/domain_authority.py` to modify tiers

#### ✅ ALS (Ambient Location Signals)
- **Deterministic generation**: ≤350 NFC chars, SHA256 hashing
- **100% propagation**: Router hardening ensures metadata presence
- **Immutability**: No runtime randomization, stable variants

#### ✅ Two-Step Attestation
- **Vertex JSON+grounded**: Step 1 grounds, Step 2 reshapes with no tools
- **Attestation fields**: `step2_tools_invoked=false`, `step2_source_ref=SHA256`
- **PRD compliance**: Enforces immutability requirement

## Test Results Summary

### Latest Test Run (2025-08-31)
- **Total Tests**: 24 (20 successful, 4 expected failures)
- **ALS Detection**: 100% (all ALS-enabled tests show `als_present: true`)
- **Vertex Grounding**: 100% success (8/8 tests)
- **OpenAI Grounding**: 0% (expected - model limitation)
- **Authority Scores**: Currently 40/100 due to Vertex redirect URLs

### Key Findings
1. **OpenAI AUTO mode rarely grounds** - This is expected model behavior, not a bug
2. **Vertex citations are redirect URLs** - URLResolver created to handle this
3. **REQUIRED mode works correctly** - Fails closed as designed
4. **ALS propagation is 100% reliable** - Router hardening ensures this

## Quick Start

### Environment Setup
```bash
# Required
export OPENAI_API_KEY="your-key"
export GOOGLE_CLOUD_PROJECT="your-project"
export VERTEX_LOCATION="europe-west4"

# Optional
export ALLOWED_OPENAI_MODELS="gpt-5,gpt-5-chat-latest"
export ALLOWED_VERTEX_MODELS="publishers/google/models/gemini-2.5-pro"
```

### Run Tests
```bash
# Full test suite with authority scoring
python test_als_grounding_final.py

# CI gates for PRD compliance
pytest tests/test_grounding_gates.py -v

# Quick authority scoring test
python test_authority_quick.py
```

## File Structure
```
backend/
├── app/llm/
│   ├── unified_llm_adapter.py      # Router with ALS hardening
│   ├── adapters/
│   │   ├── openai_adapter.py       # OpenAI with adaptive tools
│   │   └── vertex_adapter.py       # Vertex with two-step pipeline
│   ├── domain_authority.py         # Authority scoring system
│   └── url_resolver.py            # Redirect resolution
├── tests/
│   └── test_grounding_gates.py    # CI compliance tests
└── test_als_grounding_final.py    # Comprehensive test suite
```

## Known Limitations & Expected Behaviors

### OpenAI
- **AUTO mode rarely grounds** (model behavior, not adapter issue)
- **REQUIRED mode correctly fails** with GROUNDING_NOT_SUPPORTED
- Some models don't support any web_search variant

### Vertex
- **Citations show as redirect URLs** (affects authority scores)
- **Empty responses may occur** for ungrounded requests
- Regional availability affects SDK selection

## Monitoring & Analytics

### Key Metrics
- `grounded_effective`: Did grounding actually occur?
- `grounding_mode_requested`: AUTO/REQUIRED/NONE
- `authority_score`: 0-100 domain quality score
- `als_present`: Was ALS context provided?
- `step2_tools_invoked`: Two-step attestation (must be false)

### Dashboard Recommendations
```
[Mode: AUTO] [Grounded: ✓] [Citations: 5] [Authority: 85/100]
[ALS: US] [SHA: b190af...] [Tier-1: 60%]
```

## Compliance Status

✅ **PRD Requirements Met**:
- REQUIRED mode fails closed
- ALS propagates to response.metadata
- Authority scoring implemented
- Two-step attestation for JSON+grounded
- Telemetry includes all required fields
- Deterministic ALS generation
- URL redirect handling
- CI gates for critical paths

## Support

For issues or questions:
1. Check [GROUNDING_IMPLEMENTATION.md](./GROUNDING_IMPLEMENTATION.md) troubleshooting section
2. Review [ADAPTER_ENGINEERING_RATIONALE.md](./ADAPTER_ENGINEERING_RATIONALE.md) for provider-specific issues
3. Run `pytest tests/test_grounding_gates.py -v` to verify compliance

## Version History
- **2025-09-04**: Major refactoring and router upgrade
  - OpenAI adapter reduced by 55% (removed SDK duplicates)
  - Added capability gating (prevents 400 errors)
  - Implemented circuit breaker and pacing
  - Fixed GPT-5 empty response issues
  - Enhanced telemetry with new fields
- **2025-08-31**: Full PRD compliance achieved
  - Fixed ALS propagation bugs
  - Added authority scoring system
  - Implemented two-step attestation
  - Created comprehensive test suite
  - Documented all provider issues and solutions