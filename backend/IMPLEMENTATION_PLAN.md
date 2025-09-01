# Implementation Plan - Critical Adapter Fixes

Based on the detailed code review, here's the refined plan addressing the root causes:

## Priority 1 - Critical Fixes (Immediate Impact)

### A. Fix Vertex Ungrounded Retry Token Budget Bug
**Root Cause:** Retry uses smaller token budget than first attempt
**Location:** `backend/app/llm/adapters/vertex_adapter.py` - `complete()` method

**Changes:**
1. Capture actual first-attempt budget after `_create_generation_config_step1()`
2. Force retry to use `max(first_attempt_max * 2, 3000)` tokens
3. Add metadata fields: `first_attempt_max_tokens`, `retry_max_tokens`

**Unified Diff:**
```diff
*** a/app/llm/adapters/vertex_adapter.py
--- b/app/llm/adapters/vertex_adapter.py
@@
-        else:
-            # UNGROUNDED path (single step prose). Build step-1 config and call once, then optional retry
-            generation_config = self._create_generation_config_step1(req)
+        else:
+            # UNGROUNDED path (single step prose). Build step-1 config and call once, then optional retry
+            generation_config = self._create_generation_config_step1(req)
+            # Track real first-attempt budget for decisive retry sizing
+            first_attempt_max = getattr(generation_config, "max_output_tokens", None) or getattr(generation_config, "max_tokens", None)
+            metadata["first_attempt_max_tokens"] = first_attempt_max
@@
-            if not text:
-                # Retry with higher tokens and text/plain to avoid multi-part serialization issues
-                retry_tokens = max(getattr(req, "max_tokens", 500) * 2, 2000)
-                retry_cfg = gm.GenerationConfig(
-                    temperature=max(0.5, getattr(req, "temperature", 0.7) - 0.2),
-                    top_p=0.95,
-                    max_output_tokens=retry_tokens,
-                    response_mime_type="text/plain"
-                )
+            if not text:
+                # Retry with a *larger* budget than attempt #1 and force text/plain
+                # Cap at model's max to avoid MAX_TOKENS loops
+                model_max = 8192  # Gemini 1.5 Pro max, adjust per model
+                retry_tokens = min(max(int((first_attempt_max or 1500) * 2), 3000), model_max)
+                metadata["retry_max_tokens"] = retry_tokens
+                metadata["retry_reason"] = getattr(resp, "finish_reason", "no_parts")  # Track why we retried
+                metadata["model_max_tokens"] = model_max  # For visibility
+                retry_cfg = gm.GenerationConfig(
+                    temperature=max(0.5, getattr(req, "temperature", 0.7) - 0.2),
+                    top_p=0.95,
+                    max_output_tokens=retry_tokens,
+                    response_mime_type="text/plain"
+                )
```

### B. Add Candidate-Level Citation Scan
**Root Cause:** Citations live at `candidate.citationMetadata`, not inside `groundingMetadata`
**Location:** `backend/app/llm/adapters/vertex_adapter.py` - `_extract_vertex_citations()`

**Changes:**
1. Scan `candidate.citationMetadata` / `candidate.citation_metadata` (sibling of groundingMetadata)
2. Extract direct URIs when present
3. JOIN via sourceId when only IDs available
4. Keep existing groundingMetadata scan

**Unified Diff:**
```diff
*** a/app/llm/adapters/vertex_adapter.py
--- b/app/llm/adapters/vertex_adapter.py
@@ _extract_vertex_citations()
-        # Log forensics if tools called but no citations
+        # NEW: Candidate-level citationMetadata scan (sibling of groundingMetadata)
+        for cand in cands:
+            try:
+                cand_dict = {}
+                # Prefer model_dump() for typed genai objects
+                if hasattr(cand, "model_dump"):
+                    cand_dict = cand.model_dump()
+                else:
+                    cand_dict = dict(cand) if hasattr(cand, "__iter__") else {k: getattr(cand, k) for k in dir(cand) if not k.startswith("_")}
+            except Exception:
+                cand_dict = {}
+            cmeta = (cand_dict.get("citationMetadata")
+                     or cand_dict.get("citation_metadata")
+                     or {})
+            if isinstance(cmeta, dict):
+                for ci in cmeta.get("citations", []) or []:
+                    cd = ci if isinstance(ci, dict) else {}
+                    url = cd.get("uri") or cd.get("url")
+                    if url:
+                        _add(url, title=cd.get("title",""), snippet=cd.get("snippet") or cd.get("text") or "", raw=cd)
+                    else:
+                        # If an id/index is present, try joining via source_map that we built above
+                        sid = cd.get("sourceId") or cd.get("source_index")
+                        if sid is not None:
+                            sd = source_id_map.get(str(sid))
+                            if sd:
+                                u = (sd.get("url") or sd.get("uri") or sd.get("pageUrl") or sd.get("sourceUrl")
+                                     or (sd.get("web") or {}).get("url") or (sd.get("web") or {}).get("uri"))
+                                if u:
+                                    _add(u, title=sd.get("title",""), snippet=sd.get("snippet") or sd.get("text") or sd.get("summary") or "", raw=sd)
+
+        # Log forensics if tools called but no citations
```

### C. Allow Vertex SDK Grounded Path
**Root Cause:** Hard-fail prevents testing alternate citation shapes
**Location:** `backend/app/llm/adapters/vertex_adapter.py` - `complete()` method

**Changes:**
1. Change `GROUNDING_REQUIRES_GENAI` from error to warning
2. Allow fallthrough to `_step1_grounded()` with SDK
3. Enables A/B testing of citation shapes

**Unified Diff:**
```diff
*** a/app/llm/adapters/vertex_adapter.py
--- b/app/llm/adapters/vertex_adapter.py
@@
-        # CRITICAL: Fail-closed for grounded requests without google-genai
-        # The vertexai SDK fallback doesn't properly support grounding
-        if is_grounded and not self.use_genai:
-            error_msg = (
-                "GROUNDING_REQUIRES_GENAI: Grounded requests require google-genai client. "
-                f"Current state: GENAI_AVAILABLE={GENAI_AVAILABLE}, use_genai={self.use_genai}. "
-                "To fix: pip install google-genai>=0.8.3 and ensure VERTEX_USE_GENAI_CLIENT != 'false'"
-            )
-            logger.error(f"[VERTEX_GROUNDING] {error_msg}")
-            raise ValueError(error_msg)
+        # If google-genai is unavailable, *warn* and use the Vertex SDK Step-1 instead.
+        # This lets us A/B response shapes and often surfaces citedSources/citations.
+        if is_grounded and not self.use_genai:
+            logger.warning("[VERTEX_GROUNDING] google-genai disabled; using Vertex SDK grounded path (Tool.from_google_search_retrieval)")
```

## Priority 2 - Error Handling & Resilience

### Error Handling Strategy

#### JSON Mode Parsing
**Strict where it matters:**

1. **When json_mode=true:**
   - Parse response as JSON
   - If invalid → fail-closed with `OUTPUT_JSON_INVALID`
   - Include compact parse error + 200-char response preview
   - REQUIRED grounding still enforced afterward

2. **When json_mode=false:**
   - Don't parse; treat body as text
   - Continue processing

**Implementation:**
```python
if json_mode:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        preview = text[:200] if text else "(empty)"
        metadata["json_parse_error"] = str(e)[:100]
        metadata["response_preview"] = preview
        raise ValueError(f"OUTPUT_JSON_INVALID: {str(e)[:50]}... Preview: {preview}")
else:
    # Treat as text, no parsing required
    parsed = text
```

#### Evidence Rules

1. **REQUIRED Mode:**
   - **Normative rule:** Step-1 must show non-empty search evidence AND final includes citations referencing those results; else fail
   - If tools ran but no citations after extractor → raise `GROUNDING_REQUIRED_FAILED`
   - Router already enforces this post-validation
   - Include `citations_audit` in metadata for debugging
   - Note: OpenAI REQUIRED limited by model support (router fail-closes when unsupported)

2. **AUTO Mode:**
   - Proceed even if no citations found
   - Set `why_not_grounded` field
   - Attach `citations_audit` for visibility

**Implementation:**
```python
if grounding_mode == "REQUIRED" and tools_invoked and not citations:
    metadata["citations_audit"] = audit_data
    raise ValueError("GROUNDING_REQUIRED_FAILED: Tools invoked but no citations extracted")
elif grounding_mode == "AUTO" and tools_invoked and not citations:
    metadata["why_not_grounded"] = "tools_invoked_no_citations"
    metadata["citations_audit"] = audit_data
```

#### Extractor Resilience

1. **Safe field access:**
   - Guard every read with `.get()`
   - Tolerate both camelCase/snake_case
   - Handle SDK models with `model_dump()` or attr-walk fallback

