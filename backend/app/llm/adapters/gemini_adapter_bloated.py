"""
Enhanced Gemini Direct adapter with anchored citations support.
"""
import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlunparse

import google.genai as genai
from google.genai.types import (
    FunctionCallingConfig, FunctionDeclaration, GenerateContentConfig,
    GoogleSearch, HarmBlockThreshold, HarmCategory, SafetySetting, Schema,
    Tool, ToolConfig
)
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.llm.errors import GroundingRequiredFailedError
from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model
# from app.llm.context_utils import detect_als_position  # Using local _detect_als_position instead

logger = logging.getLogger(__name__)

# Circuit breaker state management
@dataclass
class CircuitBreakerState:
    """Circuit breaker state for a specific vendor+model combination."""
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "closed"  # closed, open, half-open
    open_until: Optional[datetime] = None
    total_503_count: int = 0
    
# Global circuit breaker states per vendor+model
_circuit_breakers: Dict[str, CircuitBreakerState] = {}

def _get_registrable_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        p = urlparse(url)
        domain = p.netloc.lower().replace("www.", "")
        return domain if domain else "unknown"
    except Exception:
        return "unknown"

def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    try:
        p = urlparse(url)
        p = p._replace(fragment="")
        if p.query:
            q = parse_qs(p.query, keep_blank_values=True)
            q = {k: v for k, v in q.items() if not k.lower().startswith("utm_")}
            if q:
                pairs = []
                for k, vs in q.items():
                    for v in vs:
                        pairs.append(f"{k}={v}")
                p = p._replace(query="&".join(pairs))
            else:
                p = p._replace(query="")
        return urlunparse(p._replace(netloc=p.netloc.lower()))
    except Exception:
        return url

def _extract_redirect_url(google_url: str) -> str:
    """Extract real URL from Google grounding redirect."""
    if "vertexaisearch.cloud.google.com/grounding-api-redirect/" in google_url:
        # This is a redirect URL, extract if possible
        # For now, return as-is; in production, decode the redirect
        return google_url
    return google_url

def _extract_text_from_response(response) -> str:
    """Extract text from Gemini response."""
    if not response or not getattr(response, "candidates", None):
        return ""
    buf: List[str] = []
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                t = getattr(part, "text", None)
                if isinstance(t, str):
                    buf.append(t)
    return "".join(buf).strip()

def _extract_function_call(response) -> Tuple[Optional[str], Optional[Dict]]:
    """Extract function call from response."""
    if not response or not getattr(response, "candidates", None):
        return None, None
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    return fc.name, dict(getattr(fc, "args", {}) or {})
    return None, None

