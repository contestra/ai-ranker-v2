"""
Vertex AI adapter for Gemini models via Vertex AI.
Default allowed models: gemini-2.5-pro, gemini-2.0-flash
Configurable via ALLOWED_VERTEX_MODELS env var.

This adapter uses only the google-genai client. Legacy Vertex SDK has been removed 
per PRD-Adapter-Layer-V1 (Phase-0).

Implements two-step grounded JSON policy as required:
- Step 1: Gemini + GoogleSearch() for grounding
- Step 2: JSON reshape with tools=[], attestation fields
"""
import json
import os
import re
import time
import logging
import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Tuple

# REQUIRED: google-genai is the only client for Vertex/Gemini calls
import google.genai as genai
from google.genai.types import (
    HarmCategory,
    HarmBlockThreshold,
    GenerateContentConfig,
    Tool,
    GoogleSearch
)

from starlette.concurrency import run_in_threadpool

# Import settings for feature flags
from app.core.config import settings

from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model
from .grounding_detection_helpers import detect_vertex_grounding
from urllib.parse import urlparse, urlunparse, parse_qs
from app.llm.citations.resolver import resolve_citation_url, resolve_citations_with_budget
from app.llm.citations.domains import registrable_domain_from_url

logger = logging.getLogger(__name__)

# Debug flag for citation extraction
DEBUG_GROUNDING = os.getenv("DEBUG_GROUNDING", "false").lower() == "true"
# Optional: emit unlinked (non-anchored) sources when no anchored citations were found.
# Default false to keep telemetry clean; can be enabled per-run via env.
EMIT_UNLINKED_SOURCES = os.getenv("CITATION_EXTRACTOR_EMIT_UNLINKED", "false").lower() == "true"

# Centralized citation type definitions
# Router counts as anchored only JOIN/direct - text-anchored citations with specific spans
# Chunks/supports are evidence but not text-anchored, so they count as unlinked
ANCHORED_CITATION_TYPES = {"direct_uri", "v1_join"}
UNLINKED_CITATION_TYPES = {"unlinked", "legacy", "text_harvest", "groundingChunks"}

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
        
        # For Vertex redirects, keep the full domain
        if 'vertexaisearch.cloud.google.com' in domain:
            return domain
        
        # For most domains, return as-is (keeps subdomains)
        # Only strip for known second-level TLDs
        parts = domain.split('.')
        if len(parts) >= 3:
            # Check if it's a known second-level TLD pattern
            if parts[-2] in ['co', 'ac', 'gov', 'edu', 'org', 'net', 'com'] and parts[-1] in ['uk', 'jp', 'au', 'nz', 'za']:
                # e.g., example.co.uk -> return last 3 parts
                return '.'.join(parts[-3:])
        
        # For everything else, return full domain
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
        # Lowercase the host
        netloc = parsed.netloc.lower() if parsed.netloc else ""
        
        # Filter out UTM params
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in params.items() 
                       if not k.lower().startswith('utm_')}
            # Reconstruct query string
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


def _extract_text_from_candidates(response) -> str:
    """Extract text from Vertex response candidates."""
    if not response or not hasattr(response, 'candidates'):
        return ""
    
    texts = []
    for candidate in response.candidates:
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            for part in candidate.content.parts:
                if hasattr(part, 'text'):
                    texts.append(part.text)
    
    return ''.join(texts)


