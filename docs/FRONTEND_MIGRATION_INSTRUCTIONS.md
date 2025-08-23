# Frontend Migration Instructions for AI Ranker V2

## Overview
The V1 frontend has a working PromptTracking component that needs to be adapted for the V2 API. This document guides the migration.

## Files to Copy from V1

Copy these files from Windows to WSL:

```bash
# Core frontend files
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/src/components/PromptTracking.tsx ~/ai-ranker-v2/frontend/src/components/
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/src/lib/api.ts ~/ai-ranker-v2/frontend/src/lib/
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/package.json ~/ai-ranker-v2/frontend/
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/next.config.js ~/ai-ranker-v2/frontend/
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/tsconfig.json ~/ai-ranker-v2/frontend/
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/tailwind.config.ts ~/ai-ranker-v2/frontend/
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/src/app/layout.tsx ~/ai-ranker-v2/frontend/src/app/
cp /mnt/d/OneDrive/CONTESTRA/Microapps/ai-ranker/frontend/src/app/page.tsx ~/ai-ranker-v2/frontend/src/app/
```

## API Endpoint Mapping

The frontend needs to be updated to use the new V2 endpoints:

### OLD V1 Endpoints (to replace):
```typescript
// In api.ts and PromptTracking.tsx
POST   /api/prompt-tracking/templates
GET    /api/prompt-tracking/templates
PUT    /api/prompt-tracking/templates/{id}
DELETE /api/prompt-tracking/templates/{id}
POST   /api/prompt-tracking/run
GET    /api/prompt-tracking/results/{run_id}
GET    /api/prompt-tracking/analytics/{brand_name}
```

### NEW V2 Endpoints (to use instead):
```typescript
// New endpoints from PRD v2.7
POST   /v1/templates                          // Create template (with idempotency)
GET    /v1/templates                          // List templates
GET    /v1/templates/{id}                     // Get template details
POST   /v1/templates/{id}/run                 // Execute single run
POST   /v1/templates/{id}/batch-run           // Execute batch run
GET    /v1/templates/{id}/runs                // List runs for template
GET    /v1/providers/{provider}/versions      // Get provider versions
```

## Required Frontend Changes

### 1. Update api.ts

```typescript
// Change the base URL and endpoints
const API_BASE = 'http://localhost:8000';  // Remove /api prefix

// Update all endpoint calls to use /v1/ instead of /api/prompt-tracking/
// Example:
// OLD: ${API_BASE}/api/prompt-tracking/templates
// NEW: ${API_BASE}/v1/templates
```

### 2. Update PromptTracking.tsx

Key changes needed:
- Remove brand_name field (V2 is prompter-only)
- Add template_sha256 display (show the hash)
- Add response_output_sha256 display for runs
- Show model_version_effective and model_fingerprint
- Display grounded_effective status
- Remove analytics tab (no brand analytics in V2)
- Add provider version display

### 3. Data Model Updates

The V2 response format is different:

```typescript
// V1 Template
interface TemplateV1 {
  id: number;
  name: string;
  prompt_text: string;
  model_name: string;
  // ... other fields
}

// V2 Template  
interface TemplateV2 {
  template_id: string;  // UUID not number
  template_name: string;
  template_sha256: string;  // NEW: hash of canonical config
  canonical_json: object;   // NEW: canonicalized config
  created_at: string;
  record_hmac?: string;     // NEW: tamper detection
}

// V2 Run
interface RunV2 {
  run_id: string;
  template_id: string;
  run_sha256: string;              // NEW: hash of run config
  model_version_effective: string;
  model_fingerprint?: string;      // NEW: provider build ID
  output: string;
  response_output_sha256: string;  // NEW: hash of output
  grounded_effective: boolean;
  output_json_valid?: boolean;
  latency_ms: number;
  created_at: string;
}
```

### 4. Features to Remove

Remove all references to:
- Brand entity strength
- Concordance analysis  
- Entity extraction
- Weekly tracking
- Brand analytics
- Any non-prompter features

### 5. Features to Add/Update

Add display for:
- Template SHA-256 hash
- Run SHA-256 hash
- Output SHA-256 hash
- Model fingerprint
- Grounding effectiveness
- JSON validity status
- Canonicalized configuration
- Idempotency handling (show when template already exists)

## Component Structure

```typescript
// Main tabs to keep:
- Templates (CRUD operations)
- Run Template (execute single/batch)
- Results (view run outputs with hashes)
- Countries (keep for ALS testing)

// Remove these tabs:
- Analytics
- Brand Tracking
- Entity Analysis
```

## Testing the Migration

1. After updating the frontend:
```bash
cd ~/ai-ranker-v2/frontend
npm install
npm run dev
```

2. Verify:
- Templates can be created with proper hashing
- Runs execute and return provenance data
- SHA-256 hashes are displayed
- Model versions are shown
- Grounding status is visible

## Key Implementation Notes

1. **Idempotency**: When creating templates, handle 409 conflicts gracefully and show the diff
2. **Provider Versions**: Display the current model version and fingerprint for each run
3. **Immutability**: Show that templates cannot be edited, only created
4. **Hashing**: Display all three hashes (template, run, output) prominently
5. **Phase-1**: No Redis/Celery features - all execution is synchronous

## Summary for Claude

When implementing:
1. Keep the UI structure from PromptTracking.tsx
2. Update all API calls to use /v1/ endpoints
3. Remove brand-related features
4. Add hash displays (template_sha256, run_sha256, response_output_sha256)
5. Show model fingerprints and versions
6. Display grounding effectiveness
7. Handle UUID instead of numeric IDs
8. Show canonicalized JSON configuration