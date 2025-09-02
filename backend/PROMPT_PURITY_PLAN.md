# Prompt Purity Implementation Plan

## Goal
Ensure prompt purity:
- No "grounding enforcement" or "search nudges" should appear in the system message or the user input
- The user's prompt text must remain exactly what the human typed
- The system instruction must remain only Contestra's canonical system content (no added lines like "You MUST use web_search")
- All enforcement of grounding behavior must happen outside the prompt, at the adapter/router level

## Required Changes

### 1. System Message
- Remove any concatenation of grounding instructions ("You MUST call the web_search tool…", "As of today include URL…", etc.) into params["instructions"] or the system role content
- Preserve only the canonical system string (e.g., from request.instructions or Contestra default system message)

### 2. User Message
- Do not prepend or append grounding instructions to the user's input
- The user_input field must equal exactly the caller's provided text, unmodified

### 3. ALS Block
- ALS is allowed (as per PRD), but only in its canonical system-adjacent block
- Verify ALS injection stays within the orchestrator as a distinct block — not merged into the user message

### 4. Router Enforcement
- Grounding enforcement (e.g., REQUIRED mode checks) must happen post-hoc:
  - If grounded_effective=false when mode=REQUIRED → raise GROUNDING_REQUIRED_FAILED
- Do not attempt to enforce grounding by altering prompts

### 5. Provoker Policy
- If provoker mode ("as of today…") is active, inject it only when immutability is not strict
- Gate this behind a config flag (e.g., prompt_immutability=RELAXED)

### 6. Telemetry
- Keep logging of grounding_attempted, grounded_effective, why_not_grounded
- Use telemetry to measure when grounding was skipped — but do not modify the prompt to influence it

## Acceptance Criteria
✅ System message contains no grounding instructions or nudges
✅ User prompt is byte-for-byte identical to caller input
✅ ALS remains as a separate system block, ≤350 chars, not merged into user content
✅ REQUIRED enforcement happens only after model response inspection, not in the prompt
✅ Provoker lines (e.g., "as of today…") are only allowed in RELAXED immutability mode
✅ Unit tests confirm that params["input"] == original user text, and params["instructions"] == canonical system message

## Implementation Steps
1. Analyze current prompt handling in all adapters
2. Remove any grounding nudges from system messages
3. Ensure user messages remain unmodified
4. Verify ALS block handling remains separate
5. Implement post-hoc grounding enforcement
6. Add prompt_immutability config flag
7. Update telemetry for grounding tracking
8. Create unit tests for prompt purity
9. Document changes