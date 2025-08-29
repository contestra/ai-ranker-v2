# PR: Restore Spec-Correct ALS in `unified_llm_adapter.py`

## 1) Entry Point — Ensure ALS Applied Once, Before Routing

**Target:** `UnifiedLLMAdapter.complete(...)`  
**Current Line:** 65-75

**Change:**
- Call `_apply_als(req)` **unconditionally** on every request before vendor routing
- Do **not** rely on any BatchRunner to add ALS. ALS belongs in the orchestrator, *once per run*

**Code Location:**
```python
# Line 65 - CHANGE FROM:
if hasattr(request, 'als_context') and request.als_context and not als_already_applied:

# TO:
if hasattr(request, 'als_context') and request.als_context:
```

**Acceptance:** Provider payloads (for UNGROUNDED tests) show message order **system → ALS → user**

---

## 2) `_apply_als(req)` — Replace Brittle Detection with Internal Flag

**Target:** `_apply_als(req)`  
**Current Lines:** 66-71 (detection logic)

**Replace:**
- ❌ Fragile string checks (e.g., first user message starts with `"[Context:"`)
- ✅ Use request-scoped boolean (e.g., `req.meta["als_applied"]=True`) set the *first* time `_apply_als` runs

**Code Location:**
```python
# Line 66-71 - REPLACE:
als_already_applied = False
if request.messages:
    first_user_msg = next((m for m in request.messages if m.get('role') == 'user'), None)
    if first_user_msg and first_user_msg.get('content', '').startswith('[Context:'):
        als_already_applied = True

# WITH:
als_already_applied = getattr(request, 'als_applied', False)
```

**Spec Backstop:** ALS is applied exactly once in the orchestrator and never in adapters/BatchRunner

---

## 3) Build Distinct ALS Block + Enforce 350-char Rule

**Target:** `_apply_als(req)`  
**Current Lines:** 168-210

**Change:**
- Construct ALS as its **own block** (string) based on ALSBuilder
- Normalize to **NFC**, count characters, and **fail-closed** if > **350** with specific error `ALS_BLOCK_TOO_LONG`
- No truncation allowed
- **Insert order:** system → ALS → user

**Implementation Points:**
```python
# Add to _apply_als() method:
import unicodedata

# NFC normalization
als_block_nfc = unicodedata.normalize('NFC', als_block)

# Length enforcement
if len(als_block_nfc) > 350:
    raise ValueError(f"ALS_BLOCK_TOO_LONG: {len(als_block_nfc)} chars exceeds 350 limit")
```

**Acceptance:** Test with oversized ALS produces 400/`ALS_BLOCK_TOO_LONG` error; nothing silently trimmed

---

## 4) Persist ALS Provenance for Telemetry

**Target:** `_apply_als(req)`  
**Current Lines:** 204-208 (metadata storage)

**Change - Add to `req.metadata`:**
- `als_block_text` (exact text used)
- `als_block_sha256` (hex)
- `als_variant_id`
- `seed_key_id`
- Optional: `als_country`, `als_nfc_length`

**Implementation:**
```python
# Line 204-208 - EXPAND:
import hashlib

als_block_sha256 = hashlib.sha256(als_block_nfc.encode('utf-8')).hexdigest()

request.metadata.update({
    'als_block_text': als_block_nfc,
    'als_block_sha256': als_block_sha256,
    'als_variant_id': getattr(self.als_builder, 'last_variant_id', 'default'),
    'seed_key_id': getattr(self.als_builder, 'seed_key_id', 'default'),
    'als_country': country_code,
    'als_nfc_length': len(als_block_nfc),
    'als_present': True
})
```

**Why:** These are **normative** for immutability & audit. Must be recorded per run.

---

## 5) Insert ALS Between System and User in Messages

**Target:** `_apply_als(req)` message mutation  
**Current Lines:** 189-199

**Change:**
- Find first **system** message; ensure it exists
- Insert ALS block **after system** and **before** first user message
- If provider requires single user string, join `ALS + "\n\n" + user` but keep **raw ALS** separately for provenance

**Current Approach (Keep but enhance):**
```python
# Lines 192-198 - Current prepending is OK if we:
# 1. Store raw ALS separately (done in step 4)
# 2. Set flag to prevent re-application
request.als_applied = True  # Add this flag
```

---

## 6) Telemetry Emission — Include ALS & Grounding Fields

**Target:** `_emit_telemetry(...)`  
**Current Lines:** 212-249

**Change - Ensure single row per call includes:**

### ALS Fields:
- `als_present`
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
- `als_country` (optional)
- `als_nfc_length` (optional)

### Grounding Fields:
- `grounding_mode_requested`
- `grounded_effective`
- `tool_call_count`
- `why_not_grounded`
- `response_api`

### Proxy/Vantage Normalization:
- `vantage_policy_before/after` or `proxies_normalized=true`

