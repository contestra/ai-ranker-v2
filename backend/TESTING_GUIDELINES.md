# Testing Guidelines - AI Ranker v2 Adapters

## Overview
This document provides comprehensive testing guidelines for the AI Ranker v2 adapter layer, including proper test architecture, recommended test matrices, and troubleshooting guides.

## Test Architecture

### Production Flow vs Test Flow

#### Production Flow (Correct)
```
Client Request
    ↓
BatchRunner (applies ALS)
    ↓
UnifiedLLMAdapter (routing)
    ↓
Vendor Adapter (OpenAI/Vertex)
    ↓
Response with full metadata
```

#### Common Test Anti-Pattern
```
Test directly calls UnifiedLLMAdapter
    ↓
Bypasses BatchRunner (no ALS)
    ↓
Missing metadata fields
```

### Correct Testing Approach
```python
# CORRECT: Use BatchRunner for integration tests
from app.services.batch_runner import BatchRunner

async def test_with_als():
    runner = BatchRunner()
    result = await runner.process_request(
        template_id="test-template",
        als_context={'country_code': 'US'},
        messages=[{"role": "user", "content": "test"}]
    )
```

## Recommended Test Matrix

### Lane A: OpenAI Ungrounded
- **Purpose**: Baseline performance, ALS effectiveness
- **Configurations**:
  - No ALS
  - ALS with US context
  - ALS with DE context
  - ALS with UK context
- **Expected**: 5-6s latency, consistent responses

### Lane B: OpenAI Grounded
- **Purpose**: Grounding fallback behavior
- **Configurations**:
  - REQUIRED mode (expect synthesis fallback)
  - AUTO mode (graceful degradation)
- **Expected**: 5-7s latency, synthesis with evidence

### Lane C: Vertex Grounded
- **Purpose**: Full grounding with Google Search
- **Configurations**:
  - REQUIRED mode with JSON
  - Two-step processing validation
- **Expected**: 20-50s latency, grounded results

### Lane D: Vertex Ungrounded
- **Purpose**: Baseline Vertex performance
- **Configurations**:
  - Standard completion
  - JSON mode validation
- **Expected**: 8-10s latency

## Test Data Specifications

### Standard Test Prompt
```python
STANDARD_PROMPT = "List the 10 most trusted longevity supplement brands"
```

### Expected Response Patterns
```python
# Brand consistency indicators
EXPECTED_BRANDS = [
    "Thorne Research",  # Should appear in 90%+ tests
    "Life Extension",   # Should appear in 80%+ tests
    "Pure Encapsulations",  # Common
    "NOW Foods",  # Common
    "Elysium Health"  # Emerging
]

# Regional indicators for ALS
REGIONAL_INDICATORS = {
    'US': ['FDA', 'NSF', 'USP', 'GMP'],
    'DE': ['EU', 'European', 'EFSA', 'CE'],
    'UK': ['MHRA', 'British', 'UK']
}
```

## Unit Testing

### Adapter Component Tests
```python
import pytest
from app.llm.adapters.openai_adapter import OpenAIAdapter

@pytest.mark.asyncio
async def test_metadata_preservation():
    adapter = OpenAIAdapter()
    request = LLMRequest(
        model="gpt-5",
        messages=[{"role": "user", "content": "test"}],
        metadata={"auto_trim": True, "proxy_used": False}
    )
    
    response = await adapter.complete(request, timeout=60)
    
    # Verify metadata preserved
    assert response.metadata.get('auto_trim') == True
    assert response.metadata.get('proxy_used') == False
    assert 'max_output_tokens_effective' in response.metadata
```

### Rate Limiter Tests
```python
@pytest.mark.asyncio
async def test_tpm_credit_system():
    limiter = TokenBucketRateLimiter(tpm_limit=10000)
    
    # Simulate overestimation
    await limiter.acquire(5000)
    limiter.record_actual_usage(5000, 3000)  # Used less
    
    # Credit should be applied
    assert limiter._tokens_used_this_minute == 3000
```

