"""
OpenAI Adapter (Live GPT-5 Implementation)
Uses Responses API for GPT-5
"""

import os
import time
import json
import logging
import random
import asyncio
import httpx
import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse, parse_qs
from openai import AsyncOpenAI

from app.llm.types import LLMRequest, LLMResponse
from app.llm.errors import GroundingNotSupportedError, GroundingRequiredFailedError
from app.llm.models import OPENAI_ALLOWED_MODELS, OPENAI_DEFAULT_MODEL, validate_model, normalize_model
from .grounding_detection_helpers import detect_openai_grounding, extract_openai_search_evidence
from app.llm.tool_detection import detect_openai_websearch_usage
from app.llm.tool_negotiation import get_negotiated_tool_type, build_typed_web_search_tool
from app.llm.citations.resolver import resolve_citation_url
from app.llm.citations.domains import registrable_domain_from_url
from app.llm.grounding_empty_results import analyze_openai_grounding, GroundingEmptyResultsError
from app.core.config import get_settings, settings
from app.prometheus_metrics import (
    inc_rate_limit as _inc_rl_metric,
    set_openai_active_concurrency, 
    set_openai_next_slot_epoch,
    inc_stagger_delays, 
    inc_tpm_deferrals
)

# --- Proxy support removed ---
# All proxy functionality has been disabled via DISABLE_PROXIES=true
# Locale/region is now handled via API parameters, not network egress
# --- end proxy removal ---

# Provider minimum output tokens requirement
PROVIDER_MIN_OUTPUT_TOKENS = 16

logger = logging.getLogger(__name__)

# Circuit breaker state management
@dataclass
class OpenAICircuitBreakerState:
    """Circuit breaker state for a specific model."""
    consecutive_5xx: int = 0
    consecutive_429: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "closed"  # closed, open, half-open
    open_until: Optional[datetime] = None
    total_5xx_count: int = 0
    total_429_count: int = 0
    
# Global circuit breaker states per model
_openai_circuit_breakers: Dict[str, OpenAICircuitBreakerState] = {}

# Debug flag for citation extraction
DEBUG_GROUNDING = os.getenv("DEBUG_GROUNDING", "false").lower() == "true"


def _get_registrable_domain(url: str) -> str:
    """
    Extract registrable domain from URL.
    Simple implementation without public suffix list.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return ""
        
        # Remove port if present
        domain = domain.split(':')[0]
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # For most domains, return as-is (keeps subdomains like ec.europa.eu)
        # Only strip for known second-level TLDs
        parts = domain.split('.')
        if len(parts) >= 3:
            # Check if it's a known second-level TLD pattern
            if parts[-2] in ['co', 'ac', 'gov', 'edu', 'org', 'net', 'com'] and parts[-1] in ['uk', 'jp', 'au', 'nz', 'za']:
                # e.g., example.co.uk -> return last 3 parts
                return '.'.join(parts[-3:])
        
        # For everything else (including ec.europa.eu), return full domain
        return domain
    except:
        return ""


def _normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication:
    - Remove UTM params
    - Remove anchors
    - Lowercase host
    """
    try:
        parsed = urlparse(url)
        # Remove fragment
        parsed = parsed._replace(fragment='')
        
        # Remove tracking params
        if parsed.query:
            params = parse_qs(parsed.query)
            # Remove common tracking params
            tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 
                              'utm_content', 'fbclid', 'gclid', 'ref', 'source'}
            cleaned_params = {k: v for k, v in params.items() 
                            if k.lower() not in tracking_params}
            
            # Rebuild query string
            if cleaned_params:
                query_parts = []
                for k, v_list in cleaned_params.items():
                    for v in v_list:
                        query_parts.append(f"{k}={v}")
                parsed = parsed._replace(query='&'.join(query_parts))
            else:
                parsed = parsed._replace(query='')
        
        # Lowercase netloc
        parsed = parsed._replace(netloc=parsed.netloc.lower())
        
        return urlunparse(parsed)
    except:
        return url