def _extract_citations_v2(response, tenant_id=None, account_id=None, template_id=None) -> tuple[List[Dict], Dict]:
    """
    Extract citations from Vertex response with v2 improvements.
    Returns (citations_list, telemetry_dict).
    
    Features:
    - Extract text-anchored citations (v1_join type)
    - Track anchored vs unlinked citations
    - Deduplicate by normalized URL
    - Return telemetry metrics
    """
    citations = []
    telemetry = {
        "citation_extractor_version": "v2",
        "anchored_count": 0,
        "unlinked_count": 0,
        "total_raw_count": 0,
        "legacy_count": 0,
        "text_harvest_count": 0,
        "chunks_count": 0,
        "supports_count": 0,
        "vertex_tool_calls": 0
    }
    
    # Track unique URLs for deduplication
    seen_urls = set()
    
    if not response:
        return citations, telemetry
    
    # Extract from grounding metadata if available
    if hasattr(response, 'candidates'):
        for candidate in response.candidates:
            # Check for grounding metadata
            if hasattr(candidate, 'grounding_metadata'):
                gm = candidate.grounding_metadata
                
                # Extract web_search_queries
                if hasattr(gm, 'web_search_queries'):
                    for query in gm.web_search_queries:
                        telemetry["vertex_tool_calls"] += 1
                
                # Extract grounding_chunks (evidence snippets)
                if hasattr(gm, 'grounding_chunks'):
                    for chunk in gm.grounding_chunks:
                        if hasattr(chunk, 'web'):
                            web = chunk.web
                            if hasattr(web, 'uri') and web.uri:
                                normalized = _normalize_url(web.uri)
                                if normalized not in seen_urls:
                                    seen_urls.add(normalized)
                                    citations.append({
                                        "url": web.uri,
                                        "title": getattr(web, 'title', ''),
                                        "snippet": '',
                                        "type": "groundingChunks",
                                        "domain": _get_registrable_domain(web.uri)
                                    })
                                    telemetry["chunks_count"] += 1
                                    telemetry["unlinked_count"] += 1
                
                # Extract grounding_supports (full documents)
                if hasattr(gm, 'grounding_supports'):
                    for support in gm.grounding_supports:
                        for chunk in support.grounding_chunk_indices:
                            if hasattr(chunk, 'web'):
                                web = chunk.web
                                if hasattr(web, 'uri') and web.uri:
                                    normalized = _normalize_url(web.uri)
                                    if normalized not in seen_urls:
                                        seen_urls.add(normalized)
                                        citations.append({
                                            "url": web.uri,
                                            "title": getattr(web, 'title', ''),
                                            "snippet": '',
                                            "type": "supports",
                                            "domain": _get_registrable_domain(web.uri)
                                        })
                                        telemetry["supports_count"] += 1
                                        telemetry["unlinked_count"] += 1
            
            # Extract from citation_metadata (text-anchored citations)
            if hasattr(candidate, 'citation_metadata') and hasattr(candidate.citation_metadata, 'citations'):
                for citation in candidate.citation_metadata.citations:
                    # Extract URI
                    uri = None
                    title = ""
                    if hasattr(citation, 'uri'):
                        uri = citation.uri
                    elif hasattr(citation, 'publicationDate'):
                        # Sometimes URI is in publicationDate field
                        uri = getattr(citation, 'publicationDate', '')
                    
                    if uri:
                        normalized = _normalize_url(uri)
                        if normalized not in seen_urls:
                            seen_urls.add(normalized)
                            
                            # Extract start/end indices for anchored citations
                            start_idx = getattr(citation, 'startIndex', None)
                            end_idx = getattr(citation, 'endIndex', None)
                            
                            citation_type = "v1_join" if start_idx is not None else "unlinked"
                            
                            citations.append({
                                "url": uri,
                                "title": getattr(citation, 'title', ''),
                                "snippet": '',
                                "type": citation_type,
                                "domain": _get_registrable_domain(uri),
                                "start_index": start_idx,
                                "end_index": end_idx
                            })
                            
                            if citation_type in ANCHORED_CITATION_TYPES:
                                telemetry["anchored_count"] += 1
                            else:
                                telemetry["unlinked_count"] += 1
    
    telemetry["total_raw_count"] = len(citations)
    
    # Filter based on settings
    if not EMIT_UNLINKED_SOURCES and telemetry["anchored_count"] > 0:
        # Keep only anchored citations if we have any
        citations = [c for c in citations if c["type"] in ANCHORED_CITATION_TYPES]
        telemetry["filtered_unlinked"] = telemetry["unlinked_count"]
        telemetry["unlinked_count"] = 0
    
    return citations, telemetry


