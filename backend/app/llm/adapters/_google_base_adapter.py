"""
_google_base_adapter.py
Shared Google adapter logic for Gemini Direct and Vertex.
- Unifies message shaping, grounding setup, JSON mode wiring, citation extraction
- Implements deterministic redirect decoding for vertexaisearch.cloud.google.com links
- Normalizes metadata keys expected by the router/telemetry
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlunparse, unquote, unquote_plus, urlencode

import google.genai as genai
from google.genai.types import (
    FunctionCallingConfig, FunctionDeclaration, GenerateContentConfig,
    GoogleSearch, HarmBlockThreshold, HarmCategory, SafetySetting, Schema,
    ThinkingConfig, Tool, ToolConfig
)

# GroundingRequiredFailedError removed - REQUIRED enforcement now in router only
from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model
from app.llm.util.meta_utils import ensure_meta_aliases, get_meta
from app.llm.util.usage_utils import normalize_usage_google
from app.llm.util.citation_utils import dedupe_citations, recompute_citation_counts
from app.llm.adapters.constants import WEB_TOOL_TYPE_NONE
from app.llm.adapters.citation_authorities import get_all_authority_domains

logger = logging.getLogger(__name__)


# --------------------------- Small shared helpers ---------------------------

def _extract_system_and_user_messages(messages: List[Dict[str, str]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Combine all system messages; convert user/assistant messages into Gemini format."""
    system_content: Optional[str] = None
    conversation: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_content = content if system_content is None else f"{system_content}\n{content}"
        elif role == "user":
            conversation.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            conversation.append({"role": "model", "parts": [{"text": content}]})
    if conversation and conversation[0]["role"] == "model":
        conversation.insert(0, {"role": "user", "parts": [{"text": "Continue"}]})
    return system_content, conversation


def _extract_text_from_response(response) -> str:
    """Extract plain text from a Gemini/Vertex response object."""
    if not response or not getattr(response, "candidates", None):
        return ""
    out: List[str] = []
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                t = getattr(part, "text", None)
                if isinstance(t, str):
                    out.append(t)
    return "\n".join(out).strip()


def _extract_function_call(response) -> Tuple[Optional[str], Optional[Dict]]:
    """Return first function call (name, args) if present."""
    if not response or not getattr(response, "candidates", None):
        return None, None
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    return getattr(fc, "name", None), getattr(fc, "args", None)
    return None, None


def _multi_unquote(s: str, rounds: int = 3) -> str:
    """Collapse nested %-encoding/plus-encoding."""
    prev = s
    for _ in range(rounds):
        cur = unquote_plus(unquote(prev))
        if cur == prev:
            return cur
        prev = cur
    return prev


def _looks_like_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return bool(p.scheme and p.netloc)
    except Exception:
        return False


def _decode_vertex_redirect(u: str) -> Tuple[str, Optional[str]]:
    """
    Best-effort resolve vertexaisearch.cloud.google.com grounding redirect → final URL.
    Purely deterministic (no network). Returns (resolved_url, original_if_redirect).
    """
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        path = p.path or ""
        if "vertexaisearch.cloud.google.com" in host and "/grounding-api-redirect/" in path:
            q = parse_qs(p.query, keep_blank_values=True) if p.query else {}
            for key in ("url", "u", "target", "q"):
                vals = q.get(key)
                if vals:
                    candidate = _multi_unquote(vals[0])
                    if _looks_like_url(candidate):
                        return candidate, u
            # last path segment may embed the target
            last_seg = path.split("/")[-1]
            candidate = _multi_unquote(last_seg)
            if _looks_like_url(candidate):
                return candidate, u
            return u, u
        return u, None
    except Exception:
        return u, None


def _normalize_url(url: str) -> str:
    """Lower host, drop fragment, strip utm_* params to improve deduplication."""
    try:
        p = urlparse(url)
        p = p._replace(fragment="", netloc=(p.netloc or "").lower())
        if p.query:
            q = parse_qs(p.query, keep_blank_values=True)
            # Filter out utm_* tracking parameters
            q = {k: v for k, v in q.items() if not k.lower().startswith("utm_")}
            # Use urlencode with doseq=True to properly handle multiple values and escaping
            p = p._replace(query=urlencode(q, doseq=True) if q else "")
        return urlunparse(p)
    except Exception:
        return url


