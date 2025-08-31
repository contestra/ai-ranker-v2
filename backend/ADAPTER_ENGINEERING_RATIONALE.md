# Adapter Engineering Rationale

## Why Custom Adapters Were Required

This document explains why off-the-shelf SDKs were insufficient and why Contestra built custom adapters for OpenAI and Google Vertex.

## Executive Summary

Public SDKs and wrappers:
- **Hide failures** by silently skipping unsupported features
- Don't **fail closed** when grounding is required
- Don't normalize outputs for cross-provider analytics
- Don't enforce **immutability, determinism, or attestation** rules

Custom adapters ensure:
- **Consistent modes** (Ungrounded, Auto, Required) with enforceable semantics
- **Fail-closed correctness**: no false positives when grounding is missing
- **Two-step JSON compliance** on Gemini
- **Authority scoring** from resolved domains, not redirects
- **Immutable provenance**: ALS propagation, hashes, attestation

## Provider-Specific Issues & Solutions

### 🔴 OpenAI (GPT-5 Responses API)

#### Issues Encountered
1. **Inconsistent tool support**: Some accounts/models accepted `web_search`, others only `web_search_preview`. Unsupported types caused 400-errors.

2. **AUTO rarely grounded**: Even with tools attached, GPT-5 almost never invoked search in AUTO mode.

3. **REQUIRED not enforced**: The API didn't guarantee a search call, even with `tool_choice:"required"`.

4. **Usage reporting messy**: Token counts nested under varying keys (`input_tokens_details`, `reasoning_tokens`).

#### Engineering Solutions
- Built **adaptive chooser + retry**: try preview vs full tool, retry once, then fail-closed if unsupported
- Implemented **fail-closed REQUIRED mode**: if no tool call detected, raise `GROUNDING_REQUIRED_ERROR`
- Added **reasoning-only detection + retries**: if output lacked text, retry with "plain text only" instructions
- **Flattened usage objects**: standardized token reporting for consistent analytics

### 🔴 Google Vertex (Gemini via Vertex AI)

#### Issues Encountered
1. **JSON + grounding incompatibility**: Gemini cannot ground and produce strict JSON in the same step.

2. **Scattered grounding metadata**: Evidence appeared as `grounding_attributions`, `grounding_chunks`, `groundingSupports`, or camelCase variants.

3. **Redirect URLs**: Returned `vertexaisearch.cloud.google.com/grounding-api-redirect/...` instead of real domains.

4. **Auth friction**: ADC/Workload Identity Federation errors were opaque (`403 aiplatform.endpoints.predict`).

#### Engineering Solutions
- Created **two-step pipeline**: 
  - Step-1: grounded answer with Google Search
  - Step-2: strict JSON reshape with **no tools**
  - Added attestation (`step2_tools_invoked=false`, `step2_source_ref=sha256`)
- **Normalized metadata extraction**: handles all SDK variants and dict/camelCase keys
- Added **URLResolver**: follows redirects to recover real authority domains
- Implemented **fail-fast auth checks**: clear error messages with remediation

### 🔴 Google-genai Client (new Vertex API surface)

#### Issues Encountered
1. **Tool config mismatch**: API accepted `"AUTO"` and `"ANY"`, but not `"REQUIRED"`. Code sending `"REQUIRED"` silently broke enforcement.

2. **Inconsistent response shapes**: `model_dump()` sometimes returned camelCase instead of snake_case; evidence nested under `web`/`reference`.

3. **Initialization quirks**: Client required `vertexai=True` plus explicit `project` and `location`. Wrong settings silently defaulted to "global" or hung.

4. **Step-2 enforcement not obvious**: Without explicitly passing `tools=[]`, Step-2 could still allow tool calls, violating PRD rules.

#### Engineering Solutions
- Added **mode mapping layer**: Contestra's `AUTO` → `"AUTO"`, `REQUIRED` → `"ANY"`
- Built **robust normalizers**: citation extraction checks both camelCase/snake_case and digs into nested structures
- Hardened **client initialization**: force `vertexai=True`, always inject project+location, log SDK versions
- Enforced **Step-2 purity**: explicitly send `tools=[]` and assert attestation

### 🔴 Cross-cutting Problems

#### Issues Encountered
1. **Empty or noisy responses**: Providers sometimes returned reasoning blocks without user-visible text.

2. **Different evidence definitions**: OpenAI evidence = tool calls; Vertex evidence = grounding metadata.

3. **No immutability guarantees**: Neither provider enforced ALS insertion, ≤350-char limit, or deterministic hashing.

#### Engineering Solutions
- Added **multi-path text extraction + retries** to recover plain content
- Unified evidence into single `grounded_effective` flag for analytics
- Router enforces **ALS determinism**: injects ≤350 NFC-normalized chars, computes `als_block_sha256`, persists provenance

## Key Adapter Features

### 1. Fail-Closed Behavior
- REQUIRED mode must ground or error (never silent fallback)
- Empty responses trigger retries with stricter instructions
- Auth failures provide clear remediation steps

### 2. Evidence Normalization
- Unified `grounded_effective` flag across providers
- Recursive citation extraction from various field names
- Authority scoring on resolved domains

### 3. Immutability Guarantees
- Two-step attestation for JSON+grounded
- ALS deterministic hashing and length enforcement
- Source reference SHA256 for audit trails

### 4. Telemetry Consistency
- Flattened usage reporting
- Normalized metadata fields
- Consistent error classification

## Current Known Limitations

### OpenAI
- **AUTO mode rarely grounds** (appears to be model behavior, not adapter issue)
- Some models don't support any web_search variant
- REQUIRED mode correctly fails with GROUNDING_NOT_SUPPORTED

### Vertex
- All citations show as redirect URLs (authority scores affected)
- Empty responses still occur for some ungrounded requests
- Regional availability affects google-genai vs vertexai SDK selection

## Testing & Validation

The adapters include comprehensive tests for:
- Fail-closed REQUIRED mode behavior
- ALS propagation and determinism
- Authority scoring accuracy
- Two-step attestation presence
- Grounding mode telemetry accuracy

## Maintenance Notes

When updating adapters:
1. Always test both AUTO and REQUIRED modes
2. Verify fail-closed behavior (no silent fallbacks)
3. Check attestation fields for two-step flows
4. Ensure ALS propagation through router hardening
5. Validate authority scoring with real citations

## References

- Original issues documented: 2025-08-31
- Adapter implementation: Phase-0 spec compliant
- Testing framework: `test_grounding_gates.py`
- Full test suite: `test_als_grounding_final.py`