def _extract_openai_citations(response) -> List[Dict]:
    """
    Extract citations from OpenAI Responses API response.
    Returns list of normalized citation dicts following the uniform schema.
    """
    citations = []
    seen_urls = {}  # normalized_url -> citation dict (for deduplication)
    
    try:
        # Helper to add citation with deduplication
        def add_citation(url: str, title: str = "", snippet: str = "", 
                        source_type: str = "web", rank: Optional[int] = None,
                        raw_data: Optional[dict] = None):
            if not url:
                return
            
            normalized = _normalize_url(url)
            
            # If we've seen this URL, update rank if lower
            if normalized in seen_urls:
                existing = seen_urls[normalized]
                if rank is not None and (existing.get('rank') is None or rank < existing['rank']):
                    existing['rank'] = rank
                return
            
            # New citation
            citation = {
                "provider": "openai",
                "url": url,
                "source_domain": "",  # Will be set after resolution
                "title": title or "",
                "snippet": snippet or "",
                "source_type": source_type,
                "rank": rank,
                "raw": raw_data or {}
            }
            
            # Resolve redirects and set source_domain
            citation = resolve_citation_url(citation)
            resolved_url = citation.get("resolved_url") or url
            citation["source_domain"] = registrable_domain_from_url(resolved_url) or _get_registrable_domain(url)
            
            seen_urls[normalized] = citation
            citations.append(citation)
        
        # 1. Try typed path first (Responses SDK returns typed objects)
        if hasattr(response, 'output') and response.output:
            rank_counter = 1
            for item in response.output:
                # Handle typed objects first
                if hasattr(item, 'type'):
                    item_type = getattr(item, 'type', '')
                    
                    # web_search or web_search_preview tool results (typed)
                    if item_type in ['web_search', 'web_search_preview']:
                        content = getattr(item, 'content', None)
                        if content:
                            # Try to parse as typed results first
                            if hasattr(content, 'results'):
                                results = getattr(content, 'results', [])
                                for idx, result in enumerate(results):
                                    if hasattr(result, 'url'):
                                        add_citation(
                                            url=getattr(result, 'url', ''),
                                            title=getattr(result, 'title', ''),
                                            snippet=getattr(result, 'snippet', ''),
                                            rank=idx + 1,
                                            raw_data={"tool_type": item_type}
                                        )
                            elif isinstance(content, str):
                                # Parse string content
                                lines = content.split('\n')
                                for line in lines:
                                    url_match = re.search(r'https?://[^\s]+', line)
                                    if url_match:
                                        url = url_match.group(0).rstrip('.,;)')
                                        title = line[:url_match.start()].strip(' -•·')
                                        add_citation(url, title=title, rank=rank_counter,
                                                   raw_data={"tool_type": item_type})
                                        rank_counter += 1
                    
                    # url_citation annotations (typed) - these are ANCHORED
                    elif item_type == 'url_citation':
                        add_citation(
                            url=getattr(item, 'url', ''),
                            title=getattr(item, 'title', ''),
                            snippet=getattr(item, 'snippet', ''),
                            source_type="annotation",  # Anchored to text
                            raw_data={"type": "url_citation"}
                        )
                    
                    # tool_result frames (typed)
                    elif item_type == 'tool_result':
                        tool_name = getattr(item, 'name', '')
                        if tool_name in ['web_search', 'web_search_preview']:
                            content = getattr(item, 'content', '')
                            if isinstance(content, str) and content:
                                # Parse structured JSON if present
                                try:
                                    content_data = json.loads(content)
                                    if isinstance(content_data, dict):
                                        results = content_data.get('results', [])
                                        for idx, result in enumerate(results):
                                            add_citation(
                                                url=result.get('url', ''),
                                                title=result.get('title', ''),
                                                snippet=result.get('snippet', ''),
                                                rank=idx + 1,
                                                raw_data=result
                                            )
                                except (json.JSONDecodeError, TypeError):
                                    pass
                
                # Fall back to dict handling if not typed
                elif isinstance(item, dict):
                    item_type = item.get('type', '')
                
                # web_search or web_search_preview tool results
                if item_type in ['web_search', 'web_search_preview']:
                    # Extract search results
                    content = item.get('content')
                    if isinstance(content, str):
                        # Parse content for URLs and titles
                        # Simple pattern matching for typical search result format
                        lines = content.split('\n')
                        for line in lines:
                            # Look for URL patterns
                            url_match = re.search(r'https?://[^\s]+', line)
                            if url_match:
                                url = url_match.group(0).rstrip('.,;)')
                                # Try to extract title (often before URL)
                                title = line[:url_match.start()].strip(' -•·')
                                add_citation(url, title=title, rank=rank_counter, 
                                           raw_data={"tool_type": item_type})
                                rank_counter += 1
                    elif isinstance(content, dict):
                        # Structured search results
                        results = content.get('results', [])
                        for idx, result in enumerate(results):
                            if isinstance(result, dict):
                                add_citation(
                                    url=result.get('url', ''),
                                    title=result.get('title', ''),
                                    snippet=result.get('snippet', ''),
                                    rank=idx + 1,
                                    raw_data=result
                                )
                
                # Check for url_citation annotations
                elif item_type == 'url_citation':
                    add_citation(
                        url=item.get('url', ''),
                        title=item.get('title', ''),
                        snippet=item.get('snippet', ''),
                        raw_data=item
                    )
                
                # Handle tool_result frames (new Responses API format)
                elif item_type == 'tool_result':
                    tool_name = item.get('name', '')
                    if tool_name in ['web_search', 'web_search_preview']:
                        # Extract content from tool result
                        content = item.get('content', '')
                        
                        if isinstance(content, str):
                            # Parse text content for URLs
                            lines = content.split('\n')
                            for line in lines:
                                url_match = re.search(r'https?://[^\s]+', line)
                                if url_match:
                                    url = url_match.group(0).rstrip('.,;)')
                                    title = line[:url_match.start()].strip(' -•·')
                                    add_citation(url, title=title, rank=rank_counter,
                                               raw_data={"tool_type": "tool_result", "tool_name": tool_name})
                                    rank_counter += 1
                        elif isinstance(content, dict):
                            # Structured tool result
                            results = content.get('results', [])
                            for idx, result in enumerate(results):
                                if isinstance(result, dict):
                                    add_citation(
                                        url=result.get('url', ''),
                                        title=result.get('title', ''),
                                        snippet=result.get('snippet', ''),
                                        rank=idx + 1,
                                        raw_data=result
                                    )
        
        # 2. Check message content for annotations (typed and dict paths)
        # Look for the last message item in output for url_citation annotations
        last_message = None
        if hasattr(response, 'output') and response.output:
            for item in reversed(response.output):
                # Typed path
                if hasattr(item, 'type') and getattr(item, 'type', '') == 'message':
                    last_message = item
                    break
                # Dict path
                elif isinstance(item, dict) and item.get('type') == 'message':
                    last_message = item
                    break
        
        if last_message:
            # Handle typed message
            if hasattr(last_message, 'content'):
                content = getattr(last_message, 'content', None)
                if content:
                    # Check if content is a list of blocks
                    if hasattr(content, '__iter__') and not isinstance(content, str):
                        for block in content:
                            if hasattr(block, 'annotations'):
                                annotations = getattr(block, 'annotations', [])
                                for ann in annotations:
                                    if hasattr(ann, 'type') and getattr(ann, 'type', '') == 'url_citation':
                                        add_citation(
                                            url=getattr(ann, 'url', ''),
                                            title=getattr(ann, 'title', ''),
                                            snippet=getattr(ann, 'snippet', ''),
                                            raw_data={"type": "url_citation", "source": "message_annotation"}
                                        )
            # Handle dict message
            elif isinstance(last_message, dict):
                content = last_message.get('content', [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            for ann in block.get('annotations', []):
                                if isinstance(ann, dict) and ann.get('type') == 'url_citation':
                                    add_citation(
                                        url=ann.get('url', ''),
                                        title=ann.get('title', ''),
                                        snippet=ann.get('snippet', ''),
                                        raw_data=ann
                                    )
        
        # Log if tools were called but no citations found
        if DEBUG_GROUNDING and not citations:
            # Check if tools were actually called
            tool_count = 0
            if hasattr(response, 'output'):
                for item in response.output:
                    if isinstance(item, dict) and item.get('type') in ['web_search', 'web_search_preview']:
                        tool_count += 1
            
            if tool_count > 0:
                logger.warning(f"[CITATIONS] OpenAI: {tool_count} tool calls but 0 citations extracted. "
                             f"First output item: {response.output[0] if response.output else 'none'}")
    
    except Exception as e:
        logger.error(f"[CITATIONS] Error extracting OpenAI citations: {e}")
        import traceback
        logger.error(f"[CITATIONS] Traceback: {traceback.format_exc()}")
    
    return citations


class _OpenAIRateLimiter:
    """Process-wide rate limiter for OpenAI API calls with sliding window"""
    def __init__(self):
        s = get_settings()
        self._enabled = s.openai_gate_in_adapter
        self._sem = asyncio.Semaphore(max(1, s.openai_max_concurrency))
        self._tpm_limit = int(s.openai_tpm_limit)
        
        # Sliding window for token tracking
        self._window_lock = asyncio.Lock()
        self._window_start = time.time()
        self._tokens_used_this_minute = 0
        self._debt = 0  # Track underestimation debt
        
        # For concurrency tracking
        self._active_lock = asyncio.Lock()
        self._active = 0
        
        # Adaptive multiplier tracking for grounded calls
        self._grounded_ratios = []  # List of (actual/estimated) ratios
        self._grounded_ratios_max = 20  # Keep last 20 ratios for better smoothing
    
    async def await_tpm(self, estimated_tokens, max_output_tokens=None):
        """Wait until TPM budget allows next request with sliding window
        
        Args:
            estimated_tokens: Token estimate for this request
            max_output_tokens: If provided, can suggest auto-trim
            
        Returns:
            (should_trim, suggested_max_tokens): Auto-trim suggestion if budget tight
        """
        if not self._enabled or not estimated_tokens:
            return False, None
        
        async with self._window_lock:
            now = time.time()
            
            # Reset window if more than 60 seconds have passed
            if now - self._window_start >= 60:
                self._window_start = now
                self._tokens_used_this_minute = self._debt  # Carry over debt
                self._debt = 0
            
            # Check if we have budget
            tokens_needed = estimated_tokens
            if self._tokens_used_this_minute + tokens_needed > self._tpm_limit:
                # Calculate how long to sleep
                time_in_window = now - self._window_start
                time_remaining = 60 - time_in_window
                
                if time_remaining > 0:
                    # Sleep until next window with jitter to prevent thundering herd
                    jitter = random.uniform(0.5, 0.75)  # 500-750ms jitter
                    sleep_time = time_remaining + 0.1 + jitter  # Buffer + jitter
                    logger.info(f"[RL_TPM] Sleeping {sleep_time:.1f}s (used {self._tokens_used_this_minute}/{self._tpm_limit} TPM, jitter={jitter:.3f}s)")
                    inc_tpm_deferrals()
                    await asyncio.sleep(sleep_time)
                    
                    # Reset window after sleep
                    self._window_start = time.time()
                    self._tokens_used_this_minute = self._debt
                    self._debt = 0
            
            # Check if auto-trim is needed (when budget is tight)
            should_trim = False
            suggested_max = None
            if max_output_tokens and tokens_needed > 0:
                remaining_budget = self._tpm_limit - self._tokens_used_this_minute - self._debt
                time_remaining = max(0, 60 - (now - self._window_start))
                
                # Auto-trim if: time remaining < 10s OR would exceed budget
                if time_remaining < 10 or tokens_needed > remaining_budget:
                    # Calculate how much we can afford for output
                    input_portion = estimated_tokens - (max_output_tokens or 0)
                    available_for_output = max(500, remaining_budget - input_portion)  # Min 500 tokens
                    
                    if available_for_output < max_output_tokens:
                        should_trim = True
                        suggested_max = int(available_for_output * 0.8)  # Keep 20% buffer
                        logger.info(f"[RL_AUTOTRIM] Suggesting trim from {max_output_tokens} to {suggested_max} tokens")
            
            # Reserve tokens
            self._tokens_used_this_minute += tokens_needed
            logger.debug(f"[RL_TPM] Reserved {tokens_needed} tokens (total: {self._tokens_used_this_minute}/{self._tpm_limit})")
            
            return should_trim, suggested_max
    
    async def commit_actual_tokens(self, actual_tokens, estimated_tokens, is_grounded=False):
        """Commit actual token usage and track debt
        
        Args:
            actual_tokens: Actual tokens used from response.usage
            estimated_tokens: What we estimated before the call
            is_grounded: Whether this was a grounded request
        """
        if not self._enabled or not actual_tokens:
            return
        
        # Track ratio for grounded calls
        if is_grounded and estimated_tokens > 0:
            ratio = actual_tokens / estimated_tokens
            async with self._window_lock:
                self._grounded_ratios.append(ratio)
                # Keep only last N ratios
                if len(self._grounded_ratios) > self._grounded_ratios_max:
                    self._grounded_ratios.pop(0)
                logger.debug(f"[RL_ADAPTIVE] Grounded ratio {ratio:.2f} (history: {len(self._grounded_ratios)} samples)")
        
        # Handle both underestimation (debt) and overestimation (credit)
        difference = actual_tokens - estimated_tokens
        
        async with self._window_lock:
            if difference > 0:
                # We underestimated - add debt
                self._debt += difference
                logger.info(f"[RL_DEBT] Underestimated by {difference} tokens (total debt: {self._debt})")
            elif difference < 0:
                # We overestimated - apply credit (reduce current usage within the minute)
                credit = abs(difference)
                # Apply credit up to current usage, don't go negative
                credit_applied = min(credit, self._tokens_used_this_minute)
                self._tokens_used_this_minute -= credit_applied
                logger.debug(f"[RL_CREDIT] Overestimated by {credit} tokens, applied {credit_applied} credit (usage now: {self._tokens_used_this_minute})")
    
    def get_grounded_multiplier(self):
        """Get adaptive multiplier for grounded calls based on history"""
        if not self._grounded_ratios:
            return 1.15  # Default multiplier when no history
        
        # Use median of recent ratios, clamped to [1.0, 2.0]
        sorted_ratios = sorted(self._grounded_ratios)
        median_ratio = sorted_ratios[len(sorted_ratios) // 2]
        return max(1.0, min(2.0, median_ratio))
    
    def suggest_trim(self, requested_max_tokens: int, min_out: int = 128) -> int:
        """Suggest trimmed max_tokens if TPM budget is tight
        
        Args:
            requested_max_tokens: Originally requested max output tokens
            min_out: Minimum acceptable output tokens
            
        Returns:
            Suggested max_tokens (may be less than requested if budget tight)
        """
        headroom = max(0, self._tpm_limit - self._tokens_used_this_minute)
        # If less than 10% headroom, suggest trimming
        if headroom < int(0.10 * self._tpm_limit):
            return max(min_out, int(requested_max_tokens * 0.75))
        return requested_max_tokens
    
    async def acquire_slot(self):
        """Acquire concurrency slot"""
        if self._enabled:
            await self._sem.acquire()
    
    def release_slot(self):
        """Release concurrency slot"""
        if self._enabled:
            self._sem.release()
    
    async def handle_429(self, retry_after=None):
        """Handle rate limit error with exponential backoff
        
        Args:
            retry_after: Seconds to wait from Retry-After header
        """
        if not self._enabled:
            return
        
        async with self._window_lock:
            # Add penalty debt
            self._debt += 1000  # Penalty tokens for hitting limit
            
        if retry_after:
            await asyncio.sleep(retry_after)
        else:
            # Exponential backoff with jitter
            base_delay = 2.0
            jitter = random.random() * 2 - 1  # -1 to 1
            delay = min(30, base_delay * (2 ** random.randint(0, 3))) + jitter
            await asyncio.sleep(delay)
    
    @asynccontextmanager
    async def concurrency(self):
        """Context manager for OpenAI concurrency tracking"""
        if not self._enabled:
            yield
            return
        await self._sem.acquire()
        try:
            async with self._active_lock:
                self._active += 1
                set_openai_active_concurrency(self._active)
            yield
        finally:
            async with self._active_lock:
                self._active = max(0, self._active-1)
                set_openai_active_concurrency(self._active)
            self._sem.release()


# Singleton instance
_RL = _OpenAIRateLimiter()


def _extract_text_from_responses_obj(r) -> str:
    """Robustly extract assistant text from Responses API objects."""
    # 0) canonical fast-path
    txt = getattr(r, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt

    collected: List[str] = []

    def _as_dict(obj):
        # Best-effort: prefer SDK's model_dump_json (typed models), then .json(), else dir-walk
        try:
            if hasattr(obj, "model_dump_json"):
                return json.loads(obj.model_dump_json())
        except Exception:
            pass
        try:
            if hasattr(obj, "json"):
                return json.loads(obj.json())
        except Exception:
            pass
        return None

    # 1) Try typed access first: r.output[*].content[*]
    out = getattr(r, "output", None)
    if isinstance(out, list) and out:
        for item in out:
            # Skip reasoning items - they don't contain user-facing text
            item_type = getattr(item, "type", None)
            if item_type == "reasoning":
                continue
            
            # Handle message items which contain the actual text
            if item_type != "message":
                continue
                
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for blk in content:
                    # Check block type - we want output_text or redacted_text blocks
                    blk_type = getattr(blk, "type", None) or (blk.get("type") if isinstance(blk, dict) else None)
                    if blk_type not in {None, "text", "output_text", "redacted_text"}:
                        continue
                    
                    # typed class: blk.text or blk.text.value
                    t = getattr(blk, "text", None)
                    if isinstance(t, str) and t.strip():
                        collected.append(t)
                        continue
                    if hasattr(t, "value") and isinstance(t.value, str) and t.value.strip():
                        collected.append(t.value)
                        continue
                    # dict-shaped block
                    if isinstance(blk, dict):
                        t = blk.get("text")
                        if isinstance(t, str) and t.strip():
                            collected.append(t)
                            continue
                        if isinstance(t, dict):
                            v = t.get("value")
                            if isinstance(v, str) and v.strip():
                                collected.append(v)
                                continue

    if collected:
        return "\n".join(collected).strip()

    # 2) As a last resort, inspect dict form
    as_dict = _as_dict(r)
    if isinstance(as_dict, dict):
        try:
            for item in as_dict.get("output", []):
                # Skip reasoning items in dict form too
                if item.get("type") == "reasoning":
                    continue
                    
                # Handle message items explicitly
                if item.get("type") == "message":
                    for blk in item.get("content", []):
                        if blk.get("type") in {"text", "output_text", "redacted_text"}:
                            t = blk.get("text")
                            if isinstance(t, str) and t.strip():
                                collected.append(t)
                            elif isinstance(t, dict) and isinstance(t.get("value"), str) and t["value"].strip():
                                collected.append(t["value"])
                else:
                    # Generic content extraction
                    for blk in item.get("content", []):
                        t = blk.get("text")
                        if isinstance(t, str) and t.strip():
                            collected.append(t)
                        elif isinstance(t, dict) and isinstance(t.get("value"), str) and t["value"].strip():
                            collected.append(t["value"])
            if collected:
                return "\n".join(collected).strip()
        except Exception:
            pass

    # 3) Still nothing — log a compact dump
    safe_dump = None
    try:
        safe_dump = as_dict or _as_dict(r)
    except Exception:
        safe_dump = None
    logger.info("Responses extract: no text found. dump=%s",
                (json.dumps(safe_dump)[:2000] if isinstance(safe_dump, dict) else "unavailable"))
    return ""


def _split_messages(messages: List[Dict[str, Any]]) -> tuple[Optional[str], str]:
    """Split messages into instructions (system) and input (user) for Responses API"""
    sys_parts, user_parts = [], []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            sys_parts.append(content)
        elif role == "assistant":
            # Assistant messages become part of conversation context
            user_parts.append(f"Assistant: {content}")
        else:  # user
            user_parts.append(content)
    
    instructions = "\n\n".join(p for p in sys_parts if p).strip() or None
    user_input = "\n".join(p for p in user_parts if p).strip() or ""
    
    # Ensure there's always user input to trigger text generation
    if not user_input:
        user_input = "Please answer now in plain text."
    
    return instructions, user_input


def _is_empty(s: str | None) -> bool:
    """Check if string is empty or whitespace only"""
    return not s or not s.strip()


def _nudge_plain_text(user_input: str) -> str:
    """Add explicit instruction for plain text output"""
    return (user_input + "\n\n"
            "Answer in plain, concise text. Do not include tool plans or hidden reasoning.").strip()


def _had_reasoning_only(response) -> bool:
    """Check if response contains only reasoning items with no text"""
    output = getattr(response, "output", None)
    if not output:
        return False
    
    # Check if ALL items are reasoning type
    for item in output:
        item_type = getattr(item, "type", None)
        if not item_type:
            # Check dict form
            if isinstance(item, dict):
                item_type = item.get("type")
        if item_type != "reasoning":
            return False  # Found non-reasoning item
    
    # All items were reasoning type
    return True


# UNUSED: Probe function kept for potential future use
async def _probe_web_search_capability(client, model_name: str, timeout_s: int) -> bool:
    """
    UNUSED - Fast one-shot capability probe: ask the Responses API with web_search tool,
    tiny token budget, and trivial input. Returns True if accepted, False if 400-not-supported.
    Never used to fetch real content.
    """
    return True  # Stub implementation since unused
    # Original implementation commented out:
    # try:
    #     probe_params = {
    #         "model": model_name,
    #         "input": "capability probe",
    #         "tools": [{"type":"web_search"}, {"type":"web_search_preview"}],
    #         "tool_choice": "auto",
    #         "max_output_tokens": 16,
    #         "text": {"verbosity": "low"}
    #     }
    #     _ = await client.with_options(timeout=timeout_s).responses.create(**probe_params)
    #     return True
    # except Exception as e:
    #     low = str(e).lower()
    #     if ("not supported" in low and "web_search" in low) or ("hosted tool 'web_search'" in low and "not supported" in low):
    #         return False
    #     # Any other error: don't decide here; treat as unknown (optimistic)
    #     return True


def _extract_openai_citations_old(response) -> list:
    """
    [DEPRECATED - kept for reference]
    Old OpenAI citation extractor.
    """
    citations = []
    try:
        rd = response.model_dump() if hasattr(response, "model_dump") else {}
        output = rd.get("output", []) or []
        rank = 1
        
        # 1) Final assistant message annotations
        # Find last message item
        last_msg = None
        for item in output:
            if isinstance(item, dict) and item.get("type") == "message":
                last_msg = item
        
        if last_msg:
            for blk in last_msg.get("content", []) or []:
                if isinstance(blk, dict):
                    for ann in blk.get("annotations", []) or []:
                        if isinstance(ann, dict) and ann.get("type") == "url_citation":
                            url = ann.get("url") or ann.get("uri")
                            if url:
                                citations.append({
                                    "provider": "openai",
                                    "url": url,
                                    "title": ann.get("title"),
                                    "snippet": ann.get("snippet"),
                                    "source_type": "annotation",
                                    "rank": rank
                                })
                                rank += 1
        
        # 2) Optional: harvest from web_search* tool items (if present)
        for item in output:
            if isinstance(item, dict):
                t = item.get("type")
                if isinstance(t, str) and t.startswith("web_search"):
                    for blk in item.get("content", []) or []:
                        if isinstance(blk, dict):
                            url = blk.get("url") or blk.get("uri")
                            if url:
                                citations.append({
                                    "provider": "openai",
                                    "url": url,
                                    "title": blk.get("title"),
                                    "snippet": blk.get("snippet"),
                                    "source_type": "tool_item",
                                    "rank": rank
                                })
                                rank += 1
    except Exception:
        pass
    return citations


class OpenAIAdapter:
    """Live OpenAI adapter using Responses API for GPT-5"""
    
    def __init__(self):
        # API Key required
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY required - set in backend/.env")
        
        # Configure timeouts
        connect_s = float(os.getenv("OPENAI_CONNECT_TIMEOUT_MS", "2000")) / 1000.0
        read_s = float(os.getenv("OPENAI_READ_TIMEOUT_MS", "60000")) / 1000.0
        
        # Create client with timeouts
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(
                connect=connect_s,
                read=read_s,
                write=read_s,
                pool=read_s
            )
        )
        
        # Use centralized model allowlist
        self.allowlist = OPENAI_ALLOWED_MODELS
        
        # Enhanced capability cache with composite keys
        # Key: (model_id, toolset_signature, org_id, allowlist_hash)
        # Value: (tool_type, cached_at)
        # Values: "web_search" | "web_search_preview" | "unsupported" | None
        # Includes TTL for unsupported entries to allow re-checking after entitlement changes
        self._web_search_tool_type = {}  # (model, tool_sig, org, allowlist) -> (tool_type, cached_at)
        self._cache_ttl_seconds = 900  # 15 minutes TTL for "unsupported" entries
        
        # Cache invalidation hook - hash of allowed models
        self._allowlist_hash = self._compute_allowlist_hash()
    
    def _compute_allowlist_hash(self) -> str:
        """Compute hash of allowed models for cache invalidation"""
        import hashlib
        allowed = os.getenv("ALLOWED_OPENAI_MODELS", "")
        return hashlib.md5(allowed.encode()).hexdigest()[:8]
    
    def _get_cache_key(self, model: str, toolset_signature: str = "web_search") -> tuple:
        """Build composite cache key"""
        # Get org_id from OpenAI client config if available
        org_id = os.getenv("OPENAI_ORG_ID", "default")
        allowlist_hash = self._compute_allowlist_hash()
        return (model, toolset_signature, org_id, allowlist_hash)
    
    def _get_cached_tool_type(self, model: str, toolset_signature: str = "web_search") -> Optional[str]:
        """Get cached tool type with TTL handling for unsupported entries"""
        cache_key = self._get_cache_key(model, toolset_signature)
        logger.debug(f"[CACHE_GET] Looking up tool type for key: {cache_key}")
        import time
        
        if cache_key not in self._web_search_tool_type:
            return None
            
        tool_type, cached_at = self._web_search_tool_type[cache_key]
        
        # If unsupported, check TTL
        if tool_type == "unsupported":
            elapsed = time.time() - cached_at
            if elapsed > self._cache_ttl_seconds:
                # TTL expired, remove from cache to allow retry
                del self._web_search_tool_type[cache_key]
                logger.debug(f"[CACHE_TTL] Expired unsupported cache for {cache_key} after {elapsed:.0f}s")
                return None
        
        return tool_type
    
    def _set_cached_tool_type(self, model: str, tool_type: str, toolset_signature: str = "web_search"):
        """Set cached tool type with timestamp"""
        import time
        cache_key = self._get_cache_key(model, toolset_signature)
        self._web_search_tool_type[cache_key] = (tool_type, time.time())
        logger.info(f"[CACHE_SET] Set tool type for {cache_key}: {tool_type}")
        logger.debug(f"[CACHE_SET] Current cache size: {len(self._web_search_tool_type)}")
    
    def _detect_grounding(self, response) -> tuple[bool, int]:
        """
        Detect web search usage in Responses API output.
        Uses new robust detection that works for both streaming and non-streaming.
        """
        # Convert response to dict if needed
        response_dict = None
        if hasattr(response, 'model_dump'):
            try:
                response_dict = response.model_dump()
            except:
                pass
        elif isinstance(response, dict):
            response_dict = response
        
        # Use new robust detector
        tools_used, call_count, kinds = detect_openai_websearch_usage(response=response_dict)
        
        # Log detected tool kinds for debugging
        if kinds:
            logger.debug(f"[TOOL_DETECTION] Detected tool kinds: {kinds}")
        
        # Return in expected format (grounded_effective, tool_call_count)
        return tools_used, call_count
    
    async def complete(self, request: LLMRequest, timeout: int = None) -> LLMResponse:
        """
        Execute OpenAI API call with GPT-5 specific requirements.
        Uses Responses API with adaptive error handling and retry logic.
        
        Args:
            request: LLM request
            timeout: Timeout in seconds (default: 120 for grounded, 60 for ungrounded)
        """
        # Set default timeout based on grounding
        if timeout is None:
            timeout = 120 if request.grounded else 60
        # Calculate token estimate for rate limiting
        # Rough estimate: ~4 chars per token for input
        input_chars = sum(len(m.get("content", "")) for m in request.messages)
        estimated_input_tokens = input_chars // 4 + 100  # Add buffer for role/structure
        
        # Initialize metadata early
        metadata = {
            "proxies_enabled": False,
            "proxy_mode": "disabled",
            "response_api": "responses_http",
            "provider_api_version": "openai:responses-v1",
            # Feature flags for monitoring
            "feature_flags": {
                "citation_extractor_v2": settings.citation_extractor_v2,
                "citation_extractor_enable_legacy": settings.citation_extractor_enable_legacy,
                "ungrounded_retry_policy": settings.ungrounded_retry_policy,
                "text_harvest_auto_only": settings.text_harvest_auto_only,
                "citations_extractor_enable": settings.citations_extractor_enable,
            }
        }
        
        # Token configuration with environment defaults
        DEFAULT_MAX = int(os.getenv("OPENAI_DEFAULT_MAX_OUTPUT_TOKENS", "6000"))
        CAP = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS_CAP", "6000"))
        
        requested_tokens = request.max_tokens or DEFAULT_MAX
        effective_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, requested_tokens))
        
        # Calculate token estimate using effective_tokens instead of requested
        estimated_tokens = int((estimated_input_tokens + effective_tokens) * 1.2)
        
        # Add extra for grounded requests (search overhead) using adaptive multiplier
        if request.grounded:
            grounded_multiplier = _RL.get_grounded_multiplier()
            estimated_tokens = int(estimated_tokens * grounded_multiplier)
            logger.debug(f"[RL_ADAPTIVE] Using grounded multiplier: {grounded_multiplier:.2f}")
        
        # Check TPM budget before acquiring slot
        # Also get auto-trim suggestion if budget is tight
        try:
            should_trim, suggested_max = await _RL.await_tpm(estimated_tokens, effective_tokens)
            
            # Apply auto-trim if needed and allowed
            if should_trim and suggested_max and os.getenv("OPENAI_AUTO_TRIM", "true").lower() == "true":
                original_effective = effective_tokens
                effective_tokens = suggested_max
                metadata["auto_trimmed"] = True
                metadata["auto_trim_original"] = original_effective
                metadata["auto_trim_reduced"] = suggested_max
                logger.info(f"[AUTO_TRIM] Reduced max_tokens from {original_effective} to {suggested_max}")
        except Exception as _e:
            logger.warning(f"[RL_WARN] Rate limiting issue: {_e}")
            raise
        
        # Proxy support removed - using direct connection only
        _client_for_call = self.client
        
        # Initialize tracking variables for logging/telemetry
        vantage_policy = str(getattr(request, 'vantage_policy', 'NONE')).upper().replace("VANTAGEPOLICY.", "")
        
        # Ensure these exist even when proxy wiring is absent
        proxy_mode = None  # "rotating"/"backbone" previously; now always None (direct)
        country_code = None  # used to be from req.meta; keep None
        
        # Normalize and validate model
        # Check if model was already adjusted for grounding - if so, skip normalization
        model_adjusted = False
        if hasattr(request, 'metadata') and request.metadata:
            model_adjusted = request.metadata.get('model_adjusted_for_grounding', False)
        
        if model_adjusted:
            # Model was already adjusted in unified adapter, use as-is
            model_name = request.model
            logger.debug(f"[MODEL] Using pre-adjusted model: {model_name} (original: {request.metadata.get('original_model')})")
        else:
            # Normal normalization path
            model_name = normalize_model("openai", request.model)
        
        is_valid, error_msg = validate_model("openai", model_name)
        if not is_valid:
            raise ValueError(f"MODEL_NOT_ALLOWED: {error_msg}")
        
        # Split messages properly for Responses API
        instructions, user_input = _split_messages(request.messages)
        
        # Build base parameters
        logger.info(f"[API_CALL] Using model: {model_name} (was_adjusted: {model_adjusted}, original: {request.metadata.get('original_model') if model_adjusted else 'N/A'})")
        params: Dict[str, Any] = {
            "model": model_name,  # Use normalized model instead of request.model
            "input": user_input,
            "max_output_tokens": effective_tokens,
        }
        
        # Add instructions if present
        if instructions:
            params["instructions"] = instructions
        
        # Add grounding tools if requested
        grounded_effective = False
        tool_call_count = 0
        grounding_mode = "AUTO"  # Default mode
        
        if request.grounded:
            # Extract grounding mode (AUTO or REQUIRED)
            grounding_mode = getattr(request, "grounding_mode", "AUTO")
            if hasattr(request, "meta") and isinstance(request.meta, dict):
                grounding_mode = request.meta.get("grounding_mode", grounding_mode)
            metadata["grounding_mode_requested"] = grounding_mode
            
            logger.debug(f"[OPENAI_GROUNDING] Attempting grounded request: model={model_name}, mode={grounding_mode}")
            
            # Check tri-state cache for known tool type
            logger.debug(f"[CACHE_CHECK] Checking cache for model: {model_name} (adjusted: {model_adjusted})")
            # Include toolset signature in cache lookup
            toolset_sig = "web_search" if not request.json_mode else "web_search_json"
            cached_tool_type = self._get_cached_tool_type(model_name, toolset_sig)
            logger.debug(f"[CACHE_CHECK] Result for {model_name}: {cached_tool_type}")
            
            if cached_tool_type == "unsupported":
                # Known unsupported (both variants failed) → act immediately
                logger.debug(f"[OPENAI_GROUNDING] Model {model_name} known not to support any web_search variant, "
                           f"proceeding ungrounded (cached)")
                metadata["grounding_status_reason"] = "both_web_search_variants_unsupported"
                metadata["grounding_not_supported"] = True
                if grounding_mode == "REQUIRED":
                    logger.debug(f"[OPENAI_GROUNDING] Model {model_name} unsupported but proceeding with ungrounded for router enforcement")
                # AUTO: proceed ungrounded (realistic), no tools
            else:
                # Get preferred tool type (from env or cache)
                tool_type = _choose_web_search_tool_type(cached_tool_type)
                
                # Attach the tool with proper typing
                logger.debug(f"[OPENAI_GROUNDING] Attaching {tool_type} tool with mode={grounding_mode}")
                
                # Build properly typed WebSearchTool
                params["tools"] = _build_grounded_tools(tool_type)
                metadata["response_api_tool_type"] = tool_type
                metadata["chosen_web_tool_type"] = tool_type  # For telemetry correlation
                logger.info(f"[TOOL_TYPE_CHOSEN] Model: {model_name}, Tool: {tool_type}, Mode: {grounding_mode}")
                
                # Set tool_choice to "auto" for all modes
                # IMPORTANT: web_search tools don't support tool_choice:"required"
                # In REQUIRED mode, we use "auto" and let the router enforce post-hoc
                params["tool_choice"] = "auto"
                if grounding_mode == "REQUIRED":
                    logger.info(f"[TOOL_CHOICE] REQUIRED mode using tool_choice:auto, router will enforce post-hoc")
                    metadata["required_enforcement"] = "post_hoc_router"
                else:
                    logger.debug(f"[TOOL_CHOICE] Using tool_choice=auto for mode={grounding_mode}")
            
            # PROMPT PURITY: Do not add grounding instructions to prompts
            # All grounding enforcement happens post-hoc at the adapter/router level
            # Only add grounding nudges if explicitly enabled (deprecated)
            if settings.enable_grounding_nudges:
                # Legacy behavior - deprecated, will be removed
                max_web_searches = int(os.getenv("OPENAI_MAX_WEB_SEARCHES", "2"))
                
                # Different instruction for JSON vs plain text mode
                if request.json_mode:
                    # JSON mode: instruct to return valid JSON object
                    grounding_instruction = (
                        "If the question refers to information after your knowledge cutoff or uses recency terms "
                        "like 'today', 'yesterday', 'this week', 'this month', 'latest', 'right now', 'currently', "
                        "'as of', 'this morning', 'this afternoon', 'this evening', or 'breaking', you MUST call the "
                        "web_search tool at least once before answering. After finishing any tool calls (limit: "
                        f"{max_web_searches} web searches), you MUST produce a final assistant message containing "
                        "a single, valid JSON object that answers the user request. Do not output prose or "
                        "explanations outside the JSON."
                    )
                else:
                    # Plain text mode: existing instruction
                    grounding_instruction = (
                        "If the question refers to information after your knowledge cutoff or uses recency terms "
                        "like 'today', 'yesterday', 'this week', 'this month', 'latest', 'right now', 'currently', "
                        "'as of', 'this morning', 'this afternoon', 'this evening', or 'breaking', you MUST call the "
                        "web_search tool at least once before answering. Do not respond from memory and do not include "
                        "knowledge-cutoff disclaimers when the tool is available. After finishing any tool calls, you "
                        f"MUST produce one final assistant message in plain text. Use at most {max_web_searches} web "
                        "searches and prefer primary/official sources. Include url_citation annotations in your final "
                        "message for each distinct source you relied on."
                    )
                
                if instructions:
                    params["instructions"] = f"{instructions}\n\n{grounding_instruction}"
                else:
                    params["instructions"] = grounding_instruction
                    
                metadata["grounding_nudges_added"] = True
            else:
                # PROMPT PURITY: Keep system message unmodified
                if instructions:
                    params["instructions"] = instructions
                metadata["grounding_nudges_added"] = False
        
        # Determine if tools are attached (not necessarily used)
        # tools_attached: we attached OpenAI web_search on this call (not the same as "search actually happened")
        tools_attached = bool(params.get("tools"))
        
        # Temperature Policy (per PRD):
        # - GPT-5 ALWAYS uses temperature=1.0 (model requirement)
        # - ANY grounded request uses temperature=1.0 (tools attached)
        # - This OVERRIDES user-provided temperatures for consistency
        # - Document in router PRD to avoid downstream surprises
        if model_name.startswith("gpt-5") or tools_attached:
            # MANDATORY: temperature=1.0 for any GPT-5 variant or when using tools
            params["temperature"] = 1.0
            if request.temperature is not None and request.temperature != 1.0:
                logger.debug(f"[TEMPERATURE_OVERRIDE] User temperature {request.temperature} -> 1.0 "
                           f"(reason: {'GPT-5' if model_name == 'gpt-5' else 'tools attached'})")
        else:
            if request.temperature is not None:
                params["temperature"] = request.temperature
        
        # JSON mode
        if request.json_mode:
            params["response_format"] = {"type": "json_object"}
        else:
            params["text"] = {"verbosity": "medium"}
        
        # Track timing and retries
        t0 = time.perf_counter()
        retry_mode = "none"
        attempts = 0
        reasoning_only = False
        
        # Update metadata instead of overwriting it
        metadata.update({
            "max_output_tokens_requested": requested_tokens,
            "max_output_tokens_effective": effective_tokens,
            "temperature_used": params.get("temperature"),
        })
        
        # Configure timeouts
        connect_s = float(os.getenv("OPENAI_CONNECT_TIMEOUT_MS", "2000")) / 1000.0
        read_s = float(os.getenv("OPENAI_READ_TIMEOUT_MS", "60000")) / 1000.0
        total_s = connect_s + read_s
        
        # [LLM_ROUTE] Log before API call
        route_info = {
            "vendor": "openai",
            "model": model_name,  # Use normalized model
            "vantage_policy": vantage_policy or "NONE",
            "proxy_mode": proxy_mode or "direct",
            "country": country_code or "none",
            "grounded": request.grounded,
            "max_tokens": effective_tokens,
            "timeouts_s": {"connect": connect_s, "read": read_s, "total": total_s}
        }
        
        # [WIRE_DEBUG] Log exact payload being sent
        if request.grounded:
            logger.debug(f"[WIRE_DEBUG] OpenAI Responses API call:")
            logger.debug(f"  Endpoint: /v1/responses")
            logger.debug(f"  Tools: {params.get('tools', [])}")
            logger.debug(f"  Tool choice: {params.get('tool_choice', 'none')}")
            logger.debug(f"  Text format present: {'text' in params and 'format' in params.get('text', {})}")
            logger.debug(f"  JSON mode: {request.json_mode}")
            logger.debug(f"  Max output tokens: {params.get('max_output_tokens', 'not set')}")
        logger.info(f"[LLM_ROUTE] {json.dumps(route_info)}")
        
        # Generate stable request ID for idempotency
        request_id = metadata.get("request_id") or f"req_{int(time.time()*1000)}_{random.randint(1000,9999)}"
        metadata["request_id"] = request_id
        
        # Check circuit breaker
        breaker_key = f"openai:{model_name}"
        breaker = _openai_circuit_breakers.get(breaker_key)
        if not breaker:
            breaker = OpenAICircuitBreakerState()
            _openai_circuit_breakers[breaker_key] = breaker
        
        # Check if circuit is open
        if breaker.state == "open":
            if breaker.open_until and datetime.now() > breaker.open_until:
                # Try half-open
                breaker.state = "half-open"
                logger.info(f"[openai] Circuit breaker half-open for {breaker_key}")
            else:
                # Fail fast
                metadata["circuit_state"] = "open"
                metadata["breaker_open_reason"] = "consecutive_5xx"
                metadata["error_type"] = "service_unavailable_upstream"
                raise Exception(f"Circuit breaker open for {breaker_key} until {breaker.open_until}")
        
        metadata["circuit_state"] = breaker.state
        
        # Internal call function with enhanced error handling
        async def _call(call_params):
            """
            Robust call with retries, circuit breaker, and proper error handling.
            """
            max_attempts = 4  # 1 initial + 3 retries for 5xx
            base_delay = 0.5
            last_error = None
            
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        # Exponential backoff with jitter for retries
                        delay = base_delay * (2 ** (attempt - 1))  # 0.5s, 1s, 2s, 4s
                        jitter = random.uniform(0, delay * 0.5)
                        total_delay = delay + jitter
                        metadata["backoff_ms_last"] = int(total_delay * 1000)
                        logger.info(f"[openai] Retry {attempt}/{max_attempts-1} after {total_delay:.2f}s for {request_id}")
                        await asyncio.sleep(total_delay)
                    
                    client_with_timeout = _client_for_call.with_options(timeout=timeout)
                    response = await client_with_timeout.responses.create(
                        **{k: v for k, v in call_params.items() if v is not None}
                    )
                    
                    # Success - reset circuit breaker
                    if breaker.state == "half-open" or breaker.consecutive_5xx > 0:
                        logger.info(f"[openai] Circuit breaker reset for {breaker_key}")
                    breaker.consecutive_5xx = 0
                    breaker.consecutive_429 = 0  
                    breaker.state = "closed"
                    metadata["retry_count"] = attempt
                    
                    return response
                except Exception as e:
                    msg = str(e)
                    low = msg.lower()
                    last_error = e
                    
                    # Extract status code if available
                    status_code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
                    
                    # Parameter sanitation (don't count as retry)
                    if "unexpected keyword argument" in msg or "unknown parameter" in low:
                        import re
                        m = re.search(r"'(\w+)'", msg)
                        if m:
                            bad_param = m.group(1)
                            logger.info(f"Removing unsupported parameter: {bad_param}")
                            call_params = dict(call_params)
                            call_params.pop(bad_param, None)
                            continue  # Don't count as attempt
                    
                    # Check for 5xx errors (retry with backoff)
                    if status_code and status_code >= 500:
                        breaker.consecutive_5xx += 1
                        breaker.total_5xx_count += 1
                        breaker.last_failure_time = datetime.now()
                        
                        metadata["upstream_status"] = status_code
                        metadata["upstream_error"] = f"HTTP_{status_code}"
                        
                        # Check if we should open the circuit
                        if breaker.consecutive_5xx >= 5:
                            hold_time = random.randint(60, 120)
                            breaker.state = "open"
                            breaker.open_until = datetime.now() + timedelta(seconds=hold_time)
                            metadata["circuit_state"] = "open"
                            metadata["breaker_open_reason"] = f"{breaker.consecutive_5xx}_consecutive_5xx"
                            logger.error(f"[openai] Circuit breaker opened for {breaker_key} after {breaker.consecutive_5xx} consecutive 5xx errors")
                        
                        if attempt < max_attempts - 1:
                            logger.warning(f"[openai] {status_code} error on attempt {attempt+1}/{max_attempts}: {msg[:100]}")
                            continue  # Retry
                    
                    # Check for network/timeout errors (retry with backoff)
                    elif "timeout" in low or "timed out" in low or "connection" in low or "socket" in low:
                        metadata["upstream_error"] = "network_error"
                        if attempt < max_attempts - 1:
                            logger.warning(f"[openai] Network error on attempt {attempt+1}/{max_attempts}: {msg[:100]}")
                            continue  # Retry
                    
                    # 429 rate limit (special handling)
                    elif "rate limit" in low or "429" in low or status_code == 429:
                        try:
                            _inc_rl_metric("openai")
                        except Exception:
                            pass
                        
                        breaker.consecutive_429 += 1
                        breaker.total_429_count += 1
                        metadata["upstream_status"] = 429
                        metadata["upstream_error"] = "rate_limited"
                        
                        # Extract Retry-After header
                        retry_after = None
                        try:
                            retry_after = getattr(e, "retry_after", None)
                            if retry_after is not None:
                                retry_after = float(retry_after)
                            elif hasattr(e, "response") and hasattr(e.response, "headers"):
                                retry_after_str = e.response.headers.get("retry-after")
                                if retry_after_str:
                                    retry_after = float(retry_after_str)
                        except Exception:
                            retry_after = None
                        
                        # Check if it's persistent quota issue
                        if breaker.consecutive_429 >= 10:
                            metadata["error_type"] = "rate_limited_quota"
                            raise RuntimeError(f"RATE_LIMITED_QUOTA: Persistent 429 after {breaker.consecutive_429} attempts") from e
                        
                        # Let rate limiter handle the backoff
                        await _RL.handle_429(retry_after)
                        
                        # Don't count against max_attempts for 429
                        continue
                    
                    # Check if web_search is not supported (don't retry for this)
                    if request.grounded and (
                        ("not supported" in low and "web_search" in low) or
                        ("hosted tool 'web_search'" in low and "not supported" in low) or
                        ("hosted tool 'web_search_preview'" in low and "not supported" in low)
                    ):
                        # Capture full error details for evidence
                        metadata["openai_error_status"] = getattr(e, "status_code", 400)
                        metadata["openai_error_message"] = msg
                        metadata["openai_error_type"] = "hosted_tool_not_supported"
                        if hasattr(e, "response") and hasattr(e.response, "headers"):
                            metadata["openai_request_id"] = e.response.headers.get("openai-request-id", "")
                        
                        # Current tool type failed, try alternate
                        current_tool = params.get("tools", [{}])[0].get("type", "")
                        # Fallback chain: date-stamped -> preview -> basic
                        if current_tool == "web_search_preview_2025_03_11":
                            alternate_tool = "web_search_preview"  # Fall back to base preview
                        elif current_tool == "web_search_preview":
                            alternate_tool = "web_search"  # Fall back to basic
                        else:
                            alternate_tool = "web_search_preview"  # Default fallback
                        
                        logger.info(f"[TOOL_FALLBACK] {current_tool} not supported, trying {alternate_tool}")
                        metadata["tool_variant_retry"] = True
                        
                        # Retry with alternate tool type
                        retry_params = dict(call_params)
                        retry_params["tools"] = _build_grounded_tools(alternate_tool)
                        
                        try:
                            retry_response = await client_with_timeout.responses.create(**retry_params)
                            # Cache the working tool type
                            # Cache with toolset signature
                            toolset_sig = "web_search" if not request.json_mode else "web_search_json"
                            self._set_cached_tool_type(model_name, alternate_tool, toolset_sig)
                            metadata["response_api_tool_type"] = alternate_tool
                            metadata["chosen_web_tool_type"] = alternate_tool  # For telemetry correlation
                            metadata["tool_type_fallback"] = True
                            logger.info(f"[TOOL_FALLBACK] Success with {alternate_tool}")
                            logger.info(f"[TOOL_TYPE_CHOSEN] Model: {model_name}, Tool: {alternate_tool} (fallback), Mode: {grounding_mode}")
                            return retry_response
                            
                        except Exception as retry_e:
                            # Check if alternate also failed with "not supported"
                            retry_msg = str(retry_e)
                            retry_msg_low = retry_msg.lower()
                            if "not supported" in retry_msg_low:
                                logger.warning(f"[TOOL_FALLBACK] Both tool types unsupported for {model_name}")
                                # Cache as unsupported (both variants failed)
                                # Cache as unsupported with toolset signature
                                toolset_sig = "web_search" if not request.json_mode else "web_search_json"
                                self._set_cached_tool_type(model_name, "unsupported", toolset_sig)
                                metadata["grounding_not_supported"] = True
                                metadata["grounding_status_reason"] = "hosted_web_search_not_supported_for_model"
                                # Capture second failure details
                                metadata["openai_retry_error_status"] = getattr(retry_e, "status_code", 400)
                                metadata["openai_retry_error_message"] = retry_msg
                                if hasattr(retry_e, "response") and hasattr(retry_e.response, "headers"):
                                    metadata["openai_retry_request_id"] = retry_e.response.headers.get("openai-request-id", "")
                                
                                if grounding_mode == "REQUIRED":
                                    logger.debug(f"[OPENAI_GROUNDING] Both variants rejected but proceeding for router enforcement")
                                
                                # AUTO: proceed ungrounded
                                logger.warning(f"Grounding not supported for {request.model}, proceeding without")
                                ungrounded_params = dict(call_params)
                                ungrounded_params.pop("tools", None)
                                ungrounded_params.pop("tool_choice", None)
                                try:
                                    final_response = await client_with_timeout.responses.create(**ungrounded_params)
                                    logger.debug(f"[OPENAI_GROUNDING] Ungrounded fallback successful")
                                    return final_response
                                except Exception as final_e:
                                    logger.warning(f"Ungrounded retry failed: {final_e}")
                                    raise final_e from e
                            else:
                                # Different error on retry - propagate
                                logger.warning(f"Alternate tool retry failed with different error: {retry_e}")
                                raise retry_e from e
                    
                    # No longer need separate preview check since we handle both in fallback above
                    else:
                        # Not a web_search support issue
                        # Only retry with web_search_preview if the original request had tools
                        # This avoids noisy retries for non-grounded requests
                        if "tools" in call_params and call_params["tools"]:
                            retry_params = dict(call_params)
                            retry_params["tools"] = _build_grounded_tools("web_search_preview")
                            try:
                                retry_response = await client_with_timeout.responses.create(**retry_params)
                                metadata["response_api_tool_variant"] = "preview_retry"
                                return retry_response
                            except Exception as retry_e:
                                logger.warning(f"Preview retry failed: {retry_e}")
                    
                    # For other errors, don't retry (tool fallback, etc.)
                    raise
            
            # If we exhausted all retries
            if last_error:
                metadata["retry_count"] = max_attempts - 1
                metadata["error_type"] = "service_unavailable_upstream"
                raise last_error

        
        # First attempt (with concurrency limiting)
        async with _RL.concurrency():
            response = await _call(params)
        content = _extract_text_from_responses_obj(response)
        
        # Detect grounding if tools were used
        if request.grounded:
            # Use new comprehensive analysis
            grounding_analysis = analyze_openai_grounding(response)
            
            # Legacy compatibility - keep old variables
            grounded_effective = grounding_analysis["grounded_effective"]
            tool_call_count = grounding_analysis["tool_call_count"]
            web_search_count = grounding_analysis["web_search_count"]
            web_grounded = grounded_effective  # For legacy compatibility
            
            # Add all telemetry fields
            metadata.update({
                "grounding_attempted": grounding_analysis["grounding_attempted"],
                "grounded_effective": grounded_effective,
                "tool_call_count": tool_call_count,
                "tool_result_count": grounding_analysis["tool_result_count"],
                "web_search_count": web_search_count,
                "web_search_queries": grounding_analysis.get("web_search_queries", []),
                "grounding_status_reason": grounding_analysis["why_not_grounded"]
            })
            
            logger.debug(f"[OPENAI_GROUNDING] Analysis: attempted={grounding_analysis['grounding_attempted']}, "
                        f"effective={grounded_effective}, tool_calls={tool_call_count}, "
                        f"results={grounding_analysis['tool_result_count']}, reason={grounding_analysis.get('why_not_grounded', 'N/A')}")
            
            # Extract citations if grounding was effective
            if grounded_effective:
                citations = _extract_openai_citations(response)
                metadata["citations"] = citations
                metadata["citation_count"] = len(citations)
                
                # Count url_citation annotations specifically (these are anchored)
                url_citation_count = sum(1 for c in citations 
                                        if c.get('source_type') == 'annotation'
                                        or c.get('raw', {}).get('type') == 'url_citation')
                metadata["url_citations_count"] = url_citation_count
                
                # Compute anchored vs unlinked based on source_type
                # 'annotation' = anchored (url_citations in final message)
                # 'web' or others = unlinked (from tool results)
                anchored_count = sum(1 for c in citations if c.get('source_type') == 'annotation')
                metadata['anchored_citations_count'] = anchored_count
                metadata['unlinked_sources_count'] = len(citations) - anchored_count
                
                if DEBUG_GROUNDING:
                    logger.debug(f"[CITATIONS] OpenAI: Extracted {len(citations)} citations, "
                               f"{url_citation_count} from url_citation annotations")
            
            # POST-HOC GROUNDING ENFORCEMENT for REQUIRED mode
            # Strict enforcement: web tool must be invoked AND citations must be produced
            if grounding_mode == "REQUIRED":
                if not grounded_effective:
                    # Web tool was not invoked
                    metadata["required_pass_reason"] = "REQUIRED_GROUNDING_MISSING"
                    error_msg = (
                        f"REQUIRED grounding mode: web search tool was not invoked. "
                        f"Tool calls: {tool_call_count}, Web searches: {web_search_count}."
                    )
                    logger.error(f"[OPENAI_GROUNDING] {error_msg}")
                    metadata["required_grounding_failed"] = True
                    raise GroundingRequiredFailedError(error_msg)
                    
                # Check if anchored citations were produced
                if grounded_effective and url_citation_count == 0:
                    # Tool was invoked but no anchored citations produced
                    metadata["required_pass_reason"] = "REQUIRED_GROUNDING_MISSING"
                    error_msg = (
                        f"REQUIRED grounding mode: web search executed but no anchored citations produced. "
                        f"Tool calls: {tool_call_count}, URL citations: {url_citation_count}."
                    )
                    logger.error(f"[OPENAI_GROUNDING] {error_msg}")
                    metadata["required_grounding_failed"] = True
                    raise GroundingRequiredFailedError(error_msg)
                    
                # Success - anchored citations present
                metadata["required_pass_reason"] = "anchored_openai"
                metadata["anchored_citations_count"] = url_citation_count
        
        # Check if initial response had reasoning only
        if _had_reasoning_only(response):
            reasoning_only = True
        
        # First retry - only if NOT in JSON mode and content is empty
        if _is_empty(content) and "response_format" not in params:
            attempts = 1
            metadata["retry_reason"] = "reasoning_only" if reasoning_only else "no_text"
            metadata["reasoning_only_detected"] = reasoning_only
            
            # Bump token budget and add text nudge
            bumped_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, effective_tokens * 2))
            retry_params = dict(params)
            retry_params["max_output_tokens"] = bumped_tokens
            retry_params["input"] = _nudge_plain_text(user_input)
            retry_params["text"] = {"verbosity": "low"}
            
            try:
                r2 = await _call(retry_params)
                content2 = _extract_text_from_responses_obj(r2)
                if not _is_empty(content2):
                    content = content2
                    response = r2
                    effective_tokens = bumped_tokens
                    retry_mode = "responses_retry1"
                    reasoning_only = _had_reasoning_only(r2)
                    metadata["max_output_tokens_effective"] = bumped_tokens
            except Exception as e:
                logger.warning(f"First retry failed: {e}")
        
        # Second retry - only if still empty AND not in JSON mode
        if _is_empty(content) and "response_format" not in params:
            attempts = 2
            
            # Triple token budget and add stronger text instruction
            final_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, effective_tokens * 3))
            retry2_params = dict(params)
            retry2_params["max_output_tokens"] = final_tokens
            retry2_params["input"] = _nudge_plain_text(user_input) + " Respond with plain text only."
            retry2_params["text"] = {"verbosity": "low"}
            
            try:
                r3 = await _call(retry2_params)
                content3 = _extract_text_from_responses_obj(r3)
                if not _is_empty(content3):
                    content = content3
                    response = r3
                    effective_tokens = final_tokens
                    retry_mode = "responses_retry2"
                    reasoning_only = _had_reasoning_only(r3)
                    metadata["max_output_tokens_effective"] = final_tokens
            except Exception as e:
                logger.warning(f"Second retry failed: {e}")
        
        # Calculate final latency
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Extract usage - ChatGPT fix: flatten response.usage and sum numeric keys ending with _tokens
        usage = {}
        usage_source = "absent"
        if hasattr(response, 'usage'):
            resp_usage = response.usage
            if resp_usage:
                # Extract all token fields (input_tokens, output_tokens, reasoning_tokens)
                input_tokens = getattr(resp_usage, 'input_tokens', 0) or getattr(resp_usage, 'prompt_tokens', 0) or 0
                output_tokens = getattr(resp_usage, 'output_tokens', 0) or getattr(resp_usage, 'completion_tokens', 0) or 0
                reasoning_tokens = getattr(resp_usage, 'reasoning_tokens', 0) or 0
                total_tokens = getattr(resp_usage, 'total_tokens', 0) or (input_tokens + output_tokens + reasoning_tokens)
                
                usage = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "total_tokens": total_tokens,
                    # Add synonyms for telemetry compatibility
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens
                }
                usage_source = "provider"
                
                # Commit actual token usage to rate limiter
                if total_tokens > 0:
                    await _RL.commit_actual_tokens(total_tokens, estimated_tokens, is_grounded=request.grounded)
        
        # If no usage from provider, use the estimate
        if not usage or usage.get('total_tokens', 0) == 0:
            usage = {
                "input_tokens": estimated_tokens // 3,  # Rough estimate
                "output_tokens": estimated_tokens * 2 // 3,  # Rough estimate
                "reasoning_tokens": 0,
                "total_tokens": estimated_tokens,
                # Add synonyms for telemetry compatibility
                "prompt_tokens": estimated_tokens // 3,
                "completion_tokens": estimated_tokens * 2 // 3
            }
            usage_source = "estimate"
        
        # Enhanced fallback for grounded empty responses
        if not content and request.grounded:
            # NEVER access response.text - it's a config object, not content!
            # Try model_dump for additional extraction paths
            if hasattr(response, 'model_dump'):
                response_data = response.model_dump()
                
                # Try output_text from dict (backup to typed access)
                if not content:
                    output_text = response_data.get('output_text', '')
                    if isinstance(output_text, str) and output_text.strip():
                        content = output_text.strip()
                        metadata['extraction_path'] = 'output_text_dict'
                
                # Try message blocks from output array
                if not content:
                    for item in response_data.get('output', []) or []:
                        if item.get('type') == 'message':
                            # Extract from content blocks
                            item_content = item.get('content', [])
                            if isinstance(item_content, list):
                                for block in item_content:
                                    if isinstance(block, dict) and block.get('type') in {'output_text', 'redacted_text'}:
                                        text = block.get('text', '')
                                        if isinstance(text, str):
                                            content = text.strip()
                                            metadata['extraction_path'] = 'message_blocks'
                                            break
                            if content:
                                break
            
            if content:
                metadata['grounding_extraction_fallback'] = True
            else:
                # Log extraction failure for debugging
                logger.warning("Failed to extract content from grounded response - all paths exhausted")
                metadata['extraction_path'] = 'none'
                
                # Two-step safety net: If grounding happened but no message, request synthesis
                if grounded_effective and hasattr(response, 'model_dump'):
                    response_data = response.model_dump()
                    has_message = any(item.get('type') == 'message' for item in response_data.get('output', []))
                    
                    if not has_message:
                        metadata['why_no_content'] = 'no_message_items_after_tool_calls'
                        logger.warning("Grounding complete but no message - attempting synthesis step")
                        
                        # Extract search evidence from the first response
                        search_evidence = extract_openai_search_evidence(response)
                        enhanced_input = user_input + search_evidence
                        
                        # Step 2: Synthesis-only request (no tools) with injected evidence
                        synthesis_params = {
                            "model": model_name,  # Use normalized model
                            "input": enhanced_input,  # Include search evidence
                            "instructions": (
                                "Based on the search evidence provided above, give a direct answer "
                                "to the user's question in plain text. Do not use any tools."
                            ),
                            "max_output_tokens": effective_tokens,  # Same as original (6000 in our case)
                            "temperature": params.get("temperature", 1.0),
                            "text": {"verbosity": "medium"}
                        }
                        
                        try:
                            synthesis_response = await _call(synthesis_params)
                            synthesis_content = _extract_text_from_responses_obj(synthesis_response)
                            if not _is_empty(synthesis_content):
                                content = synthesis_content
                                response = synthesis_response
                                metadata['synthesis_step_used'] = True
                                metadata['extraction_path'] = 'synthesis_fallback'
                                logger.info("Synthesis step successful, content recovered")
                            else:
                                metadata['synthesis_step_failed'] = True
                                logger.error("Synthesis step failed to produce content")
                        except Exception as e:
                            logger.error(f"Synthesis step failed with error: {e}")
                            metadata['synthesis_step_error'] = str(e)
        
        # Get system fingerprint
        sys_fp = getattr(response, "system_fingerprint", None)
        
        # Add complete tracking to metadata
        metadata["retry_mode"] = retry_mode
        metadata["attempts"] = attempts
        metadata["reasoning_only_detected"] = reasoning_only
        metadata["had_text_after_retry"] = not _is_empty(content)
        metadata["response_format"] = params.get("response_format")
        
        # Add telemetry with standardized keys
        metadata["vantage_policy"] = vantage_policy
        metadata["proxies_enabled"] = False
        metadata["proxy_mode"] = "disabled"
        metadata["timeouts_s"] = {
            "connect": 30,
            "read": 60,
            "total": timeout
        }
        
        # Add shape summary to metadata for debugging
        if request.grounded and hasattr(response, 'model_dump'):
            response_data = response.model_dump()
            output_items = response_data.get('output', [])
            
            # Count output types
            type_counts = {}
            for item in output_items:
                item_type = item.get('type', 'unknown')
                type_counts[item_type] = type_counts.get(item_type, 0) + 1
            
            # Get last message content types if exists
            message_items = [item for item in output_items if item.get('type') == 'message']
            last_message_content_types = []
            if message_items:
                last_msg = message_items[-1]
                content_blocks = last_msg.get('content', [])
                last_message_content_types = [
                    block.get('type') for block in content_blocks 
                    if isinstance(block, dict)
                ]
            
            # Count URL citations
            url_citations = 0
            for item in message_items:
                for block in item.get('content', []):
                    if isinstance(block, dict):
                        annotations = block.get('annotations', [])
                        url_citations += sum(
                            1 for a in annotations 
                            if isinstance(a, dict) and a.get('type') == 'url_citation'
                        )
            
            metadata['shape_summary'] = {
                'output_types': type_counts,
                'last_message_content_types': last_message_content_types,
                'url_citations_count': url_citations,
                'extraction_path': metadata.get('extraction_path', 'unknown'),
                'why_no_content': metadata.get('why_no_content')
            }
        
        # ---- Citations (normalized) ----
        # Note: Citations are already extracted when grounded_effective=True (see lines ~1340-1360)
        # No need to extract again here; metadata['citations'] is already populated if applicable
        
        # Add usage tracking metadata
        metadata['usage_source'] = usage_source
        metadata['estimated_tokens'] = estimated_tokens
        metadata['actual_tokens'] = usage.get('total_tokens', 0)
        
        # Add grounding signal metadata
        if request.grounded:
            metadata['grounded_effective'] = grounded_effective
            metadata['tool_call_count'] = tool_call_count
            metadata['web_grounded'] = web_grounded
            metadata['web_search_count'] = web_search_count
        
        # Debug logging for grounding
        if request.grounded:
            logger.info(
                "OpenAI Grounding: requested=%s effective=%s tool_calls=%s web_grounded=%s web_searches=%s shape=%s",
                request.grounded, grounded_effective, tool_call_count, web_grounded, web_search_count,
                metadata.get('shape_summary', {})
            )
        
        # No proxy clients to close anymore
        
        # [LLM_RESULT] Log successful response
        result_info = {
            "vendor": "openai",
            "model": model_name,  # Use normalized model
            "vantage_policy": vantage_policy or "NONE",
            "proxy_mode": proxy_mode or "direct",
            "country": country_code or "none",
            "grounded": request.grounded,
            "grounded_effective": grounded_effective,
            "latency_ms": latency_ms,
            "usage": usage,
            "content_length": len(content) if content else 0,
            "retry_mode": retry_mode,
            "attempts": attempts
        }
        logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
        
        # Final success/empty evaluation
        success_flag = True
        error_type = None
        error_message = None
        if _is_empty(content):
            success_flag = False
            error_type = "EMPTY_COMPLETION"
            if request.grounded:
                metadata.setdefault("why_no_content", "no_text_after_retries_grounded")
            else:
                metadata.setdefault("why_no_content", "no_text_after_retries_ungrounded")
        
        # --- ALS and model adjustment propagation into response metadata ---
        try:
            req_meta = getattr(request, 'metadata', {}) or {}
            if isinstance(req_meta, dict):
                # Copy ALS fields if present
                if req_meta.get('als_present'):
                    for k in ('als_present','als_block_sha256','als_variant_id','seed_key_id','als_country','als_locale','als_nfc_length','als_template_id'):
                        if k in req_meta:
                            metadata[k] = req_meta[k]
                
                # Copy model adjustment fields if present
                if req_meta.get('model_adjusted_for_grounding'):
                    metadata['model_adjusted_for_grounding'] = req_meta['model_adjusted_for_grounding']
                    metadata['original_model'] = req_meta.get('original_model')
        except Exception as _:
            pass
        
        # Add hash for immutability verification
        try:
            # Combine all messages for hash
            messages_str = json.dumps(request.messages, sort_keys=True)
            messages_hash = hashlib.sha256(messages_str.encode()).hexdigest()
            metadata["messages_hash"] = messages_hash[:16]  # First 16 chars for brevity
            metadata["model_identity"] = request.model
        except Exception:
            pass
        
        # Build response with comprehensive telemetry
        return LLMResponse(
            content=content,
            model_version=getattr(response, 'model', request.model),
            model_fingerprint=sys_fp,
            grounded_effective=grounded_effective,
            usage=usage,
            latency_ms=latency_ms,
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else None,
            success=success_flag,
            vendor="openai",
            model=request.model,
            metadata=metadata,
            error_type=error_type,
            error_message=error_message,
            # Add top-level citations if available
            citations=metadata.get("citations", []) if grounded_effective else [],
            # Add annotations for anchored citations
            annotations=[]  # TODO: Extract from url_citation annotations
        )
    
    def supports_model(self, model: str) -> bool:
        """Check if model is in allowlist"""
        return model in self.allowlist

