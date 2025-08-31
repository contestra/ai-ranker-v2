# Grounding Implementation Guide

## Overview
This document describes the complete grounding implementation with authority scoring, ALS propagation, and PRD compliance.

> **Why Custom Adapters?** See [ADAPTER_ENGINEERING_RATIONALE.md](./ADAPTER_ENGINEERING_RATIONALE.md) for detailed explanation of why off-the-shelf SDKs were insufficient and the specific provider issues that required custom engineering solutions.

## Architecture

### 1. Grounding Modes
- **AUTO**: Model decides whether to use grounding tools
- **REQUIRED**: Must ground or fail closed (never returns ungrounded)
- **NONE**: Explicitly disabled (default when grounded=false)

### 2. Provider Implementations

#### OpenAI
- Uses `web_search` or `web_search_preview` tools
- Adaptive tool selection based on model support
- REQUIRED mode sets `tool_choice: "required"`
- Graceful fallback for unsupported models

#### Vertex AI  
- Uses GoogleSearch tool for grounding
- Two SDK paths: google-genai and vertexai
- Mode mapping: REQUIRED → "ANY", AUTO → "AUTO"
- Two-step process for grounded+JSON requests

### 3. ALS (Ambient Location Signals)

#### Flow
1. Request includes `als_context` with country/locale
2. Router applies ALS to messages via `_apply_als()`
3. ALS metadata stored in request.metadata
4. Providers copy ALS to response.metadata
5. Router hardening ensures propagation (failsafe)

#### Metadata Fields
- `als_present`: Boolean flag
- `als_block_sha256`: SHA256 of NFC-normalized text
- `als_country`: Country code (e.g., "US", "DE")
- `als_locale`: Full locale (e.g., "en-US")
- `als_nfc_length`: Character count after normalization
- `als_variant_id`: Which template variant was used
- `als_template_id`: Template identifier

## Authority Scoring

### Domain Tiers
- **Tier 1** (100 points): Premium sources (Reuters, Bloomberg, WSJ, etc.)
- **Tier 2** (70 points): Reputable specialized sources
- **Tier 3** (40 points): General/acceptable sources
- **Tier 4** (0 points): Penalty/low-quality sources

### Metrics
- **Authority Score**: Weighted average (0-100)
- **Tier-1 Percentage**: % of citations from premium sources
- **Premium Percentage**: % from Tier 1+2 combined
- **Penalty Percentage**: % from low-quality sources

### Configuration
Edit `app/llm/domain_authority.py` to modify tier assignments:
```python
TIER_1_DOMAINS = {...}  # Add premium sources
TIER_2_DOMAINS = {...}  # Add good sources
PENALTY_DOMAINS = {...}  # Add sources to penalize
```

## Two-Step Attestation

When `grounded=True` and `json_mode=True`, Vertex uses two-step process:

### Step 1: Grounded generation
- Uses GoogleSearch tool
- Returns natural language with citations

### Step 2: JSON transformation
- NO tools allowed (attestation requirement)
- Transforms Step 1 output to JSON
- Includes attestation metadata:
  - `step2_tools_invoked`: Must be False
  - `step2_source_ref`: SHA256 of Step 1 text

## Environment Variables

### Required
- `OPENAI_API_KEY`: OpenAI API key
- `GOOGLE_CLOUD_PROJECT`: GCP project ID
- `VERTEX_LOCATION`: Vertex AI location (e.g., "europe-west4")

### Optional
- `ALLOWED_OPENAI_MODELS`: Comma-separated list (default: "gpt-5,gpt-5-chat-latest")
- `ALLOWED_VERTEX_MODELS`: Comma-separated list
- `ALLOW_PREVIEW_COMPAT`: Enable web_search_preview fallback (default: "true")
- `USE_GENAI_FOR_VERTEX`: Use google-genai SDK (default: based on region)

## Testing

### Run CI Gates
```bash
pytest tests/test_grounding_gates.py -v
```

### Run Full Test Suite
```bash
python test_als_grounding_final.py
```

