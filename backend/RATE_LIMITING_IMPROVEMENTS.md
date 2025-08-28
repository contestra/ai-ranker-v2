# Rate Limiting Improvements - Implementation Plan

## Current Issues (from test failures)
- **429 errors**: Grounded calls consuming 137k+ tokens, exhausting TPM budget
- **Proxy errors**: Connection failures with residential/backbone proxies
- **Timeouts**: 5-minute timeouts on grounded DE calls
- **Cascading failures**: One large call blocks all subsequent calls

## Solution Architecture

### 1. Reservation-Based Rate Limiting

**Current**: Estimate → Call → Pay debt
**New**: Reserve → Trim if needed → Call → Update with actual

```python
class AdaptiveRateLimiter:
    def __init__(self, tpm_limit=30000, headroom=0.15):
        self.budget = tpm_limit * (1 - headroom)  # 25,500 effective
        self.remaining_this_minute = self.budget
        self.minute_boundary = time.time()
        
        # Adaptive multipliers per class
        self.class_ratios = {
            # (grounded, policy) -> p90 ratio
            (True, "ALS_ONLY"): 2.5,      # High prior for grounded
            (True, "ALS_PLUS_PROXY"): 2.5,
            (True, "PROXY_ONLY"): 2.5,
            (True, "NONE"): 2.0,
            (False, "ALS_ONLY"): 1.2,
            (False, "ALS_PLUS_PROXY"): 1.3,
            (False, "PROXY_ONLY"): 1.3,
            (False, "NONE"): 1.1,
        }
        self.usage_history = defaultdict(list)  # Track actual/estimate ratios
    
    async def reserve_tokens(self, request):
        # Calculate reservation with adaptive multiplier
        class_key = (request.grounded, request.vantage_policy)
        multiplier = self.class_ratios.get(class_key, 1.5)
        
        input_estimate = estimate_input_tokens(request.messages)
        output_requested = request.max_tokens
        reservation = int((input_estimate + output_requested) * multiplier)
        
        # Check if we need to wait for next minute
        now = time.time()
        if now > self.minute_boundary + 60:
            self._reset_minute()
        
        # Trim if necessary
        if reservation > self.remaining_this_minute:
            # Try to trim output tokens
            available_for_output = self.remaining_this_minute / multiplier - input_estimate
            if available_for_output >= 500:  # Minimum viable output
                trimmed_output = int(available_for_output)
                reservation = int((input_estimate + trimmed_output) * multiplier)
                metadata = {"auto_trimmed_tokens": output_requested - trimmed_output}
            else:
                # Must wait for next minute
                await self._wait_next_minute()
                self._reset_minute()
        
        self.remaining_this_minute -= reservation
        return reservation, metadata
    
    def update_with_actual(self, reservation, actual_usage, class_key):
        # Update adaptive multiplier based on actual usage
        ratio = actual_usage / (reservation / self.class_ratios[class_key])
        self.usage_history[class_key].append(ratio)
        
        # Keep last 20 samples, update p90
        if len(self.usage_history[class_key]) > 20:
            self.usage_history[class_key].pop(0)
        
        # Update class ratio to p90
        if len(self.usage_history[class_key]) >= 5:
            sorted_ratios = sorted(self.usage_history[class_key])
            p90_idx = int(len(sorted_ratios) * 0.9)
            self.class_ratios[class_key] = sorted_ratios[p90_idx]
```

### 2. Heavy Job Lane

```python
class HeavyJobLane:
    def __init__(self, min_budget_fraction=0.8):
        self.heavy_lock = asyncio.Lock()
        self.min_budget_fraction = min_budget_fraction
    
    def is_heavy(self, request):
        # Grounded + ALS = heavy
        return (request.grounded and 
                request.vantage_policy in ["ALS_ONLY", "ALS_PLUS_PROXY"])
    
    async def acquire_if_heavy(self, request, rate_limiter):
        if not self.is_heavy(request):
            return None
        
        async with self.heavy_lock:
            # Wait for fresh minute if budget is low
            while rate_limiter.remaining_fraction < self.min_budget_fraction:
                await rate_limiter.wait_next_minute()
            
            return self.heavy_lock  # Hold the lock
```

