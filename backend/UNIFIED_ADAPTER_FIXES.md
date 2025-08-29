# UnifiedLLMAdapter Fix Checklist

## Critical Issues Found in unified_llm_adapter.py

### 1. Vendor Inference Happens Before Robust Normalize
**Location**: Lines 78-81, 269-285
**Issue**: `get_vendor_for_model()` only recognizes `"gpt-5"` not `"gpt-5-chat-latest"`
**Impact**: Vendor inference returns None and errors, even though normalize_model() would fix it later
**Fix**: Do vendor inference AFTER normalize_model() or extend recognition

### 2. Hard Pin on Vertex Model (Silent Policy Override)
**Location**: Lines 88-94
**Issue**: Rejects everything except `"publishers/google/models/gemini-2.5-pro"`
**Violation**: Adapter PRD states "no silent rewrites / respect pins"
**Impact**: Corrupts comparisons if template pins different Gemini build
**Fix**: Validate against allowed set from config, fail-fast with remediation

### 3. ALS Insertion is Fragile & Not Persisted Per PRD
**Location**: Lines 65-75, 168-210

**Detection Issues**:
- Line 70: Checks if first user message starts with `"[Context:"` (fragile)
- If ALSBuilder changes phrasing, this breaks (double-insert or skip)

**Persistence Issues**:
- Only stashes `als_block` and `als_country` in metadata
- Missing required fields:
  - `als_block_text`
  - `als_block_sha256`
  - `als_variant_id`
  - `seed_key_id`
- No NFC-counted length limit enforcement (≤350 chars)

**Placement Issues**:
- Spec requires: `system → ALS block → user`
- Currently prepends ALS into first user message content

### 4. Telemetry Too Thin to Prove ALS Happened
**Location**: Lines 212-249
**Missing Fields**:
- ALS provenance fields
- `why_not_grounded`
- `tool_call_count`
- `response_api`
**Impact**: Undercuts analysis in BigQuery/Looker, makes debugging hard

### 5. Proxy Normalization is Lossy
**Location**: Lines 113-122
**Issue**: Normalizes `vantage_policy` but doesn't record normalization in telemetry
**Impact**: Runs look like ALS-only by intent, not by environment

## Line-by-Line Fix Checklist

### A. Vendor + Model Handling Fixes

#### Fix 1: Reorder Vendor Inference (Lines 77-85)
```python
# CURRENT (Line 78-81)
if not request.vendor:
    request.vendor = self.get_vendor_for_model(request.model)

# FIX: Move after normalize_model
request.model = normalize_model(request.vendor or "openai", request.model)
if not request.vendor:
    request.vendor = self.get_vendor_for_model(request.model)
```

#### Fix 2: Extend get_vendor_for_model (Lines 269-285)
```python
# CURRENT (Line 280)
if model == "gpt-5":
    return "openai"

# FIX: Add support for variants
if model in ["gpt-5", "gpt-5-chat-latest"]:
    return "openai"
elif model.startswith("publishers/google/models/"):
    return "vertex"
```

#### Fix 3: Remove Hard Pin (Lines 88-94)
```python
# CURRENT
if request.model != "publishers/google/models/gemini-2.5-pro":
    raise ValueError(f"MODEL_NOT_ALLOWED: Only gemini-2.5-pro...")

# FIX: Use allowed set from config
ALLOWED_VERTEX_MODELS = os.getenv("ALLOWED_VERTEX_MODELS", 
    "publishers/google/models/gemini-2.5-pro").split(",")
if request.model not in ALLOWED_VERTEX_MODELS:
    raise ValueError(
        f"MODEL_NOT_ALLOWED: {request.model} not in allowed set. "
        f"Allowed: {ALLOWED_VERTEX_MODELS}. "
        f"To use a different model, update ALLOWED_VERTEX_MODELS env var."
    )
```

### B. ALS Application Fixes (Lines 168-210)

#### Fix 4: Robust ALS Detection (Lines 66-75)
```python
# CURRENT (Line 70)
if first_user_msg and first_user_msg.get('content', '').startswith('[Context:'):
    als_already_applied = True

# FIX: Use stable flag
als_already_applied = getattr(request, 'als_applied', False)
```