def _get_registrable_domain(url: str) -> str:
    """Basic registrable domain extraction (heuristic)."""
    try:
        p = urlparse(url)
        return (p.netloc or "").lower().replace("www.", "") or "unknown"
    except Exception:
        return "unknown"


def _extract_citations_from_grounding(response) -> Tuple[List[Dict[str, Any]], int, int, List[str]]:
    """
    Parse grounding_metadata for citations and search queries.
    Returns: (citations, anchored_count, unlinked_count, queries)
    - Only unlinked sources from grounding_chunks are treated as citations.
    - search_queries are returned separately (not counted as citations).
    """
    citations: List[Dict[str, Any]] = []
    anchored_count = 0  # Anchored evidence rarely present from Google
    unlinked_count = 0
    queries: List[str] = []

    if not response or not getattr(response, "candidates", None):
        return citations, anchored_count, unlinked_count, queries

    seen_urls = set()
    seen_domains = set()

    for cand in response.candidates or []:
        gm = getattr(cand, "grounding_metadata", None)
        if not gm:
            continue

        # Accumulate search queries (not citations)
        for q in getattr(gm, "search_queries", []) or []:
            if isinstance(q, str) and q not in queries:
                queries.append(q)

        # Convert chunks → unlinked citations
        for ch in getattr(gm, "grounding_chunks", []) or []:
            web = getattr(ch, "web", None)
            if not web:
                continue
            uri = getattr(web, "uri", None)
            title = getattr(web, "title", None)
            if not uri:
                continue

            resolved, original = _decode_vertex_redirect(uri)
            normalized = _normalize_url(resolved)
            if normalized in seen_urls:
                continue
            domain = _get_registrable_domain(resolved)
            # secondary dedup by domain (keep first per domain if we already have many)
            if domain in seen_domains and len(citations) >= 10:
                continue

            seen_urls.add(normalized)
            seen_domains.add(domain)

            rec: Dict[str, Any] = {
                "url": resolved,
                "title": (title or "")[:200],
                "source_type": "grounding_chunk",
                "domain": domain,
                "type": "unlinked",  # Google grounding chunks are unlinked evidence
                "resolved_url": resolved
            }
            if original and original != resolved:
                rec["original_url"] = uri
            citations.append(rec)
            unlinked_count += 1
            if len(citations) >= 10:
                break

    return citations, anchored_count, unlinked_count, queries


# ------------------------------- Base class --------------------------------