def _select_and_extract_citations(response, tenant_id=None, account_id=None, template_id=None, tool_call_count=0) -> tuple[List[Dict], Dict]:
    """
    Select citation extractor based on A/B test configuration.
    Returns (citations_list, telemetry_dict).
    """
    # Always use v2 extractor (legacy removed in Phase-0)
    citations, telemetry = _extract_citations_v2(
        response, tenant_id=tenant_id, account_id=account_id, template_id=template_id
    )
    
    # Add tool call count to telemetry
    telemetry["vertex_tool_calls"] = tool_call_count
    
    return citations, telemetry


class VertexAdapter:
    """
    Vertex AI adapter using google-genai client exclusively.
    Legacy Vertex SDK support has been removed per PRD-Adapter-Layer-V1 (Phase-0).
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
        # This creates a single, reusable client configured for Vertex AI
        try:
            # This is the correct way to initialize the client for Vertex AI
            # Store it in self.genai_client for use by all methods
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
            # Hard error - no fallback to legacy SDK
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
    
    def _build_content_string(self, messages: List[Dict], als_block: str = None) -> tuple[str, str]:
        """
        Build content string from messages.
        Returns (system_instruction, user_content).
        Keeps system separate, ALS goes in first user message.
        """
        system_text = None
        user_texts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            
            if not text:
                continue
            
            if role == "system":
                # Keep system text separate for system_instruction
                if system_text is None:
                    system_text = text
                else:
                    system_text = f"{system_text}\n\n{text}"
            elif role == "user":
                # For first user message, prepend ALS if provided
                if als_block and not user_texts:
                    # ALS goes BEFORE user content in the user message
                    user_texts.append(als_block)
                user_texts.append(text)
            elif role == "assistant":
                # Add assistant messages as context
                user_texts.append(f"Assistant: {text}")
        
        # Combine user texts
        user_content = "\n\n".join(user_texts) if user_texts else ""
        
        return system_text, user_content
    
    def _create_generation_config_step1(self, req: LLMRequest) -> GenerateContentConfig:
        """Create generation config for Step 1 (grounded or ungrounded, NO JSON)."""
        # For ungrounded requests, ensure minimum tokens to avoid empty responses
        requested_tokens = getattr(req, "max_tokens", 6000)
        is_grounded = getattr(req, "grounded", False)
        
        # For ungrounded: increase minimum tokens to avoid empty responses
        if not is_grounded:
            if requested_tokens < 1500:
                logger.warning(f"Increasing max_tokens from {requested_tokens} to 1500 for Vertex ungrounded")
                max_tokens = 1500
            else:
                max_tokens = requested_tokens
        else:
            max_tokens = requested_tokens
        
        config = GenerateContentConfig(
            temperature=getattr(req, "temperature", 0.7),
            top_p=getattr(req, "top_p", 0.95),
            max_output_tokens=max_tokens,
        )
        
        # For ungrounded: slightly reduce temperature for stability
        if not is_grounded:
            if config.temperature > 0.5:
                config.temperature = max(0.5, config.temperature - 0.2)
                logger.debug(f"Reduced temperature to {config.temperature} for ungrounded stability")
        
        return config
    
    def _create_generation_config_step2_json(self) -> GenerateContentConfig:
        """Create generation config for Step 2 (JSON reshape, NO tools)."""
        return GenerateContentConfig(
            temperature=0.1,  # Low temp for consistent JSON
            max_output_tokens=6000,
            response_mime_type="application/json"
        )
    
    async def _step1_grounded_genai(self, req: LLMRequest, user_content: str, 
                                    generation_config: GenerateContentConfig, timeout: int, 
                                    mode: str = "AUTO", system_instruction: str = None) -> tuple[Any, bool, int]:
        """
        Step 1 using google-genai: Generate grounded response with GoogleSearch tool.
        Returns (response, grounded_effective, tool_call_count).
        """
        # Create GoogleSearch tool for grounding
        search_tool = Tool(google_search=GoogleSearch())
        
        logger.debug(f"[WIRE_DEBUG] Vertex Step-1 grounded call with genai")
        logger.debug(f"  Mode: {mode}")
        
        try:
            # Create GenerativeModel object - this is the correct approach!
            model_name = req.model.replace("publishers/google/models/", "")
            
            # Create the GenerativeModel with optional system instruction
            if system_instruction:
                model = genai.GenerativeModel(
                    model_name=f"publishers/google/models/{model_name}",
                    system_instruction=system_instruction
                )
            else:
                model = genai.GenerativeModel(
                    model_name=f"publishers/google/models/{model_name}"
                )
            
            # Now call generate_content on the MODEL object, not client.models
            response = await asyncio.wait_for(
                run_in_threadpool(
                    model.generate_content,
                    user_content,
                    generation_config=generation_config,
                    tools=[search_tool],
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                ),
                timeout=timeout
            )
            
            # Check if grounding was actually used
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            
            # Post-hoc enforcement for REQUIRED mode
            if mode == "REQUIRED" and not grounded_effective:
                raise ValueError(
                    f"REQUIRED mode specified but no grounding evidence found. "
                    f"Response must include web search results."
                )
            
            logger.debug(f"[VERTEX_GROUNDING] Step-1 complete: grounded={grounded_effective}, count={grounding_count}")
            
            return response, grounded_effective, grounding_count
            
        except asyncio.TimeoutError:
            logger.error(f"Vertex Step-1 grounded timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Vertex Step-1 grounded failed: {e}")
            raise
    
    async def _step2_reshape_json_genai(self, req: LLMRequest, step1_text: str, 
                                        original_request: str, timeout: int,
                                        system_instruction: str = None) -> Any:
        """
        Step 2 using google-genai: Reshape to JSON without tools.
        Includes attestation fields for integrity.
        """
        # Create prompt for JSON reshape
        json_prompt = f"""Based on the following information, create a JSON response.