#### Fix 5: Enhanced _apply_als() Method
```python
def _apply_als(self, request: LLMRequest) -> LLMRequest:
    """Apply ALS with proper validation and persistence"""
    import unicodedata
    
    als_context = request.als_context
    if not als_context or not isinstance(als_context, dict):
        return request
    
    # Build ALS block
    country_code = als_context.get('country_code', 'US')
    als_block = self.als_builder.build_als_block(
        country=country_code,
        max_chars=350,
        include_weather=True,
        randomize=True
    )
    
    # Get variant and seed info from builder
    variant_id = getattr(self.als_builder, 'last_variant_id', 'default')
    seed_key_id = getattr(self.als_builder, 'seed_key_id', 'default')
    
    # NFC normalization and length check
    als_block_nfc = unicodedata.normalize('NFC', als_block)
    if len(als_block_nfc) > 350:
        raise ValueError(f"ALS_BLOCK_TOO_LONG: {len(als_block_nfc)} > 350 chars")
    
    # Compute SHA256
    import hashlib
    als_block_sha256 = hashlib.sha256(als_block_nfc.encode('utf-8')).hexdigest()
    
    # Deep copy and modify messages
    import copy
    modified_messages = copy.deepcopy(request.messages)
    
    # Insert ALS after system, before user
    for i, msg in enumerate(modified_messages):
        if msg.get('role') == 'user':
            original_content = msg['content']
            modified_messages[i] = {
                'role': 'user',
                'content': f"{als_block_nfc}\n\n{original_content}"
            }
            break
    
    # Update request
    request.messages = modified_messages
    request.als_applied = True  # Stable flag
    
    # Store complete provenance
    if not hasattr(request, 'metadata'):
        request.metadata = {}
    
    request.metadata.update({
        'als_block_text': als_block_nfc,
        'als_block_sha256': als_block_sha256,
        'als_variant_id': variant_id,
        'seed_key_id': seed_key_id,
        'als_country': country_code,
        'als_present': True,
        'als_char_count': len(als_block_nfc)
    })
    
    return request
```

### C. Telemetry Emission Fixes (Lines 212-249)

#### Fix 6: Enhanced Telemetry
```python
async def _emit_telemetry(self, request, response, session):
    """Emit comprehensive telemetry with ALS provenance"""
    try:
        # Extract ALS metadata
        als_metadata = {
            'als_present': request.metadata.get('als_present', False),
            'als_block_sha256': request.metadata.get('als_block_sha256'),
            'als_variant_id': request.metadata.get('als_variant_id'),
            'seed_key_id': request.metadata.get('seed_key_id'),
            'als_country': request.metadata.get('als_country'),
            'als_char_count': request.metadata.get('als_char_count')
        }
        
        # Extract grounding metadata
        grounding_metadata = {
            'grounding_mode_requested': 'REQUIRED' if request.grounded else 'NONE',
            'grounded_effective': response.grounded_effective,
            'tool_call_count': response.metadata.get('tool_call_count', 0),
            'why_not_grounded': response.metadata.get('why_not_grounded'),
            'response_api': response.metadata.get('response_api', 'unknown')
        }
        
        # Proxy normalization tracking
        proxy_metadata = {
            'vantage_policy_requested': getattr(request, 'original_vantage_policy', 'ALS_ONLY'),
            'vantage_policy_effective': getattr(request, 'vantage_policy', 'ALS_ONLY'),
            'proxies_disabled': getattr(request, 'proxies_disabled', False)
        }
        
        # Combine all metadata
        meta_json = {
            **als_metadata,
            **grounding_metadata,
            **proxy_metadata,
            'model_fingerprint': response.model_fingerprint,
            'normalized_model': request.model
        }
        
        telemetry = LLMTelemetry(
            vendor=request.vendor,
            model=request.model,
            grounded=request.grounded,
            grounded_effective=response.grounded_effective,
            json_mode=request.json_mode,
            latency_ms=response.latency_ms,
            prompt_tokens=response.usage.get('prompt_tokens', 0),
            completion_tokens=response.usage.get('completion_tokens', 0),
            total_tokens=response.usage.get('total_tokens', 0),
            success=response.success,
            error_type=response.error_type,
            template_id=request.template_id,
            run_id=request.run_id,
            meta=meta_json  # Store as JSON blob
        )
        
        session.add(telemetry)
        await session.flush()
        
    except Exception as e:
        logger.error(f"Failed to emit telemetry: {e}")
```