def _extract_anchored_citations(response, response_text: str) -> tuple[List[Dict], List[Dict], Dict]:
    """
    Extract both anchored and unlinked citations from Gemini response.
    Handles defensive case when search runs but chunks/supports are empty.
    
    Returns:
        annotations: List of anchored text spans with sources
        citations: Deduplicated list of all sources
        telemetry: Metrics about citation extraction
    """
    annotations = []
    citations_map = {}  # key: resolved_url, value: citation dict
    telemetry = {
        "citation_extractor_version": "anchored_ffc",
        "anchored_citations_count": 0,
        "unlinked_sources_count": 0,
        "total_raw_count": 0,
        "tool_call_count": 0,
        "anchored_coverage_pct": 0.0,
        "why_not_anchored": None,
        "grounding_evidence_missing": False
    }
    
    anchored_sources = set()
    all_chunks = {}  # chunk_index -> chunk_data
    
    try:
        for cand in getattr(response, "candidates", []) or []:
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
                
            # Count tool calls (web searches)
            web_searches = getattr(gm, "web_search_queries", []) or []
            telemetry["tool_call_count"] = len(web_searches)
            
            # First, collect all chunks
            chunks = getattr(gm, "grounding_chunks", []) or []
            
            # Defensive: Check if search ran but chunks are empty
            if len(web_searches) > 0 and len(chunks) == 0:
                logger.warning(f"[gemini_direct] Search executed ({len(web_searches)} queries), "
                             "but grounding_chunks are empty. Anchored citations unavailable.")
                telemetry["why_not_anchored"] = "API_RESPONSE_MISSING_GROUNDING_CHUNKS"
                telemetry["grounding_evidence_missing"] = True
            for idx, chunk in enumerate(chunks):
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri:
                    raw_uri = uri
                    resolved_url = _extract_redirect_url(uri)
                    title = getattr(web, "title", "") or ""
                    
                    all_chunks[idx] = {
                        "raw_uri": raw_uri,
                        "resolved_url": resolved_url,
                        "title": title,
                        "domain": _get_registrable_domain(resolved_url),
                        "chunk_index": idx
                    }
            
            # Now process grounding supports for anchored citations
            supports = getattr(gm, "grounding_supports", []) or []
            covered_chars = 0
            
            # Defensive: Check if search ran but supports are empty
            if len(web_searches) > 0 and len(supports) == 0:
                logger.warning(f"[gemini_direct] Search executed ({len(web_searches)} queries), "
                             "but grounding_supports are empty. Anchored citations unavailable.")
                if not telemetry.get("why_not_anchored"):
                    telemetry["why_not_anchored"] = "API_RESPONSE_MISSING_GROUNDING_SUPPORTS"
                telemetry["grounding_evidence_missing"] = True
            
            for support in supports:
                segment = getattr(support, "segment", None)
                if not segment:
                    continue
                    
                # Extract text position
                start_idx = getattr(segment, "start_index", None)
                end_idx = getattr(segment, "end_index", None)
                text = getattr(segment, "text", None)
                
                if start_idx is None or end_idx is None:
                    continue
                    
                # Get referenced chunks
                chunk_indices = getattr(support, "grounding_chunk_indices", []) or []
                sources = []
                
                for chunk_idx in chunk_indices:
                    if chunk_idx in all_chunks:
                        chunk_data = all_chunks[chunk_idx]
                        sources.append({
                            "resolved_url": chunk_data["resolved_url"],
                            "raw_uri": chunk_data["raw_uri"],
                            "title": chunk_data["title"],
                            "domain": chunk_data["domain"],
                            "source_id": f"chunk_{chunk_idx}",
                            "chunk_index": chunk_idx
                        })
                        anchored_sources.add(chunk_data["resolved_url"])
                        
                        # Add to citations map
                        url_key = chunk_data["resolved_url"]
                        if url_key not in citations_map:
                            citations_map[url_key] = {
                                "resolved_url": chunk_data["resolved_url"],
                                "raw_uri": chunk_data["raw_uri"],
                                "title": chunk_data["title"],
                                "domain": chunk_data["domain"],
                                "source_id": f"chunk_{chunk_idx}",
                                "count": 0
                            }
                        citations_map[url_key]["count"] += 1
                
                if sources:
                    # Verify text matches
                    if text and response_text and start_idx < len(response_text):
                        actual_text = response_text[start_idx:end_idx]
                        if text != actual_text:
                            logger.debug(f"Text mismatch: expected '{text}', got '{actual_text}'")
                    
                    annotations.append({
                        "start": start_idx,
                        "end": end_idx,
                        "text": text or response_text[start_idx:end_idx] if response_text else "",
                        "sources": sources
                    })
                    covered_chars += (end_idx - start_idx)
            
            # Add unlinked sources (chunks not referenced by any support)
            for idx, chunk_data in all_chunks.items():
                if chunk_data["resolved_url"] not in anchored_sources:
                    url_key = chunk_data["resolved_url"]
                    if url_key not in citations_map:
                        citations_map[url_key] = {
                            "resolved_url": chunk_data["resolved_url"],
                            "raw_uri": chunk_data["raw_uri"],
                            "title": chunk_data["title"],
                            "domain": chunk_data["domain"],
                            "source_id": f"chunk_{idx}",
                            "count": 0
                        }
                    telemetry["unlinked_sources_count"] += 1
            
            # Calculate coverage
            if response_text and len(response_text) > 0:
                telemetry["anchored_coverage_pct"] = min(100.0, (covered_chars / len(response_text)) * 100)
            
            telemetry["anchored_citations_count"] = len(anchored_sources)
            telemetry["total_raw_count"] = len(all_chunks)
            
    except Exception as e:
        logger.warning(f"[Gemini anchored citations] extraction failed: {e}")
    
    # Convert citations map to list
    citations = list(citations_map.values())
    
    return annotations, citations, telemetry

