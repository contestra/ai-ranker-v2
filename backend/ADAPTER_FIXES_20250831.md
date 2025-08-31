# Adapter Fixes - August 31, 2025

## Overview
This document describes critical fixes applied to the LLM adapters to achieve full PRD compliance for grounding and ALS (Ambient Location Signals) functionality.

## Issues Fixed

### 1. ALS Propagation Issues
**Problem:** ALS metadata was not appearing in response.metadata despite being set in request.metadata.

**Root Causes:**
- **Vertex Adapter:** Variable name bug - used `request` instead of `req` parameter (line 1262)
- **Router:** ALS hardening code was placed after `return response`, making it unreachable
- **Router:** ALSContext object was being rejected by `isinstance(als_context, dict)` check

**Fixes Applied:**
- Fixed variable reference in vertex_adapter.py
- Moved ALS hardening block before telemetry emission in unified_llm_adapter.py
- Updated isinstance check to handle both dict and ALSContext objects

### 2. Vertex REQUIRED Mode Not Enforcing Grounding
**Problem:** REQUIRED mode was not actually forcing tool calls, only checking after-the-fact.

**Root Causes:**
- **google-genai path:** Passing invalid mode "REQUIRED" to SDK (not recognized)
- **vertexai SDK path:** Not passing any tool_config to enforce tool usage

**Fixes Applied:**
- Map application modes to SDK modes:
  - APP "REQUIRED" → SDK "ANY" (at least one tool call)
  - APP "AUTO" → SDK "AUTO" (model decides)
- Added ToolConfig with Mode.ANY for vertexai SDK path when REQUIRED

### 3. OpenAI Tool Type Selection
**Problem:** Hardcoded `web_search` tool type causing failures when only `web_search_preview` is supported.

**Fix Applied:**
- Use existing `_choose_web_search_tool_type()` helper instead of hardcoding
- Enabled ALLOW_PREVIEW_COMPAT by default for automatic fallback

### 4. Telemetry Reporting Issues
**Problem:** `grounding_mode_requested` was always "REQUIRED" when grounded=True, losing AUTO vs REQUIRED distinction.

**Fix Applied:**
- Updated telemetry to report actual requested mode from `request.meta['grounding_mode']`
- Added `grounding_mode_requested` to provider metadata for consistency

## Test Results

### Before Fixes
- ALS Detection: 0% (always False)
- Vertex Grounding: Partial (AUTO worked, REQUIRED failed)
- OpenAI Grounding: 0% (hardcoded tool type issues)

### After Fixes
- **ALS Detection: 100%** ✅
  - `als_present: True` for all ALS-enabled tests
  - Full metadata propagation (SHA256, country, locale, etc.)
  - Router-level hardening ensures consistency
  
- **Vertex Grounding: 100%** ✅
  - AUTO mode: Successfully grounds with citations
  - REQUIRED mode: Enforces grounding or fails closed
  
- **OpenAI: Correct Behavior** ✅
  - AUTO: Attempts grounding when supported
  - REQUIRED: Correctly fails with GROUNDING_NOT_SUPPORTED for unsupported models

## Technical Details

### ALS Propagation Flow
1. Request includes `als_context` (ALSContext object)
2. Router's `_apply_als()` enriches messages and sets `request.metadata`
3. Provider adapters copy ALS fields to response metadata
4. Router hardening ensures ALS fields are in response (failsafe)
5. Telemetry captures ALS fields for analytics

### Grounding Mode Enforcement
- **AUTO Mode:** Model decides whether to use tools
- **REQUIRED Mode:** 
  - OpenAI: Sets `tool_choice: "required"`
  - Vertex: Uses ToolConfig with Mode.ANY or function_calling_config with mode="ANY"
  - Both: Fail closed if no grounding occurs

### Files Modified
1. `app/llm/unified_llm_adapter.py`
   - Fixed ALS hardening placement
   - Fixed ALSContext isinstance check
   - Fixed telemetry mode reporting
   
2. `app/llm/adapters/vertex_adapter.py`
   - Fixed variable reference bug
   - Added REQUIRED mode enforcement for both SDK paths
   - Added grounding_mode_requested to metadata
   
3. `app/llm/adapters/openai_adapter.py`
   - Fixed tool type selection
   - Added grounding_mode_requested to metadata
   - Enabled preview compatibility

## Validation Checklist
- [x] ALS present in response.metadata when provided
- [x] Vertex REQUIRED mode enforces grounding
- [x] OpenAI adaptively selects tool type
- [x] Telemetry reports correct grounding mode
- [x] All tests pass with expected behavior

## Implementation Notes
These fixes ensure full compliance with the Phase-0 adapter specification and PRD requirements for immutability, grounding, and ALS propagation.