2. **Type handling:**
```python
def _safe_get(obj, *keys):
    """Try multiple key variations (camelCase, snake_case)"""
    for key in keys:
        if hasattr(obj, key):
            return getattr(obj, key)
        elif isinstance(obj, dict):
            # Try exact key
            if key in obj:
                return obj[key]
            # Try case variations
            snake = _to_snake(key)
            camel = _to_camel(key)
            for variant in [key, snake, camel]:
                if variant in obj:
                    return obj[variant]
    return None

def _to_dict_safe(obj):
    """Convert SDK objects to dict safely"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    elif hasattr(obj, "__dict__"):
        return obj.__dict__
    elif hasattr(obj, "__iter__") and not isinstance(obj, str):
        try:
            return dict(obj)
        except:
            pass
    # Fallback: walk attributes
    result = {}
    for key in dir(obj):
        if not key.startswith("_"):
            try:
                result[key] = getattr(obj, key)
            except:
                pass
    return result
```

3. **Text-harvest fallback:**
   - When all structured pools empty but tools ran
   - Run text-harvest with `source_type="text_harvest"`
   - Still let REQUIRED fail-closed after harvest attempt

#### Forensics & Audit

**Always include `citations_audit` with:**
- Found keys at each level
- 1-2 sampled items (truncated to keep small)
- `candidate_keys` preview
- Keep payloads compact (<1KB)

**Implementation:**
```python
def _build_citations_audit(resp, citations, tools_invoked):
    audit = {
        "tools_invoked": tools_invoked,
        "citations_found": len(citations),
        "candidate_count": len(getattr(resp, "candidates", [])),
        "keys_found": {},
        "samples": {}
    }
    
    if hasattr(resp, "candidates") and resp.candidates:
        c0 = resp.candidates[0]
        # Candidate-level keys
        audit["keys_found"]["candidate"] = [k for k in dir(c0) if not k.startswith("_")][:10]
        
        # Sample grounding metadata
        gm = _safe_get(c0, "grounding_metadata", "groundingMetadata")
        if gm:
            gm_dict = _to_dict_safe(gm)
            audit["keys_found"]["grounding_metadata"] = list(gm_dict.keys())[:10]
            # Sample one citation if present (capped for PII safety)
            if "citations" in gm_dict and gm_dict["citations"]:
                sample = str(gm_dict["citations"][0])[:100]  # Max 100 chars
                # Remove any potential PII patterns
                import re
                sample = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', sample)
                sample = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', sample)
                audit["samples"]["citation"] = sample
        
        # Sample citation metadata
        cm = _safe_get(c0, "citationMetadata", "citation_metadata")
        if cm:
            cm_dict = _to_dict_safe(cm)
            audit["keys_found"]["citation_metadata"] = list(cm_dict.keys())[:10]
    
    # Ensure total audit size < 1KB for log safety
    import json
    audit_json = json.dumps(audit)
    if len(audit_json) > 1024:
        # Truncate samples if too large
        audit["samples"] = {"truncated": "Size limit exceeded"}
    
    return audit
```

## Priority 3 - Performance Optimizations

### Redirect Resolution Cache

**LRU cache with TTL for redirect resolution:**
- Size: 5-10k entries
- TTL: 24 hours
- Key: Normalized redirect URL → `{resolved_url, status}`
- Warm via background lazy writes
- Evict on 4xx/5xx responses
- Mirrors provider-version single-flight mindset

**Implementation:**
```python
from functools import lru_cache
from datetime import datetime, timedelta
import hashlib

class RedirectCache:
    def __init__(self, max_size=5000, ttl_hours=24):
        self.cache = {}  # {url_hash: (resolved_url, status, expiry)}
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
        self.access_order = []  # For LRU eviction
    
    def _normalize_url(self, url):
        """Strip UTM params, normalize protocol, lowercase domain"""
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(url.lower())
        # Remove tracking params
        params = parse_qs(parsed.query)
        cleaned_params = {k: v for k, v in params.items() 
                         if not k.startswith(('utm_', 'fbclid', 'gclid'))}
        cleaned_query = urlencode(cleaned_params, doseq=True)
        return urlunparse(parsed._replace(query=cleaned_query))
    
    def get(self, url):
        normalized = self._normalize_url(url)
        url_hash = hashlib.md5(normalized.encode()).hexdigest()
        
        if url_hash in self.cache:
            resolved, status, expiry = self.cache[url_hash]
            if datetime.now() < expiry:
                # Move to end for LRU
                self.access_order.remove(url_hash)
                self.access_order.append(url_hash)
                return resolved, status
            else:
                # Expired
                del self.cache[url_hash]
                self.access_order.remove(url_hash)
        return None, None
    
    def set(self, url, resolved_url, status):
        # Evict on errors
        if status >= 400:
            return
            
        normalized = self._normalize_url(url)
        url_hash = hashlib.md5(normalized.encode()).hexdigest()
        
        # LRU eviction if at capacity
        if len(self.cache) >= self.max_size and url_hash not in self.cache:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
        
        expiry = datetime.now() + self.ttl
        self.cache[url_hash] = (resolved_url, status, expiry)
        if url_hash in self.access_order:
            self.access_order.remove(url_hash)
        self.access_order.append(url_hash)

# Global instance
redirect_cache = RedirectCache()
```

### Extraction Memoization

**Cache extracted citations by content hash:**
- Key: Hash of `candidate.groundingMetadata` + `candidate.citationMetadata`
- Value: Normalized citations list
- TTL: 1-6 hours
- Use stable hash of `model_dump()` when available

**Implementation:**
```python
import hashlib
import json
from datetime import datetime, timedelta

class ExtractionCache:
    def __init__(self, ttl_hours=3):
        self.cache = {}  # {content_hash: (citations, expiry)}
        self.ttl = timedelta(hours=ttl_hours)
    
    def _compute_hash(self, candidate):
        """Stable hash of grounding + citation metadata"""
        content = {}
        
        # Try model_dump first (cheapest for SDK objects)
        if hasattr(candidate, "model_dump"):
            try:
                full_dump = candidate.model_dump()
                content["grounding"] = full_dump.get("groundingMetadata", {})
                content["citation"] = full_dump.get("citationMetadata", {})
            except:
                pass
        
        # Fallback to attribute access
        if not content:
            gm = getattr(candidate, "grounding_metadata", None) or \
                 getattr(candidate, "groundingMetadata", None)
            cm = getattr(candidate, "citation_metadata", None) or \
                 getattr(candidate, "citationMetadata", None)
            
            if gm:
                content["grounding"] = _to_dict_safe(gm)
            if cm:
                content["citation"] = _to_dict_safe(cm)
        
        # Stable JSON serialization for hashing
        json_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def get(self, candidate):
        try:
            content_hash = self._compute_hash(candidate)
            if content_hash in self.cache:
                citations, expiry = self.cache[content_hash]
                if datetime.now() < expiry:
                    return citations
                else:
                    del self.cache[content_hash]
        except:
            pass
        return None
    
    def set(self, candidate, citations):
        try:
            content_hash = self._compute_hash(candidate)
            expiry = datetime.now() + self.ttl
            self.cache[content_hash] = (citations, expiry)
        except:
            pass

# Global instance
extraction_cache = ExtractionCache()
```

### I/O Caps & Concurrency

**Limit resolution attempts per response:**
- Max 8 URLs per response
- Async pool with concurrency=4
- Timeout per resolution: 2 seconds

**Implementation:**
```python
import asyncio
from typing import List, Dict

async def resolve_citations_batch(citations: List[Dict], max_urls=8, concurrency=4, total_timeout=3.0):
    """Resolve citations with I/O caps and total time budget"""
    import time
    start_time = time.time()
    
    # Dedupe on normalized URL first
    seen_normalized = set()
    unique_citations = []
    
    for cit in citations[:max_urls]:  # Cap at max_urls
        url = cit.get("url", "")
        normalized = _normalize_url(url)
        if normalized not in seen_normalized:
            seen_normalized.add(normalized)
            unique_citations.append(cit)
    
    # Create async pool
    semaphore = asyncio.Semaphore(concurrency)
    
    async def resolve_one(citation):
        async with semaphore:
            # Check total time budget
            if time.time() - start_time > total_timeout:
                citation["resolved_url"] = citation.get("url", "")
                citation["resolution_status"] = 408  # Timeout
                return citation
                
            url = citation.get("url", "")
            
            # Check cache first
            resolved, status = redirect_cache.get(url)
            if resolved:
                citation["resolved_url"] = resolved
                citation["resolution_status"] = status
                return citation
            
            # Resolve with timeout (per-URL timeout)
            remaining_time = total_timeout - (time.time() - start_time)
            per_url_timeout = min(2.0, max(0.1, remaining_time))
            
            try:
                resolved_url = await asyncio.wait_for(
                    resolve_citation_url(url),
                    timeout=per_url_timeout
                )
                redirect_cache.set(url, resolved_url, 200)
                citation["resolved_url"] = resolved_url
                citation["resolution_status"] = 200
            except asyncio.TimeoutError:
                citation["resolved_url"] = url  # Keep original
                citation["resolution_status"] = 408  # Timeout
            except Exception as e:
                citation["resolved_url"] = url
                citation["resolution_status"] = 500
                citation["resolution_error"] = str(e)[:50]
            
            return citation
    
    # Resolve all in parallel
    tasks = [resolve_one(cit) for cit in unique_citations]
    resolved = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out exceptions
    return [r for r in resolved if not isinstance(r, Exception)]
```