class GoogleBaseAdapter:
    """
    Template-method base for Google adapters.
    Subclasses provide: client init, vendor key, response_api string,
    model normalization, caps, and region.
    """

    # ---- Hooks (override in subclasses) ----
    def _vendor_key(self) -> str: ...
    def _response_api(self) -> str: ...
    def _init_client(self) -> genai.Client: ...
    def _normalize_for_validation(self, model: str) -> str: ...
    def _normalize_for_sdk(self, model: str) -> str: ...
    def _region(self) -> Optional[str]: return None
    def _grounded_cap(self) -> int: return int(os.getenv("GOOGLE_GROUNDED_MAX_TOKENS", "6000"))
    def _ungrounded_cap(self) -> int: return int(os.getenv("GOOGLE_MAX_OUTPUT_TOKENS", "8192"))
    # ---------------------------------------

    def __init__(self):
        self.client = self._init_client()
        logger.info(f"[{self._vendor_key()}_init] Base adapter initialized")

    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        start = time.perf_counter()
        request_id = f"req_{int(time.time()*1000)}"
        
        # Normalize meta and metadata to be interchangeable
        ensure_meta_aliases(request)
        meta = get_meta(request)

        # Validate & normalize model
        model_for_validation = self._normalize_for_validation(request.model)
        ok, msg = validate_model(self._vendor_key(), model_for_validation)
        if not ok:
            raise ValueError(f"Invalid {self._vendor_key()} model: {msg}")
        model_for_sdk = self._normalize_for_sdk(request.model)

        # Base metadata
        metadata: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": self._vendor_key(),
            "model": model_for_validation,
            "response_api": self._response_api(),
            "request_id": request_id,
        }
        reg = self._region()
        if reg:
            metadata["region"] = reg

        # Capabilities from router
        caps_container = getattr(request, "metadata", None)
        caps = caps_container.get("capabilities", {}) if isinstance(caps_container, dict) else {}

        # Messages → system + history
        system_instruction, conversation = _extract_system_and_user_messages(request.messages)

        # Token budgets
        max_tokens = request.max_tokens or 1024
        max_tokens = min(max_tokens, self._grounded_cap() if request.grounded else self._ungrounded_cap())

        # Safety
        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
        ]

        # Thinking config
        thinking_config = None
        thinking_requested = (meta.get("thinking_budget") is not None or 
                             meta.get("include_thoughts") is not None)
        
        if caps.get("supports_thinking_budget", False):
            thinking_budget = caps_container.get("thinking_budget_tokens") if isinstance(caps_container, dict) else None
            include_thoughts = False
            if caps.get("include_thoughts_allowed", False):
                include_thoughts = meta.get("include_thoughts", False)
            if thinking_budget is not None:
                thinking_config = ThinkingConfig(thinking_budget=thinking_budget, include_thoughts=include_thoughts)
                metadata["thinking_budget_tokens"] = thinking_budget
                metadata["include_thoughts"] = include_thoughts
                metadata["thinking_hint_applied"] = True
        elif thinking_requested:
            # Thinking was requested but not supported
            metadata["thinking_hint_dropped"] = True
            metadata["thinking_hint_drop_reason"] = "model_not_capable"
            logger.debug(f"[GOOGLE_BASE] Dropped thinking hint for non-thinking model: {request.model}")

        gen_config = GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=getattr(request, "temperature", 0.7),
            top_p=getattr(request, "top_p", 0.95),
            system_instruction=system_instruction,
            safety_settings=safety_settings,
            thinking_config=thinking_config,
        )

        # JSON schema wiring (if any)
        json_schema_requested = False
        json_schema = meta.get("json_schema")
        if json_schema and "schema" in json_schema:
            json_schema_requested = True

        # Grounding mode
        grounding_mode = None
        if request.grounded:
            grounding_mode = meta.get("grounding_mode", "AUTO")
            metadata["grounding_mode_requested"] = grounding_mode

        # Configure tools / modes
        if request.grounded and json_schema_requested:
            # Grounded + JSON: schema-as-tool + GoogleSearch (single call)
            try:
                schema_obj = Schema(**json_schema["schema"])
            except Exception:
                try:
                    schema_obj = Schema.from_json(json_schema["schema"])  # type: ignore[attr-defined]
                except Exception:
                    schema_obj = json_schema["schema"]
            emit_decl = FunctionDeclaration(name="emit_result", parameters=schema_obj)
            gen_config.tools = [Tool(google_search=GoogleSearch()), Tool(function_declarations=[emit_decl])]
            gen_config.tool_config = ToolConfig(function_calling_config=FunctionCallingConfig(mode="ANY", allowed_function_names=["emit_result"]))
            # Track web tool type consistently with OpenAI
            metadata["web_tool_type_initial"] = "google_search"
            metadata["web_tool_type_final"] = "google_search"  # Google doesn't negotiate
            metadata["web_tool_type"] = "google_search"  # Backward compatibility
            metadata["schema_tool_present"] = True
        elif request.grounded:
            gen_config.tools = [Tool(google_search=GoogleSearch())]
            # Track web tool type consistently with OpenAI
            metadata["web_tool_type_initial"] = "google_search"
            metadata["web_tool_type_final"] = "google_search"  # Google doesn't negotiate
            metadata["web_tool_type"] = "google_search"  # Backward compatibility
        elif json_schema_requested:
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema["schema"]
            metadata["json_mode_active"] = True

        # Call SDK
        # Debug logging
        logger.debug(f"[{self._vendor_key()}] Calling generate_content with:")
        logger.debug(f"  - model_for_sdk: {model_for_sdk}")
        logger.debug(f"  - grounded: {request.grounded}")
        logger.debug(f"  - tools present: {hasattr(gen_config, 'tools') and gen_config.tools is not None}")
        if hasattr(gen_config, 'tools') and gen_config.tools:
            logger.debug(f"  - tools count: {len(gen_config.tools)}")
            for i, tool in enumerate(gen_config.tools):
                if hasattr(tool, 'google_search'):
                    logger.debug(f"  - tool[{i}]: GoogleSearch")
                elif hasattr(tool, 'function_declarations'):
                    logger.debug(f"  - tool[{i}]: Functions")
        
        try:
            # Wrap SDK call with timeout to ensure it respects the timeout even if SDK hangs
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=model_for_sdk,
                    contents=conversation,
                    config=gen_config,
                ),
                timeout=timeout
            )

            # Prefer tool result if present
            func_name, func_args = _extract_function_call(response)
            if func_name == "emit_result" and isinstance(func_args, dict):
                content = json.dumps(func_args, ensure_ascii=False)
                metadata["extraction_path"] = "google_schema_tool"
                metadata["schema_tool_invoked"] = True
            else:
                content = _extract_text_from_response(response)
                metadata["schema_tool_invoked"] = False

            # Grounding extraction
            citations: List[Dict[str, Any]] = []
            grounded_effective = False
            tool_call_count = 0

            if request.grounded:
                raw_citations, raw_anchored, raw_unlinked, queries = _extract_citations_from_grounding(response)
                
                # Apply citation deduplication
                authority_domains = get_all_authority_domains()
                # Get official domains from request if available
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
                
                metadata["anchored_citations_count"] = anchored_count
                metadata["unlinked_sources_count"] = unlinked_count
                
                # Add deduplication telemetry
                if raw_citations and len(raw_citations) != len(citations):
                    metadata["citation_dedup_applied"] = True
                    metadata["citations_raw_count"] = len(raw_citations)
                    metadata["citations_deduped_count"] = len(citations)
                
                # NEW (P8a): write final deduped list into metadata for router/UI use
                metadata["citations"] = citations or []
                
                if queries:
                    metadata["search_queries"] = queries[:10]

                # Improved tool-call counting: count actual search signals
                tool_call_count = 0
                
                # Count search queries as a signal
                if queries:
                    tool_call_count += 1
                
                # Count citations (chunks) as a signal
                if anchored_count + unlinked_count > 0:
                    tool_call_count += 1
                
                # Store raw count for telemetry evolution
                tool_call_count_raw = tool_call_count
                metadata["web_search_signal_count"] = tool_call_count_raw
                
                # Cap at 1 for backward compatibility
                tool_call_count = min(tool_call_count, 1)
                
                # If we have any tool calls, grounding is effective
                if tool_call_count > 0:
                    grounded_effective = True
                    # Add extraction_path hint when we have grounding chunks
                    if anchored_count + unlinked_count > 0:
                        metadata["extraction_path"] = "google_grounding_chunks"
                
                # Also check for grounding_metadata presence (fallback)
                grounding_confidence = None
                for cand in response.candidates or []:
                    gm = getattr(cand, "grounding_metadata", None)
                    if gm:
                        # Even if no queries/chunks counted above, presence of metadata indicates attempt
                        if not grounded_effective and (getattr(gm, "grounding_chunks", []) or getattr(gm, "search_queries", [])):
                            grounded_effective = True
                            if tool_call_count == 0:
                                tool_call_count = 1
                        
                        # Capture grounding confidence if SDK exposes it (for future ranking)
                        if hasattr(gm, "grounding_confidence"):
                            grounding_confidence = getattr(gm, "grounding_confidence", None)
                        elif hasattr(gm, "confidence_score"):
                            grounding_confidence = getattr(gm, "confidence_score", None)
                        elif hasattr(gm, "retrieval_metadata"):
                            rm = getattr(gm, "retrieval_metadata", None)
                            if rm and hasattr(rm, "confidence"):
                                grounding_confidence = getattr(rm, "confidence", None)
                        break

                metadata["tool_call_count"] = tool_call_count
                metadata["grounded_evidence_present"] = grounded_effective
                
                # Add grounding confidence if available for evidence quality ranking
                if grounding_confidence is not None:
                    metadata["grounding_confidence"] = grounding_confidence

                # REQUIRED mode enforcement removed - now handled centrally in router
                # Just report the facts for router to decide
                if grounding_mode == "REQUIRED" and not grounded_effective:
                    metadata["why_not_grounded"] = "No GoogleSearch invoked despite REQUIRED mode"
            else:
                # Not grounded - set defaults
                metadata["anchored_citations_count"] = 0
                metadata["unlinked_sources_count"] = 0
                metadata["tool_call_count"] = 0
                metadata["grounded_evidence_present"] = False
                metadata["web_search_signal_count"] = 0

            # Usage & finish reason
            if hasattr(response, "usage_metadata"):
                um = response.usage_metadata
                # Collect raw usage data
                usage_raw = {
                    "thoughts_token_count": getattr(um, "thoughts_token_count", None),
                    "input_token_count": getattr(um, "prompt_token_count", 0),
                    "output_token_count": getattr(um, "candidates_token_count", 0),
                    "total_token_count": getattr(um, "total_token_count", 0),
                }
                
                # Normalize usage for consistent analytics
                normalized_usage, vendor_usage = normalize_usage_google(usage_raw)
                metadata["usage"] = normalized_usage
                metadata["vendor_usage"] = vendor_usage

            # Extract finish_reason - harmonized with OpenAI adapter
            finish_reason = None
            finish_reason_source = None
            
            if getattr(response, "candidates", None):
                for cand in response.candidates:
                    if hasattr(cand, "finish_reason") and cand.finish_reason is not None:
                        # Google SDK provides finish_reason as an enum/int
                        # Common values: STOP (1), MAX_TOKENS (2), SAFETY (3), etc.
                        raw_reason = cand.finish_reason
                        finish_reason = str(raw_reason)
                        finish_reason_source = "sdk_native"
                        
                        # Map Google enum values to readable strings
                        if hasattr(raw_reason, "name"):
                            finish_reason = raw_reason.name
                        elif isinstance(raw_reason, int):
                            # Map known integer values
                            reason_map = {
                                1: "STOP",
                                2: "MAX_TOKENS", 
                                3: "SAFETY",
                                4: "RECITATION",
                                5: "OTHER"
                            }
                            finish_reason = reason_map.get(raw_reason, f"CODE_{raw_reason}")
                        
                        metadata["finish_reason"] = finish_reason
                        metadata["finish_reason_source"] = finish_reason_source
                        
                        # Standardized version is already in the right format for Google
                        # but add it for consistency with OpenAI
                        metadata["finish_reason_standardized"] = finish_reason
                        break
            
            # If no finish_reason found, try to infer
            if finish_reason is None:
                if content:
                    metadata["finish_reason"] = "STOP"
                    metadata["finish_reason_source"] = "inferred_from_content"
                    metadata["finish_reason_standardized"] = "STOP"
                else:
                    metadata["finish_reason"] = "UNKNOWN"
                    metadata["finish_reason_source"] = "no_signal"
                    metadata["finish_reason_standardized"] = "UNKNOWN"

            latency_ms = int((time.perf_counter() - start) * 1000)
            metadata["latency_ms"] = latency_ms

            # Ensure canonical telemetry keys are set (keep legacy aliases)
            # tool_call_count, anchored_citations_count, unlinked_sources_count already set above
            # Just ensure they have defaults if missing
            metadata.setdefault("tool_call_count", metadata.get("tool_call_count", 0))
            metadata.setdefault("anchored_citations_count", metadata.get("anchored_citations_count", 0))
            metadata.setdefault("unlinked_sources_count", metadata.get("unlinked_sources_count", 0))
            
            # Set canonical web_tool_type
            if request.grounded and metadata.get("web_tool_type") in ["google_search", "GoogleSearch"]:
                metadata["web_tool_type"] = "google_search"
            elif not request.grounded or not metadata.get("tool_call_count", 0):
                metadata["web_tool_type"] = WEB_TOOL_TYPE_NONE
            # else keep whatever was already set
            
            # Debug logging for telemetry
            usage_info = metadata.get("usage", {})
            logger.debug(
                f"[ADAPTER:{self._vendor_key()}] tool_call_count={metadata.get('tool_call_count', 0)} "
                f"anchored={metadata.get('anchored_citations_count', 0)} "
                f"unlinked={metadata.get('unlinked_sources_count', 0)} "
                f"web_tool_type={metadata.get('web_tool_type', 'none')} "
                f"usage={{input:{usage_info.get('input_tokens', 0)}, "
                f"output:{usage_info.get('output_tokens', 0)}, "
                f"total:{usage_info.get('total_tokens', 0)}}}"
            )

            return LLMResponse(
                content=content,
                model_version=model_for_validation,
                model_fingerprint=None,
                grounded_effective=grounded_effective,
                usage=metadata.get("vendor_usage", {}),
                latency_ms=latency_ms,
                raw_response=None,
                success=True,
                vendor=self._vendor_key(),
                model=request.model,
                metadata=metadata,
                citations=citations,
            )

        # GroundingRequiredFailedError handling removed - router enforces REQUIRED
        except asyncio.TimeoutError:
            # Log timeout and re-raise so router CB/pacing can act
            logger.error(f"[{self._vendor_key()}] SDK call exceeded timeout={timeout}s")
            raise
        except Exception as e:
            logger.error(f"[{self._vendor_key()}] API error: {str(e)[:200]}")
            raise
