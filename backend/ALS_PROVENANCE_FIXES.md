# ALS Provenance Centralization

## Problem
Multiple hardcoded `seed_key_id` values across the codebase:
- Config default: "k1"
- OpenAI adapter: "v1_2025" (from env var)
- Router hardcoded: "v1_2025"
- Types default: "k1"

This inconsistency could lead to drift and silent use of defaults in production.

## Solution
Created centralized `ALSConfig` class in `app/llm/als_config.py` that:

1. **Single Source of Truth**: All components use `ALSConfig.get_seed_key_id()`
2. **Environment Override Support**: Respects `OPENAI_SEED_KEY_ID` and `ALS_SEED_KEY_ID`
3. **Provenance Tracking**: Marks metadata with source information
4. **Default Detection**: Clearly identifies when defaults/placeholders are used

## Changes Made

### New File: `app/llm/als_config.py`
- Centralized configuration class
- Production vs development seed keys
- Metadata marking functions
- Environment override handling

### Updated Files:
1. **app/llm/adapters/openai_adapter.py**
   - Uses `ALSConfig.get_seed_key_id("openai")`
   - Adds provenance metadata via `ALSConfig.mark_als_metadata()`

2. **app/llm/unified_llm_adapter.py**
   - Uses `ALSConfig.get_seed_key_id()` in `_apply_als()`
   - Adds provenance metadata to request

3. **app/llm/types.py**
   - Changed `ALSContext.seed_key_id` default to `None`
   - Will be set by router using centralized config

## Metadata Fields Added
When ALS is applied, the following metadata fields are now included:
- `als_seed_key_id`: The actual seed key ID used
- `als_seed_is_default`: True if using development default
- `als_seed_is_production`: True if using production key
- `als_seed_warning`: Warning message if using defaults
- `als_seed_source`: Source of the seed key (config_default, openai_env_override, global_env_override)

## Testing
Created comprehensive tests:
- `test_als_centralized.py`: Tests configuration behavior
- `test_als_integration.py`: Tests integration across components

## Benefits
1. **No Silent Defaults**: Defaults are clearly marked in metadata
2. **Consistent Behavior**: All components use same configuration
3. **Production Safety**: Easy to detect non-production keys in telemetry
4. **Debugging**: Clear provenance tracking for troubleshooting
5. **Flexibility**: Environment overrides still supported when needed