### String Work Optimizations

**Normalize and dedupe efficiently:**
- Normalize/UTM-strip once per URL
- Dedupe with set on normalized URLs
- Cache computed domains
- Avoid recomputing domains repeatedly

**Implementation:**
```python
from urllib.parse import urlparse
import functools

@functools.lru_cache(maxsize=1000)
def extract_domain(url: str) -> str:
    """Extract and cache domain from URL"""
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except:
        return ""

def dedupe_citations(citations: List[Dict]) -> List[Dict]:
    """Efficiently dedupe citations by normalized URL"""
    seen = set()
    deduped = []
    
    for cit in citations:
        url = cit.get("url", "")
        normalized = _normalize_url(url)
        
        if normalized not in seen:
            seen.add(normalized)
            # Pre-compute and cache domain
            cit["source_domain"] = extract_domain(normalized)
            deduped.append(cit)
    
    return deduped
```

### Token Budget Optimizations

**For Gemini ungrounded retries (already in plan):**
- Guarantee: `retry_max_tokens ≥ first_attempt_max_tokens`
- Jump decisively: `max(first_attempt_max * 2, 3000)`
- Emit both in metadata: `first_attempt_max_tokens`, `retry_max_tokens`

This is already covered in Priority 1, Section A, but reinforced here:

```python
# From Priority 1 implementation
if not text:
    # Retry with a *larger* budget than attempt #1
    retry_tokens = max(int((first_attempt_max or 1500) * 2), 3000)
    metadata["retry_max_tokens"] = retry_tokens
    # ... rest of retry logic
```

## Priority 4 - Migration Strategy (Feature Flags & Rollout)

### Feature Flag Configuration

**Narrow, revertible flags for safe rollout:**

1. **`EXTRACTOR_V2=true`**
   - Enables candidate-level citationMetadata scan
   - Default: `false` (use legacy extraction only)
   - Allows instant revert to previous extractor

2. **`VERTEX_TEXT_HARVEST=true`**
   - Enables last-resort URL harvest from assistant text
   - Default: `false` (structured extraction only)
   - Safety net for edge cases

3. **`VERTEX_USE_GENAI_CLIENT=true/false`**
   - Choose google-genai vs Vertex SDK for Step-1
   - Don't hard-fail when `false`; warn and use SDK
   - Default: `true` (prefer google-genai)

4. **`UNGROUNDED_RETRY_POLICY=v2`**
   - Activates "never smaller than attempt #1" rule
   - Default: `v1` (legacy retry behavior)
   - Values: `v1` (legacy), `v2` (improved)

**Implementation:**
```python
import os
from typing import Optional

class FeatureFlags:
    """Feature flags for migration strategy"""
    
    def __init__(self):
        # Load from environment with defaults
        self.extractor_v2 = os.getenv("EXTRACTOR_V2", "false").lower() == "true"
        self.vertex_text_harvest = os.getenv("VERTEX_TEXT_HARVEST", "false").lower() == "true"
        self.vertex_use_genai = os.getenv("VERTEX_USE_GENAI_CLIENT", "true").lower() == "true"
        self.ungrounded_retry_policy = os.getenv("UNGROUNDED_RETRY_POLICY", "v1").lower()
        
        # DB-backed flags for percentage rollout (if needed)
        self._db_overrides = {}
    
    def check_flag(self, flag_name: str, tenant_id: Optional[str] = None, 
                   batch_id: Optional[str] = None) -> bool:
        """Check flag with tenant/batch gating"""
        # Check DB overrides first (for percentage rollout)
        if tenant_id or batch_id:
            override = self._get_db_override(flag_name, tenant_id, batch_id)
            if override is not None:
                return override
        
        # Fall back to environment flags
        return getattr(self, flag_name.lower(), False)
    
    def _get_db_override(self, flag_name: str, tenant_id: str, batch_id: str) -> Optional[bool]:
        """Get DB-backed flag override for percentage rollout"""
        # Pseudo-code for DB lookup
        # query = "SELECT enabled FROM feature_flags WHERE flag_name = ? AND (tenant_id = ? OR batch_id = ?)"
        # result = db.execute(query, [flag_name, tenant_id, batch_id])
        # return result.enabled if result else None
        
        # For now, use hash-based rollout simulation
        if flag_name in self._db_overrides:
            rollout_pct = self._db_overrides[flag_name]
            # Hash tenant/batch to deterministic value
            hash_val = hash(f"{tenant_id}:{batch_id}") % 100
            return hash_val < rollout_pct
        return None
    
    def set_rollout_percentage(self, flag_name: str, percentage: int):
        """Set rollout percentage for a flag (0-100)"""
        self._db_overrides[flag_name] = percentage

# Global instance
feature_flags = FeatureFlags()
```

### Integration Points

**In `_extract_vertex_citations()`:**
```python
def _extract_vertex_citations(resp) -> List[Dict]:
    # ... existing extraction logic ...
    
    # NEW: Candidate-level scan (gated by flag)
    if feature_flags.extractor_v2:
        for cand in cands:
            # Candidate-level citationMetadata scan
            # ... implementation from Section B ...
    
    # NEW: Text harvest fallback (gated by flag)
    if feature_flags.vertex_text_harvest and not citations:
        # Text harvest implementation
        # ... implementation from Section D ...
    
    return citations
```

**In `complete()` method for SDK choice:**
```python
# Updated logic (from Section C)
if is_grounded:
    # Check flag instead of hard-coded value
    if not feature_flags.vertex_use_genai:
        logger.warning("[VERTEX_GROUNDING] google-genai disabled by flag; using Vertex SDK")
        # Use SDK path...
    else:
        # Use google-genai path...
```

**In ungrounded retry logic:**
```python
if not text:
    if feature_flags.ungrounded_retry_policy == "v2":
        # NEW: Never smaller than attempt #1
        retry_tokens = max(int((first_attempt_max or 1500) * 2), 3000)
    else:
        # LEGACY: Old retry logic
        retry_tokens = max(getattr(req, "max_tokens", 500) * 2, 2000)
    
    metadata["retry_policy"] = feature_flags.ungrounded_retry_policy
    metadata["retry_max_tokens"] = retry_tokens
```

### Rollout Strategy

**Phased rollout plan with SLO gates:**

1. **Phase 0: Dark Launch (0%)**
   - All flags `false`/`v1`
   - Deploy code without activation
   - Monitor for deployment issues

2. **Phase 1: Canary (5%)**
   - Enable EXTRACTOR_V2 first (without text harvest)
   - Gate by tenant_id or batch_id hash
   - Monitor metrics: citations_count, extraction_time, errors
   - **SLO Gates to proceed:**
     - Citation success rate ≥ baseline - 5% (grounded calls)
     - REQUIRED fail rate ≤ baseline + 2%
     - If either fails for 30 minutes → auto-rollback

3. **Phase 2: Limited (50%)**
   - Expand EXTRACTOR_V2 to 50%
   - Enable VERTEX_TEXT_HARVEST only if V2 alone insufficient
   - A/B comparison of old vs new
   - Validate citation quality and performance

4. **Phase 3: General Availability (100%)**
   - Enable for all traffic
   - Keep flags for instant revert
   - Monitor for 1-2 weeks before removing old code
   - Capture SDK vs genai shape diff for long-term preference

**Rollout implementation:**
```python
# Example rollout progression
def apply_rollout_phase(phase: str):
    """Apply rollout phase configuration"""
    if phase == "dark":
        feature_flags.set_rollout_percentage("extractor_v2", 0)
        feature_flags.set_rollout_percentage("vertex_text_harvest", 0)
        feature_flags.ungrounded_retry_policy = "v1"
    
    elif phase == "canary":
        feature_flags.set_rollout_percentage("extractor_v2", 5)
        feature_flags.set_rollout_percentage("vertex_text_harvest", 5)
        # Fix: Use correct flag name
        feature_flags.ungrounded_retry_policy = "v2"  # Enable for 5% via hash
    
    elif phase == "limited":
        feature_flags.set_rollout_percentage("extractor_v2", 50)
        feature_flags.set_rollout_percentage("vertex_text_harvest", 50)
        # 50% get v2 retry policy
        feature_flags.ungrounded_retry_policy = "v2"  # Can use hash-based rollout
    
    elif phase == "ga":
        feature_flags.set_rollout_percentage("extractor_v2", 100)
        feature_flags.set_rollout_percentage("vertex_text_harvest", 100)
        feature_flags.ungrounded_retry_policy = "v2"
```

### Monitoring & Rollback