### Grounding Detection Tests
```python
def test_grounding_signal_separation():
    # Mock response with web search
    response = create_mock_response_with_search()
    
    grounded, tools, web, searches = detect_openai_grounding(response)
    
    assert grounded == True
    assert web == True
    assert searches > 0
    assert tools >= searches  # Tools include searches
```

## Integration Testing

### Full Stack Test
```python
async def test_full_stack_with_als():
    """Test complete flow from request to response"""
    
    # 1. Create request with ALS context
    request = {
        "template_id": "test-template",
        "als_context": {"country_code": "DE"},
        "prompt": STANDARD_PROMPT,
        "vendor": "openai",
        "model": "gpt-5",
        "grounded": False
    }
    
    # 2. Process through BatchRunner
    runner = BatchRunner()
    response = await runner.process(request)
    
    # 3. Verify ALS application
    assert "[Context:" in response['messages_sent'][0]['content']
    
    # 4. Check for regional indicators
    content = response['llm_response']['content']
    found_indicators = [
        ind for ind in REGIONAL_INDICATORS['DE']
        if ind.lower() in content.lower()
    ]
    assert len(found_indicators) > 0
```

### Vendor Comparison Test
```python
async def test_vendor_consistency():
    """Ensure similar results across vendors"""
    
    prompt = STANDARD_PROMPT
    
    # Test both vendors
    openai_response = await test_vendor("openai", "gpt-5", prompt)
    vertex_response = await test_vendor("vertex", "gemini-2.5-pro", prompt)
    
    # Extract brands
    openai_brands = extract_brands(openai_response)
    vertex_brands = extract_brands(vertex_response)
    
    # Check overlap (should be >50%)
    overlap = set(openai_brands[:5]) & set(vertex_brands[:5])
    assert len(overlap) >= 3
```

## Performance Testing

### Latency Benchmarks
```python
async def benchmark_adapter_latency():
    """Measure adapter performance"""
    
    configs = [
        ("openai", "gpt-5", False),  # Ungrounded
        ("openai", "gpt-5", True),   # Grounded
        ("vertex", "gemini-2.5-pro", False),
        ("vertex", "gemini-2.5-pro", True)
    ]
    
    results = []
    for vendor, model, grounded in configs:
        times = []
        for _ in range(5):
            start = time.perf_counter()
            await run_test(vendor, model, grounded)
            times.append(time.perf_counter() - start)
        
        results.append({
            "config": f"{vendor}-{grounded}",
            "avg_ms": int(np.mean(times) * 1000),
            "p95_ms": int(np.percentile(times, 95) * 1000)
        })
    
    return results
```

### Load Testing
```python
async def test_rate_limiting_under_load():
    """Verify rate limiting behavior"""
    
    adapter = OpenAIAdapter()
    
    # Generate high load
    tasks = []
    for i in range(20):
        request = create_test_request(tokens=5000)
        tasks.append(adapter.complete(request, timeout=60))
    
    # Should handle gracefully with delays
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check success rate
    successes = sum(1 for r in results if not isinstance(r, Exception))
    assert successes >= 18  # 90% success rate
```

## Mock Strategies

### Effective Mocking
```python
# Mock OpenAI response
def create_mock_openai_response(grounded=False):
    response = Mock()
    response.choices = [Mock()]
    response.choices[0].message = Mock()
    response.choices[0].message.content = "Test response"
    
    if grounded:
        response.choices[0].message.search_results = [
            Mock(title="Source 1", url="http://example.com", snippet="Test")
        ]
    
    response.usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150
    }
    
    return response
```

### Vertex Mock with Tools
```python
def create_mock_vertex_grounded():
    response = Mock()
    response.candidates = [Mock()]
    response.candidates[0].content = Mock()
    response.candidates[0].content.parts = [
        Mock(text='{"results": ["Brand 1", "Brand 2"]}')
    ]
    response.candidates[0].grounding_metadata = Mock()
    response.candidates[0].grounding_metadata.search_queries = ["longevity supplements"]
    
    return response
```

