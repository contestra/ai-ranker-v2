# ALS Determinism Fix - Surgical Patch

## Problem Identified
ALS blocks were non-deterministic between runs for the same country/locale, violating the immutability PRD requirement.

## Root Causes Found

1. **Random variant selection**: `random.randint()` used without seeding
2. **Random timezone selection**: US has 4 timezones, randomly chosen
3. **Live timestamps**: `datetime.now()` generating current dates

## Fixes Applied

### 1. Deterministic Variant Selection
```python
# Before: randomize=True with random.randint()
# After: HMAC-based deterministic selection
seed_data = f"{seed_key_id}:{template_id}:{country_code}".encode('utf-8')
hmac_hash = hmac.new(b'als_secret_key', seed_data, hashlib.sha256).hexdigest()
variant_idx = int(hmac_hash[:8], 16) % num_variants
```

### 2. Deterministic Timezone Selection
```python
# For multi-timezone countries (US), use HMAC to pick consistent timezone
if tpl.timezone_samples:
    tz_idx = int(hmac_hash[8:12], 16) % len(tpl.timezone_samples)
    tz_override = tpl.timezone_samples[tz_idx]
```

### 3. Fixed Date Instead of Live Time
```python
# Use regulatory-neutral placeholder date
fixed_date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo('UTC'))
als_block = ALSTemplates.render_block(
    code=country_code,
    phrase_idx=variant_idx,
    now=fixed_date,  # No more datetime.now()
    tz_override=tz_override
)
```

### 4. Complete Provenance Tracking
```python
request.metadata.update({
    'als_block_text': als_block_nfc,  # Exact text inserted
    'als_block_sha256': als_block_sha256,  # SHA256 of NFC text
    'als_variant_id': f'variant_{variant_idx}',
    'seed_key_id': 'v1_2025',
    'als_template_id': f'als_template_{country_code}'
})
```

## Test Results

### Before Fix
- US: 3 different SHA256s across 5 runs ❌
- DE: Deterministic ✅
- GB: Deterministic ✅
- FR: Deterministic ✅

### After Fix
- US: Same SHA256 across 5 runs ✅
- DE: Same SHA256 across 5 runs ✅
- GB: Same SHA256 across 5 runs ✅
- FR: Same SHA256 across 5 runs ✅

## Verification

Run `test_als_determinism.py` to verify:
```bash
venv/bin/python test_als_determinism.py
```

Expected output:
```
Deterministic: 4/4 configurations
✅ ALL CONFIGURATIONS ARE DETERMINISTIC
```

## ALS Deterministic Builder Contract

The following invariants are now enforced in `_apply_als()`:

1. **Canonicalize locale** - ISO uppercase, consistent region handling
2. **Select variant deterministically** - HMAC(seed_key_id, template_id)
3. **Build without runtime date/time** - Fixed placeholder date
4. **Normalize to NFC** - Unicode normalization before hashing
5. **Enforce ≤350 chars** - Fail-closed, no truncation
6. **Compute SHA256** - Over final NFC text
7. **Persist all fields** - Complete provenance for audit
8. **Insert order** - system → ALS → user

## Impact

- **Caching**: ALS blocks can now be cached by SHA256
- **Audit**: Provenance is complete and verifiable
- **Compliance**: Same context always produces same ALS
- **Testing**: Deterministic fixtures possible

## Note on Timestamps

ALS blocks contain a fixed placeholder date (01/15/2024) which is:
- **Deterministic**: Same date every time
- **Regulatory neutral**: Not current time
- **Intentional**: Provides date format context without implying "now"

This is NOT a live timestamp and is compliant with requirements.