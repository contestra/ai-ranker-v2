"""
OpenAI Adapter - Lean implementation using Responses API only.
Focuses on shape conversion, policy enforcement, and telemetry.
Transport/retries/backoff handled by SDK.
"""
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from app.core.config import get_settings
# GroundingRequiredFailedError removed - REQUIRED enforcement now in router only
from app.llm.models import OPENAI_ALLOWED_MODELS, validate_model
from app.llm.als_config import ALSConfig
from app.llm.types import LLMRequest, LLMResponse
from app.llm.util.meta_utils import ensure_meta_aliases, get_meta
from app.llm.util.usage_utils import normalize_usage_openai
from app.llm.util.citation_utils import dedupe_citations, recompute_citation_counts
from app.llm.adapters.constants import WEB_TOOL_TYPE_NONE
from app.llm.adapters.citation_authorities import get_all_authority_domains

logger = logging.getLogger(__name__)
settings = get_settings()

# Environment configuration
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "5"))
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
GROUNDED_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_GROUNDED_MAX_TOKENS", "6000"))
MIN_OUTPUT_TOKENS = 16  # Responses API minimum

# Feature flags for grounded mode
OPENAI_PROVOKER_ENABLED = os.getenv("OPENAI_PROVOKER_ENABLED", "true").lower() == "true"
OPENAI_GROUNDED_TWO_STEP = os.getenv("OPENAI_GROUNDED_TWO_STEP", "false").lower() == "true"
OPENAI_GROUNDED_MAX_EVIDENCE = int(os.getenv("OPENAI_GROUNDED_MAX_EVIDENCE", "5"))

# Tool negotiation feature flag and constants
OPENAI_SEARCH_NEGOTIATION_ENABLED = os.getenv("OPENAI_SEARCH_NEGOTIATION_ENABLED", "true").lower() == "true"
NEGOTIATION_FROM = "web_search"
NEGOTIATION_TO = "web_search_preview"

# TextEnvelope schema for ungrounded fallback (GPT-5 empty text quirk)
TEXT_ENVELOPE_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"}
    },
    "required": ["content"],
    "additionalProperties": False
}