Original Request: {original_request}

Information to structure as JSON:
{step1_text}

Respond ONLY with valid JSON that addresses the original request."""
        
        # JSON generation config (NO tools in step 2)
        config = self._create_generation_config_step2_json()
        
        try:
            model_name = req.model.replace("publishers/google/models/", "")
            
            # Use the client's models.generate_content method directly
            response = await asyncio.wait_for(
                run_in_threadpool(
                    self.genai_client.models.generate_content,
                    model=f"publishers/google/models/{model_name}",
                    contents=json_prompt,
                    config=config,
                    system_instruction=system_instruction,
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                ),
                timeout=timeout
            )
            
            return response
            
        except asyncio.TimeoutError:
            logger.error(f"Vertex Step-2 JSON reshape timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Vertex Step-2 JSON reshape failed: {e}")
            raise
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """
        Main entry point for Vertex adapter.
        Handles both grounded and ungrounded requests using google-genai.
        """
        start_time = time.time()
        
        # Validate model
        is_valid, error_msg = validate_model("vertex", req.model)
        if not is_valid:
            raise ValueError(f"Invalid model for Vertex: {error_msg}")
        model_id = req.model
        
        # Initialize metadata
        metadata = {
            "provider": "vertex",
            "model": model_id,
            "response_api": "vertex_genai",
            "provider_api_version": "vertex:genai-v1",
            "region": self.location,
            "proxies_enabled": False,
            "proxy_mode": "disabled",
            "vantage_policy": str(getattr(req, "vantage_policy", "NONE")),
            # Feature flags for monitoring
            "feature_flags": {
                "citation_extractor_v2": settings.citation_extractor_v2,
                "citation_extractor_enable_legacy": False,  # Legacy removed
                "ungrounded_retry_policy": settings.ungrounded_retry_policy,
                "text_harvest_auto_only": settings.text_harvest_auto_only,
                "citations_extractor_enable": settings.citations_extractor_enable,
            }
        }
        
        # Build content and extract system instruction
        system_instruction, user_content = self._build_content_string(req.messages, None)
        
        # Check if JSON mode is needed
        is_json_mode = getattr(req, "json_mode", False)
        is_grounded = getattr(req, "grounded", False)
        
        # Extract grounding mode (AUTO or REQUIRED)
        grounding_mode = getattr(req, "grounding_mode", "AUTO")
        if hasattr(req, "meta") and isinstance(req.meta, dict):
            grounding_mode = req.meta.get("grounding_mode", grounding_mode)
        metadata["grounding_mode_requested"] = grounding_mode
        
        # Determine two-step requirement
        needs_two_step = is_grounded and is_json_mode
        
        if needs_two_step:
            logger.info(f"Two-step grounded JSON mode activated (mode={grounding_mode})")
            
            # Step 1: Grounded generation (NO JSON)
            generation_config = self._create_generation_config_step1(req)
            step1_resp, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                req, user_content, generation_config, timeout, 
                mode=grounding_mode, system_instruction=system_instruction
            )
            
            # Extract citations from Step 1
            tenant_id = req.meta.get("tenant_id") if hasattr(req, "meta") else None
            account_id = req.meta.get("account_id") if hasattr(req, "meta") else None
            template_id = req.meta.get("template_id") if hasattr(req, "meta") else None
            
            step1_citations, citation_telemetry = _select_and_extract_citations(
                step1_resp, tenant_id=tenant_id, account_id=account_id, 
                template_id=template_id, tool_call_count=tool_call_count
            )
            metadata.update(citation_telemetry)
            step1_text = _extract_text_from_candidates(step1_resp)
            
            # Step 2: Reshape to JSON (NO TOOLS)
            original_request = ""
            for msg in reversed(req.messages):
                if msg.get("role") == "user":
                    original_request = msg.get("content", "")
                    break
            
            step2_resp = await self._step2_reshape_json_genai(
                req, step1_text, original_request, timeout, system_instruction
            )
            
            # Use Step 2 response as final, but keep Step 1 citations
            response = step2_resp
            citations = step1_citations
            
            # Add attestation fields
            metadata["step2_tools_invoked"] = False  # No tools in step 2
            metadata["step2_source_ref"] = hashlib.sha256(step1_text.encode()).hexdigest()[:16]
            metadata["grounded_effective"] = grounded_effective
            
        elif is_grounded:
            # Grounded non-JSON request
            generation_config = self._create_generation_config_step1(req)
            response, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                req, user_content, generation_config, timeout, 
                mode=grounding_mode, system_instruction=system_instruction
            )
            
            # Extract citations
            tenant_id = req.meta.get("tenant_id") if hasattr(req, "meta") else None
            account_id = req.meta.get("account_id") if hasattr(req, "meta") else None
            template_id = req.meta.get("template_id") if hasattr(req, "meta") else None
            
            citations, citation_telemetry = _select_and_extract_citations(
                response, tenant_id=tenant_id, account_id=account_id,
                template_id=template_id, tool_call_count=tool_call_count
            )
            metadata.update(citation_telemetry)
            metadata["grounded_effective"] = grounded_effective
            
        else:
            # Ungrounded request
            generation_config = self._create_generation_config_step1(req)
            
            # Add JSON mode if requested
            if is_json_mode:
                generation_config.response_mime_type = "application/json"
            
            model_name = req.model.replace("publishers/google/models/", "")
            
            # Use the client's models.generate_content method directly for ungrounded
            response = await asyncio.wait_for(
                run_in_threadpool(
                    self.genai_client.models.generate_content,
                    model=f"publishers/google/models/{model_name}",
                    contents=user_content,
                    config=generation_config,
                    system_instruction=system_instruction,
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                ),
                timeout=timeout
            )
            
            citations = []
            metadata["grounded_effective"] = False
        
        # Extract response text
        response_text = _extract_text_from_candidates(response)
        
        # Add timing
        metadata["response_time_ms"] = int((time.time() - start_time) * 1000)
        
        # Add model version if available
        if hasattr(response, 'model_version'):
            metadata["modelVersion"] = response.model_version
        
        return LLMResponse(
            text=response_text,
            metadata=metadata,
            citations=citations if citations else None
        )