**Key metrics to track:**
- Citation extraction rate (citations_count > 0)
- Extraction latency (p50, p95, p99)
- Error rates by flag combination
- Token usage (first_attempt vs retry)

**Instant rollback:**
```python
def emergency_rollback():
    """Instantly revert all flags to safe defaults"""
    os.environ["EXTRACTOR_V2"] = "false"
    os.environ["VERTEX_TEXT_HARVEST"] = "false"
    os.environ["VERTEX_USE_GENAI_CLIENT"] = "true"
    os.environ["UNGROUNDED_RETRY_POLICY"] = "v1"
    
    # Reload flags
    global feature_flags
    feature_flags = FeatureFlags()
    
    logger.critical("EMERGENCY ROLLBACK: All feature flags reverted to safe defaults")
```

### Configuration Management

**Environment variables (primary):**
```bash
# .env or deployment config
EXTRACTOR_V2=false
VERTEX_TEXT_HARVEST=false
VERTEX_USE_GENAI_CLIENT=true
UNGROUNDED_RETRY_POLICY=v1
```

**Database schema (for percentage rollout):**
```sql
CREATE TABLE feature_flags (
    flag_name VARCHAR(50) PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE,
    rollout_percentage INTEGER DEFAULT 0,
    tenant_whitelist TEXT,  -- JSON array of tenant IDs
    batch_whitelist TEXT,   -- JSON array of batch IDs
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

This migration strategy aligns with the PRD's upgrade-seams philosophy and provides safe, reversible deployment with granular control.

## Priority 5 - Monitoring & Alerts

### Per-Run Metrics (Emit to Neon/BigQuery)

**Analytics Sink Note:** Neon is source-of-truth for operational metrics. BigQuery handles long-term analytics per the engineering guide. Both receive grounded/attestation fields to avoid divergent dashboards.

**Core metrics to collect on every run:**

```python
from datetime import datetime
from typing import Dict, List, Optional
import asyncpg  # For Neon Postgres

class MetricsCollector:
    """Collect and emit metrics for monitoring"""
    
    def __init__(self, neon_conn_str: str):
        self.neon_conn_str = neon_conn_str
        self.metrics_buffer = []
        self.batch_size = 100
    
    async def collect_run_metrics(self, 
                                  response: Any,
                                  metadata: Dict,
                                  citations: List[Dict],
                                  request: Any) -> Dict:
        """Collect metrics from a single run"""
        
        # Extract citation source types
        source_types = {}
        for cit in citations:
            source_type = cit.get("source_type", "web")
            source_types[source_type] = source_types.get(source_type, 0) + 1
        
        # Extract top domains
        domains = {}
        for cit in citations:
            domain = cit.get("source_domain", "")
            if domain:
                domains[domain] = domains.get(domain, 0) + 1
        top_domains = sorted(domains.items(), key=lambda x: x[1], reverse=True)[:3]
        
        metrics = {
            # Grounding metrics
            "grounded_effective": metadata.get("grounded_effective", False),
            "tool_call_count": metadata.get("tool_call_count", 0),
            "tool_result_count": metadata.get("tool_result_count", 0),
            
            # Citation metrics
            "citations_count": len(citations),
            "citations_web": source_types.get("web", 0),
            "citations_text_harvest": source_types.get("text_harvest", 0),
            "citations_redirect_only": source_types.get("redirect", 0),
            "top_domain_1": top_domains[0][0] if len(top_domains) > 0 else None,
            "top_domain_2": top_domains[1][0] if len(top_domains) > 1 else None,
            "top_domain_3": top_domains[2][0] if len(top_domains) > 2 else None,
            
            # Failure tracking
            "why_not_grounded": metadata.get("why_not_grounded"),
            "citations_audit_present": "citations_audit" in metadata,
            
            # Token budgets (ungrounded)
            "first_attempt_max_tokens": metadata.get("first_attempt_max_tokens"),
            "retry_max_tokens": metadata.get("retry_max_tokens"),
            
            # Performance metrics
            "latency_ms": metadata.get("latency_ms"),
            "token_usage": metadata.get("token_usage"),
            "response_size": len(str(response)) if response else 0,
            
            # Context
            "provider": metadata.get("provider", "vertex"),
            "model": metadata.get("model"),
            "grounding_mode": getattr(request, "grounding_mode", "AUTO"),
            "tenant_id": getattr(request, "tenant_id", None),
            "batch_id": getattr(request, "batch_id", None),
            "timestamp": datetime.utcnow(),
            
            # Runtime flags (for correlation during canary)
            "runtime_flags": {
                "extractor_v2": feature_flags.extractor_v2,
                "vertex_text_harvest": feature_flags.vertex_text_harvest,
                "vertex_use_genai": feature_flags.vertex_use_genai,
                "ungrounded_retry_policy": feature_flags.ungrounded_retry_policy
            },
            
            # Derived fields
            "tools_invoked_no_citations": tools_invoked and citations_count == 0,
            "retry_reason": metadata.get("retry_reason"),
            
            # Grounding tracking (mirror PRD distinction)
            "grounding_attempted": metadata.get("grounding_attempted", False),
            "grounded_effective": metadata.get("grounded_effective", False),
            
            # Two-step attestation (Gemini)
            "two_step_used": metadata.get("two_step_used", False),
            "step2_tools_invoked": metadata.get("step2_tools_invoked", False),
            "step2_source_ref": metadata.get("step2_source_ref"),  # SHA256 of step1
            
            # Citation source breakdown (for OpenAI)
            "citations_from_annotations": metadata.get("citations_from_annotations", 0),
            "citations_from_tool_results": metadata.get("citations_from_tool_results", 0),
            
            # ALS propagation check
            "als_nfc_length": len(metadata.get("als_nfc", "")) if metadata.get("als_nfc") else 0,
            "als_sha256_present": bool(metadata.get("als_sha256"))
        }
        
        return metrics
    
    async def emit_metrics(self, metrics: Dict):
        """Emit metrics to Neon Postgres"""
        self.metrics_buffer.append(metrics)
        
        if len(self.metrics_buffer) >= self.batch_size:
            await self._flush_metrics()
    
    async def _flush_metrics(self):
        """Flush metrics buffer to database"""
        if not self.metrics_buffer:
            return
            
        conn = await asyncpg.connect(self.neon_conn_str)
        try:
            await conn.executemany(
                """
                INSERT INTO llm_metrics (
                    timestamp, provider, model, grounded_effective,
                    tool_call_count, tool_result_count, citations_count,
                    citations_web, citations_text_harvest, citations_redirect_only,
                    top_domain_1, top_domain_2, top_domain_3,
                    why_not_grounded, citations_audit_present,
                    first_attempt_max_tokens, retry_max_tokens,
                    latency_ms, token_usage, response_size,
                    grounding_mode, tenant_id, batch_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 
                         $11, $12, $13, $14, $15, $16, $17, $18, $19, 
                         $20, $21, $22, $23)
                """,
                [(m["timestamp"], m["provider"], m["model"], m["grounded_effective"],
                  m["tool_call_count"], m["tool_result_count"], m["citations_count"],
                  m["citations_web"], m["citations_text_harvest"], m["citations_redirect_only"],
                  m["top_domain_1"], m["top_domain_2"], m["top_domain_3"],
                  m["why_not_grounded"], m["citations_audit_present"],
                  m["first_attempt_max_tokens"], m["retry_max_tokens"],
                  m["latency_ms"], m["token_usage"], m["response_size"],
                  m["grounding_mode"], m["tenant_id"], m["batch_id"])
                 for m in self.metrics_buffer]
            )
            self.metrics_buffer.clear()
        finally:
            await conn.close()

# Global instance
metrics_collector = MetricsCollector(os.getenv("NEON_CONN_STR"))
```

### Database Schema (Neon Postgres)

```sql
CREATE TABLE llm_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100),
    
    -- Grounding metrics
    grounded_effective BOOLEAN,
    tool_call_count INTEGER DEFAULT 0,
    tool_result_count INTEGER DEFAULT 0,
    
    -- Citation metrics
    citations_count INTEGER DEFAULT 0,
    citations_web INTEGER DEFAULT 0,
    citations_text_harvest INTEGER DEFAULT 0,
    citations_redirect_only INTEGER DEFAULT 0,
    top_domain_1 VARCHAR(100),
    top_domain_2 VARCHAR(100),
    top_domain_3 VARCHAR(100),
    
    -- Failure tracking
    why_not_grounded VARCHAR(100),
    citations_audit_present BOOLEAN DEFAULT FALSE,
    
    -- Token budgets
    first_attempt_max_tokens INTEGER,
    retry_max_tokens INTEGER,
    
    -- Performance
    latency_ms INTEGER,
    token_usage INTEGER,
    response_size INTEGER,
    
    -- Context
    grounding_mode VARCHAR(20),
    tenant_id VARCHAR(100),
    batch_id VARCHAR(100),
    
    -- Indexes for queries
    INDEX idx_timestamp (timestamp),
    INDEX idx_provider_model (provider, model),
    INDEX idx_grounded (grounded_effective),
    INDEX idx_tenant (tenant_id)
);
```

### Derived Metrics & Dashboards

**Key derived metrics to calculate:**

```sql
-- Citation success rate (per provider/model)
SELECT 
    provider,
    model,
    COUNT(*) FILTER (WHERE grounded_effective AND citations_count > 0) * 100.0 / 
    NULLIF(COUNT(*) FILTER (WHERE grounded_effective), 0) AS citation_success_rate
