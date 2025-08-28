# AI Ranker V2 - Full Test Results
Date: Wed Aug 27 15:53:50 CEST 2025

## Environment Configuration
```
OPENAI_MAX_CONCURRENCY: 
OPENAI_STAGGER_SECONDS: 
OPENAI_TPM_LIMIT: 
OPENAI_TPM_HEADROOM: 
OPENAI_EST_TOKENS_PER_RUN: 
```

## Test 1: Rate Limiting (Simple)
```
======================================================================
RATE LIMITING TEST - 5 Simultaneous OpenAI Requests
Expected: Max 3 concurrent, with retry on any 429s
======================================================================
[ 1] Starting request...
[ 2] Starting request...
[ 3] Starting request...
[ 4] Starting request...
[ 5] Starting request...
[ 1] ✓ Success in 1.9s
[ 4] ✓ Success in 3.7s
[ 3] ✓ Success in 4.1s
[ 5] ✓ Success in 4.7s
[ 2] ✓ Success in 5.1s

======================================================================
Results: 5/5 successful
✅ All requests succeeded - rate limiting and retry logic working!
======================================================================
```

## Test 2: ALS Quick Verification
```
```

## Test 3: Comprehensive Rate Limiting
```
```

## Test 4: Batch Runner Rate Limiting
```
/home/leedr/ai-ranker-v2/backend/venv/lib/python3.12/site-packages/pydantic/_internal/_fields.py:132: UserWarning: Field "model_fingerprint_allowlist" in RunRequest has conflict with protected namespace "model_".

You may be able to resolve this warning by setting `model_config['protected_namespaces'] = ()`.
  warnings.warn(
/home/leedr/ai-ranker-v2/backend/venv/lib/python3.12/site-packages/pydantic/_internal/_fields.py:132: UserWarning: Field "model_version_effective" in RunResponse has conflict with protected namespace "model_".

You may be able to resolve this warning by setting `model_config['protected_namespaces'] = ()`.
  warnings.warn(
/home/leedr/ai-ranker-v2/backend/venv/lib/python3.12/site-packages/pydantic/_internal/_fields.py:132: UserWarning: Field "model_fingerprint" in RunResponse has conflict with protected namespace "model_".

You may be able to resolve this warning by setting `model_config['protected_namespaces'] = ()`.
  warnings.warn(
```

## Test Summary

### Rate Limiting
- Simple test: See results above
- Comprehensive test: See results above
- Batch runner test: See results above

### ALS (Ambient Location System)
- Quick verification: See results above

### Overall Status
Tests completed at: Wed Aug 27 15:59:56 CEST 2025