**Implementation Location:**
```python
# Line 228-241 - Add meta JSON blob:
meta_json = {
    # ALS fields
    'als_present': request.metadata.get('als_present', False),
    'als_block_sha256': request.metadata.get('als_block_sha256'),
    'als_variant_id': request.metadata.get('als_variant_id'),
    'seed_key_id': request.metadata.get('seed_key_id'),
    
    # Grounding fields
    'grounded_effective': response.grounded_effective,
    'tool_call_count': response.metadata.get('tool_call_count', 0),
    'why_not_grounded': response.metadata.get('why_not_grounded'),
    'response_api': response.metadata.get('response_api'),
    
    # Proxy normalization
    'vantage_policy_requested': getattr(request, 'original_vantage_policy', None),
    'vantage_policy_effective': request.vantage_policy,
    'proxies_normalized': getattr(request, 'proxy_normalization_applied', False)
}
```

**Why:** Analytics schema and runbooks expect these for dashboards and QA

---

## 7) Vendor/Model Handling — No Silent Rewrites

**Target:** Model validation section  
**Current Lines:** 88-101

**Change:**
- **Do not** hard-pin Vertex to single model in orchestrator
- Validate requested model against **configurable allowlist**
- Pass through if allowed, else **fail-fast with remediation text**
- Keep Direct Gemini disabled

**Replace Lines 88-94:**
```python
# FROM:
if request.model != "publishers/google/models/gemini-2.5-pro":
    raise ValueError(f"MODEL_NOT_ALLOWED: Only gemini-2.5-pro...")

# TO:
allowed_models = os.getenv("ALLOWED_VERTEX_MODELS", "...").split(",")
if request.model not in allowed_models:
    raise ValueError(
        f"MODEL_NOT_ALLOWED: {request.model} not in allowed set. "
        f"Allowed: {allowed_models}. "
        f"To use different model, update ALLOWED_VERTEX_MODELS env var."
    )
```

**Also Fix Vendor Inference (Lines 269-285):**
- Make it recognize `gpt-5-chat-latest` and full Vertex publisher IDs
- Or move inference AFTER normalization

**Why:** Spec requires respecting pinned models; no silent rewrites

---

## 8) Don't Let BatchRunner Own ALS

**Target:** Any BatchRunner integration  
**Action:** Remove ALS generation from BatchRunner

**Rule:**
- BatchRunner may **select** locales/variants
- BatchRunner **must not** inject/alter message content
- Orchestrator is single source of ALS application

---

# Smoke Tests to Add (Run via Public Path)

## 1. ALS Presence & Order (UNGROUNDED Lane)
**Test:**
- Run ungrounded request with ALS context
- Dump provider payload

**Assert:**
- Payload contains **system, ALS, user** (or ALS embedded at top of user)
- Row includes `als_block_sha256` & related fields

## 2. ALS Length Fail
**Test:**
- Send forced ALS >350 NFC chars

**Assert:**
- Expect `ALS_BLOCK_TOO_LONG` error
- No truncation occurs

## 3. Mode Separation
**Test Both:**

### Preferred (Auto):
- Tools attached
- Allow zero tool calls
- `grounded_effective=false`

### Required:
- Enforce evidence or fail-closed
- `why_not_grounded` populated
- Telemetry shows `response_api`, counts, reason

## 4. Model Pin Respect (Vertex)
**Test:**
- Template pinned to non-default model

**Assert:**
- Either pass through (if allowed)
- Or fail with remediation
- **No** silent rewrite

## 5. Telemetry Completeness
**Test:**
- Run any request

**Assert:**
- One row per call
- ALS + grounding fields populated
- Tokens & latency present
- `response_api` set

---

# Reviewer Crib Notes (Why These Changes Are Non-Negotiable)

## ALS Architecture
ALS is defined as a **weak prior** applied **once** in the orchestrator, measured cleanly in **Ungrounded (ALS-only)** and kept consistent across grounded modes for fair comparison. 

**Violations Break:**
- **Immutability** story (can't audit what happened)
- **Analytics** story (can't measure effectiveness)

## Model Pinning
Pinned models must be **respected**; silent rewriting to a single Gemini build:
- Invalidates comparisons
- Violates Adapter PRD
- Breaks template expectations

## Testing Path
All tests must go through public orchestrator path because:
- Ensures ALS is applied
- Validates complete flow
- Matches production behavior

---

# Implementation Checklist

## Immediate (5 min each):
- [ ] Fix ALS detection logic (use flag not string)
- [ ] Add als_applied flag setting
- [ ] Store original vantage_policy for tracking

## Core Changes (10-15 min each):
- [ ] Enhance _apply_als() with NFC check and SHA256
- [ ] Add complete provenance fields to metadata
- [ ] Extend telemetry emission with meta JSON
- [ ] Replace Vertex hard-pin with allowlist

## Testing (20 min):
- [ ] Add 5 smoke tests
- [ ] Verify through orchestrator path
- [ ] Check database rows for completeness

## Total Estimated Time: 60-75 minutes

---

# Environment Variables to Add

```bash
# Model allowlists
ALLOWED_VERTEX_MODELS=publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash
ALLOWED_OPENAI_MODELS=gpt-5,gpt-5-chat-latest

# ALS configuration
ALS_MAX_CHARS=350
ENFORCE_ALS_LIMIT=true

# For testing
LOG_PROVIDER_PAYLOADS=true  # To verify ALS presence
```

---

*Checklist Created: August 29, 2025*  
*Target File: unified_llm_adapter.py*  
*Review Required: Yes*  
*Backwards Compatible: Yes*