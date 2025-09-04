"""
Vertex AI adapter for Gemini models via Vertex AI.
Uses single-call Forced Function Calling (FFC) strategy for grounded + structured output.
No two-step fallback, no prompt mutations beyond ALS placement.

This adapter uses only the google-genai client. Legacy Vertex SDK has been removed 
per PRD-Adapter-Layer-V1 (Phase-0).
"""
import json
import os
import random
import re
import time
import logging
import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# REQUIRED: google-genai is the only client for Vertex/Gemini calls
import google.genai as genai
from google.genai.types import (
    HarmCategory,
    HarmBlockThreshold,
    GenerateContentConfig,
    Content,
    Part,
    Tool,
    GoogleSearch,
    FunctionDeclaration,
    Schema,
    ToolConfig,
    FunctionCallingConfig,
    SafetySetting
)

from starlette.concurrency import run_in_threadpool

# Import settings for feature flags
from app.core.config import settings

from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model
from .grounding_detection_helpers import detect_vertex_grounding
from urllib.parse import urlparse, urlunparse, parse_qs
from app.llm.errors import GroundingRequiredFailedError

logger = logging.getLogger(__name__)

# Circuit breaker state management (shared with gemini_adapter for consistency)
@dataclass
class VertexCircuitBreakerState:
    """Circuit breaker state for a specific vendor+model combination."""
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "closed"  # closed, open, half-open
    open_until: Optional[datetime] = None
    total_503_count: int = 0
    
# Global circuit breaker states per model
_vertex_circuit_breakers: Dict[str, VertexCircuitBreakerState] = {}

# Debug flag for citation extraction
DEBUG_GROUNDING = os.getenv("DEBUG_GROUNDING", "false").lower() == "true"
# Optional: emit unlinked (non-anchored) sources when no anchored citations were found.
EMIT_UNLINKED_SOURCES = os.getenv("CITATION_EXTRACTOR_EMIT_UNLINKED", "false").lower() == "true"

# Centralized citation type definitions
ANCHORED_CITATION_TYPES = {"direct_uri", "v1_join"}
UNLINKED_CITATION_TYPES = {"unlinked", "legacy", "text_harvest", "groundingChunks"}


def _get_registrable_domain(url: str) -> str:
    """Extract registrable domain from URL."""
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
        
        # For Vertex redirects, keep the full domain
        if 'vertexaisearch.cloud.google.com' in domain:
            return domain
        
        # For most domains, return as-is (keeps subdomains)
        parts = domain.split('.')
        if len(parts) >= 3:
            # Check if it's a known second-level TLD pattern
            if parts[-2] in ['co', 'ac', 'gov', 'edu', 'org', 'net', 'com'] and parts[-1] in ['uk', 'jp', 'au', 'nz', 'za']:
                return '.'.join(parts[-3:])
        
        return domain
    except:
        return ""


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower() if parsed.netloc else ""
        
        # Filter out UTM params
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in params.items() 
                       if not k.lower().startswith('utm_')}
            query = '&'.join([f"{k}={'&'.join(v)}" if v else k 
                             for k, v in filtered.items()])
        else:
            query = ""
        
        # Rebuild URL without fragment/anchor
        return urlunparse((
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            query,
            ""  # No fragment
        ))
    except:
        return url


def _extract_text_from_response(response) -> str:
    """Extract text from Vertex response."""
    if not response or not hasattr(response, 'candidates'):
        return ""
    
    texts = []
    for candidate in response.candidates:
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            for part in candidate.content.parts:
                if hasattr(part, 'text'):
                    texts.append(part.text)
    
    return ''.join(texts)


def _extract_function_call(response) -> tuple[Optional[str], Optional[Dict]]:
    """
    Extract the final function call from response.
    Returns (function_name, arguments_dict) or (None, None) if no function call.
    """
    if not response or not hasattr(response, 'candidates'):
        return None, None
    
    for candidate in response.candidates:
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            for part in candidate.content.parts:
                if hasattr(part, 'function_call'):
                    fc = part.function_call
                    return fc.name, dict(fc.args) if hasattr(fc, 'args') else {}
    
    return None, None