def detect_vertex_grounding(response) -> tuple[bool, int]:
    """Check if Vertex/Gemini grounding actually ran."""
    tool_calls = 0
    if not response or not getattr(response, "candidates", None):
        return False, 0
    for cand in response.candidates or []:
        gm = getattr(cand, "grounding_metadata", None)
        if gm:
            queries = getattr(gm, "web_search_queries", []) or []
            tool_calls = len(queries)
            if tool_calls > 0:
                return True, tool_calls
    return False, 0

def _detect_als_position(system_text: str, user_text: str) -> str:
    """Detect where ALS context appears."""
    if system_text and "ALS" in system_text:
        return "system"
    elif user_text and "ALS" in user_text:
        return "user"
    return "absent"

def _to_direct_gemini_model(model_id: str) -> str:
    """
    Convert model ID to Direct API format.
    
    ⚠️ CRITICAL: ONLY use gemini-2.5-pro in production
    ⚠️ DO NOT use gemini-2.0-flash for ANY purpose
    """
    if not model_id:
        return "models/gemini-2.5-pro"  # PRODUCTION DEFAULT
    
    # Validate we're not using flash
    if "flash" in model_id.lower():
        logger.error(f"BLOCKED: Attempted to use flash model: {model_id}")
        return "models/gemini-2.5-pro"  # Force to production model
    
    if model_id.startswith("publishers/google/models/"):
        return f"models/{model_id.split('publishers/google/models/',1)[1]}"
    if model_id.startswith("models/"):
        return model_id
    return f"models/{model_id}"

def _estimate_tokens(text: str, method: str = "char4", pad: float = 1.15) -> int:
    """Estimate token count from text."""
    if not text:
        return 0
    try:
        if method == "char4":
            base = max(0, len(text)) / 4.0
        else:
            base = max(0, len(text)) / 4.0
        return int(max(0, round(base * float(pad))))
    except Exception:
        return 0

def _create_output_schema(req: LLMRequest) -> FunctionDeclaration:
    """Create schema for structured output."""
    schema = Schema(
        type="object",
        properties={
            "response": Schema(type="string"),
            "data": Schema(type="object", properties={})
        },
        required=["response"]
    )
    return FunctionDeclaration(
        name="format_response",
        description="Return the response and optional structured data.",
        parameters=schema
    )