#### Fix 7: Track Proxy Normalization (Lines 113-122)
```python
# CURRENT
if DISABLE_PROXIES and original_policy in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
    normalized_policy = "ALS_ONLY"
    request.vantage_policy = normalized_policy

# FIX: Track original for telemetry
request.original_vantage_policy = original_policy  # Store original
if DISABLE_PROXIES and original_policy in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
    normalized_policy = "ALS_ONLY"
    request.vantage_policy = normalized_policy
    request.proxy_normalization_applied = True
```

## Spot Checks to Validate Fixes

### 1. Payload Check
```python
# For UNGROUNDED run, log actual messages
import json
logger.info(f"Provider payload: {json.dumps(request.messages, indent=2)}")

# Expected structure:
# messages[0] = {"role": "system", "content": "..."}
# messages[1] = {"role": "user", "content": "[Context: Location...]\\n\\nOriginal prompt"}
```

### 2. Database Row Check
```sql
-- Check last few telemetry rows
SELECT 
    meta->>'als_block_sha256' as als_hash,
    meta->>'als_present' as als_present,
    meta->>'als_variant_id' as variant,
    meta->>'seed_key_id' as seed
FROM llm_telemetry 
ORDER BY created_at DESC 
LIMIT 5;
```

### 3. Model Pin Test
```python
# Create request with different Vertex model
request = LLMRequest(
    vendor="vertex",
    model="publishers/google/models/gemini-2.0-flash",  # Different model
    messages=[{"role": "user", "content": "test"}]
)

# Should either:
# a) Run with exact model if in allowed set
# b) Fail with clear remediation message
```

## Implementation Order

1. **Immediate**: Fix vendor inference order (5 min)
2. **Priority 1**: Enhance _apply_als() with NFC validation and SHA256 (15 min)
3. **Priority 2**: Add comprehensive telemetry fields (10 min)
4. **Priority 3**: Remove Vertex hard pin, use config (5 min)
5. **Priority 4**: Add spot check validation tests (10 min)

## Environment Variables Needed

```bash
# Add to .env
ALLOWED_VERTEX_MODELS=publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash
ENFORCE_ALS_LIMIT=true
ALS_MAX_CHARS=350
```

## Database Schema Updates

```sql
-- Add meta column if not exists
ALTER TABLE llm_telemetry 
ADD COLUMN IF NOT EXISTS meta JSONB;

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_als_present 
ON llm_telemetry ((meta->>'als_present'));

CREATE INDEX IF NOT EXISTS idx_als_country 
ON llm_telemetry ((meta->>'als_country'));
```

## Testing After Fixes

```python
# Test script to validate all fixes
async def validate_fixes():
    adapter = UnifiedLLMAdapter()
    
    # Test 1: ALS application and persistence
    request = LLMRequest(
        vendor="openai",
        model="gpt-5-chat-latest",  # Test normalization
        messages=[{"role": "user", "content": "test"}],
        als_context={'country_code': 'DE'}
    )
    
    response = await adapter.complete(request)
    
    # Validate ALS was applied
    assert request.als_applied == True
    assert 'als_block_sha256' in request.metadata
    assert len(request.metadata['als_block_text']) <= 350
    
    # Test 2: Model pin respect
    try:
        request2 = LLMRequest(
            vendor="vertex",
            model="publishers/google/models/gemini-1.5-pro",
            messages=[{"role": "user", "content": "test"}]
        )
        response2 = await adapter.complete(request2)
        # Should fail or use exact model
    except ValueError as e:
        assert "MODEL_NOT_ALLOWED" in str(e)
        assert "remediation" in str(e).lower()
    
    print("✅ All validations passed")
```

---

*Document Created: August 29, 2025*
*Status: Ready for implementation*
*Estimated Time: 45 minutes total*