# --- Contestra: OpenAI web_search tool-type compatibility (adaptive) ---
import os

def _choose_web_search_tool_type(preferred: str | None = None) -> str:
    # Env override wins
    env = os.getenv("OPENAI_WEB_SEARCH_TOOL_TYPE", "").strip().lower()
    if env:  # Accept any env value, let runtime negotiation validate
        return env
    if preferred:  # Accept any preferred value
        return preferred
    # Use runtime negotiation to determine best available type
    # This inspects the SDK's WebSearchToolParam at runtime
    return get_negotiated_tool_type()

def _build_grounded_tools(tool_type: str) -> list:
    """Build properly typed WebSearchTool for OpenAI SDK.
    
    Uses runtime negotiation to build the correct SDK type.
    Returns a typed WebSearchToolParam object (not a dict) to avoid Pydantic warnings.
    """
    # Build the typed tool object
    tool = build_typed_web_search_tool(tool_type)
    
    # Return as a list (Responses API expects a list of tools)
    # The tool is already properly typed, no need for dict conversion
    return [tool]

def _send_responses_http_with_grounding(session, body: dict, grounded_mode: str, preferred_tool_type: str | None = None):
    # Try primary
    t1 = _choose_web_search_tool_type(preferred_tool_type)
    body1 = dict(body)
    body1["tools"] = _build_grounded_tools(t1)
    resp = session.post('/v1/responses', json=body1)
    try:
        j = resp.json()
    except Exception:
        j = {}
    # If tool unsupported, retry with the alternate type once
    if getattr(resp, "status_code", 0) in (400, 404) and isinstance(j, dict):
        msg = json.dumps(j).lower()
        if "not supported" in msg and ("web_search_preview" in msg or "web_search" in msg):
            alt = "web_search" if t1 == "web_search_preview" else "web_search_preview"
            body2 = dict(body)
            body2["tools"] = _build_grounded_tools(alt)
            alt_resp = session.post('/v1/responses', json=body2)
            try:
                alt_json = alt_resp.json()
            except Exception:
                alt_json = {}
            if getattr(alt_resp, "status_code", 0) in (400, 404) and isinstance(alt_json, dict) and "not supported" in json.dumps(alt_json).lower():
                # BOTH tool types unsupported for this account/model
                if grounded_mode.upper() == "REQUIRED":
                    raise GroundingNotSupportedError("Web_search tools not available for this model; REQUIRED grounding cannot proceed.")
                # Preferred: proceed ungrounded by resending without tools
                body3 = dict(body)
                body3.pop("tools", None)
                body3.pop("tool_choice", None)
                fallback_resp = session.post('/v1/responses', json=body3)
                try:
                    setattr(fallback_resp, "_contestra_grounding_not_supported", True)
                except Exception:
                    pass
                return fallback_resp
            return alt_resp
    return resp