## Debugging Guide

### Common Issues and Solutions

#### Issue: ALS Not Applied
```python
# WRONG
adapter = UnifiedLLMAdapter()
response = await adapter.complete(request)  # Bypasses BatchRunner

# RIGHT
runner = BatchRunner()
response = await runner.process(request)  # Includes ALS
```

#### Issue: Mock Serialization Error
```python
# WRONG
mock_response = Mock()
json.dumps(mock_response)  # Fails

# RIGHT
mock_response = {
    "choices": [{"message": {"content": "test"}}],
    "usage": {"total_tokens": 100}
}
```

#### Issue: Rate Limiting Not Working
```python
# Check environment variables
assert os.getenv("OPENAI_TPM_LIMIT")
assert os.getenv("OPENAI_RPM_LIMIT")

# Verify limiter initialization
adapter = OpenAIAdapter()
assert adapter.tpm_limiter is not None
assert adapter.tpm_limiter.tpm_limit > 0
```

## Test Execution

### Running Tests
```bash
# Unit tests only
pytest tests/unit/test_adapters.py -v

# Integration tests
pytest tests/integration/test_full_stack.py -v

# Performance benchmarks
pytest tests/performance/test_benchmarks.py -v --benchmark

# Full test suite
pytest tests/ -v --cov=app/llm --cov-report=html
```

### Continuous Integration
```yaml
# .github/workflows/test.yml
name: Adapter Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          VERTEX_PROJECT_ID: ${{ secrets.VERTEX_PROJECT }}
        run: pytest tests/ -v --cov
```

## Test Data Management

### Fixtures
```python
# conftest.py
@pytest.fixture
async def openai_adapter():
    adapter = OpenAIAdapter()
    yield adapter
    # Cleanup if needed

@pytest.fixture
def standard_request():
    return LLMRequest(
        vendor="openai",
        model="gpt-5",
        messages=[{"role": "user", "content": STANDARD_PROMPT}],
        temperature=0.3,
        max_tokens=500
    )
```

### Test Database
```python
@pytest.fixture
async def test_db():
    # Create test database session
    async with AsyncSession() as session:
        yield session
        await session.rollback()
```

## Reporting

### Test Report Format
```markdown
## Test Results - [Date]

### Summary
- Total Tests: X
- Passed: Y
- Failed: Z
- Success Rate: Y/X %

### Vendor Performance
| Vendor | Config | Avg Latency | P95 | Success Rate |
|--------|--------|-------------|-----|--------------|
| OpenAI | Ungrounded | 5.5s | 7.2s | 100% |
| Vertex | Grounded | 35s | 52s | 95% |

### ALS Effectiveness
- Tests with ALS: X
- Regional indicators found: Y%
- Brand consistency: Z%

### Issues Found
1. [Issue description]
   - Test: [test name]
   - Expected: [expected behavior]
   - Actual: [actual behavior]
```

## Best Practices

### DO
- ✅ Test through BatchRunner for production-like behavior
- ✅ Use proper async/await patterns
- ✅ Mock external services appropriately
- ✅ Test error conditions and edge cases
- ✅ Verify metadata preservation
- ✅ Check for memory leaks in long-running tests

### DON'T
- ❌ Test directly against production APIs without rate limiting
- ❌ Hard-code API keys in test files
- ❌ Skip ALS testing because it's "complex"
- ❌ Ignore flaky tests - investigate and fix
- ❌ Use time.sleep() - use proper async waiting

## Troubleshooting

### Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable adapter debug logs
logger = logging.getLogger("app.llm.adapters")
logger.setLevel(logging.DEBUG)
```

### Common Error Messages
```
"MODEL_NOT_ALLOWED" - Model validation failed
"Rate limit exceeded" - TPM/RPM limits hit
"Grounding not supported" - OpenAI web_search unavailable
"Mock object is not JSON serializable" - Improper mocking
```

---

*Last Updated: August 29, 2025*
*For questions: #ai-ranker-support*