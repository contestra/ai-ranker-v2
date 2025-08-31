# ALS Ambient QA Report
Generated: 2025-08-31T17:05:46.042162

## Executive Summary

✅ **PASSED**: No prompt leakage - all prompts are location-neutral

⚠️ **Limited ALS Effects**: Geographic steering not clearly demonstrated


**Stats**: 48 runs | 24 grounded | 0 OpenAI NO_TOOLS


## Prompt: evidence

### Grounded Results Comparison

| Metric | ALS_NONE | ALS_CH | ALS_DE | ALS_US |
|--------|----------|---------|---------|---------|
| **Vertex** | | | | |
| grounded_effective | False | False | False | False | |
| tool_calls/results | 0/0 | 0/0 | 0/0 | 0/0 | |
| top_tlds | none | none | none | none | |
| unique_local | 0 domains | 0 domains | 0 domains | 0 domains | |
| language | - | - | - | - | |
| **OpenAI** | | | | |
| grounded_effective | False | False | False | False | |
| tool_status | ERROR | ERROR | ERROR | ERROR | |

### Analysis

**Limited ALS effects**: Geographic steering not clearly demonstrated in TLD distribution.

### Leakage Check

✅ **No prompt leakage** - user text is location-neutral


**Result**: ❌ FAILED


## Prompt: brand_cross_check

### Grounded Results Comparison

| Metric | ALS_NONE | ALS_CH | ALS_DE | ALS_US |
|--------|----------|---------|---------|---------|
| **Vertex** | | | | |
| grounded_effective | False | False | False | False | |
| tool_calls/results | 0/0 | 0/0 | 0/0 | 0/0 | |
| top_tlds | none | none | none | none | |
| unique_local | 0 domains | 0 domains | 0 domains | 0 domains | |
| language | - | - | - | - | |
| **OpenAI** | | | | |
| grounded_effective | False | False | False | False | |
| tool_status | ERROR | ERROR | ERROR | ERROR | |

### Analysis

**Limited ALS effects**: Geographic steering not clearly demonstrated in TLD distribution.

### Leakage Check

✅ **No prompt leakage** - user text is location-neutral


**Result**: ❌ FAILED


## Prompt: press_scan

### Grounded Results Comparison

| Metric | ALS_NONE | ALS_CH | ALS_DE | ALS_US |
|--------|----------|---------|---------|---------|
| **Vertex** | | | | |
| grounded_effective | False | False | False | False | |
| tool_calls/results | 0/0 | 0/0 | 0/0 | 0/0 | |
| top_tlds | none | none | none | none | |
| unique_local | 0 domains | 0 domains | 0 domains | 0 domains | |
| language | - | - | - | - | |
| **OpenAI** | | | | |
| grounded_effective | False | False | False | False | |
| tool_status | ERROR | ERROR | ERROR | ERROR | |

### Analysis

**Limited ALS effects**: Geographic steering not clearly demonstrated in TLD distribution.

### Leakage Check

✅ **No prompt leakage** - user text is location-neutral


**Result**: ❌ FAILED


## Overall Summary

### ❌ OVERALL: FAILED

- **Issue**: ALS effects not clearly demonstrated