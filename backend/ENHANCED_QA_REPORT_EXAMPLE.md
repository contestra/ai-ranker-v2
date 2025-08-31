# ALS Ambient QA Report (Enhanced)
Generated: 2025-08-31T18:00:00

## Executive Summary

✅ **PASSED**: No prompt leakage - all prompts are location-neutral

⚠️ **REQUIRED Mode Issues**: 4 runs failed to invoke tools despite REQUIRED mode
   (This is expected for OpenAI which cannot force tool usage)

**Stats**: 48 runs | 24 grounded | 4 REQUIRED failures

## Prompt: evidence

### Run Details

| Run Tag | ALS | Citations | TLDs | Status | Notes |
|---------|-----|-----------|------|--------|-------|
| `vertex:gemini-2.5-pro:AUTO→grounded_ok` | NONE | 12 | .com(8), .org(4) | ✅ | |
| `vertex:gemini-2.5-pro:AUTO→grounded_ok` | CH | 14 | .com(9), .ch(3), .org(2) | ✅ | |
| `vertex:gemini-2.5-pro:REQUIRED→grounded_ok` | NONE | 11 | .com(7), .gov(4) | ✅ | |
| `openai:gpt-5:AUTO→auto_no_tools` | NONE | 0 | none | ❌ | Tools not invoked |
| `openai:gpt-5:REQUIRED→REQUIRED_FAILED` | NONE | 0 | none | ❌ | REQUIRED not met; (OpenAI can't force) |
| `openai:gpt-5:REQUIRED→REQUIRED_FAILED` | CH | 0 | none | ❌ | REQUIRED not met; (OpenAI can't force) |
| `vertex:gemini-2.5-pro:None→ungrounded` | NONE | 0 | none | ❌ | |

### Grounding Mode Analysis

- **AUTO**: 8/12 effective (67%)
- **REQUIRED**: 4/8 effective (50%)
  - OpenAI: 0/4 (cannot force tools, will fail in router post-validation)
- **UNGROUNDED**: 0/4 effective (0%)

### ALS Effects

- **CH**: ✅ Increased .ch domains (0→3)
- **DE**: ⚠️ No increase in .de domains
- **US**: ✅ Increased .com domains (8→11)

## Error Analysis

- REQUIRED validation failure: 4 occurrences
- Timeout: 1 occurrence

## Overall Summary

### ⚠️ OVERALL: PASSED WITH WARNINGS

- **Warning**: 4 OpenAI REQUIRED failures (expected - cannot force tools)

## Run Tag Format

```
provider:model:mode_sent→status

Status values:
- grounded_ok: Tools successfully invoked
- auto_no_tools: AUTO mode, tools not invoked (model choice)
- REQUIRED_FAILED: REQUIRED mode but tools not invoked
- ungrounded: Request not configured for grounding
```

---

## Key Improvements in This Report

1. **Clear Run Tags**: Each run is tagged with `provider:model:mode→outcome` making it immediately obvious what was attempted and what happened.

2. **REQUIRED Mode Visibility**: Explicitly shows when REQUIRED mode was sent but tools weren't invoked, with notes explaining this is expected for OpenAI.

3. **Grounding Mode Analysis**: Breaks down success rates by mode (AUTO, REQUIRED, UNGROUNDED) with provider-specific notes.

4. **Mode Sent vs. Effective**: 
   - `grounded` field = what was requested
   - `grounded_effective` field = what actually happened
   - Run tag shows both: `REQUIRED→REQUIRED_FAILED`

5. **Provider-Specific Context**: Notes like "(OpenAI can't force)" help reviewers understand expected vs. unexpected failures.

6. **Error Classification**: Groups errors by type, making it easy to spot patterns.

This format ensures reviewers can immediately identify:
- When "REQUIRED sent to OpenAI" explains an error (expected)
- When a genuine grounding failure occurred (unexpected)
- Which provider/model combinations are working as intended
- Where ALS effects are visible in the results