class OpenAIAdapter:
    """Lean OpenAI adapter using Responses API exclusively."""
    
    def __init__(self):
        """Initialize with SDK-managed client."""
        local_settings = get_settings()
        api_key = os.getenv("OPENAI_API_KEY") or local_settings.openai_api_key
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        
        # Let SDK handle all transport concerns
        self.client = AsyncOpenAI(
            api_key=api_key,
            max_retries=OPENAI_MAX_RETRIES,
            timeout=OPENAI_TIMEOUT_SECONDS
        )
        
        self.allowlist = OPENAI_ALLOWED_MODELS
        logger.info(
            f"[OAI_INIT] Adapter initialized - "
            f"max_retries={OPENAI_MAX_RETRIES}, timeout={OPENAI_TIMEOUT_SECONDS}s"
        )
    
    def _build_payload(self, request: LLMRequest, is_grounded: bool) -> Dict:
        """Build Responses API payload preserving full conversation history."""
        meta = get_meta(request)
        
        # Preserve full conversation history
        input_messages = []
        
        for msg in request.messages:
            role = msg["role"]
            content = msg["content"]
            
            # Map role appropriately (system, user, assistant)
            if role == "system":
                input_messages.append({
                    "role": "system",
                    "content": [{"type": "input_text", "text": content}]
                })
            elif role == "user":
                input_messages.append({
                    "role": "user",
                    "content": [{"type": "input_text", "text": content}]
                })
            elif role == "assistant":
                input_messages.append({
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content}]
                })
            # Skip any other roles for now
        
        # Base payload
        # Use the model exactly as provided - no silent rewrites (router enforces immutability)
        effective_model = request.model
        
        if is_grounded:
            # Grounded: use higher default (6000) to avoid token starvation
            # Caller can still override with lower value if needed
            max_tokens = request.max_tokens or GROUNDED_MAX_OUTPUT_TOKENS
            # But still cap at the maximum we allow
            max_tokens = min(max_tokens, GROUNDED_MAX_OUTPUT_TOKENS)
            
            payload = {
                "model": effective_model,
                "input": input_messages,
                "tools": [{"type": "web_search"}],  # Will negotiate if needed
                "max_output_tokens": max(max_tokens, MIN_OUTPUT_TOKENS)
            }
            
            # Tool choice for grounding mode
            # Note: web_search only supports "auto" tool_choice
            # NOTE: web_search only supports tool_choice="auto".
            # Router handles REQUIRED mode enforcement centrally
            payload["tool_choice"] = "auto"
            
            # Add text format to ensure final synthesis
            payload["text"] = {
                "format": {"type": "text"}
            }
        else:
            # Ungrounded: respect caller's max_tokens if provided, otherwise use default
            max_tokens = request.max_tokens or 1024
            payload = {
                "model": effective_model,
                "input": input_messages,
                "tools": [],
                "max_output_tokens": max(max_tokens, MIN_OUTPUT_TOKENS)
            }
            
            # Honor router capabilities for reasoning hints
            caps_container = getattr(request, "metadata", None)
            caps = caps_container.get("capabilities", {}) if isinstance(caps_container, dict) else {}
            reasoning_requested = meta.get("reasoning_effort") is not None
            
            if caps.get("supports_reasoning_effort", False):
                # Router says this model supports reasoning hints
                reasoning_effort = meta.get("reasoning_effort", "minimal")
                payload["reasoning"] = {"effort": reasoning_effort}
                # Note: metadata tracking happens in complete() method, not here
            elif reasoning_requested:
                # Reasoning was requested but not supported
                # Note: metadata tracking happens in complete() method, not here
                logger.debug(f"[OPENAI] Dropped reasoning hint for non-reasoning model: {request.model}")
        
        # Add JSON schema if requested
        json_schema = meta.get("json_schema")
        if json_schema:
            schema = json_schema.get("schema", {})
            if "additionalProperties" not in schema:
                schema["additionalProperties"] = False
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.get("name", "Output"),
                    "schema": schema,
                    "strict": True
                }
            }
        elif not is_grounded:
            # Add text format hint for ungrounded
            payload["text"] = {
                "format": {"type": "text"}
            }
        
        return payload
    
    async def _call_with_tool_negotiation(self, payload: Dict, timeout: int) -> Tuple[Any, str, Dict]:
        """Call Responses API with tool type negotiation for grounded.
        
        Returns: (response, effective_tool_type, negotiation_metadata)
        """
        web_tool_type = NEGOTIATION_FROM  # Start with web_search
        tried_negotiation = False
        negotiation_reason = None
        
        try:
            # Try with web_search first
            response = await self.client.responses.create(**payload, timeout=timeout)
            negotiation_metadata = {
                "web_tool_negotiation": "none",
                "tried_negotiation": False
            }
            return response, web_tool_type, negotiation_metadata
        except Exception as exc:
            if OPENAI_SEARCH_NEGOTIATION_ENABLED:
                needs_fallback, reason = self._oai_needs_preview_fallback_from_exc(exc)
                if needs_fallback and not tried_negotiation:
                    tried_negotiation = True
                    negotiation_reason = reason or "structured_or_message_match"
                    
                    # Log the negotiation
                    logger.info(f"[OPENAI] tool negotiation: {NEGOTIATION_FROM}→{NEGOTIATION_TO} reason={negotiation_reason}")
                    
                    # Retry with web_search_preview
                    payload["tools"] = [{"type": NEGOTIATION_TO}]
                    web_tool_type = NEGOTIATION_TO
                    response = await self.client.responses.create(**payload, timeout=timeout)
                    
                    negotiation_metadata = {
                        "web_tool_negotiation": f"{NEGOTIATION_FROM}→{NEGOTIATION_TO}",
                        "web_tool_negotiation_reason": negotiation_reason,
                        "tried_negotiation": True
                    }
                    return response, web_tool_type, negotiation_metadata
                else:
                    # Check if preview itself is unsupported
                    error_str = str(exc).lower()
                    if "hosted tool 'web_search_preview' is not supported" in error_str:
                        logger.warning(f"[OAI] web_search_preview not supported for model {payload.get('model')}, failing closed")
                        raise ValueError(f"Grounding not supported for model {payload.get('model')}: {exc}")
                    raise
            else:
                # Negotiation disabled - re-raise original exception
                raise
    
    def _extract_content(self, response: Any, is_grounded: bool = False) -> Tuple[str, str]:
        """Extract text content from response.
        Returns: (content, source)
        """
        # For grounded: prefer output_text (where final synthesis appears)
        # For ungrounded: try message items first, then output_text
        
        if is_grounded:
            # Grounded: output_text is primary
            if hasattr(response, 'output_text') and response.output_text:
                return response.output_text, "output_text"
            
            # Fallback to message items
            if hasattr(response, 'output') and isinstance(response.output, list):
                for item in response.output:
                    if hasattr(item, 'type') and item.type == 'message':
                        if hasattr(item, 'content') and isinstance(item.content, list):
                            texts = []
                            for content_item in item.content:
                                if hasattr(content_item, 'text'):
                                    texts.append(content_item.text)
                            if texts:
                                return '\n'.join(texts), "message"
            
            # Log if we have search but no content
            if hasattr(response, 'output') and isinstance(response.output, list):
                has_search = any(
                    hasattr(item, 'type') and 'search' in item.type 
                    for item in response.output
                )
                if has_search:
                    logger.warning("[OAI] Grounded response has search results but no output_text or message")
        else:
            # Ungrounded: try message items first
            if hasattr(response, 'output') and isinstance(response.output, list):
                for item in response.output:
                    if hasattr(item, 'type') and item.type == 'message':
                        if hasattr(item, 'content') and isinstance(item.content, list):
                            texts = []
                            for content_item in item.content:
                                if hasattr(content_item, 'text'):
                                    texts.append(content_item.text)
                            if texts:
                                return '\n'.join(texts), "message"
            
            # Fallback to output_text
            if hasattr(response, 'output_text') and response.output_text:
                return response.output_text, "output_text"
        
        return "", "none"
    
    def _count_tool_calls(self, response: Any) -> Tuple[int, List[str]]:
        """Count tool calls in response.
        Returns: (count, tool_types)
        """
        count = 0
        types = []
        
        if hasattr(response, 'output') and isinstance(response.output, list):
            for item in response.output:
                if hasattr(item, 'type'):
                    # Broaden detection: any item with "search" and ("call" or "tool")
                    if 'search' in item.type and ('call' in item.type or 'tool' in item.type):
                        count += 1
                        types.append(item.type)
        
        return count, types
    
    def _extract_openai_citations(self, response: Any, source_type: str = "web_search_result") -> Tuple[List[Dict[str, Any]], int, int]:
        """Extract citations from OpenAI response.
        Returns: (citations list, anchored_count, unlinked_count)
        """
        from urllib.parse import urlparse
        
        citations = []
        anchored_count = 0
        seen_urls = set()
        seen_domains = set()
        
        if hasattr(response, 'output') and isinstance(response.output, list):
            for item in response.output:
                # Look for web_search_call items
                if hasattr(item, 'type') and 'search' in item.type and 'call' in item.type:
                    # Try different possible attributes for search results
                    search_results = None
                    
                    # Try search_results attribute
                    if hasattr(item, 'search_results') and isinstance(item.search_results, list):
                        search_results = item.search_results
                    # Try results attribute
                    elif hasattr(item, 'results') and isinstance(item.results, list):
                        search_results = item.results
                    # Try web_results attribute
                    elif hasattr(item, 'web_results') and isinstance(item.web_results, list):
                        search_results = item.web_results
                    
                    if search_results:
                        for result in search_results:
                            url = getattr(result, 'url', None) or getattr(result, 'link', None)
                            if url:
                                # Normalize URL for deduplication
                                normalized_url = url.lower().strip('/')
                                if normalized_url in seen_urls:
                                    continue
                                seen_urls.add(normalized_url)
                                
                                # Extract and normalize domain
                                parsed = None
                                try:
                                    parsed = urlparse(url)
                                    domain = parsed.netloc.lower().replace('www.', '')
                                except:
                                    domain = 'unknown'
                                
                                # Secondary dedup by domain (only keep first from each domain)
                                domain_key = domain + '_' + (parsed.path[:50] if parsed else '')
                                if domain_key in seen_domains and len(citations) >= 10:
                                    continue
                                seen_domains.add(domain_key)
                                
                                # Extract title
                                title = getattr(result, 'title', '') or getattr(result, 'name', '') or ''
                                
                                # Check for anchored annotations (rare in OpenAI)
                                has_annotation = getattr(result, 'annotation', None) is not None
                                if has_annotation:
                                    anchored_count += 1
                                    citation_type = "url_annotation"
                                else:
                                    citation_type = source_type
                                
                                citations.append({
                                    'url': url,
                                    'title': title[:200] if title else '',
                                    'domain': domain,
                                    'source_type': citation_type,
                                    'type': 'anchored'  # OpenAI citations always have URLs
                                })
                                
                                # Limit to top 10 citations
                                if len(citations) >= 10:
                                    break
        
        # Second pass: check message items for anchored citations
        # This handles cases where citations appear inline without explicit web_search_call
        if hasattr(response, 'output') and isinstance(response.output, list):
            for item in response.output:
                if hasattr(item, 'type') and item.type == 'message':
                    if hasattr(item, 'content') and isinstance(item.content, list):
                        for content_item in item.content:
                            # Check for annotations, references, or citations on the content part
                            annotations = None
                            if hasattr(content_item, 'annotations'):
                                annotations = content_item.annotations
                            elif hasattr(content_item, 'references'):
                                annotations = content_item.references
                            elif hasattr(content_item, 'citations'):
                                annotations = content_item.citations
                            
                            if annotations and isinstance(annotations, list):
                                for annotation in annotations:
                                    url = None
                                    if hasattr(annotation, 'url'):
                                        url = annotation.url
                                    elif hasattr(annotation, 'link'):
                                        url = annotation.link
                                    elif hasattr(annotation, 'href'):
                                        url = annotation.href
                                    
                                    if url:
                                        # Normalize URL for deduplication
                                        normalized_url = url.lower().strip('/')
                                        if normalized_url not in seen_urls:
                                            seen_urls.add(normalized_url)
                                            
                                            # Extract domain
                                            try:
                                                parsed = urlparse(url)
                                                domain = parsed.netloc.lower().replace('www.', '')
                                            except:
                                                domain = 'unknown'
                                            
                                            # Extract title if available
                                            title = ''
                                            if hasattr(annotation, 'title'):
                                                title = annotation.title
                                            elif hasattr(annotation, 'text'):
                                                title = annotation.text
                                            elif hasattr(annotation, 'name'):
                                                title = annotation.name
                                            
                                            # These are anchored by definition
                                            anchored_count += 1
                                            
                                            citations.append({
                                                'url': url,
                                                'title': title[:200] if title else '',
                                                'domain': domain,
                                                'source_type': 'url_annotation',
                                                'type': 'anchored'  # Has URL
                                            })
                                            
                                            # Still limit to 10 total
                                            if len(citations) >= 10:
                                                break
        
        # Calculate unlinked count
        unlinked_count = len(citations) - anchored_count
        
        return citations, anchored_count, unlinked_count
    
    def _extract_citations(self, response: Any) -> Tuple[List[Dict[str, Any]], int, int]:
        """Legacy wrapper for citation extraction - delegates to new method."""
        return self._extract_openai_citations(response, source_type="web_search_result")
    
    def _oai_needs_preview_fallback_from_exc(self, exc) -> tuple[bool, str]:
        """
        Return (needs_fallback, reason). Prefer structured fields from the SDK/HTTP response.
        Fallback to message substrings only if structured fields are missing.
        """
        # Try structured attributes the SDK often exposes
        status = getattr(exc, "status", None) or getattr(exc, "http_status", None)
        data = getattr(exc, "response", None) or getattr(exc, "error", None)
        
        # Some SDKs attach a dict under .response or .error
        err_obj = None
        if isinstance(data, dict):
            err_obj = data.get("error") or data
        
        err_type = (err_obj or {}).get("type") if err_obj else None
        err_code = (err_obj or {}).get("code") if err_obj else None
        err_msg = ((err_obj or {}).get("message") if err_obj else None) or str(exc)
        
        # Heuristics: hosted tool unsupported for this account/model
        structured_hit = (
            status in (400, 404) and
            (err_type in ("invalid_request_error", "unsupported_feature", "parameter_error", None)) and
            (
                (err_code and "tool" in str(err_code).lower()) or
                ("web_search" in (err_msg or "").lower() and "not support" in err_msg.lower())
            )
        )
        if structured_hit:
            return True, f"{status or 'NA'}:{err_type or 'NA'}:{err_code or 'NA'}"
        
        # Last-resort substrings
        msg = (str(exc) or "").lower()
        substr_hits = [
            "hosted tool 'web_search' is not supported",
            "unsupported tool type: web_search",
            "unknown tool: web_search",
            "tools not enabled for this model"
        ]
        if any(s in msg for s in substr_hits):
            return True, "message_match"
        
        return False, ""
    
    def _standardize_finish_reason(self, reason: str) -> str:
        """Standardize finish reasons for cross-vendor comparison.
        
        Maps vendor-specific finish reasons to common values:
        - STOP: Normal completion
        - MAX_TOKENS: Hit token limit
        - SAFETY: Content filtered for safety
        - ERROR: Error occurred
        - UNKNOWN: Unknown reason
        """
        if not reason:
            return "UNKNOWN"
        
        reason_lower = reason.lower()
        
        # Map OpenAI reasons to standardized values
        if reason_lower in ("stop", "stopped", "complete", "completed"):
            return "STOP"
        elif reason_lower in ("length", "max_tokens", "token_limit"):
            return "MAX_TOKENS"
        elif reason_lower in ("content_filter", "safety", "blocked"):
            return "SAFETY"
        elif reason_lower in ("error", "failed"):
            return "ERROR"
        elif reason_lower == "tool_calls_only":
            return "TOOL_CALLS"  # OpenAI-specific but useful to track
        else:
            # Keep original if no mapping found
            return reason.upper()
    
    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete request using Responses API only."""
        start_time = time.perf_counter()
        
        # Normalize meta and metadata to be interchangeable
        ensure_meta_aliases(request)
        meta = get_meta(request)
        
        # Validate model
        ok, msg = validate_model("openai", request.model)
        if not ok:
            raise ValueError(f"Invalid OpenAI model: {msg}")
        
        # Prepare metadata
        seed_key_id = ALSConfig.get_seed_key_id("openai")
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": "openai",
            "model": request.model,
            "response_api": "responses_sdk",
            "provider_api_version": "openai:responses-v1 (sdk)",
            "seed_key_id": seed_key_id
        }
        
        # Mark ALS provenance in metadata
        ALSConfig.mark_als_metadata(metadata, seed_key_id, "openai")
        
        is_grounded = request.grounded
        grounding_mode = meta.get("grounding_mode", "AUTO") if is_grounded else None
        
        try:
            # Build payload
            payload = self._build_payload(request, is_grounded)
            effective_model = payload["model"]
            if effective_model != request.model:
                metadata["mapped_model"] = effective_model
            
            # Track reasoning hints in metadata (was attempted in _build_payload but metadata not available there)
            caps_container = getattr(request, "metadata", None)
            caps = caps_container.get("capabilities", {}) if isinstance(caps_container, dict) else {}
            reasoning_requested = meta.get("reasoning_effort") is not None
            
            if caps.get("supports_reasoning_effort", False) and "reasoning" in payload:
                metadata["reasoning_effort_applied"] = payload["reasoning"].get("effort", "minimal")
            elif reasoning_requested:
                metadata["reasoning_hint_dropped"] = True
                metadata["reasoning_hint_drop_reason"] = "model_not_capable"
            
            # Make API call
            if is_grounded:
                # Grounded: negotiate tool type
                response, web_tool_type, negotiation_metadata = await self._call_with_tool_negotiation(payload, timeout)
                
                # Add negotiation breadcrumbs to metadata
                metadata["web_tool_type_initial"] = NEGOTIATION_FROM  # Always starts with web_search
                metadata["web_tool_type_final"] = web_tool_type
                metadata["web_tool_type"] = web_tool_type  # Keep for backward compatibility
                
                # Add negotiation metadata
                metadata["web_tool_negotiation"] = negotiation_metadata.get("web_tool_negotiation", "none")
                if negotiation_metadata.get("web_tool_negotiation_reason"):
                    metadata["web_tool_negotiation_reason"] = negotiation_metadata["web_tool_negotiation_reason"]
                
                # Legacy flag for backward compatibility
                if negotiation_metadata.get("tried_negotiation"):
                    metadata["web_tool_type_negotiated"] = True
                
                # Extract tool evidence
                tool_count, tool_types = self._count_tool_calls(response)
                metadata["tool_call_count"] = tool_count
                metadata["tool_types"] = tool_types
                metadata["grounded_evidence_present"] = tool_count > 0
                
                # Early REQUIRED check - must have tool calls
                # Final check happens after citation extraction
            else:
                # Ungrounded: direct call
                response = await self.client.responses.create(**payload, timeout=timeout)
                metadata["tool_call_count"] = 0
                metadata["grounded_evidence_present"] = False
                
                # Check if we need TextEnvelope fallback
                content, source = self._extract_content(response, is_grounded=False)
                if not content:
                    # Single fallback for GPT-5 empty text quirk
                    logger.info("[OAI] Empty ungrounded response, trying TextEnvelope fallback")
                    metadata["fallback_used"] = True
                    
                    # Wrap with TextEnvelope schema
                    fallback_payload = payload.copy()
                    fallback_payload["text"] = {
                        "format": {
                            "type": "json_schema",
                            "name": "TextEnvelope",
                            "schema": TEXT_ENVELOPE_SCHEMA,
                            "strict": True
                        }
                    }
                    
                    # Make fallback call
                    response = await self.client.responses.create(**fallback_payload, timeout=timeout)
                    
                    # Extract from JSON envelope
                    if hasattr(response, 'output_text') and response.output_text:
                        try:
                            envelope = json.loads(response.output_text)
                            content = envelope.get("content", "")
                            source = "text_envelope"
                        except json.JSONDecodeError:
                            content = ""
                            source = "failed_envelope"
                else:
                    metadata["fallback_used"] = False
            
            # Extract content for grounded (or use ungrounded result)
            citations = []
            anchored_count = 0
            unlinked_count = 0
            if is_grounded:
                metadata["why_not_grounded"] = None  # Grounded was requested
                content, source = self._extract_content(response, is_grounded=True)
                metadata["fallback_used"] = False
                # Extract raw citations from web search results
                raw_citations, raw_anchored, raw_unlinked = self._extract_citations(response)
                
                # Apply citation deduplication
                authority_domains = get_all_authority_domains()
                # Get official domains from request if available (future enhancement)
                official_domains = set()
                if hasattr(request, 'metadata') and request.metadata:
                    official_domains = request.metadata.get('official_domains', set())
                
                # Deduplicate citations
                citations = dedupe_citations(
                    raw_citations,
                    official_domains=official_domains,
                    authority_domains=authority_domains,
                    per_domain_cap=2
                )
                
                # Recompute counts after deduplication
                anchored_count, unlinked_count = recompute_citation_counts(citations)
                
                # Set both canonical and legacy fields
                metadata["citation_count"] = len(citations)  # Legacy field for BC
                metadata["anchored_citations_count"] = anchored_count
                metadata["unlinked_sources_count"] = unlinked_count
                
                # Add deduplication telemetry
                if raw_citations and len(raw_citations) != len(citations):
                    metadata["citation_dedup_applied"] = True
                    metadata["citations_raw_count"] = len(raw_citations)
                    metadata["citations_deduped_count"] = len(citations)
                
                # NEW (P8a): persist the final, deduped list for router/UI presentation
                metadata["citations"] = citations or []
                
                # If we have anchored citations but no tool calls, still mark as grounded
                if anchored_count > 0 and metadata["tool_call_count"] == 0:
                    metadata["grounded_evidence_present"] = True
                    metadata["extraction_path"] = "openai_anchored_annotations"
                
                # Provoker retry: if enabled and we have searches but no content, try once more with a provoker
                if OPENAI_PROVOKER_ENABLED and tool_count > 0 and not content:
                    logger.info("[OAI] Grounded response has searches but no content, trying provoker retry")
                    metadata["provoker_retry_used"] = True
                    metadata["provoker_initial_tool_type"] = web_tool_type  # What we used before retry
                    metadata["initial_empty_reason"] = "search_only_output"  # Document why initial was empty
                    
                    # Add provoker message to input
                    utc_date = datetime.utcnow().strftime("%Y-%m-%d")
                    provoker_text = f"As of today ({utc_date}), produce a concise final answer that directly answers the user and include at least one official source URL."
                    metadata["provoker_value"] = provoker_text
                    
                    provoker_payload = payload.copy()
                    provoker_payload["input"] = provoker_payload["input"].copy()
                    provoker_payload["input"].append({
                        "role": "user",
                        "content": [{"type": "input_text", "text": provoker_text}]
                    })
                    
                    # Retry with provoker
                    response, retry_tool_type = await self._call_with_tool_negotiation(provoker_payload, timeout)
                    content, source = self._extract_content(response, is_grounded=True)
                    
                    # Track both initial and final tool types for retry
                    metadata["provoker_final_tool_type"] = retry_tool_type
                    if retry_tool_type != web_tool_type:
                        metadata["provoker_tool_type_changed"] = True
                        logger.info(f"[OAI] Tool type changed from {web_tool_type} to {retry_tool_type} during provoker retry")
                    
                    # Update the final tool type for overall tracking
                    metadata["web_tool_type_final"] = retry_tool_type
                    metadata["web_tool_type"] = retry_tool_type  # Update for backward compatibility
                    
                    # Re-extract citations from the new response
                    if content:
                        citations, anchored_count, unlinked_count = self._extract_citations(response)
                        metadata["citation_count"] = len(citations)
                        metadata["anchored_citations_count"] = anchored_count
                        metadata["unlinked_sources_count"] = unlinked_count
                        
                        # Recalculate grounded evidence after provoker
                        if anchored_count > 0 and metadata["tool_call_count"] == 0:
                            metadata["grounded_evidence_present"] = True
                            metadata["extraction_path"] = "openai_anchored_annotations"
                    
                    # Two-step fallback if still empty and flag is enabled
                    if tool_count > 0 and not content and OPENAI_GROUNDED_TWO_STEP:
                        logger.info("[OAI] Provoker failed, attempting two-step synthesis")
                        metadata["synthesis_step_used"] = True
                        metadata["synthesis_tool_count"] = tool_count
                        metadata["provoker_no_content_reason"] = "persistent_empty_after_provoker"
                        
                        # Preserve Step-A citations for final response
                        step_a_citations = citations.copy() if citations else []
                        
                        # Build evidence block from citations (capped by OPENAI_GROUNDED_MAX_EVIDENCE)
                        evidence_lines = []
                        evidence_citations = []
                        for i, cite in enumerate(citations[:OPENAI_GROUNDED_MAX_EVIDENCE], 1):
                            title = cite.get('title', 'Untitled')[:80]
                            url = cite.get('url', '')
                            if url:
                                evidence_lines.append(f"{i}) {title} — {url}")
                                # Mark these as evidence_list type for Step-B
                                evidence_cite = cite.copy()
                                evidence_cite['source_type'] = 'evidence_list'
                                evidence_citations.append(evidence_cite)
                        
                        metadata["synthesis_evidence_count"] = len(evidence_lines)
                        
                        # Build synthesis payload without tools
                        synthesis_payload = {
                            "model": effective_model,
                            "input": payload["input"].copy(),
                            "tools": [],  # No tools for synthesis
                            "max_output_tokens": max(payload.get("max_output_tokens", 1024), MIN_OUTPUT_TOKENS)
                        }
                        
                        # Add evidence and synthesis instruction
                        if evidence_lines:
                            evidence_text = "Evidence (for your synthesis):\n" + "\n".join(evidence_lines)
                            synthesis_payload["input"].append({
                                "role": "user",
                                "content": [{"type": "input_text", "text": evidence_text}]
                            })
                        
                        synthesis_payload["input"].append({
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Synthesize a final answer now. Do not browse. Cite from the evidence list only."}]
                        })
                        
                        # Keep text format if it was requested
                        if "text" in payload:
                            synthesis_payload["text"] = payload["text"]
                        
                        # Call without tools for synthesis
                        response = await self.client.responses.create(**synthesis_payload, timeout=timeout)
                        content, source = self._extract_content(response, is_grounded=False)  # Use ungrounded extraction for synthesis
                        metadata["text_source"] = f"synthesis_{source}"
                        
                        # Use evidence citations from Step-A since Step-B has no tools
                        if content and evidence_citations:
                            citations = evidence_citations
                            anchored_count = 0  # No anchored citations in synthesis
                            unlinked_count = len(citations)
                            metadata["citation_count"] = len(citations)
                            metadata["anchored_citations_count"] = anchored_count
                            metadata["unlinked_sources_count"] = unlinked_count
                            metadata["synthesis_evidence_count"] = len(citations)
                        else:
                            # Even two-step failed to produce content
                            metadata["synthesis_no_content_reason"] = "two_step_synthesis_failed"
                            logger.warning("[OAI] Two-step synthesis still produced no content")
                    else:
                        # Provoker succeeded or wasn't attempted for two-step
                        if not content:
                            metadata["provoker_no_content_reason"] = "provoker_retry_empty"
                else:
                    metadata["provoker_retry_used"] = False
                    metadata["provoker_value"] = None  # No provoker used
                
                # Initialize telemetry fields if not set
                if "synthesis_step_used" not in metadata:
                    metadata["synthesis_step_used"] = False
                if "synthesis_tool_count" not in metadata:
                    metadata["synthesis_tool_count"] = 0
                if "synthesis_evidence_count" not in metadata:
                    metadata["synthesis_evidence_count"] = 0
                if "provoker_value" not in metadata:
                    metadata["provoker_value"] = None
            else:
                # Ungrounded - always set counts and flags to defaults
                metadata["anchored_citations_count"] = 0
                metadata["unlinked_sources_count"] = 0
                metadata["provoker_retry_used"] = False
                metadata["synthesis_step_used"] = False
                metadata["synthesis_tool_count"] = 0
                metadata["synthesis_evidence_count"] = 0
                metadata["provoker_value"] = None
                metadata["why_not_grounded"] = "not_requested"  # User didn't request grounding
            
            metadata["text_source"] = source
            
            # Final diagnostic: log if we still have no content after all attempts
            if is_grounded and tool_count > 0 and not content:
                logger.warning(f"[OAI] Grounded response has {tool_count} tool calls but still no output_text after all retries")
                metadata["final_empty_reason"] = metadata.get("synthesis_no_content_reason") or metadata.get("provoker_no_content_reason") or "all_attempts_failed"
                metadata["empty_despite_tools"] = True
            
            # REQUIRED mode enforcement removed - now handled centrally in router
            # Adapter only reports the facts: tool_call_count, citations, etc.
            
            # Extract usage and normalize
            usage_raw = {}
            if hasattr(response, 'usage'):
                usage_obj = response.usage
                # Collect all raw usage fields
                usage_raw = {
                    "prompt_tokens": getattr(usage_obj, 'input_tokens', 0),
                    "completion_tokens": getattr(usage_obj, 'output_tokens', 0),
                    "reasoning_tokens": getattr(usage_obj, 'reasoning_tokens', 0),
                    "total_tokens": getattr(usage_obj, 'total_tokens', 0)
                }
                
                # Normalize usage for consistent analytics
                normalized_usage, vendor_usage = normalize_usage_openai(usage_raw)
                metadata["usage"] = normalized_usage
                metadata["vendor_usage"] = vendor_usage
            
            # Extract finish_reason for telemetry parity with Google adapters
            # Harmonized with Google path for cross-vendor comparisons
            finish_reason = None
            finish_reason_source = None
            
            # Priority 1: Check if SDK provides finish_reason (future-proofing)
            if hasattr(response, 'finish_reason') and response.finish_reason is not None:
                finish_reason = str(response.finish_reason)
                finish_reason_source = "sdk_native"
            # Priority 2: Check for stop_reason (current SDK field)
            elif hasattr(response, 'stop_reason') and response.stop_reason is not None:
                finish_reason = str(response.stop_reason)
                finish_reason_source = "stop_reason"
            # Priority 3: Infer from response characteristics
            else:
                if content:
                    # If we have content, likely finished normally
                    finish_reason = "stop"
                    finish_reason_source = "inferred_from_content"
                elif tool_count > 0:
                    # If we have tools but no content, might be a synthesis issue
                    finish_reason = "tool_calls_only"
                    finish_reason_source = "inferred_from_tools"
                else:
                    # No clear signal
                    finish_reason = "unknown"
                    finish_reason_source = "no_signal"
            
            # Store in metadata - harmonized with Google adapters
            metadata["finish_reason"] = finish_reason
            metadata["finish_reason_source"] = finish_reason_source
            
            # Map to standardized values for cross-vendor comparison
            # Google uses: STOP, MAX_TOKENS, SAFETY, etc.
            # OpenAI uses: stop, length, content_filter, etc.
            standardized = self._standardize_finish_reason(finish_reason)
            metadata["finish_reason_standardized"] = standardized
            
            # Calculate response hash for provenance
            if content:
                content_bytes = content.encode('utf-8')
                metadata["response_output_sha256"] = hashlib.sha256(content_bytes).hexdigest()
            else:
                metadata["response_output_sha256"] = None
            
            # Calculate latency
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            metadata["latency_ms"] = latency_ms
            
            # Ensure canonical telemetry keys are set (keep legacy aliases)
            # These are already set above but ensure consistency
            metadata.setdefault("tool_call_count", tool_count if is_grounded else 0)
            metadata.setdefault("anchored_citations_count", anchored_count if is_grounded else 0)
            metadata.setdefault("unlinked_sources_count", unlinked_count if is_grounded else 0)
            
            # Set canonical web_tool_type
            if is_grounded:
                # Map the negotiated tool type to canonical value
                if web_tool_type == "web_search":
                    metadata["web_tool_type"] = "web_search"
                elif web_tool_type == "web_search_preview":
                    metadata["web_tool_type"] = "web_search_preview"
                else:
                    metadata["web_tool_type"] = WEB_TOOL_TYPE_NONE
            else:
                metadata["web_tool_type"] = WEB_TOOL_TYPE_NONE
            
            
            # Debug logging for telemetry
            usage_info = metadata.get("usage", {})
            logger.debug(
                f"[ADAPTER:openai] tool_call_count={metadata.get('tool_call_count', 0)} "
                f"anchored={metadata.get('anchored_citations_count', 0)} "
                f"unlinked={metadata.get('unlinked_sources_count', 0)} "
                f"web_tool_type={metadata.get('web_tool_type', 'none')} "
                f"usage={{input:{usage_info.get('input_tokens', 0)}, "
                f"output:{usage_info.get('output_tokens', 0)}, "
                f"total:{usage_info.get('total_tokens', 0)}}}"
            )
            
            return LLMResponse(
                content=content,
                model_version=effective_model,
                model_fingerprint=None,
                grounded_effective=metadata.get("grounded_evidence_present", False),
                usage=metadata.get("vendor_usage", {}),
                latency_ms=latency_ms,
                raw_response=None,
                success=True,
                vendor="openai",
                model=request.model,
                metadata=metadata,
                citations=citations
            )
            
        # GroundingRequiredFailedError handling removed - router enforces REQUIRED
        except Exception as e:
            # Let SDK errors bubble up naturally
            logger.error(f"[OAI] API error: {str(e)[:200]}")
            raise
    
    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model in self.allowlist