### Test Coverage
- ✅ REQUIRED mode fail-closed behavior
- ✅ ALS propagation to response
- ✅ Authority scoring accuracy
- ✅ Grounding mode telemetry
- ✅ Two-step attestation
- ✅ Deterministic ALS generation

## Telemetry Fields

The following fields are included in response.metadata:

### Grounding
- `grounded_effective`: Whether grounding actually occurred
- `grounding_mode_requested`: AUTO/REQUIRED/NONE
- `tool_call_count`: Number of tool invocations
- `citations`: Array of citation objects
- `why_not_grounded`: Reason if grounding failed

### Authority
- `authority_score`: 0-100 score
- `tier_1_percentage`: % premium sources
- `premium_percentage`: % tier 1+2
- `penalty_percentage`: % low-quality

### Two-Step (Vertex only)
- `step2_tools_invoked`: False (attestation)
- `step2_source_ref`: SHA256 of source text

### ALS
- `als_present`: Boolean
- `als_block_sha256`: Hash of ALS text
- `als_country`: Country code
- `als_locale`: Locale string
- `als_nfc_length`: Character count
- `als_mirrored_by_router`: Failsafe flag

## Dashboard Integration

### Recommended UI Elements

#### Grounding Status Pill
```
[Requested: AUTO] [Effective: ✓] [Citations: 5] [Authority: 85/100]
```

#### Authority Breakdown
```
Tier-1: 60% | Premium: 80% | ⚠️ Low-quality: 20%
```

#### ALS Indicator
```
📍 US | en-US | SHA: b190af13...
```

## Monitoring Queries

### Grounding Effectiveness
```sql
SELECT 
    grounding_mode_requested,
    COUNT(*) as total,
    SUM(CASE WHEN grounded_effective THEN 1 ELSE 0 END) as grounded,
    AVG(tool_call_count) as avg_tools,
    AVG((metadata->>'authority_score')::float) as avg_authority
FROM llm_telemetry
WHERE grounded = true
GROUP BY grounding_mode_requested;
```

### Authority Distribution
```sql
SELECT
    vendor,
    AVG((metadata->>'tier_1_percentage')::float) as avg_tier1_pct,
    AVG((metadata->>'authority_score')::float) as avg_authority
FROM llm_telemetry  
WHERE grounded_effective = true
GROUP BY vendor;
```

### ALS Usage
```sql
SELECT
    DATE(created_at) as date,
    COUNT(*) FILTER (WHERE metadata->>'als_present' = 'true') as with_als,
    COUNT(*) FILTER (WHERE metadata->>'als_present' != 'true') as without_als
FROM llm_telemetry
GROUP BY DATE(created_at);
```

## Troubleshooting

### Issue: ALS not showing in response
- Check request.als_context is ALSContext object
- Verify router ALS hardening is before return
- Check response.metadata for als_mirrored_by_router flag

### Issue: OpenAI not grounding in AUTO mode
- **This is expected behavior** - GPT-5 rarely invokes search even with tools attached
- The adapter correctly attaches tools but the model chooses not to use them
- REQUIRED mode correctly fails with GROUNDING_NOT_SUPPORTED
- This is a model limitation, not an adapter bug

### Issue: REQUIRED mode not enforcing
- Verify mode mapping (REQUIRED → "ANY" for SDK)
- Check grounding_mode in request.meta
- Look for GROUNDING_NOT_SUPPORTED errors

### Issue: Low authority scores
- Review domain classifications in domain_authority.py
- Check for redirect URLs (Vertex)
- Verify citation extraction is working

### Issue: Two-step attestation missing
- Only applies when grounded=True AND json_mode=True
- Check for step2_tools_invoked in metadata
- Verify Step 2 has empty tools array

## Compliance Checklist

- [x] REQUIRED mode fails closed
- [x] ALS propagates to response.metadata
- [x] Authority scoring implemented
- [x] Two-step attestation for JSON+grounded
- [x] Telemetry includes all required fields
- [x] Deterministic ALS generation
- [x] URL redirect handling (Vertex)
- [x] CI gates for critical paths