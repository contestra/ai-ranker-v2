# PR DoD — ALS Restored, Pins Respected, Telemetry Complete

## A) Behavior (Spec-Correct)

- [ ] **ALS is applied in the orchestrator for every run** (single place), not in adapters or BatchRunner; message order is **system → ALS → user**. No duplicate insertion.

- [ ] **ALS block is spec-valid:** NFC-counted length ≤ **350**; if over, request fails with a specific `ALS_BLOCK_TOO_LONG` error (no truncation).

- [ ] **ALS provenance is persisted per run:** `als_block_text`, `als_block_sha256`, `als_variant_id`, `seed_key_id`, and determinism tier stored exactly as defined.

- [ ] **Model pins are respected:** no silent rewrite to a single Vertex model. Router + adapters either pass through the requested/pinned model or fail fast with remediation (no Direct Gemini API).

- [ ] **Three evaluation modes behave exactly as defined:**
  - [ ] **UNGROUNDED (ALS-only):** no tools; ALS present.
  - [ ] **GROUNDED (Preferred/auto):** tools attached; zero tool calls are allowed and logged.
  - [ ] **GROUNDED (Required/forced):** OpenAI uses `tool_choice:"required"`; Vertex must show non-empty grounding metadata; otherwise **fail-closed** with reason.

- [ ] **Gemini two-step policy held:** if strict JSON + grounding, Step-1 = grounded prose; Step-2 = JSON reshape **with no tools**, and attestation fields captured.

## B) Routing, Normalization, and Pins

- [ ] **Vendor inference is robust** after normalization (recognizes full OpenAI and full Vertex publisher IDs). No false "unknown vendor" paths.

- [ ] **No hard-coded Vertex model** in orchestrator or adapter; allowed models come from config/allowlist; disallowed models error with remediation text.

## C) Telemetry / Run Record (Neon SOR, BQ-Ready)

Each run emits one normalized record with:

### Core Fields:
- [ ] `vendor`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `success/error`

### ALS Fields:
- [ ] `als_present`
- [ ] `als_block_sha256`
- [ ] `als_variant_id`
- [ ] `seed_key_id`
- [ ] `als_country`
- [ ] NFC length (optional)

### Grounding Fields:
- [ ] `grounding_mode_requested`
- [ ] `grounded_effective`
- [ ] `tool_call_count`
- [ ] `why_not_grounded`
- [ ] `response_api` (`responses_http`, `vertex_v1`, etc.)

### Gemini Two-Step Attestation (when applicable):
- [ ] `step2_tools_invoked=false`
- [ ] `step2_source_ref=sha256(step1_text)`

### Proxy/Vantage Normalization:
- [ ] If proxies were disabled or policy mutated, record `vantage_policy_before/after` (or a boolean `proxies_normalized`). (Keeps analytics honest.)

## D) Tests (Acceptance)

Run these via the **public orchestrator path** (or HTTP endpoint), not by calling adapters directly:

### 1. ALS Presence & Length
- [ ] For UNGROUNDED run, assert provider payload is `system, ALS, user`
- [ ] Assert ALS NFC length ≤ 350
- [ ] If >350, assert specific error

### 2. ALS Provenance
- [ ] Assert run record contains `als_block_text` (or stored elsewhere but persisted)
- [ ] Assert `als_block_sha256` present
- [ ] Assert `als_variant_id` present
- [ ] Assert `seed_key_id` present

### 3. Mode Separation
- [ ] **Preferred**: allow zero tool calls; `grounded_effective=false`
- [ ] **Required**: zero tool calls → fail-closed with `why_not_grounded`

### 4. Model Pin Respect
- [ ] Template pinned to non-default Vertex model runs **without** silent rewrite
- [ ] Or errors with remediation if disallowed

### 5. Gemini Two-Step
- [ ] For grounded JSON, assert Step-2 had **no tools**
- [ ] Attestation fields are persisted

### 6. Telemetry Parity
- [ ] One row per call
- [ ] ALS + grounding fields present
- [ ] Numeric token fields populated
- [ ] `response_api` set

### 7. Neon Parity / Invariants (Spot)
- [ ] Numeric normalization rules unchanged
- [ ] Output hashing rules unchanged
- [ ] Hashes stable for same inputs

## E) Guardrails (CI)

- [ ] Fails if **ALS missing** between system and user on any runtime path (simple payload grep in test doubles)

