"""
_google_base_adapter.py
Shared Google adapter logic for Gemini Direct and Vertex.
- Unifies message shaping, grounding setup, JSON mode wiring, citation extraction
- Implements deterministic redirect decoding for vertexaisearch.cloud.google.com links
- Normalizes metadata keys expected by the router/telemetry
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlunparse, unquote, unquote_plus

import google.genai as genai
from google.genai.types import (
    FunctionCallingConfig, FunctionDeclaration, GenerateContentConfig,
    GoogleSearch, HarmBlockThreshold, HarmCategory, SafetySetting, Schema,
    ThinkingConfig, Tool, ToolConfig
)

from app.llm.errors import GroundingRequiredFailedError
from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model

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
    return "".join(out).strip()


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
            q = {k: v for k, v in q.items() if not k.lower().startswith("utm_")}
            p = p._replace(query="&".join(f"{k}={v}" for k, vs in q.items() for v in vs) if q else "")
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
        caps = request.metadata.get("capabilities", {}) if hasattr(request, "metadata") else {}

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
        if caps.get("supports_thinking_budget", False):
            thinking_budget = request.metadata.get("thinking_budget_tokens") if hasattr(request, "metadata") else None
            include_thoughts = False
            if caps.get("include_thoughts_allowed", False):
                if hasattr(request, "meta") and request.meta:
                    include_thoughts = request.meta.get("include_thoughts", False)
            if thinking_budget is not None:
                thinking_config = ThinkingConfig(thinking_budget=thinking_budget, include_thoughts=include_thoughts)
                metadata["thinking_budget_tokens"] = thinking_budget
                metadata["include_thoughts"] = include_thoughts

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
        json_schema = None
        if hasattr(request, "meta") and request.meta and request.meta.get("json_schema"):
            json_schema = request.meta["json_schema"]
            if "schema" in json_schema:
                json_schema_requested = True

        # Grounding mode
        grounding_mode = None
        if request.grounded:
            grounding_mode = request.meta.get("grounding_mode", "AUTO") if hasattr(request, "meta") and request.meta else "AUTO"
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
            metadata["web_tool_type"] = "google_search"
            metadata["schema_tool_present"] = True
        elif request.grounded:
            gen_config.tools = [Tool(google_search=GoogleSearch())]
            metadata["web_tool_type"] = "google_search"
        elif json_schema_requested:
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema["schema"]
            metadata["json_mode_active"] = True

        # Call SDK
        try:
            response = await self.client.aio.models.generate_content(
                model=model_for_sdk,
                contents=conversation,
                config=gen_config,
            )

            # Prefer tool result if present
            func_name, func_args = _extract_function_call(response)
            if func_name == "emit_result" and isinstance(func_args, dict):
                content = json.dumps(func_args, ensure_ascii=False)
                metadata["schema_tool_invoked"] = True
            else:
                content = _extract_text_from_response(response)
                metadata["schema_tool_invoked"] = False

            # Grounding extraction
            citations: List[Dict[str, Any]] = []
            grounded_effective = False
            tool_call_count = 0

            if request.grounded:
                citations, anchored_count, unlinked_count, queries = _extract_citations_from_grounding(response)
                metadata["anchored_citations_count"] = anchored_count
                metadata["unlinked_sources_count"] = unlinked_count
                if queries:
                    metadata["search_queries"] = queries[:10]

                # Primary signal: any grounding_metadata chunks/queries
                for cand in response.candidates or []:
                    gm = getattr(cand, "grounding_metadata", None)
                    if gm and (getattr(gm, "grounding_chunks", []) or getattr(gm, "search_queries", [])):
                        grounded_effective = True
                        tool_call_count = 1
                        break

                metadata["tool_call_count"] = tool_call_count
                metadata["grounded_evidence_present"] = grounded_effective

                if grounding_mode == "REQUIRED" and not grounded_effective:
                    metadata["why_not_grounded"] = "No GoogleSearch invoked despite REQUIRED mode"
                    raise GroundingRequiredFailedError(
                        f"REQUIRED grounding specified but no grounding evidence found. Tool calls: {tool_call_count}"
                    )
            else:
                metadata["anchored_citations_count"] = 0
                metadata["unlinked_sources_count"] = 0

            # Usage & finish reason
            usage = {}
            if hasattr(response, "usage_metadata"):
                um = response.usage_metadata
                usage = {
                    "prompt_tokens": getattr(um, "prompt_token_count", 0),
                    "completion_tokens": getattr(um, "candidates_token_count", 0),
                    "total_tokens": getattr(um, "total_token_count", 0),
                }
                metadata["usage"] = {
                    "thoughts_token_count": getattr(um, "thoughts_token_count", None),
                    "input_token_count": getattr(um, "prompt_token_count", 0),
                    "output_token_count": getattr(um, "candidates_token_count", 0),
                    "total_token_count": getattr(um, "total_token_count", 0),
                }

            if getattr(response, "candidates", None):
                for cand in response.candidates:
                    if hasattr(cand, "finish_reason"):
                        metadata["finish_reason"] = str(cand.finish_reason)
                        break

            latency_ms = int((time.perf_counter() - start) * 1000)
            metadata["latency_ms"] = latency_ms

            return LLMResponse(
                content=content,
                model_version=model_for_validation,
                model_fingerprint=None,
                grounded_effective=grounded_effective,
                usage=usage,
                latency_ms=latency_ms,
                raw_response=None,
                success=True,
                vendor=self._vendor_key(),
                model=request.model,
                metadata=metadata,
                citations=citations,
            )

        except GroundingRequiredFailedError:
            raise
        except Exception as e:
            logger.error(f"[{self._vendor_key()}] API error: {str(e)[:200]}")
            raise
