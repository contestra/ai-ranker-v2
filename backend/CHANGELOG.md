# Changelog

## [2025-09-06] - Adapter Improvements and Strict Provider Separation

### Changed

#### OpenAI Adapter
- Enhanced citation extraction with second pass for anchored citations
- Improved tool detection with broader matching patterns
- Fixed text stitching to use newline joins for better readability
- Added `extraction_path` metadata hint: "openai_anchored_annotations"
- Ensured `finish_reason_standardized` is always set for telemetry parity

#### Google Base Adapter (Vertex/Gemini)
- Added asyncio timeout wrapper to prevent SDK hanging (60s default)
- Improved tool-call counting to track actual search signals (queries + chunks)
- Fixed text stitching to use newline joins matching OpenAI approach
- Added `extraction_path` metadata hints: "google_grounding_chunks" and "google_schema_tool"
- Ensured `finish_reason_standardized` is always set for telemetry consistency

#### Unified LLM Adapter (Router)
- **BREAKING**: Enforced strict provider separation - no cross-provider failover
- Removed all failover logic between gemini_direct and vertex
- Implemented deterministic `get_vendor_for_model()` without environment dependencies
- Simplified routing to strict vendor boundaries
- Cleaned up telemetry to remove failover-related fields

### Added
- Test file: `test_vertex_required_semantics.py` - Tests REQUIRED mode enforcement for Vertex/Gemini
- Test file: `test_vertex_als_de_comprehensive.py` - Comprehensive Vertex tests with three grounding modes

### Fixed
- OpenAI adapter now correctly handles anchored citations without explicit tool calls
- Google adapters no longer hang on slow SDK responses
- Vendor inference is now deterministic and doesn't rely on environment variables
- Text responses now have proper line breaks for multi-part content

### Configuration
- Updated `.env` locations from `europe-west4` to `us-central1`:
  - `GOOGLE_CLOUD_LOCATION=us-central1`
  - `VERTEX_LOCATION=us-central1`

### Testing
All adapters tested with:
- ALS (Ambient Location Signals) = DE (Germany)
- Ungrounded and grounded modes
- Various prompts including AVEA Life and German emergency information
- Confirmed strict provider separation working correctly