- [ ] Fails if **Direct Gemini API** is referenced or if any silent model rewrite occurs

- [ ] Keeps the "**no silent fallbacks**" stance:
  - [ ] Vertex auth issues surface with remediation
  - [ ] OpenAI REQUIRED without search fails-closed

---

# Remediation Text Snippets

## Vertex Model Not Allowed
```
MODEL_NOT_ALLOWED: The model '{requested_model}' is not in the allowed set.

Allowed models:
- publishers/google/models/gemini-2.5-pro
- publishers/google/models/gemini-2.0-flash

To use a different model:
1. Update ALLOWED_VERTEX_MODELS environment variable
2. Or contact admin to add model to allowlist

Note: Direct Gemini API is not supported. All Gemini models must be accessed via Vertex AI.
```

## Vertex Authentication Failed
```
VERTEX_AUTH_ERROR: Failed to authenticate with Vertex AI.

To fix:
1. Ensure Application Default Credentials are configured:
   $ gcloud auth application-default login

2. Verify project and location:
   $ export VERTEX_PROJECT_ID=your-project-id
   $ export VERTEX_LOCATION=us-central1

3. Check service account permissions:
   - Requires: Vertex AI User role
   - Project: {project_id}

For service accounts:
$ export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

Documentation: https://cloud.google.com/vertex-ai/docs/start/client-libraries
```

## ALS Block Too Long
```
ALS_BLOCK_TOO_LONG: ALS block exceeds 350 character limit.

Current length: {actual_length} characters (NFC normalized)
Maximum allowed: 350 characters

The ALS block cannot be truncated as per immutability requirements.

To fix:
1. Reduce ALS content in template configuration
2. Check ALSBuilder.build_als_block() parameters
3. Verify include_weather and other flags

ALS content that was rejected:
{als_block_preview}...
```

## Grounding Required But Not Available
```
GROUNDING_REQUIRED_FAILED: Grounding was required but could not be performed.

Vendor: {vendor}
Model: {model}
Reason: {why_not_grounded}

For OpenAI:
- web_search tool is not yet available in Responses API
- Consider using GROUNDED_AUTO mode which allows fallback

For Vertex:
- Ensure google_search tool is properly configured
- Check project has Search API enabled
- Verify grounding configuration in request

Current configuration:
- Mode: GROUNDED_REQUIRED
- Tool choice: required
- Tools available: {available_tools}
```

## Unknown Vendor for Model
```
UNKNOWN_VENDOR: Cannot determine vendor for model '{model}'.

Recognized patterns:
- OpenAI: gpt-5, gpt-5-chat-latest
- Vertex: gemini-*, publishers/google/models/*

To fix:
1. Specify vendor explicitly in request:
   {"vendor": "openai", "model": "{model}"}

2. Use a recognized model name:
   - OpenAI: "gpt-5"
   - Vertex: "gemini-2.5-pro"

3. Update model normalization in app/llm/models.py
```

---

# PR Description Template

```markdown
## Summary
Restores spec-correct ALS application, respects model pins, and completes telemetry implementation per PRD requirements.

## Changes
- Fixed ALS application to occur once in orchestrator (not BatchRunner)
- Added complete ALS provenance fields (sha256, variant_id, seed_key_id)
- Enforced 350 NFC character limit with fail-closed behavior
- Removed Vertex model hard-pinning, now uses configurable allowlist
- Enhanced telemetry with ALS and grounding metadata
- Fixed vendor inference to occur after model normalization

## Testing
- [x] All acceptance tests pass via public orchestrator path
- [x] ALS presence validated in payload spot-checks
- [x] Database rows contain complete metadata
- [x] Model pin tests show proper validation
- [x] Three grounding modes behave distinctly

## Definition of Done
See [PR_DEFINITION_OF_DONE.md](./PR_DEFINITION_OF_DONE.md) for complete checklist.

## Breaking Changes
None - all changes are backward compatible.

## Deployment Notes
1. Update environment variables for allowed models
2. No database migration required (uses JSON meta field)
3. Monitor telemetry for ALS effectiveness

## Related Issues
- Fixes: ALS not being applied consistently
- Fixes: Model pins being silently overridden
- Fixes: Incomplete telemetry data
```

---

*Last Updated: August 29, 2025*
*Ready for PR submission*