FROM llm_metrics
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY provider, model;

-- REQUIRED failure breakdown
SELECT 
    why_not_grounded,
    COUNT(*) as failure_count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as failure_percentage
FROM llm_metrics
WHERE grounding_mode = 'REQUIRED' 
    AND grounded_effective = FALSE
    AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY why_not_grounded;

-- Authority share (tier-1 domains)
WITH tier1_domains AS (
    SELECT * FROM (VALUES 
        ('nih.gov'), ('nature.com'), ('sciencedirect.com'),
        ('pubmed.ncbi.nlm.nih.gov'), ('who.int')
    ) AS t(domain)
)
SELECT 
    COUNT(*) FILTER (WHERE top_domain_1 IN (SELECT domain FROM tier1_domains)) * 100.0 / 
    NULLIF(COUNT(*), 0) AS tier1_percentage
FROM llm_metrics
WHERE citations_count > 0
    AND timestamp > NOW() - INTERVAL '24 hours';

-- TLD mix for ALS efficacy
SELECT 
    SUBSTRING(top_domain_1 FROM '\.([^.]+)$') AS tld,
    COUNT(*) as count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
FROM llm_metrics
WHERE top_domain_1 IS NOT NULL
    AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY tld
ORDER BY count DESC;

-- Extractor error rate
SELECT 
    provider,
    model,
    COUNT(*) FILTER (WHERE citations_audit_present) * 100.0 / 
    NULLIF(COUNT(*) FILTER (WHERE grounded_effective), 0) AS error_rate
FROM llm_metrics
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY provider, model;

-- Redirect burden
SELECT 
    AVG(citations_redirect_only::FLOAT / NULLIF(citations_count, 0)) * 100 AS redirect_percentage,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) 
        FILTER (WHERE citations_redirect_only > 0) AS resolver_p95_ms
FROM llm_metrics
WHERE citations_count > 0
    AND timestamp > NOW() - INTERVAL '1 hour';
```

### Alert Configuration

**Implement alerting rules:**

```python
class AlertManager:
    """Manage alerts based on metrics thresholds"""
    
    def __init__(self, slack_webhook: str = None, pagerduty_key: str = None):
        self.slack_webhook = slack_webhook
        self.pagerduty_key = pagerduty_key
        self.alert_state = {}  # Track alert state to avoid spam
    
    async def check_alerts(self, conn: asyncpg.Connection):
        """Check metrics and trigger alerts if needed"""
        
        # Alert 1: Citation success rate drop
        result = await conn.fetchone("""
            SELECT provider, model, 
                   COUNT(*) FILTER (WHERE grounded_effective AND citations_count > 0) * 100.0 / 
                   NULLIF(COUNT(*) FILTER (WHERE grounded_effective), 0) AS success_rate
            FROM llm_metrics
            WHERE timestamp > NOW() - INTERVAL '60 minutes'
            GROUP BY provider, model
            HAVING COUNT(*) FILTER (WHERE grounded_effective) > 10
        """)
        
        for row in result:
            baseline = self.alert_state.get(f"baseline_{row['provider']}_{row['model']}", 80)
            if row['success_rate'] < baseline * 0.8:  # 20% drop
                await self.page(
                    f"Citation success rate dropped to {row['success_rate']:.1f}% "
                    f"for {row['provider']}/{row['model']} (baseline: {baseline}%)"
                )
        
        # Alert 2: REQUIRED failure rate
        result = await conn.fetchone("""
            SELECT COUNT(*) * 100.0 / NULLIF(
                (SELECT COUNT(*) FROM llm_metrics 
                 WHERE grounding_mode = 'REQUIRED' 
                 AND timestamp > NOW() - INTERVAL '60 minutes'), 0
            ) AS failure_rate
            FROM llm_metrics
            WHERE grounding_mode = 'REQUIRED' 
                AND grounded_effective = FALSE
                AND timestamp > NOW() - INTERVAL '60 minutes'
        """)
        
        if result and result['failure_rate']:
            if result['failure_rate'] > 15:
                await self.page(f"REQUIRED failure rate critical: {result['failure_rate']:.1f}%")
            elif result['failure_rate'] > 5:
                await self.warn(f"REQUIRED failure rate elevated: {result['failure_rate']:.1f}%")
        
        # Alert 3: Extractor exceptions
        result = await conn.fetchone("""
            SELECT COUNT(*) FILTER (WHERE citations_audit_present) * 100.0 / 
                   NULLIF(COUNT(*) FILTER (WHERE grounded_effective), 0) AS error_rate
            FROM llm_metrics
            WHERE timestamp > NOW() - INTERVAL '60 minutes'
        """)
        
        if result and result['error_rate'] and result['error_rate'] > 0.5:
            await self.warn(f"Extractor error rate: {result['error_rate']:.2f}%")
        
        # Alert 4: Resolver performance
        result = await conn.fetchone("""
            SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
                   COUNT(*) FILTER (WHERE latency_ms IS NULL) * 100.0 / COUNT(*) AS error_rate
            FROM llm_metrics
            WHERE citations_redirect_only > 0
                AND timestamp > NOW() - INTERVAL '60 minutes'
        """)
        
        if result:
            if result['p95_ms'] and result['p95_ms'] > 800:
                await self.warn(f"Resolver p95 latency: {result['p95_ms']}ms")
            if result['error_rate'] and result['error_rate'] > 5:
                await self.warn(f"Resolver error rate: {result['error_rate']:.1f}%")
    
    async def warn(self, message: str):
        """Send warning alert"""
        logger.warning(f"[ALERT] {message}")
        if self.slack_webhook:
            # Send to Slack
            pass
    
    async def page(self, message: str):
        """Send critical alert (page)"""
        logger.error(f"[CRITICAL] {message}")
        if self.pagerduty_key:
            # Trigger PagerDuty
            pass
        if self.slack_webhook:
            # Also send to Slack
            pass

# Global instance
alert_manager = AlertManager(
    slack_webhook=os.getenv("SLACK_WEBHOOK"),
    pagerduty_key=os.getenv("PAGERDUTY_KEY")
)
```

### Dashboard Queries

**Grafana/Metabase dashboard queries:**

```sql
-- Real-time citation success rate
SELECT 
    date_trunc('minute', timestamp) AS time,
    provider || '/' || model AS series,
    AVG(CASE WHEN grounded_effective AND citations_count > 0 THEN 100.0 ELSE 0 END) AS success_rate
FROM llm_metrics
WHERE timestamp > NOW() - INTERVAL '6 hours'
GROUP BY time, series
ORDER BY time DESC;

-- Citation source type distribution
SELECT 
    date_trunc('hour', timestamp) AS time,
    SUM(citations_web) AS web,
    SUM(citations_text_harvest) AS text_harvest,
    SUM(citations_redirect_only) AS redirect_only
FROM llm_metrics
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY time
ORDER BY time DESC;

-- Token budget efficiency
SELECT 
    model,
    AVG(first_attempt_max_tokens) AS avg_first_attempt,
    AVG(retry_max_tokens) AS avg_retry,
    COUNT(*) FILTER (WHERE retry_max_tokens IS NOT NULL) * 100.0 / COUNT(*) AS retry_rate
FROM llm_metrics
WHERE timestamp > NOW() - INTERVAL '24 hours'
    AND first_attempt_max_tokens IS NOT NULL
GROUP BY model;
```

This monitoring strategy provides comprehensive visibility into citation extraction performance with actionable alerts.

## Priority 6 - Documentation & Runbooks

### Citation Troubleshooting Runbook

#### Symptom → Checks → Actions Table

| Symptom | Checks | Actions |
|---------|--------|---------|
| **Tools used, citations=0** | • Check `metadata["citations_audit"]["candidate_keys"]`<br>• Look for `citationMetadata` in keys<br>• Verify `tool_call_count > 0` | • Toggle `EXTRACTOR_V2=true`<br>• Check logs for text-harvest attempts<br>• Verify `VERTEX_TEXT_HARVEST=true`<br>• Review `_extract_vertex_citations` debug logs |
| **REQUIRED failing** | • Check `metadata["why_not_grounded"]`<br>• Verify if `tools_invoked=true`<br>• Check `citations_count` | • If `not_supported`: Model doesn't support grounding<br>• If `empty_evidence`: Enable text-harvest<br>• If `extractor_error`: Check citations_audit<br>• Reproduce: See curl command below |
| **Ungrounded empty** | • Check `metadata["first_attempt_max_tokens"]`<br>• Check `metadata["retry_max_tokens"]`<br>• Verify retry ≥ first attempt | • Set `UNGROUNDED_RETRY_POLICY=v2`<br>• Increase base token budget<br>• Check `finish_reason` for MAX_TOKENS<br>• Force text/plain on first attempt |
| **ALS not working** | • Check `top_domain_1/2/3` TLDs<br>• Verify .de/.fr/.uk in citations<br>• Check redirect resolution | • Verify ALS propagation in context<br>• Check citation domain extraction<br>• Review resolver cache hits |

#### Reproducing Issues

**CURL command to reproduce REQUIRED failure:**
```bash
curl -X POST https://api.example.com/v1/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [{"role": "user", "content": "What is longevity?"}],
    "grounded": true,
    "grounding_mode": "REQUIRED",
    "json_mode": true,
    "max_tokens": 1000
  }'
