# ALS Fix Summary - Consolidated Requirements & Solutions

## What ALS **MUST** Do (Per Specifications)

### Core Requirements
- **Always applied in orchestrator** (never adapters / BatchRunner only). Exactly once per run:
  `system → ALS block → user`
- **ALS block rules**: NFC-counted length ≤ 350 chars; fail-closed if over; no truncation
- **Persist provenance per run**: `als_block_text`, `als_block_sha256`, `als_variant_id`, `seed_key_id`
- **Analytics**: Telemetry row must include ALS provenance + grounding fields (`grounded_effective`, `tool_call_count`, `why_not_grounded`, `response_api`)
- **Test path**: All tests go via orchestrator/HTTP path so ALS enrichment always executes

---

## What Broke in Current Code

### Issue 1: ALS Moved to Wrong Layer
- **Problem**: ALS moved into BatchRunner
- **Impact**: Direct adapter tests bypass it, so ALS not in payload
- **Violation**: Adapter PRD requirement for single-point application

### Issue 2: Fragile Detection Logic
- **Problem**: Prefix check (`"[Context:"`) is unreliable
- **Impact**: Sometimes double-inserts, sometimes skips
- **Fix Needed**: Stable boolean flag instead of string matching

### Issue 3: Missing Provenance Fields
- **Problem**: Only storing `als_country`/`als_block` in metadata
- **Missing**: SHA256, variant ID, seed key
- **Violation**: Immutability PRD requirements

### Issue 4: Model Pinning Override
- **Problem**: Vertex path hard-coded to `gemini-2.5-pro`
- **Impact**: Ignores template pins
- **Violation**: Adapter PRD's "no silent rewrites" rule

### Issue 5: Incomplete Telemetry
- **Problem**: ALS and grounding signals aren't in Postgres row
- **Impact**: Invisible in BigQuery/Looker analytics
- **Missing Fields**: Complete list in telemetry section below

---

## Fix Plan (Surgical)

### 1. Always Apply ALS in Orchestrator
**Location**: `UnifiedLLMAdapter._apply_als()`

**Actions**:
- Drop the string-prefix check, use internal `als_applied=True` flag
- Insert as distinct ALS block between system and user
- Compute NFC length; if >350, raise `ALS_BLOCK_TOO_LONG`

**Code Changes**:
```python
# Replace fragile check (line 70)
als_already_applied = getattr(request, 'als_applied', False)

# In _apply_als() method
request.als_applied = True  # Set flag after application
```

### 2. Persist Complete Provenance
**Into `request.meta` → propagate to telemetry**

**Required Fields**:
- `als_block_text` - The actual ALS content
- `als_block_sha256` - Hash for immutability
- `als_variant_id` - Which variant was selected
- `seed_key_id` - Seed for deterministic selection
- `als_country` - Country code used

**Implementation**:
```python
import hashlib
import unicodedata

# NFC normalization
als_block_nfc = unicodedata.normalize('NFC', als_block)

# Length check
if len(als_block_nfc) > 350:
    raise ValueError(f"ALS_BLOCK_TOO_LONG: {len(als_block_nfc)} > 350")

# SHA256
als_block_sha256 = hashlib.sha256(als_block_nfc.encode()).hexdigest()

# Store all fields
request.metadata.update({
    'als_block_text': als_block_nfc,
    'als_block_sha256': als_block_sha256,
    'als_variant_id': variant_id,
    'seed_key_id': seed_key_id,
    'als_country': country_code
})
```

### 3. Complete Telemetry Row
**Add to telemetry emission**:

**ALS Fields**:
- `als_present`
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`
- `als_country`

**Grounding Fields**:
- `grounded_effective`
- `tool_call_count`
- `why_not_grounded`
- `response_api`

**Proxy Normalization**:
- `vantage_policy_before`
- `vantage_policy_after`
- `proxies_normalized`

### 4. Respect Model Pins
**Remove hard-coded Gemini model**

**Current Problem** (lines 88-94):
```python
# WRONG - Silent override
if request.model != "publishers/google/models/gemini-2.5-pro":
    raise ValueError("Only gemini-2.5-pro supported")
```

**Fix**:
```python
# RIGHT - Configurable allowlist
ALLOWED_MODELS = get_allowed_models_from_config()
if request.model not in ALLOWED_MODELS:
    raise ValueError(
        f"MODEL_NOT_ALLOWED: {request.model}. "
        f"Allowed: {ALLOWED_MODELS}. "
        f"Update ALLOWED_VERTEX_MODELS env var."
    )