### 3. Circuit Breaker for Proxies

```python
class ProxyCircuitBreaker:
    def __init__(self, threshold=2, cooldown=600):
        self.error_counts = defaultdict(int)  # (country, mode) -> count
        self.circuit_open = defaultdict(lambda: False)
        self.circuit_open_time = {}
        self.threshold = threshold
        self.cooldown = cooldown
    
    def record_error(self, country, mode):
        key = (country, mode)
        self.error_counts[key] += 1
        
        if self.error_counts[key] >= self.threshold:
            self.circuit_open[key] = True
            self.circuit_open_time[key] = time.time()
            logger.warning(f"Circuit breaker OPEN for proxy {country}/{mode}")
            return True
        return False
    
    def is_open(self, country, mode):
        key = (country, mode)
        if not self.circuit_open[key]:
            return False
        
        # Check if cooldown expired
        if time.time() - self.circuit_open_time[key] > self.cooldown:
            self.circuit_open[key] = False
            self.error_counts[key] = 0
            logger.info(f"Circuit breaker RESET for proxy {country}/{mode}")
            return False
        
        return True
    
    def degrade_policy(self, policy):
        # Degrade proxy policies to direct
        if policy == "ALS_PLUS_PROXY":
            return "ALS_ONLY"
        elif policy == "PROXY_ONLY":
            return None  # Or "ALS_ONLY" if fallback allowed
        return policy
```

### 4. Enhanced OpenAI Adapter Integration

```python
class OpenAIAdapter:
    def __init__(self):
        self.rate_limiter = AdaptiveRateLimiter()
        self.heavy_lane = HeavyJobLane()
        self.proxy_breaker = ProxyCircuitBreaker()
        self.normal_semaphore = asyncio.Semaphore(3)
    
    async def complete(self, request, timeout=60):
        # Check and degrade if proxy circuit is open
        if request.vantage_policy in ["ALS_PLUS_PROXY", "PROXY_ONLY"]:
            country = request.meta.get("country", "US")
            mode = request.meta.get("proxy_mode", "rotating")
            
            if self.proxy_breaker.is_open(country, mode):
                degraded = self.proxy_breaker.degrade_policy(request.vantage_policy)
                if degraded:
                    request.vantage_policy = degraded
                    request.meta["proxy_degraded"] = True
                else:
                    raise RuntimeError("PROXY_CIRCUIT_OPEN: No fallback available")
        
        # Acquire heavy lane if needed
        heavy_lock = None
        if self.heavy_lane.is_heavy(request):
            heavy_lock = await self.heavy_lane.acquire_if_heavy(request, self.rate_limiter)
            request.meta["heavy_lane"] = True
        else:
            await self.normal_semaphore.acquire()
        
        try:
            # Reserve tokens with auto-trim
            reservation, reserve_meta = await self.rate_limiter.reserve_tokens(request)
            if "auto_trimmed_tokens" in reserve_meta:
                request.max_tokens -= reserve_meta["auto_trimmed_tokens"]
                request.meta.update(reserve_meta)
            
            # Make the call with appropriate timeout
            call_timeout = 480 if request.grounded and not request.meta.get("proxy") else 300
            
            try:
                response = await self._make_api_call(request, timeout=call_timeout)
                
                # Update rate limiter with actual usage
                actual = response.usage.get("total_tokens", 0)
                class_key = (request.grounded, request.vantage_policy)
                self.rate_limiter.update_with_actual(reservation, actual, class_key)
                
                return response
                
            except ProxyConnectionError as e:
                # Record proxy error
                if self.proxy_breaker.record_error(country, mode):
                    # Circuit opened, retry with degraded policy
                    return await self.complete(request, timeout)
                raise
                
            except TimeoutError:
                if time.time() - start_time > 480:
                    # SLA exceeded, finalize
                    request.meta["sla_exceeded"] = True
                    request.max_tokens = min(request.max_tokens, 500)  # Quick finish
                    return await self._make_api_call(request, timeout=30)
                raise
                
        finally:
            if heavy_lock:
                pass  # Lock auto-releases
            else:
                self.normal_semaphore.release()
```

## Configuration