```

**Debug environment variables:**
```bash
export DEBUG_GROUNDING=true
export VERTEX_USE_GENAI_CLIENT=true
export EXTRACTOR_V2=true
export VERTEX_TEXT_HARVEST=true
export UNGROUNDED_RETRY_POLICY=v2
```

### Response Shapes Gallery

#### 1. v1 JOIN Pattern (citationMetadata → citedSources)
```json
{
  "candidates": [{
    "citationMetadata": {
      "citations": [
        {"sourceId": "s1", "startIndex": 0, "endIndex": 45}
      ]
    },
    "groundingMetadata": {
      "citedSources": [
        {
          "id": "s1",
          "title": "Research Paper",
          "uri": "https://example.com/paper.pdf"
        }
      ]
    }
  }]
}
```
**Extractor expects:** JOIN citations[].sourceId → citedSources[].id

#### 2. Legacy groundingAttributions
```json
{
  "candidates": [{
    "grounding_metadata": {
      "grounding_attributions": [
        {
          "title": "Source Title",
          "snippet": "Evidence text",
          "web": {"uri": "https://example.com"}
        }
      ]
    }
  }]
}
```
**Extractor expects:** Direct extraction from grounding_attributions[]

#### 3. Candidate-level citationMetadata (sibling)
```json
{
  "candidates": [{
    "citationMetadata": {
      "citations": [
        {
          "uri": "https://example.com",
          "title": "Direct Citation",
          "snippet": "Evidence"
        }
      ]
    },
    "groundingMetadata": {
      // May be empty or have other data
    }
  }]
}
```
**Extractor expects:** Direct URI extraction, no JOIN needed

#### 4. Loose-harvest pattern (supportingContent)
```json
{
  "candidates": [{
    "groundingMetadata": {
      "supportingContent": [
        {
          "url": "https://example.com",
          "summary": "Content summary"
        }
      ]
    }
  }]
}
```
**Extractor expects:** Fallback extraction from various nested fields

### Quick Playbooks

#### 1. Emergency Rollback (All Flags)
```bash
# Instantly revert to legacy behavior
export EXTRACTOR_V2=false
export VERTEX_TEXT_HARVEST=false
export VERTEX_USE_GENAI_CLIENT=true
export UNGROUNDED_RETRY_POLICY=v1

# Restart service
sudo systemctl restart llm-adapter
```

#### 2. Enable V2 Extractor Only
```bash
# Enable new extraction without other changes
export EXTRACTOR_V2=true
export VERTEX_TEXT_HARVEST=false  # Keep text harvest off

# Monitor for 1 hour
watch -n 60 'psql -c "SELECT citations_count FROM llm_metrics WHERE timestamp > NOW() - INTERVAL '\''1 hour'\''"'
```

#### 3. Force Vertex SDK Path
```bash
# Use Vertex SDK instead of google-genai
export VERTEX_USE_GENAI_CLIENT=false

# Verify in logs
tail -f /var/log/llm-adapter.log | grep "VERTEX_GROUNDING"
```

#### 4. Enable Full V2 Stack
```bash
# Enable all improvements
export EXTRACTOR_V2=true
export VERTEX_TEXT_HARVEST=true
export VERTEX_USE_GENAI_CLIENT=true
export UNGROUNDED_RETRY_POLICY=v2
```

#### 5. Debug Citation Extraction
```bash
# Maximum verbosity for troubleshooting
export DEBUG_GROUNDING=true
export LOG_LEVEL=DEBUG

# Watch citation audit logs
tail -f /var/log/llm-adapter.log | grep -E "(CITATIONS|citations_audit)"
```

### FAQ

#### Q: Why do we keep redirect-only evidence?
**A:** Redirect URLs from Vertex contain valid grounding signals. Dropping them would violate our fail-closed evidence principle. We preserve the redirect URL and attempt resolution, but keep the evidence even if resolution fails. This ensures we never lose grounding attribution.

#### Q: Why is two-step JSON required on Gemini?
**A:** Gemini's grounding tools don't work reliably with `response_mime_type="application/json"` in a single call. The two-step approach:
1. Step 1: Grounded prose with tools enabled → Get citations
2. Step 2: Reshape to JSON without tools → Get structured output

This ensures we capture citations while still delivering JSON to the client.

#### Q: Why is REQUIRED mode fail-closed?
**A:** REQUIRED mode is a contract with the client that responses MUST be grounded. If we can't verify grounding (tools didn't run, no citations found, extractor failed), we must fail the request rather than return ungrounded content. This prevents hallucination in high-stakes applications.

#### Q: What's the difference between EXTRACTOR_V2 and legacy?
**A:** 
- **Legacy (V1):** Only scans `groundingMetadata` object
- **V2:** Also scans candidate-level `citationMetadata` (sibling), handles more schema variants, includes text-harvest fallback

#### Q: When should I use text-harvest fallback?
**A:** Enable `VERTEX_TEXT_HARVEST=true` when:
- Seeing citations in response text but `citations_count=0`
- Google changes schema and structured extraction breaks
- Need maximum citation recovery in AUTO mode
- Note: Still fails closed in REQUIRED if no URLs found

#### Q: How do I know which flag caused an issue?
**A:** Check `metadata["feature_flags"]` in the response:
```json
{
  "feature_flags": {
    "extractor_v2": true,
    "vertex_text_harvest": false,
    "ungrounded_retry_policy": "v2"
  }
}
```

### Monitoring Dashboards

#### Key Metrics to Watch
1. **Citation Success Rate:** Should be >80% for grounded calls
2. **REQUIRED Failure Rate:** Should be <5% baseline
3. **Extractor Error Rate:** Should be <0.5%
4. **Retry Rate:** Should be <10% for ungrounded

#### Alert Response Playbook

| Alert | First Response | Escalation |
|-------|---------------|------------|
| Citation rate drop >20% | Check extractor flags | Rollback EXTRACTOR_V2 |
| REQUIRED failures >15% | Check model support | Page on-call |
| Extractor errors >0.5% | Review citations_audit | Enable text-harvest |
| Resolver p95 >800ms | Check redirect cache | Increase cache size |

### Testing Commands

#### Verify Extraction Locally
```python
# Test extraction with fixture
from app.llm.adapters.vertex_adapter import _extract_vertex_citations
import json

with open("tests/fixtures/fixture1.json") as f:
    data = json.load(f)
    
citations = _extract_vertex_citations(data)
print(f"Extracted {len(citations)} citations")
for c in citations:
    print(f"  - {c['source_domain']}: {c['title'][:50]}")
```

#### Load Test Citation Extraction
```bash
# Run 100 grounded requests
for i in {1..100}; do
  curl -X POST http://localhost:8000/v1/completions \
    -d '{"model":"gemini-1.5-pro","grounded":true,"messages":[{"role":"user","content":"What is longevity?"}]}' &
done
wait

# Check success rate
psql -c "SELECT AVG(CASE WHEN citations_count > 0 THEN 100.0 ELSE 0 END) FROM llm_metrics WHERE timestamp > NOW() - INTERVAL '5 minutes'"
```

This runbook provides quick diagnosis and resolution paths for common citation extraction issues.

## Execution Sequencing

**Recommended implementation order to minimize blast radius:**

1. **Ungrounded retry fix** → Immediate impact on empty responses
2. **Candidate-level scan** → Core fix for citation extraction  
3. **SDK fallback (canary only)** → Test alternate shapes safely
4. **Text-harvest (opt-in after V2)** → Only if V2 insufficient
5. **Logging/Audit enhancements** → Better observability
6. **OpenAI tool_result** → Completeness for OpenAI
7. **Fixtures & tests** → Regression protection
8. **Longevity matrix re-run** → Final validation

This sequence ensures clear causality attribution for improvements.

## Definition of Done

### Concrete Acceptance Tests

**Test 1: Vertex Ungrounded Longevity**
```python
def test_vertex_ungrounded_retry_budget():
    response = await adapter.complete(longevity_prompt, max_tokens=500)
    metadata = response.metadata
    assert metadata["retry_max_tokens"] >= metadata["first_attempt_max_tokens"]
    assert response.content != ""
    assert len(response.content) > 100  # Not empty or truncated