def _extract_redirect_url(google_url: str) -> str:
    """Extract real URL from Google grounding redirect."""
    if "vertexaisearch.cloud.google.com/grounding-api-redirect/" in google_url:
        # This is a redirect URL, extract if possible
        # For now, return as-is; in production, decode the redirect
        return google_url
    return google_url


def _extract_anchored_citations(response, response_text: str) -> tuple[List[Dict], List[Dict], Dict]:
    """
    Extract both anchored and unlinked citations from Vertex response.
    
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
        "vertex_tool_calls": 0,
        "anchored_coverage_pct": 0.0,
        "why_not_anchored": None,
        "grounding_evidence_missing": False
    }
    
    anchored_sources = set()
    all_chunks = {}  # chunk_index -> chunk_data
    
    if not response:
        return annotations, list(citations_map.values()), telemetry
    
    try:
        # Extract from grounding metadata if available
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                # Check for grounding metadata
                if hasattr(candidate, 'grounding_metadata'):
                    gm = candidate.grounding_metadata
                    
                    # Count tool calls (web searches)
                    web_searches = getattr(gm, 'web_search_queries', []) or []
                    telemetry["vertex_tool_calls"] = len(web_searches)
                    
                    # First, collect all chunks
                    chunks = getattr(gm, 'grounding_chunks', []) or []
                    
                    # Defensive: Check if search ran but chunks are empty
                    if len(web_searches) > 0 and len(chunks) == 0:
                        logger.warning(f"[vertex] Search executed ({len(web_searches)} queries), "
                                     "but grounding_chunks are empty. Anchored citations unavailable.")
                        telemetry["why_not_anchored"] = "API_RESPONSE_MISSING_GROUNDING_CHUNKS"
                        telemetry["grounding_evidence_missing"] = True
                    
                    if hasattr(gm, 'grounding_chunks'):
                        for idx, chunk in enumerate(gm.grounding_chunks):
                            if hasattr(chunk, 'web'):
                                web = chunk.web
                                if hasattr(web, 'uri') and web.uri:
                                    raw_uri = web.uri
                                    resolved_url = _extract_redirect_url(web.uri)
                                    title = getattr(web, 'title', '') or ''
                                    
                                    all_chunks[idx] = {
                                        "raw_uri": raw_uri,
                                        "resolved_url": resolved_url,
                                        "title": title,
                                        "domain": _get_registrable_domain(resolved_url),
                                        "chunk_index": idx
                                    }
                    
                    # Now process grounding supports for anchored citations
                    covered_chars = 0
                    supports = getattr(gm, 'grounding_supports', []) or []
                    
                    # Defensive: Check if search ran but supports are empty
                    if len(web_searches) > 0 and len(supports) == 0:
                        logger.warning(f"[vertex] Search executed ({len(web_searches)} queries), "
                                     "but grounding_supports are empty. Anchored citations unavailable.")
                        if not telemetry.get("why_not_anchored"):
                            telemetry["why_not_anchored"] = "API_RESPONSE_MISSING_GROUNDING_SUPPORTS"
                        telemetry["grounding_evidence_missing"] = True
                    
                    if hasattr(gm, 'grounding_supports'):
                        for support in gm.grounding_supports:
                            segment = getattr(support, 'segment', None)
                            if not segment:
                                continue
                                
                            # Extract text position
                            start_idx = getattr(segment, 'start_index', None)
                            end_idx = getattr(segment, 'end_index', None)
                            text = getattr(segment, 'text', None)
                            
                            if start_idx is None or end_idx is None:
                                continue
                                
                            # Get referenced chunks
                            chunk_indices = getattr(support, 'grounding_chunk_indices', []) or []
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
                                # Verify text matches if possible
                                if text and response_text and start_idx < len(response_text):
                                    actual_text = response_text[start_idx:end_idx]
                                    if text != actual_text:
                                        logger.debug(f"Text mismatch: expected '{text}', got '{actual_text}'")
                                
                                annotations.append({
                                    "start": start_idx,
                                    "end": end_idx,
                                    "text": text or (response_text[start_idx:end_idx] if response_text else ""),
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
        logger.warning(f"[Vertex anchored citations] extraction failed: {e}")
    
    # Convert citations map to list
    citations = list(citations_map.values())
    
    # Filter based on settings if needed
    if not EMIT_UNLINKED_SOURCES and telemetry['anchored_citations_count'] > 0:
        # Keep only anchored citations
        citations = [c for c in citations if c.get("count", 0) > 0]
        telemetry["filtered_unlinked"] = telemetry['unlinked_sources_count']
        telemetry['unlinked_sources_count'] = 0
    
    return annotations, citations, telemetry


def _create_output_schema(req: LLMRequest) -> FunctionDeclaration:
    """
    Create a FunctionDeclaration that represents our desired JSON output schema.
    The function's parameters will be the structured output we want.
    """
    # Default schema for general structured output
    # This should be customized based on the specific request requirements
    schema = Schema(
        type="object",
        properties={
            "response": Schema(type="string", description="The main response content"),
            "data": Schema(
                type="object",
                description="Structured data extracted from the response",
                properties={}  # Dynamic based on request
            )
        },
        required=["response"]
    )
    
    # Create the function declaration
    return FunctionDeclaration(
        name="format_response",
        description="Format the response in the required structure",
        parameters=schema
    )


class VertexAdapter:
    """
    Vertex AI adapter using google-genai client with single-call FFC strategy.
    No two-step fallback, enforces prompt purity.
    """
    
    def __init__(self):
        """Initialize Vertex adapter with hard requirement for google-genai."""
        # Get project and location from environment
        self.project = os.getenv("VERTEX_PROJECT", os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT")))
        self.location = os.getenv("VERTEX_LOCATION", "europe-west4")
        
        if not self.project:
            raise ValueError(
                "VERTEX_PROJECT, GCP_PROJECT, or GOOGLE_CLOUD_PROJECT environment variable is required. "
                "Please set one of these variables to your GCP project ID."
            )
        
        # Initialize the google-genai client for Vertex AI backend
        try:
            self.genai_client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location
            )
            logger.info(
                f"[VERTEX_STARTUP] google-genai client initialized successfully. "
                f"Project: {self.project}, Location: {self.location}"
            )
        except Exception as e:
            error_msg = (
                f"Failed to initialize google-genai client: {e}\n"
                f"This is a REQUIRED dependency. Please ensure:\n"
                f"1. google-genai is installed: pip install google-genai>=0.8.3\n"
                f"2. Authentication is configured: gcloud auth application-default login\n"
                f"3. Project {self.project} and location {self.location} are valid"
            )
            logger.error(f"[VERTEX_STARTUP] {error_msg}")
            raise RuntimeError(error_msg)
        
        # Log version info
        try:
            genai_version = genai.__version__ if hasattr(genai, '__version__') else 'unknown'
            logger.info(f"Vertex adapter initialized: google-genai={genai_version}")
        except:
            logger.info("Vertex adapter initialized with google-genai")
    
    def _build_two_messages(self, req: LLMRequest, als_block: str = None) -> tuple[str, str]:
        """
        Build exactly two messages: system and user.
        Returns (system_content, user_content).
        
        System: canonical system instruction + optional ALS block (≤350 chars)
        User: naked user prompt (byte-for-byte)
        """
        system_parts = []
        user_text = ""
        
        # Process messages - we expect system + user only
        system_found = False
        user_found = False
        
        for msg in req.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if not content:
                continue
            
            if role == "system":
                if system_found:
                    # Multiple system messages - concatenate
                    system_parts.append(content)
                else:
                    system_parts.append(content)
                    system_found = True
            elif role == "user":
                if user_found:
                    # Multiple user messages - this violates our constraint
                    raise ValueError(
                        f"Multiple user messages not allowed for Vertex. "
                        f"Expected exactly 2 messages (system + user), got multiple user messages."
                    )
                user_text = content  # Keep byte-for-byte
                user_found = True
            elif role == "assistant":
                raise ValueError(
                    f"Assistant messages not allowed for Vertex single-call. "
                    f"Expected exactly 2 messages (system + user), got assistant message."
                )
        
        # Build system content
        system_content = "\n\n".join(system_parts) if system_parts else ""
        
        # Add ALS block to system if provided
        if als_block:
            # Validate ALS length
            if len(als_block) > 350:
                raise ValueError(f"ALS block exceeds 350 chars: {len(als_block)}")
            
            if system_content:
                system_content = f"{system_content}\n\n{als_block}"
            else:
                system_content = als_block
        
        # Ensure we have a user message
        if not user_text:
            raise ValueError("No user message found. Expected exactly 2 messages (system + user).")
        
        return system_content, user_text
    
    def _create_generation_config(self, req: LLMRequest, system_content: str = None, 
                                   tools: list = None, tool_config: dict = None,
                                   safety_settings: list = None) -> GenerateContentConfig:
        """Create generation config for single-call FFC with tools."""
        config_params = {
            "temperature": getattr(req, "temperature", 0.7),
            "topP": getattr(req, "top_p", 0.95),  # Note: camelCase for google-genai
            "maxOutputTokens": getattr(req, "max_tokens", 6000),  # Note: camelCase
        }
        
        # Add system instruction if present
        if system_content:
            config_params["systemInstruction"] = system_content
        
        # Add tools if present
        if tools:
            config_params["tools"] = tools
        
        # Add tool config if present
        if tool_config:
            config_params["toolConfig"] = ToolConfig(
                function_calling_config=FunctionCallingConfig(
                    mode=tool_config.get("function_calling_config", {}).get("mode", "AUTO"),
                    allowed_function_names=tool_config.get("function_calling_config", {}).get("allowed_function_names")
                )
            )
        
        # Add safety settings if present
        if safety_settings:
            config_params["safetySettings"] = [
                SafetySetting(
                    category=cat,
                    threshold=thresh
                )
                for cat, thresh in safety_settings.items()
            ]
        
        return GenerateContentConfig(**config_params)
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """
        Main entry point for Vertex adapter.
        Single-call FFC strategy for grounded + structured output.
        """
        # Use monotonic clock for accurate timing
        start_time = time.perf_counter()
        
        # Initialize metadata early for finally block
        metadata = {
            "provider": "vertex",
            "model": req.model,
            "response_api": "vertex_genai",
            "provider_api_version": "vertex:genai-v1",
            "region": self.location,
            "grounding_attempted": False,
            "grounded_effective": False,
            "tool_call_count": 0,
            "final_function_called": None,
            "schema_args_valid": False,
            "why_not_grounded": None,
            "response_time_ms": 0  # Initialize timing field
        }
        
        try:
            # Validate model
            is_valid, error_msg = validate_model("vertex", req.model)
            if not is_valid:
                raise ValueError(f"Invalid model for Vertex: {error_msg}")
            model_id = req.model
            
            # Build exactly two messages
            system_content, user_content = self._build_two_messages(req)
            
            # Runtime assert: exactly 2 messages
            message_count = sum([
                1 if system_content else 0,
                1 if user_content else 0
            ])
            assert message_count == 2, f"Expected exactly 2 messages, got {message_count}"
            
            # Check if grounding is requested
            is_grounded = getattr(req, "grounded", False)
            is_json_mode = getattr(req, "json_mode", False)
        
            # Extract grounding mode (AUTO or REQUIRED)
            grounding_mode = getattr(req, "grounding_mode", "AUTO")
            if hasattr(req, "meta") and isinstance(req.meta, dict):
                grounding_mode = req.meta.get("grounding_mode", grounding_mode)
            metadata["grounding_mode_requested"] = grounding_mode
        
            # Prepare model name for google-genai client
            model_name = req.model
            if not model_name.startswith("publishers/google/models/"):
                model_name = f"publishers/google/models/{model_name}"
        
            # Prepare tools for FFC
            tools = []
            schema_function = None
            tool_config = None
        
            if is_grounded or is_json_mode:
                # Add GoogleSearch for grounding
                if is_grounded:
                    tools.append(Tool(google_search=GoogleSearch()))
                    metadata["grounding_attempted"] = True
            
                # Add SchemaFunction for structured output
                if is_json_mode:
                    schema_function = _create_output_schema(req)
                    tools.append(Tool(function_declarations=[schema_function]))
            
                # Map Contestra mode to genai mode
                # AUTO → "AUTO", REQUIRED → "ANY" (Gemini doesn't accept "REQUIRED")
                tool_config = {
                    "function_calling_config": {
                        "mode": "ANY" if grounding_mode == "REQUIRED" else "AUTO"
                    }
                }
            
                # If we have a schema function, restrict final output to it
                if schema_function:
                    tool_config["function_calling_config"]["allowed_function_names"] = [
                        schema_function.name
                    ]
        
            # Configure safety settings
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        
            # Configure generation with tools embedded
            generation_config = self._create_generation_config(
                req,
                system_content=system_content,
                tools=tools if tools else None,
                tool_config=tool_config,
                safety_settings=safety_settings
            )
        
            # Single call with FFC (tools embedded in config) with retry logic
            max_attempts = 4  # 1 initial + 3 retries
            base_delay = 0.5
            request_id = metadata.get("request_id") or f"req_{int(time.time()*1000)}_{random.randint(1000,9999)}"
            metadata["request_id"] = request_id
        
            # Check circuit breaker
            breaker_key = f"vertex:{model_name}"
            breaker = _vertex_circuit_breakers.get(breaker_key)
            if not breaker:
                breaker = VertexCircuitBreakerState()
                _vertex_circuit_breakers[breaker_key] = breaker
            
            # Check if circuit is open
            if breaker.state == "open":
                if breaker.open_until and datetime.now() > breaker.open_until:
                    # Try half-open
                    breaker.state = "half-open"
                    logger.info(f"[vertex] Circuit breaker half-open for {breaker_key}")
                else:
                    # Fail fast
                    metadata["circuit_state"] = "open"
                    metadata["breaker_open_reason"] = "consecutive_503s"
                    metadata["error_type"] = "service_unavailable_upstream"
                    raise Exception(f"Circuit breaker open for {breaker_key} until {breaker.open_until}")
        
            metadata["circuit_state"] = breaker.state
        
            response = None
            last_error = None
        
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        # Exponential backoff with jitter
                        delay = base_delay * (2 ** (attempt - 1))  # 0.5s, 1s, 2s, 4s
                        jitter = random.uniform(0, delay * 0.5)  # Up to 50% jitter
                        total_delay = delay + jitter
                        metadata["backoff_ms_last"] = int(total_delay * 1000)
                        logger.info(f"[vertex] Retry {attempt}/{max_attempts-1} after {total_delay:.2f}s for {request_id}")
                        await asyncio.sleep(total_delay)
                
                    # Build contents for google-genai (just user message since system is in config)
                    contents = user_content  # google-genai accepts string directly
                
                    response = await asyncio.wait_for(
                        run_in_threadpool(
                            self.genai_client.models.generate_content,
                            model=model_name,
                            contents=contents,
                            config=generation_config  # Contains system instruction, tools, tool_config, safety settings
                        ),
                        timeout=timeout
                    )
                
                    # Success - reset circuit breaker
                    if breaker.state == "half-open" or breaker.consecutive_failures > 0:
                        logger.info(f"[vertex] Circuit breaker reset for {breaker_key}")
                    breaker.consecutive_failures = 0
                    breaker.state = "closed"
                    metadata["retry_count"] = attempt
                    break
                    
                except asyncio.TimeoutError:
                    logger.error(f"Vertex FFC call timed out after {timeout}s")
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
                            logger.error(f"[vertex] Circuit breaker opened for {breaker_key} after {breaker.consecutive_failures} consecutive 503s")
                    
                        if attempt < max_attempts - 1:
                            logger.warning(f"[vertex] 503 error on attempt {attempt+1}/{max_attempts}: {error_str}")
                            continue
                    else:
                        # Non-503 error, don't retry
                        logger.error(f"[vertex] Non-503 error: {error_str}")
                        raise
        
            if response is None:
                metadata["retry_count"] = max_attempts - 1
                metadata["error_type"] = "service_unavailable_upstream"
                raise last_error or Exception("All retry attempts failed")
        
            # Extract response text first
            response_text = _extract_text_from_response(response)
        
            # Post-call verification
            grounded_effective = False
            schema_valid = False
            citations = []
            annotations = []
        
            if is_grounded:
                # Check for grounding evidence
                grounded_effective, grounding_count = detect_vertex_grounding(response)
                metadata["grounded_effective"] = grounded_effective
                metadata["tool_call_count"] = grounding_count
            
                if not grounded_effective:
                    metadata["why_not_grounded"] = "No GoogleSearch usage detected"
            
                # Extract anchored citations
                annotations, citations, citation_telemetry = _extract_anchored_citations(response, response_text)
                metadata.update(citation_telemetry)
        
            if is_json_mode and schema_function:
                # Check for valid schema function call
                func_name, func_args = _extract_function_call(response)
                metadata["final_function_called"] = func_name
            
                if func_name == schema_function.name and func_args is not None:
                    schema_valid = True
                    metadata["schema_args_valid"] = True
                    # Use function arguments as the response
                    response_text = json.dumps(func_args)
                else:
                    metadata["schema_args_valid"] = False
                    # response_text already extracted above
        
            # Enforce REQUIRED mode post-hoc (with relaxation for Google vendors)
            if grounding_mode == "REQUIRED":
                if is_grounded:
                    if metadata.get("anchored_citations_count", 0) > 0:
                        # Prefer anchored citations
                        metadata["required_pass_reason"] = "anchored_google"
                    elif grounded_effective:
                        # Fall back to unlinked if tools ran
                        tc = int(metadata.get("tool_call_count", 0) or 0)
                        unlinked = int(metadata.get("unlinked_sources_count", 0) or 0)
                        if tc > 0 and unlinked > 0:
                            metadata["required_pass_reason"] = "unlinked_google"
                        else:
                            raise GroundingRequiredFailedError(
                                f"REQUIRED grounding mode specified but no grounding evidence found. "
                                f"Tool calls: {metadata.get('tool_call_count', 0)}"
                            )
                    else:
                        raise GroundingRequiredFailedError(
                            f"REQUIRED grounding mode specified but no grounding detected."
                        )
                if is_json_mode and not schema_valid:
                    raise ValueError(
                        f"REQUIRED mode specified but no valid schema function call found. "
                        f"Final function: {metadata.get('final_function_called', 'None')}"
                    )
        
            # Calculate timing using monotonic clock
            # This is done here but should be in finally block - moving below
        
            # Add model version if available
            if hasattr(response, 'model_version'):
                metadata["modelVersion"] = response.model_version
        
            # Add citations and annotations to metadata for telemetry compatibility
            if citations:
                metadata["citations"] = citations
                metadata["citation_count"] = len(citations)
            if annotations:
                metadata["annotations"] = annotations
        
            # Add anchor extraction status
            metadata["anchor_extraction_status"] = (
                "available" if metadata.get('anchored_citations_count', 0) > 0 else "not_available"
            )
        
            # Store annotations in metadata if present
            if annotations:
                metadata["annotations"] = annotations
        
            # Build usage dict (Vertex doesn't provide detailed token counts)
            usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        
            # Try to get usage from response if available
            if hasattr(response, 'usage_metadata'):
                usage_meta = response.usage_metadata
                if usage_meta:
                    usage["prompt_tokens"] = getattr(usage_meta, 'prompt_token_count', 0)
                    usage["completion_tokens"] = getattr(usage_meta, 'candidates_token_count', 0)
                    usage["total_tokens"] = getattr(usage_meta, 'total_token_count', 0)
            
                # Return the response
                return LLMResponse(
                    content=response_text,
                    model_version=getattr(response, '_model_id', req.model),
                    model_fingerprint=None,
                    grounded_effective=grounded_effective,
                    usage=usage,
                    latency_ms=metadata.get("response_time_ms", 0),
                    raw_response=None,
                    success=bool(response_text),
                    vendor='vertex',
                    model=req.model,
                    metadata=metadata,
                    citations=citations if citations else None,
                    error_type=None if response_text else "EMPTY_COMPLETION",
                    error_message=None if response_text else "No completion generated"
                )
        
        finally:
            # Always record timing, even on errors
            metadata["response_time_ms"] = int((time.perf_counter() - start_time) * 1000)