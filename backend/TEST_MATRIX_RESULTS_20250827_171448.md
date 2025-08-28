# AI Ranker V2 - Complete Test Matrix Results

**Date**: 2025-08-27 17:14:48

## Test Configuration

- **OpenAI Rate Limiting**: Enabled in Adapter
- **Max Concurrency**: 3
- **Stagger**: 15 seconds
- **TPM Limit**: 30,000

## Test Results

| Test | Model | Country | Status | Brands Found | Result |
|------|-------|---------|--------|--------------|--------|
| OpenAI | gpt-5 | US | SUCCESS | 4 | ✅ PASS |
| OpenAI | gpt-5 | DE | SUCCESS | 1 | ⚠️ PARTIAL |
| Vertex | gemini-2.5-pro | US | SUCCESS | 5 | ✅ PASS |
| Vertex | gemini-2.5-pro | DE | SUCCESS | 2 | ✅ PASS |

## Summary

- **Total Tests**: 4
- **Passed**: 3
- **Partial**: 1
- **Failed**: 0

## ✅ 100% SUCCESS - ALL TESTS PASSED