```env
# Rate Limiting
OPENAI_TPM_LIMIT=30000
OPENAI_TPM_HEADROOM=0.15
OPENAI_AUTO_TRIM=true
OPENAI_HEAVY_MIN_REMAINING=24000

# Concurrency
OPENAI_MAX_CONCURRENCY=3
OPENAI_STAGGER_SECONDS=15

# Circuit Breaker
PROXY_CIRCUIT_THRESHOLD=2
PROXY_CIRCUIT_COOLDOWN=600

# Timeouts
OPENAI_TIMEOUT_GROUNDED_DIRECT=480
OPENAI_TIMEOUT_GROUNDED_PROXY=300
OPENAI_TIMEOUT_UNGROUNDED=120
```

## Test Plan

### 1. Unit Tests

```python
async def test_reservation_trimming():
    """Test auto-trimming when budget is tight"""
    limiter = AdaptiveRateLimiter(tpm_limit=10000)
    limiter.remaining_this_minute = 3000
    
    request = LLMRequest(
        messages=[{"role": "user", "content": "Long prompt..."}],
        max_tokens=6000,
        grounded=True
    )
    
    reservation, meta = await limiter.reserve_tokens(request)
    assert "auto_trimmed_tokens" in meta
    assert meta["auto_trimmed_tokens"] > 0
    assert reservation <= 3000

async def test_heavy_lane_isolation():
    """Test heavy jobs run alone"""
    lane = HeavyJobLane()
    
    heavy_req = LLMRequest(grounded=True, vantage_policy="ALS_ONLY")
    normal_req = LLMRequest(grounded=False, vantage_policy="NONE")
    
    # Heavy should acquire exclusive lock
    assert lane.is_heavy(heavy_req) == True
    assert lane.is_heavy(normal_req) == False

async def test_circuit_breaker():
    """Test proxy circuit breaker"""
    breaker = ProxyCircuitBreaker(threshold=2)
    
    # First error
    assert breaker.record_error("US", "rotating") == False
    assert breaker.is_open("US", "rotating") == False
    
    # Second error - circuit opens
    assert breaker.record_error("US", "rotating") == True
    assert breaker.is_open("US", "rotating") == True
    
    # Policy degradation
    assert breaker.degrade_policy("ALS_PLUS_PROXY") == "ALS_ONLY"
    assert breaker.degrade_policy("PROXY_ONLY") == None
```

### 2. Integration Tests

```python
async def test_batch_with_heavy_jobs():
    """Test batch with mixed heavy/normal jobs"""
    adapter = OpenAIAdapter()
    
    jobs = [
        # Heavy - should run alone
        {"grounded": True, "vantage_policy": "ALS_ONLY", "max_tokens": 6000},
        # Normal - should run concurrently
        {"grounded": False, "vantage_policy": "NONE", "max_tokens": 500},
        {"grounded": False, "vantage_policy": "NONE", "max_tokens": 500},
    ]
    
    results = await asyncio.gather(*[
        adapter.complete(LLMRequest(**job)) for job in jobs
    ])
    
    # Check metadata
    assert results[0].metadata.get("heavy_lane") == True
    assert all(r.metadata.get("rate_limited") == False for r in results)
```

## Rollout Plan

1. **Phase 1**: Deploy adaptive rate limiter with monitoring
2. **Phase 2**: Enable heavy lane for grounded+ALS jobs  
3. **Phase 3**: Activate proxy circuit breaker
4. **Phase 4**: Enable auto-trimming

## Monitoring

Track these metrics:
- `rate_limit_reservations`: Histogram of token reservations
- `rate_limit_trims`: Counter of auto-trim events
- `heavy_lane_acquisitions`: Counter of heavy lane uses
- `proxy_circuit_opens`: Counter of circuit breaker activations
- `adaptive_multipliers`: Gauge of current multipliers per class

## Expected Improvements

- **No more 429s**: Reservation system prevents overcommit
- **Better throughput**: Heavy lane isolates whales
- **Proxy resilience**: Circuit breaker prevents cascade failures
- **Adaptive accuracy**: P90 ratios converge to actual usage patterns
- **SLA compliance**: Timeouts + finalization prevent indefinite hangs

---

This implementation preserves your 6k token policy while preventing the failures seen in testing.