# Changelog - September 2025

## Major Updates

### 1. OpenAI Adapter Refactoring ("Bloatectomy")
- **Reduced code by 55%** (734 lines → 332 lines)
- Removed all SDK-duplicate code:
  - Custom HTTP client
  - Rate limiting
  - Circuit breakers
  - Health checks
  - Streaming support
- Now delegates all transport to official SDK
- Uses Responses API exclusively (no Chat Completions)
- Maintains all functionality with better reliability

### 2. Router Capability Upgrade
- **Capability Gating**: Prevents 400 errors from unsupported parameters
  - Drops `reasoning.effort` for non-reasoning models (e.g., gpt-4o)
  - Drops `thinking_budget` for non-thinking Gemini models
- **Circuit Breaker**: Thin implementation at fleet level
  - Opens after N consecutive transient failures
  - Configurable cooldown period
  - No retry loops (SDK handles retries)
- **Router Pacing**: Respects Retry-After headers
  - Prevents hammering rate-limited endpoints
  - Per vendor:model tracking
- **Enhanced Telemetry**: New fields for observability
  - reasoning_hint_dropped
  - thinking_hint_dropped
  - circuit_breaker_status
  - router_pacing_delay

### 3. GPT-5 Support Improvements
- Fixed empty response issue for ungrounded GPT-5
- Added reasoning hints for GPT-5 models only
- Implemented TextEnvelope fallback for edge cases
- Proper handling of reasoning parameters

## Testing Results

### Grounded vs Ungrounded Comparison (GPT-4o)

| Metric | Grounded | Ungrounded | Difference |
|--------|----------|------------|------------|
| Response Time | 15.3s | 1.7s | 9x faster |
| Total Tokens | 19,380 | 163 | 119x fewer |
| Cost | $0.114 | $0.00124 | 92x cheaper |
| Information | Real Aug 2025 news | Declined | N/A |

### Key Findings
- **Grounded**: Provides real-time information with citations
- **Ungrounded**: Ultra-conservative, refuses future speculation
- **GPT-5**: More helpful than GPT-4o in ungrounded mode
- **Router**: Successfully prevents errors and maintains observability

## Configuration

### Environment Variables
```bash
# Circuit Breaker
CB_FAILURE_THRESHOLD=3  # Failures before opening
CB_COOLDOWN_SECONDS=60  # Cooldown period

# OpenAI
OPENAI_MAX_RETRIES=5
OPENAI_TIMEOUT_SECONDS=60
OPENAI_GROUNDED_MAX_TOKENS=6000

# Model Allowlists
ALLOWED_OPENAI_MODELS=gpt-4o,gpt-5-2025-08-07
ALLOWED_VERTEX_MODELS=publishers/google/models/gemini-2.5-pro
```

## Files Changed

### Core Changes
- `/app/llm/adapters/openai_adapter.py` - Refactored (55% reduction)
- `/app/llm/unified_llm_adapter.py` - Added capabilities, circuit breaker, pacing

### New Files
- `/app/llm/adapters/README.md` - Adapter documentation
- `/test_router_capabilities.py` - Router unit tests
- `/test_router_integration.py` - Integration tests
- `/ci_adapter_guard.py` - CI guard against pattern reintroduction
- `/.github/workflows/adapter_guard.yml` - GitHub Actions workflow

### Documentation
- `/ADAPTER_REFACTORING_2025.md` - Detailed refactoring notes
- `/ROUTER_UPGRADE_SUMMARY.md` - Router enhancement details
- `/BLOATECTOMY_COMPLETE.md` - Adapter cleanup summary

## Breaking Changes
None - All changes are backward compatible

## Migration Notes
- No code changes required for consumers
- Telemetry fields are additive
- SDK handles all retry/backoff automatically

## Next Steps
1. Monitor circuit breaker effectiveness in production
2. Add dashboards for new telemetry fields
3. Extend capability matrix for new models
4. Consider applying similar refactoring to other adapters