```

**Test 2: Grounded AUTO with Tools but No Citations**
```python
def test_grounded_auto_tools_no_citations():
    response = await adapter.complete(prompt, grounded=True, grounding_mode="AUTO")
    if response.metadata["tool_call_count"] > 0 and response.metadata["citations_count"] == 0:
        assert "citations_audit" in response.metadata
        assert response.metadata["why_not_grounded"] == "tools_invoked_no_citations"
```

**Test 3: Gemini Two-Step Attestation**
```python
def test_gemini_two_step_attestation():
    response = await adapter.complete(prompt, grounded=True, grounding_mode="REQUIRED", json_mode=True)
    metadata = response.metadata
    if metadata["two_step_used"]:
        assert metadata["step2_tools_invoked"] == False
        assert metadata["step2_source_ref"] is not None  # SHA256 of step1
        assert metadata["citations_count"] > 0
        # Verify step2 source matches step1 hash
        import hashlib
        step1_hash = hashlib.sha256(metadata["step1_text"].encode()).hexdigest()
        assert metadata["step2_source_ref"] == step1_hash
```

**Test 4: OpenAI Tool Result Extraction**
```python
def test_openai_tool_result_frames():
    # Use fixture with only tool_result{name=web_search}
    response = parse_openai_response(tool_result_only_fixture)
    citations = _extract_openai_citations(response)
    assert len(citations) >= 1
    assert response.metadata["citations_from_tool_results"] > 0
```

**Test 5: Extractor V2 Comparison**
```python
def test_extractor_v2_improvement():
    # Run with legacy extractor
    os.environ["EXTRACTOR_V2"] = "false"
    response_v1 = await adapter.complete(grounded_prompt)
    citations_v1 = response_v1.metadata["citations_count"]
    
    # Run with V2 extractor
    os.environ["EXTRACTOR_V2"] = "true"
    response_v2 = await adapter.complete(grounded_prompt)
    citations_v2 = response_v2.metadata["citations_count"]
    
    # V2 should extract more citations
    assert citations_v2 >= citations_v1
    # JSON structure should remain stable
    if response_v1.json_mode:
        assert json.loads(response_v1.content).keys() == json.loads(response_v2.content).keys()
```

**Test 6: ALS Propagation Invariants**
```python
def test_als_propagation():
    response = await adapter.complete(prompt, als_nfc="test_context")
    metadata = response.metadata
    assert metadata["als_nfc_length"] <= 350  # NFC constraint
    assert metadata["als_sha256_present"] == True
    assert "als_nfc" in metadata  # Survives to telemetry
```

**Test 7: Retry Policy Toggle**
```python
def test_retry_policy_toggle():
    # Test v1 policy
    os.environ["UNGROUNDED_RETRY_POLICY"] = "v1"
    response_v1 = await adapter.complete(longevity_prompt, max_tokens=500)
    assert response_v1.metadata["retry_policy"] == "v1"
    
    # Test v2 policy
    os.environ["UNGROUNDED_RETRY_POLICY"] = "v2"
    response_v2 = await adapter.complete(longevity_prompt, max_tokens=500)
    assert response_v2.metadata["retry_policy"] == "v2"
    assert response_v2.metadata["retry_max_tokens"] >= response_v2.metadata["first_attempt_max_tokens"]
```

**Test 8: SDK vs GenAI Parity**
```python
def test_sdk_vs_genai_parity():
    prompt = "What are the latest longevity research findings?"
    
    # Test with google-genai
    os.environ["VERTEX_USE_GENAI_CLIENT"] = "true"
    response_genai = await adapter.complete(prompt, grounded=True)
    
    # Test with Vertex SDK
    os.environ["VERTEX_USE_GENAI_CLIENT"] = "false"
    response_sdk = await adapter.complete(prompt, grounded=True)
    
    # Both should produce citations
    assert response_genai.metadata["citations_count"] >= 1
    assert response_sdk.metadata["citations_count"] >= 1
    
    # Record schema differences in audit
    if "citations_audit" in response_sdk.metadata:
        print(f"SDK schema: {response_sdk.metadata['citations_audit']['keys_found']}")
```

**Test 9: Text-Harvest AUTO-Only**
```python
def test_text_harvest_auto_only():
    os.environ["VERTEX_TEXT_HARVEST"] = "true"
    
    # AUTO mode - should use text harvest if needed
    response_auto = await adapter.complete(prompt, grounded=True, grounding_mode="AUTO")
    if response_auto.metadata.get("citations_from_text_harvest", 0) > 0:
        assert response_auto.metadata["grounding_mode"] == "AUTO"
    
    # REQUIRED mode - should NOT use text harvest
    try:
        response_req = await adapter.complete(prompt, grounded=True, grounding_mode="REQUIRED")
    except ValueError as e:
        # Should fail if no structured citations
        assert "GROUNDING_REQUIRED_FAILED" in str(e)
    else:
        # If it passes, verify no text-harvest was used
        assert response_req.metadata.get("citations_from_text_harvest", 0) == 0
```

### Acceptance Criteria

**Grounded Gemini (AUTO):**
- `citations_count > 0` in ≥80% of runs for news/research prompts
- Achieved with EXTRACTOR_V2 alone (without text-harvest)
- Per model/region validation

**Grounded Gemini (REQUIRED):**
- Pass rate ≥ baseline (no regression)
- No increase in `tools_invoked_no_citations` vs pre-change
- Text-harvest does NOT convert failures to passes

**Ungrounded Gemini:**
- `retry_max_tokens ≥ first_attempt_max_tokens` in 100% of retries
- Empty responses ≤2% (down from current ~25%)
- `retry_reason` logged for all retries

**OpenAI (where tools supported):**
- Citations ≥ baseline with tool_result harvesting
- Track `citations_from_annotations` vs `citations_from_tool_results`

**Performance & Resilience:**
- Text-harvest capped at 8 URLs, 0.1s timeout
- Redirect resolution preserves evidence on failure
- Runtime flags emitted with every run
- Test fixtures assert ≥ expected count (not exact)

## Priority 7 - Resilience & Observability (Original)

### D. Add Text-Harvest Fallback
**Safety net when tools invoked but no structured citations**
**Location:** `backend/app/llm/adapters/vertex_adapter.py` - `_extract_vertex_citations()`

**Changes:**
1. Regex harvest URLs from assistant text when citations empty
2. Mark with `source_type="text_harvest"` for audit
3. Maintains REQUIRED mode strictness

**Unified Diff:**
```diff
*** a/app/llm/adapters/vertex_adapter.py
--- b/app/llm/adapters/vertex_adapter.py
@@ _extract_vertex_citations() after candidate scan
+        # FINAL SAFETY NET: harvest URLs directly from assistant text when tools ran but structured evidence is empty
+        # IMPORTANT: Text-harvest is AUTO-ONLY and does NOT convert REQUIRED failures to passes
+        if not citations and feature_flags.vertex_text_harvest and grounding_mode != "REQUIRED":
+            texts = []
+            max_harvest_urls = 8  # Hard cap on harvested URLs
+            harvest_timeout = 0.1  # Max seconds for regex processing
+            
+            if hasattr(resp, "candidates") and resp.candidates:
+                for c in resp.candidates:
+                    if hasattr(c, "content") and hasattr(c.content, "parts"):
+                        for p in c.content.parts:
+                            t = getattr(p, "text", None)
+                            if isinstance(t, str) and t.strip():
+                                texts.append(t[:5000])  # Cap text length per part
+            
+            if texts:
+                import re
+                import time
+                start_time = time.time()
+                url_re = re.compile(r"https?://[^\s)>\]}]+")
+                
+                for t in texts:
+                    if time.time() - start_time > harvest_timeout:
+                        break  # Timeout guard
+                    for m in url_re.findall(t)[:max_harvest_urls]:
+                        _add(m, raw={"source_type":"text_harvest"})
+                        if len(citations) >= max_harvest_urls:
+                            break
```

### E. Enhanced Logging & Audit
**Location:** `backend/app/llm/adapters/vertex_adapter.py` - `_audit_grounding_metadata()` and citation extraction

**Changes:**
1. Add `candidate_keys` snapshot to audit
2. Add `candidate_citation_meta_preview` when present
3. Track token budgets in metadata

**Unified Diff for audit function:**
```diff
*** a/app/llm/adapters/vertex_adapter.py
--- b/app/llm/adapters/vertex_adapter.py
@@ def _audit_grounding_metadata(resp: Any) -> dict:
-    """Forensic audit of grounding metadata structure when citations are missing."""
-    audit = {"candidates": 0, "grounding_metadata_keys": [], "example": {}}
+    """Forensic audit of grounding metadata structure when citations are missing."""
+    audit = {"candidates": 0, "grounding_metadata_keys": [], "example": {}, "candidate_keys": [], "candidate_citation_meta_preview": []}
@@
         if hasattr(resp, "candidates") and resp.candidates:
             audit["candidates"] = len(resp.candidates)
             cand = resp.candidates[0]