# Pass through the requested model
```

### 5. Fix Test Harness
**Stop adapter-only tests**

**Wrong**:
```python
# Direct adapter call - bypasses ALS
adapter = OpenAIAdapter()
response = await adapter.complete(request)
```

**Right**:
```python
# Through orchestrator - includes ALS
runner = BatchRunner()  # or UnifiedLLMAdapter
response = await runner.process(request)
```

---

## Quick Acceptance Checks

### Check 1: Payload Dump (UNGROUNDED run)
**Test**: Log actual provider payload
**Expected**: Should literally show:
1. System message
2. ALS block (≤350 chars, starts with "[Context:")
3. User message

**Validation Code**:
```python
import json
logger.info(f"Payload: {json.dumps(request.messages, indent=2)}")
# Verify ALS is between system and user
```

### Check 2: Run Row Validation
**Query**: Check database row
**Must have non-null**:
- `als_block_sha256`
- `als_variant_id`
- `seed_key_id`

**SQL**:
```sql
SELECT 
    meta->>'als_block_sha256',
    meta->>'als_variant_id',
    meta->>'seed_key_id'
FROM llm_telemetry
WHERE created_at > NOW() - INTERVAL '1 hour'
AND meta->>'als_block_sha256' IS NOT NULL;
```

### Check 3: ALS Over-Limit Test
**Test**: Send ALS >350 chars
**Expected**: Must error `ALS_BLOCK_TOO_LONG`

**Test Code**:
```python
# Create oversized ALS
long_als = "x" * 351
request.als_context = {'country_code': 'US', 'override_text': long_als}

# Should raise
with pytest.raises(ValueError, match="ALS_BLOCK_TOO_LONG"):
    await adapter.complete(request)
```

### Check 4: Model Pin Test
**Test**: Run pinned to non-2.5 Gemini model
**Expected**: Must either:
- (a) Respect it (if in allowlist)
- (b) Fail-fast with remediation

**Test Code**:
```python
request = LLMRequest(
    vendor="vertex",
    model="publishers/google/models/gemini-1.5-pro",  # Different
    messages=[...]
)

# Should not silently rewrite to 2.5-pro
response = await runner.process(request)
assert response.model == request.model  # Or proper error
```

### Check 5: Telemetry Completeness
**Query**: Verify row includes all fields
**Check for**:
- ALS provenance fields
- Grounding metrics
- Response API field

**SQL**:
```sql
SELECT 
    meta->>'als_present',
    meta->>'grounded_effective',
    meta->>'tool_call_count',
    meta->>'response_api'
FROM llm_telemetry
ORDER BY created_at DESC
LIMIT 1;
```

---

## Files Requiring Changes

### Primary Files
1. **unified_llm_adapter.py**
   - Lines 66-75: Fix ALS detection
   - Lines 88-94: Remove model hard-coding
   - Lines 168-210: Enhance _apply_als()
   - Lines 212-249: Complete telemetry

2. **openai_adapter.py**
   - Verify ALS survives message splitting
   - Ensure synthesis includes evidence

3. **vertex_adapter.py**
   - Remove GEMINI_MODEL hard-coding
   - Pass through requested model

### Test Files
- All test files using direct adapter calls
- Update to use orchestrator path

### Configuration
- Add `ALLOWED_VERTEX_MODELS` env var
- Add `ALS_MAX_CHARS=350` env var

---

## Success Criteria

### Immediate Success
- [ ] Payload contains ALS in correct position
- [ ] Database has complete provenance
- [ ] Over-limit ALS properly rejected
- [ ] Model pins respected
- [ ] Telemetry row complete

### Long-term Success
- [ ] BigQuery analytics show ALS effectiveness
- [ ] Regional differences measurable
- [ ] No silent model rewrites
- [ ] Immutability guarantees met
- [ ] Test coverage through orchestrator

---

## Anti-Patterns to Avoid

### DON'T
- ❌ Apply ALS in adapters
- ❌ Apply ALS in BatchRunner only
- ❌ Use string prefix for detection
- ❌ Silently truncate ALS
- ❌ Hard-code model names
- ❌ Test adapters directly
- ❌ Skip provenance fields

### DO
- ✅ Apply ALS once in orchestrator
- ✅ Use boolean flag for tracking
- ✅ Fail on over-limit ALS
- ✅ Persist complete provenance
- ✅ Use configurable allowlists
- ✅ Test through public path
- ✅ Include all telemetry fields

---

*Summary Created: August 29, 2025*
*Status: Ready for implementation*
*Estimated Time: 45-60 minutes*
*Review Required: Yes*