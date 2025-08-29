# ALS Architecture Analysis & Fix Plan

## Executive Summary
ALS (Ambient Location Signals) is currently "half-wired" - it exists but is bypassed by test execution paths and not properly persisted per the Immutability PRD requirements.

## Current Issues (Mapped to Specifications)

### 1. ALS Applied in Wrong Layer / Bypassed by Tests
**Issue**: ALS must be injected ONCE in the Unified Orchestrator before routing to any provider
- **Current State**: ALS moved to BatchRunner-only path, tests call adapters directly
- **Spec Requirement**: `system → ALS block → user`, orchestrator-side, provider-agnostic
- **Impact**: Runs with no ALS influence, nothing persisted

### 2. ALS Provenance Not Persisted
**Issue**: Per Immutability PRD, every run must capture ALS metadata
- **Missing Fields**:
  - `als_block_text`
  - `als_block_sha256`
  - `als_variant_id`
  - `seed_key_id`
- **Requirement**: Length must be NFC-counted ≤350 characters
- **Impact**: Drifted from immutability guarantees, can't audit ALS effects

### 3. Model Pinning Drift
**Issue**: Hard-pinning Vertex to `gemini-2.5-pro` regardless of request
- **Spec Violation**: Adapter PRD states "no silent rewrites; respect model passed/pinned"
- **Impact**: Corrupts comparability across lanes and templates with explicit versions

### 4. Grounding/ALS Semantics Mixing
**Issue**: ALS is being confused with grounding
- **Correct Behavior**: 
  - ALS = Ungrounded (ALS-only) lane's weak prior
  - Should be included in grounded lanes for fairness
  - NOT a replacement for web tools
- **Requirement**: Keep three modes distinct and measured as defined

## Fix Plan (Execute in Order)

### Step 1: Put ALS Back Where It Belongs - Always

```python
# UnifiedLLMAdapter must run _apply_als() for EVERY request
# - Template runs
# - Single runs  
# - Batch cells

# Correct message order enforcement:
# 1. System message
# 2. ALS block (≤350 chars)
# 3. User message
```

**Implementation Points**:
- Ensure `UnifiedLLMAdapter._apply_als()` runs for every request type
- Adapters (OpenAI/Vertex) treat messages as already enriched
- No ALS logic inside individual adapters
- Enforce exact message order: `system → ALS → user`

### Step 2: Persist ALS Provenance Per Run (Immutability)

**Required Fields to Capture**:
```python
{
    "als_block_text": str,      # The actual ALS text
    "als_block_sha256": str,     # SHA256 hash of block
    "als_variant_id": str,       # Which variant was used
    "seed_key_id": str,          # Seed key for determinism
    "determinism_tier": str      # Level of determinism
}
```

**Validation Rules**:
- Reject ALS >350 NFC chars (no silent truncation)
- Add acceptance tests for 350-char rule
- Test deterministic rotation semantics

### Step 3: Respect Model Pins - Remove Silent Overrides

**Vertex Adapter Changes**:
- Remove hard-coding of `gemini-2.5-pro`
- Route EXACTLY the requested model/path from template or request
- Include location/region from request
- Fail fast with remediation if misconfigured

**Policy**:
- Keep "no Direct Gemini API" stance
- Vertex-only for Gemini
- Fail closed on auth issues with clear steps

### Step 4: Fix Test Harness to Use Public Path

**Test Architecture Fix**:
- Drive tests through orchestrator/template execution path (or HTTP endpoint)
- NOT direct adapter calls
- Required by Adapter PRD for consistent ALS, grounding policy, persistence

**Three Evaluation Modes (Strict)**:
1. **UNGROUNDED** (ALS-only)
2. **GROUNDED-AUTO** (may skip search, must record)
3. **GROUNDED-REQUIRED** (fail if no search)

### Step 5: Metrics & Visibility

**Normalized Run Record/Telemetry Fields**:
```python
{
    "als_present": bool,
    "als_block_sha256": str,
    "grounding_mode_requested": str,
    "grounded_effective": bool,
    "tool_call_count": int,
    "why_not_grounded": str,
    "response_api": str,
    "usage": dict,  # Flattened
    "latency": int
}
```

## Quick Validations (Execute Immediately)

### 1. Payload Spot-Check
Run single UNGROUNDED probe and log actual provider payload:
```python
# Expected structure:
messages[0] = system_message
messages[1] = als_block  # ≤350 chars, starts with "[Context:"
messages[2] = user_message
```
**Validation**: If ALS isn't literally present in payload, it's not applied correctly

### 2. DB Row Check
Confirm latest `runs` rows have non-null:
- `als_block_text`
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`

### 3. Mode Separation Test
**Grounded-Required runs**:
- OpenAI: Must use `tool_choice:"required"`
- Vertex: Must have non-empty grounding metadata
- STILL include ALS in prompt order
- Fail closed when searches don't happen

### 4. Model Pin Validation
- Create template pinned to different Vertex model/version
- Verify adapter doesn't rewrite it
- Confirm run captures effective model/fingerprint/region

## Guardrails to Keep It Fixed

### CI Tests (Normative)

**Required Test Coverage**:
1. **ALS Presence**: Reject if ALS isn't present between system/user on ANY runtime path
2. **Length Enforcement**: Enforce ALS ≤350 (NFC count)
3. **Mode Behavior**: Ensure three modes behave per spec with distinct outputs
4. **Neon Parity**: CI + invariant tests stay green after changes
   - Numbers normalization
   - Output hashing
   - Two-step Gemini attestation

### No Silent Fallbacks Policy

**Vertex**:
- Fail fast on ADC/roles/location problems
- Include remediation snippet in error

**OpenAI Grounded**:
- REQUIRED: Fail-closed if no `web_search` evidence
- AUTO: May skip search but MUST record that fact

## Implementation Checklist

- [ ] Fix UnifiedLLMAdapter to always apply ALS
- [ ] Add ALS metadata persistence to database schema
- [ ] Remove Vertex model hard-coding
- [ ] Update test harness to use public execution path
- [ ] Add telemetry fields for ALS tracking
- [ ] Implement payload spot-check validation
- [ ] Create CI tests for ALS enforcement
- [ ] Document no-silent-fallback policy
- [ ] Add acceptance tests for 350-char rule
- [ ] Verify deterministic rotation semantics

## Current Code Locations

### Files Requiring Changes
1. **app/llm/unified_llm_adapter.py**
   - Line 65-75: ALS application logic (currently conditional)
   - Line 168-210: `_apply_als()` method

2. **app/llm/adapters/vertex_adapter.py**
   - Lines with `gemini-2.5-pro` hard-coding

3. **Test files**
   - All tests calling adapters directly instead of through orchestrator

4. **Database schema**
   - Add ALS provenance fields to runs table

## Next Steps

1. **Immediate**: Run validation tests to confirm current state
2. **Priority 1**: Fix ALS application in UnifiedLLMAdapter
3. **Priority 2**: Add database persistence for ALS metadata
4. **Priority 3**: Fix test architecture to use public path
5. **Priority 4**: Remove model pinning overrides
6. **Priority 5**: Add comprehensive CI guards

---

*Analysis Date: August 29, 2025*
*Status: Issues identified, fixes planned*
*Next Review: After Step 1-2 implementation*