+            # candidate-level keys (helps when citationMetadata is sibling to groundingMetadata)
+            try:
+                audit["candidate_keys"] = [k for k in dir(cand) if not k.startswith("_")][:20]
+                cdict = cand.model_dump() if hasattr(cand, "model_dump") else {}
+                cm = cdict.get("citationMetadata") or cdict.get("citation_metadata") or {}
+                if isinstance(cm, dict):
+                    audit["candidate_citation_meta_preview"] = list(cm.keys())[:10]
+            except Exception:
+                pass
```

**Unified Diff for logging in extraction:**
```diff
@@ _extract_vertex_citations() forensics section
-                logger.warning(f"[CITATIONS] Vertex: {tool_count} tool calls but 0 citations extracted. "
-                             f"Grounding metadata keys found: {gm_keys}")
+                logger.warning(f"[CITATIONS] Vertex: {tool_count} tool calls but 0 citations extracted. "
+                               f"Grounding metadata keys: {gm_keys}")
+                # Candidate-level audit preview
+                try:
+                    c0 = resp.candidates[0]
+                    keys = [k for k in dir(c0) if not k.startswith("_")][:20]
+                    logger.debug(f"[CITATIONS] Vertex candidate keys: {keys}")
+                    cdict = c0.model_dump() if hasattr(c0, "model_dump") else {}
+                    cm = cdict.get("citationMetadata") or cdict.get("citation_metadata")
+                    if isinstance(cm, dict):
+                        logger.debug(f"[CITATIONS] citationMetadata keys: {list(cm.keys())[:10]}")
+                except Exception:
+                    pass
```

### F. OpenAI Tool Result Harvesting
**Location:** `backend/app/llm/adapters/openai_adapter.py` - `_extract_openai_citations()`

**Changes:**
1. Parse `tool_result` items with name `web_search`/`web_search_preview`
2. Extract citations from generic tool result frames
3. **JSON format note:** Use `response_format={"type":"json_object"}` as canonical for Phase-0 (flag alternate formats)

**Unified Diff:**
```diff
*** a/app/llm/adapters/openai_adapter.py
--- b/app/llm/adapters/openai_adapter.py
@@ def _extract_openai_citations(response) -> List[Dict]:
-                # web_search or web_search_preview tool results
+                # web_search or web_search_preview tool results
                 if item_type in ['web_search', 'web_search_preview']:
@@
-                # Check for url_citation annotations
+                # Generic tool_result frames carrying web_search outputs
+                elif item_type == 'tool_result' and (item.get('name') in ('web_search','web_search_preview')):
+                    payload = item.get('content', {})
+                    results = payload.get('results', []) if isinstance(payload, dict) else []
+                    for idx, r in enumerate(results):
+                        if isinstance(r, dict):
+                            add_citation(
+                                url=r.get('url',''),
+                                title=r.get('title',''),
+                                snippet=r.get('snippet',''),
+                                rank=idx+1,
+                                raw_data=r
+                            )
+
+                # Check for url_citation annotations
                 elif item_type == 'url_citation':
```

## Priority 3 - Test Infrastructure

### G. Create Test Fixtures
**Location:** `backend/tests/fixtures/`

Files to create:
- `fixture1.json` - v1 JOIN case (citations → citedSources)
- `fixture2.json` - Legacy groundingAttributions
- `fixture3.json` - Loose-harvest (supportingContent)
- `fixture4.json` - Empty but tools called (audit path)
- `fixture5.json` - Redirect-only URLs

### H. Implement Test Suite
**Location:** `backend/tests/test_vertex_citations.py`

Tests to implement:
- Parametrized extraction tests for fixtures 1-3
- Empty citation audit test for fixture4
- Redirect preservation test for fixture5

```python
@pytest.mark.parametrize("fixture,expected_domains", [
    ("fixture1.json", {"nih.gov", "nature.com", "who.int"}),
    ("fixture2.json", {"consensus.app", "webmd.com"}),
    ("fixture3.json", {"mit.edu", "cam.ac.uk"}),
])
def test_vertex_citation_extraction(fixture, expected_domains):
    with open(f"tests/fixtures/{fixture}") as f:
        data = json.load(f)
    out = _extract_vertex_citations(data)
    domains = {c["source_domain"] for c in out}
    assert expected_domains.issubset(domains)
    assert len(out) >= len(expected_domains)  # Minimum count, not exact

def test_vertex_citation_extraction_empty_fixture4():
    with open("tests/fixtures/fixture4.json") as f:
        data = json.load(f)
    out = _extract_vertex_citations(data)
    assert out == [] or all(not c.get("url") for c in out)
    audit = _audit_grounding_metadata(data)
    assert audit["candidates"] == 1
    assert "citations" in audit["grounding_metadata_keys"] or "citedSources" in audit["grounding_metadata_keys"]

def test_vertex_citation_redirect_only_fixture5():
    with open("tests/fixtures/fixture5.json") as f:
        data = json.load(f)
    out = _extract_vertex_citations(data)
    assert len(out) >= 1
    c = out[0]
    acceptable = {"thelancet.com", "vertexaisearch.cloud.google.com", "cell.com", "www.cell.com"}
    assert c.get("source_domain") in acceptable
    assert "url" in c and isinstance(c["url"], str) and c["url"].startswith("http")
```

## Acceptance Criteria

1. **Ungrounded Gemini:** 
   - Response no longer empty
   - `retry_max_tokens ≥ first_attempt_max_tokens`

2. **Grounded Gemini:**
   - `grounded_effective=true` AND `citations_count>0`
   - Works with both google-genai and Vertex SDK paths

3. **OpenAI Grounded:**
   - Citations extracted from tool_result frames
   - REQUIRED mode fails closed for unsupported models

## Acceptance Checklist (Quick)

* **Ungrounded Gemini**: responses contain text on first or second try; metadata shows `retry_max_tokens ≥ first_attempt_max_tokens`
* **Grounded Gemini (AUTO/REQUIRED)**: citations now appear either via sibling `citationMetadata` or via `citedSources` JOIN; REQUIRED passes
* **OpenAI grounded (where supported)**: citations appear when tool outputs are framed as `tool_result`
* **Audit logs**: when empty, you'll see `grounding_metadata_keys`, `candidate_keys`, and a `citationMetadata` preview for fast triage

## Execution Order

1. Fix ungrounded retry token budget (A)
2. Add candidate-level citation scan (B)
3. Allow Vertex SDK path (C)
4. Add text-harvest fallback (D)
5. Enhance logging/audit (E)
6. Fix OpenAI tool_result parsing (F)
7. Create test fixtures (G)
8. Implement test suite (H)
9. Run unit tests
10. Run longevity test for validation

## Key Insights from Review

- **Ungrounded failures:** Caused by retry token budget regression
- **Grounded failures:** Citations at wrong level in response hierarchy
- **Two-step policy:** Correct as-is (grounded prose → JSON reshape)
- **REQUIRED mode:** Working correctly, just needs citation extraction fixes

## Test Coverage Matrix

| Fixture | Test Case | Expected Behavior |
|---------|-----------|-------------------|
| fixture1 | v1 JOIN with sourceId mapping | Extract 3 citations via JOIN |
| fixture2 | Legacy groundingAttributions | Extract 2 citations from old format |
| fixture3 | Loose-harvest fallback | Extract 2 citations from supportingContent |
| fixture4 | Empty citations but tools called | Return empty list, audit logs metadata |
| fixture5 | Redirect-only URLs | Preserve redirect evidence, attempt resolution |

## Implementation Requirements

**Citation Extraction (_extract_vertex_citations):**
- JOIN logic for sourceId/sourceIds/sourceIndices → citedSources
- Legacy format support (groundingAttributions)
- Loose harvesting from nested structures
- Redirect URL preservation
- Domain extraction even from redirects
- Audit logging for empty cases

**Fail-Closed Principles:**
- Never drop evidence (even redirects)
- Preserve all grounding signals
- Log audit trail when metadata present but no citations
- Default to redirect domain if resolution fails

## Commit Message Template

```
feat: Critical adapter fixes for citation extraction and token management

- Fix Vertex ungrounded retry token budget regression (retry >= first attempt)
- Add candidate-level citationMetadata scan (sibling of groundingMetadata)
- Allow Vertex SDK grounded path for A/B testing citation shapes
- Add text-harvest fallback for resilient citation extraction
- Enhance audit logging with candidate-level keys and preview
- Fix OpenAI tool_result frame parsing for generic outputs

Acceptance: Ungrounded Gemini responses no longer empty, grounded citations
properly extracted via JOIN and sibling scan, REQUIRED mode correctly
enforced, comprehensive test coverage via 5 fixtures.

Aligns with Phase-0 PRD: two-step policy maintained, fail-closed REQUIRED
mode, resilient evidence preservation, no Direct Gemini fallback.
```

This plan addresses all root causes identified in the review with minimal, surgical changes.