class GeminiAdapter:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GOOGLE_API_KEY or GEMINI_API_KEY for direct Gemini")
        self.client = genai.Client(api_key=api_key)
        logger.info(f"[gemini_direct] google-genai client ready")

    def _build_two_messages(self, req: LLMRequest) -> tuple[str, str]:
        """Build exactly one system + one user message."""
        system = []
        user = None
        for m in req.messages:
            role = m.get("role")
            content = m.get("content","")
            if role == "system":
                system.append(content)
            elif role == "user":
                if user is not None:
                    raise ValueError("Gemini single-call expects exactly one user message")
                user = content
            else:
                raise ValueError("Assistant messages not allowed in single-call")
        if user is None:
            raise ValueError("Missing user message")
        return ("\n\n".join(system) if system else ""), user

    def _gen_cfg(self, req: LLMRequest, system: Optional[str], tools: Optional[List[Tool]], tool_cfg: Optional[dict]) -> GenerateContentConfig:
        cfg: Dict[str, Any] = {
            "temperature": getattr(req, "temperature", 0.7),
            "topP": getattr(req, "top_p", 0.95),
            "maxOutputTokens": getattr(req, "max_tokens", 6000),
        }
        if system:
            cfg["systemInstruction"] = system
        if tools:
            cfg["tools"] = tools
        if tool_cfg:
            cfg["toolConfig"] = ToolConfig(
                function_calling_config=FunctionCallingConfig(
                    mode=tool_cfg.get("function_calling_config", {}).get("mode", "AUTO"),
                    allowed_function_names=tool_cfg.get("function_calling_config", {}).get("allowed_function_names")
                )
            )
        cfg["safetySettings"] = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_NONE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_NONE),
        ]
        return GenerateContentConfig(**cfg)

    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        # Use monotonic clock for accurate timing
        t0 = time.perf_counter()

        # Validate using same allowlist family (vertex models)
        fq = req.model if str(req.model).startswith("publishers/google/models/") else f"publishers/google/models/{req.model}"
        ok, msg = validate_model("vertex", fq)
        if not ok:
            raise ValueError(f"Invalid/unsupported Gemini model: {msg}")
        model_api = _to_direct_gemini_model(req.model)

        metadata: Dict[str, Any] = {
            "provider": "gemini_direct",
            "model": model_api,
            "response_api": "gemini_genai",
            "provider_api_version": "genai-v1",
            "allowlist_coupling": None,
            "grounding_attempted": False,
            "grounded_effective": False,
            "tool_call_count": 0,
            "final_function_called": None,
            "schema_args_valid": False,
            "why_not_grounded": None,
        }

        system_text, user_text = self._build_two_messages(req)
        metadata["als_position"] = _detect_als_position(system_text, user_text)
        
        is_grounded = bool(getattr(req, "grounded", False))
        is_json = bool(getattr(req, "json_mode", False))
        grounding_mode = getattr(req, "grounding_mode", "AUTO")
        if isinstance(getattr(req, "meta", None), dict):
            grounding_mode = req.meta.get("grounding_mode", grounding_mode)
        metadata["grounding_mode_requested"] = grounding_mode

        tools: List[Tool] = []
        schema_fn: Optional[FunctionDeclaration] = None
        tool_cfg: Optional[dict] = None

        if is_grounded or is_json:
            if is_grounded:
                tools.append(Tool(google_search=GoogleSearch()))
                metadata["grounding_attempted"] = True
            if is_json:
                schema_fn = _create_output_schema(req)
                tools.append(Tool(function_declarations=[schema_fn]))
            # Only set function_calling_config if we have function declarations (JSON schema)
            # GoogleSearch does not use function_calling_config
            if is_json and schema_fn:
                tool_cfg = {
                    "function_calling_config": {
                        "mode": "ANY" if grounding_mode == "REQUIRED" else "AUTO",
                        "allowed_function_names": [schema_fn.name]
                    }
                }

        cfg = self._gen_cfg(req, system_text, tools if tools else None, tool_cfg)

        # Implement retry with exponential backoff and circuit breaker
        max_attempts = 4  # 1 initial + 3 retries
        base_delay = 0.5
        request_id = metadata.get("request_id") or f"req_{int(time.time()*1000)}_{random.randint(1000,9999)}"
        metadata["request_id"] = request_id
        
        # Check circuit breaker
        breaker_key = f"gemini_direct:{model_api}"
        breaker = _circuit_breakers.get(breaker_key)
        if not breaker:
            breaker = CircuitBreakerState()
            _circuit_breakers[breaker_key] = breaker
            
        # Check if circuit is open
        if breaker.state == "open":
            if breaker.open_until and datetime.now() > breaker.open_until:
                # Try half-open
                breaker.state = "half-open"
                logger.info(f"[gemini_direct] Circuit breaker half-open for {breaker_key}")
            else:
                # Fail fast
                metadata["circuit_state"] = "open"
                metadata["breaker_open_reason"] = "consecutive_503s"
                metadata["error_type"] = "service_unavailable_upstream"
                raise Exception(f"Circuit breaker open for {breaker_key} until {breaker.open_until}")
        
        metadata["circuit_state"] = breaker.state
        
        resp = None
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** (attempt - 1))  # 0.5s, 1s, 2s, 4s
                    jitter = random.uniform(0, delay * 0.5)  # Up to 50% jitter
                    total_delay = delay + jitter
                    metadata["backoff_ms_last"] = int(total_delay * 1000)
                    logger.info(f"[gemini_direct] Retry {attempt}/{max_attempts-1} after {total_delay:.2f}s for {request_id}")
                    await asyncio.sleep(total_delay)
                
                # Make the API call
                resp = await asyncio.wait_for(
                    run_in_threadpool(
                        self.client.models.generate_content,
                        model=model_api,
                        contents=user_text,
                        config=cfg
                    ),
                    timeout=timeout
                )
                
                # Success - reset circuit breaker
                if breaker.state == "half-open" or breaker.consecutive_failures > 0:
                    logger.info(f"[gemini_direct] Circuit breaker reset for {breaker_key}")
                breaker.consecutive_failures = 0
                breaker.state = "closed"
                metadata["retry_count"] = attempt
                break
                
            except asyncio.TimeoutError:
                raise
            except Exception as e:
                error_str = str(e)
                last_error = e
                
                # Check if it's a 503 error
                if "503" in error_str or "UNAVAILABLE" in error_str:
                    breaker.consecutive_failures += 1
                    breaker.total_503_count += 1
                    breaker.last_failure_time = datetime.now()
                    
                    metadata["upstream_status"] = 503
                    metadata["upstream_error"] = "UNAVAILABLE"
                    
                    # Check if we should open the circuit
                    if breaker.consecutive_failures >= 5:
                        # Open circuit for 60-120 seconds
                        hold_time = random.randint(60, 120)
                        breaker.state = "open"
                        breaker.open_until = datetime.now() + timedelta(seconds=hold_time)
                        metadata["circuit_state"] = "open"
                        metadata["breaker_open_reason"] = f"{breaker.consecutive_failures}_consecutive_503s"
                        logger.error(f"[gemini_direct] Circuit breaker opened for {breaker_key} after {breaker.consecutive_failures} consecutive 503s")
                    
                    # Check for Retry-After header (if available in response)
                    # Note: google.genai doesn't expose headers directly, so we use exponential backoff
                    
                    if attempt < max_attempts - 1:
                        logger.warning(f"[gemini_direct] 503 error on attempt {attempt+1}/{max_attempts}: {error_str}")
                        continue
                else:
                    # Non-503 error, don't retry
                    logger.error(f"[gemini_direct] Non-503 error: {error_str}")
                    raise
        
        if resp is None:
            metadata["retry_count"] = max_attempts - 1
            metadata["error_type"] = "service_unavailable_upstream"
            raise last_error or Exception("All retry attempts failed")

        # Extract response text first
        response_text = _extract_text_from_response(resp)
        
        # Inspect grounding and extract anchored citations
        grounded_effective = False
        schema_valid = False
        annotations = []
        citations = []

        if is_grounded:
            grounded_effective, tool_calls = detect_vertex_grounding(resp)
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = tool_calls
            
            # Extract anchored citations
            annotations, citations, cmeta = _extract_anchored_citations(resp, response_text)
            metadata.update(cmeta)
            
            if not grounded_effective:
                metadata["why_not_grounded"] = "No GoogleSearch usage detected"

        # JSON mode check
        if is_json and schema_fn:
            fname, fargs = _extract_function_call(resp)
            metadata["final_function_called"] = fname
            if fname == schema_fn.name and fargs is not None:
                schema_valid = True
                metadata["schema_args_valid"] = True
                response_text = json.dumps(fargs)
            else:
                metadata["schema_args_valid"] = False

        # REQUIRED policy — Option A (relaxed for Google vendors)
        if grounding_mode == "REQUIRED":
            if is_grounded:
                if metadata.get("anchored_citations_count", 0) > 0:
                    # Prefer anchored citations
                    metadata["required_pass_reason"] = "anchored_google"
                elif grounded_effective:
                    # Fall back to unlinked if tools ran
                    tc = int(metadata.get("tool_call_count", 0) or 0)
                    unlinked = int(metadata.get("unlinked_sources_count", 0) or 0)
                    
                    # Defensive: Allow pass if search ran but evidence is missing
                    if tc > 0 and metadata.get("grounding_evidence_missing"):
                        metadata["required_pass_reason"] = "unlinked_google"
                        logger.info(f"[gemini_direct] REQUIRED mode defensive pass: search ran but evidence missing")
                    elif tc > 0 and unlinked > 0:
                        metadata["required_pass_reason"] = "unlinked_google"
                    else:
                        raise GroundingRequiredFailedError("REQUIRED grounding mode but no evidence found.")
                else:
                    raise GroundingRequiredFailedError("REQUIRED grounding mode but no grounding detected.")
            if is_json and not schema_valid:
                raise ValueError(f"REQUIRED mode but no valid schema function call.")

        metadata["response_time_ms"] = int((time.perf_counter() - t0) * 1000)
        if hasattr(resp, "model_version"):
            metadata["modelVersion"] = resp.model_version

        # Add citations and annotations to metadata
        if annotations:
            metadata["annotations"] = annotations
        if citations:
            metadata["citations"] = citations
            metadata["citation_count"] = len(citations)

        # Usage estimation
        usage = {}
        if getattr(settings, 'USAGE_ESTIMATION_ENABLED', False):
            try:
                method = os.getenv("USAGE_ESTIMATE_METHOD", "char4")
                pad = float(os.getenv("USAGE_ESTIMATE_PAD", "1.15"))
                input_tokens = _estimate_tokens((system_text or "") + (user_text or ""), method=method, pad=pad)
                output_tokens = _estimate_tokens(response_text, method=method, pad=pad)
                usage = {
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens),
                    "total_tokens": int(input_tokens + output_tokens),
                    "source": "estimate",
                    "estimate_method": method,
                    "estimate_pad": pad
                }
                metadata["usage_is_estimated"] = True
                metadata["usage_source"] = "estimate"
            except Exception as e:
                logger.debug(f"Usage estimation failed: {e}")
                metadata["usage_is_estimated"] = False
                metadata["usage_source"] = "unknown"
        else:
            metadata["usage_is_estimated"] = False
            metadata["usage_source"] = "unknown"

        # Attestation
        metadata["attestation"] = {
            "strategy": "single_call",
            "step2_tools_invoked": False,
            "two_step_required": False
        }
        
        metadata["anchor_extraction_status"] = (
            "available" if metadata.get('anchored_citations_count', 0) > 0 else "not_available"
        )

        # Store annotations in metadata if present
        if annotations:
            metadata["annotations"] = annotations
            
        return LLMResponse(
            content=response_text,
            model_version=getattr(resp, "model", req.model),
            model_fingerprint=getattr(resp, 'model_version', None),
            grounded_effective=grounded_effective,
            usage=usage,
            latency_ms=metadata["response_time_ms"],
            raw_response=resp.model_dump() if hasattr(resp, "model_dump") else None,
            success=bool(response_text),
            vendor='gemini_direct',
            model=req.model,
            metadata=metadata,
            citations=citations if citations else None,
            error_type=None if response_text else "EMPTY_COMPLETION",
            error_message=None if response_text else "No completion generated"
        )