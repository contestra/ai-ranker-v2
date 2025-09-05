"""
Lean Vertex adapter - shape conversion, policy enforcement, and telemetry only.
Transport/retries/backoff handled by SDK and router.
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlunparse

import google.genai as genai
from google.genai.types import (
    FunctionCallingConfig, FunctionDeclaration, GenerateContentConfig,
    GoogleSearch, HarmBlockThreshold, HarmCategory, SafetySetting, Schema,
    ThinkingConfig, Tool, ToolConfig
)

from app.core.config import settings
from app.llm.errors import GroundingRequiredFailedError
from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model

logger = logging.getLogger(__name__)

# Environment configuration
VERTEX_PROJECT = os.getenv("VERTEX_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or settings.google_cloud_project
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION") or settings.vertex_location or "europe-west4"
VERTEX_MAX_OUTPUT_TOKENS = int(os.getenv("VERTEX_MAX_OUTPUT_TOKENS", "8192"))
VERTEX_GROUNDED_MAX_TOKENS = int(os.getenv("VERTEX_GROUNDED_MAX_TOKENS", "6000"))


def _get_registrable_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        p = urlparse(url)
        domain = p.netloc.lower().replace("www.", "")
        if 'vertexaisearch.cloud.google.com' in domain:
            return domain
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
            p = p._replace(query="&".join(f"{k}={v}" for k, vs in q.items() for v in vs) if q else "")
        return urlunparse(p._replace(netloc=p.netloc.lower()))
    except Exception:
        return url


def _extract_redirect_url(google_url: str) -> str:
    """Extract real URL from Google grounding redirect."""
    if "vertexaisearch.cloud.google.com/grounding-api-redirect/" in google_url:
        return google_url
    return google_url


def _extract_text_from_response(response) -> str:
    """Extract plain text from Vertex response."""
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
    """Extract function call from response (first encountered)."""
    if not response or not getattr(response, "candidates", None):
        return None, None
    for cand in response.candidates or []:
        content = getattr(cand, "content", None)
        if content and getattr(content, "parts", None):
            for part in content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    func_name = getattr(fc, "name", None)
                    args = getattr(fc, "args", None)
                    return func_name, args
    return None, None


def _extract_citations_from_grounding(response) -> Tuple[List[Dict[str, Any]], int, int]:
    """Extract citations from grounding metadata.
    Returns: (citations list, anchored_count, unlinked_count)
    """
    citations: List[Dict[str, Any]] = []
    anchored_count = 0
    unlinked_count = 0

    if not response or not getattr(response, "candidates", None):
        return citations, anchored_count, unlinked_count

    for cand in response.candidates or []:
        grounding_metadata = getattr(cand, "grounding_metadata", None)
        if not grounding_metadata:
            continue

        # Grounding chunks (unlinked)
        grounding_chunks = getattr(grounding_metadata, "grounding_chunks", []) or []
        for chunk in grounding_chunks:
            web = getattr(chunk, "web", None)
            if web:
                uri = getattr(web, "uri", None)
                title = getattr(web, "title", None)
                if uri:
                    final_url = _extract_redirect_url(uri)
                    citations.append({
                        "url": final_url,
                        "title": title or "",
                        "source_type": "grounding_chunk",
                        "domain": _get_registrable_domain(final_url)
                    })
                    unlinked_count += 1

        # Search queries (do not count as sources)
        search_queries = getattr(grounding_metadata, "search_queries", []) or []
        for query in search_queries:
            citations.append({
                "query": query,
                "source_type": "search_query"
            })

    return citations, anchored_count, unlinked_count


def _build_conversation_history(messages: List[Dict[str, str]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Build conversation history; extract system to system_instruction.
    Returns: (system_instruction, conversation_messages)
    """
    system_content = None
    conversation_messages = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            system_content = content if system_content is None else f"{system_content}\n{content}"
        elif role == "user":
            conversation_messages.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            conversation_messages.append({"role": "model", "parts": [{"text": content}]})

    if not system_content:
        system_content = "You are a helpful assistant."

    if not conversation_messages:
        raise ValueError("No user messages found")
    if conversation_messages[0]["role"] == "model":
        conversation_messages.insert(0, {"role": "user", "parts": [{"text": "Continue"}]})

    return system_content, conversation_messages


class VertexAdapter:
    """Lean Vertex adapter using SDK-managed transport."""

    def __init__(self):
        if not VERTEX_PROJECT:
            raise ValueError("VERTEX_PROJECT, GCP_PROJECT, or GOOGLE_CLOUD_PROJECT not set")
        self.client = genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)
        logger.info(f"[vertex_init] Lean adapter initialized - project: {VERTEX_PROJECT}, location: {VERTEX_LOCATION}")

    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        start_time = time.perf_counter()
        request_id = f"req_{int(time.time()*1000)}"

        # Validate model
        model_id = request.model
        if not model_id.startswith("publishers/google/models/"):
            model_id = f"publishers/google/models/{model_id}"
        is_valid, error_msg = validate_model("vertex", model_id)
        if not is_valid:
            raise ValueError(f"Invalid Vertex model: {error_msg}")

        # Base metadata
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": "vertex",
            "model": model_id,
            "response_api": "vertex_genai",
            "request_id": request_id,
            "region": VERTEX_LOCATION
        }

        # Router-provided capabilities
        caps = request.metadata.get("capabilities", {}) if hasattr(request, 'metadata') else {}

        # Messages → system + history (ALS is injected by router, not here)
        system_content, conversation_messages = _build_conversation_history(request.messages)

        # Token budgets
        max_tokens = request.max_tokens or 1024
        if request.grounded:
            max_tokens = min(max_tokens, VERTEX_GROUNDED_MAX_TOKENS)
        else:
            max_tokens = min(max_tokens, VERTEX_MAX_OUTPUT_TOKENS)

        # Safety settings
        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH),
        ]

        # Thinking config (snake_case)
        thinking_config = None
        if caps.get("supports_thinking_budget", False):
            thinking_budget = request.metadata.get("thinking_budget_tokens") if hasattr(request, 'metadata') else None
            include_thoughts = False
            if caps.get("include_thoughts_allowed", False):
                if hasattr(request, 'meta') and request.meta:
                    include_thoughts = request.meta.get("include_thoughts", False)
            if thinking_budget is not None:
                thinking_config = ThinkingConfig(thinking_budget=thinking_budget, include_thoughts=include_thoughts)
                metadata["thinking_budget_tokens"] = thinking_budget
                metadata["include_thoughts"] = include_thoughts

        gen_config = GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=getattr(request, 'temperature', 0.7),
            top_p=getattr(request, 'top_p', 0.95),
            system_instruction=system_content,
            safety_settings=safety_settings,
            thinking_config=thinking_config
        )

        # JSON schema (if any)
        json_schema_requested = False
        json_schema = None
        if hasattr(request, 'meta') and request.meta and request.meta.get('json_schema'):
            json_schema = request.meta['json_schema']
            if 'schema' in json_schema:
                json_schema_requested = True

        # Grounding mode
        grounding_mode = None
        if request.grounded:
            grounding_mode = request.meta.get("grounding_mode", "AUTO") if hasattr(request, 'meta') and request.meta else "AUTO"
            metadata["grounding_mode_requested"] = grounding_mode

        # Configure tools/modes
        if request.grounded and json_schema_requested:
            # Single-call FFC: GoogleSearch (auto) + schema-as-tool → force only emit_result
            metadata["web_tool_type"] = "google_search"
            metadata["grounding_mode_enforced"] = "POST_CALL"  # REQUIRED enforced after call
            # Build Schema object safely
            schema_obj = None
            try:
                # Prefer explicit Schema construction; fallback to from_json if available
                schema_obj = Schema(**json_schema['schema'])
            except Exception:
                try:
                    schema_obj = Schema.from_json(json_schema['schema'])  # type: ignore[attr-defined]
                except Exception:
                    # Last resort: pass raw dict (SDK often accepts it)
                    schema_obj = json_schema['schema']
            emit_decl = FunctionDeclaration(name="emit_result", parameters=schema_obj)

            gen_config.tools = [
                Tool(google_search=GoogleSearch()),
                Tool(function_declarations=[emit_decl])
            ]
            gen_config.tool_config = ToolConfig(
                function_calling_config=FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=["emit_result"]
                )
            )
        elif request.grounded and not json_schema_requested:
            # Grounded, no JSON: attach GoogleSearch (auto)
            gen_config.tools = [Tool(google_search=GoogleSearch())]
            gen_config.tool_config = ToolConfig(function_calling_config=FunctionCallingConfig(mode="AUTO"))
            metadata["web_tool_type"] = "google_search"
            metadata["grounding_mode_enforced"] = "POST_CALL"
        elif (not request.grounded) and json_schema_requested:
            # Ungrounded + JSON → JSON mode (no tools)
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema['schema']
            metadata["json_mode_active"] = True
        # else: ungrounded text → no tools, normal text

        # Call SDK
        try:
            response = await self.client.aio.models.generate_content(
                model=model_id,
                contents=conversation_messages,
                config=gen_config
            )

            # Prefer function call result for FFC
            func_name, func_args = _extract_function_call(response)
            content: str = ""
            if func_name == "emit_result" and isinstance(func_args, dict):
                # Emit strict JSON from function args
                try:
                    content = json.dumps(func_args, ensure_ascii=False)
                    metadata["function_emit_used"] = True
                except Exception:
                    # Fallback to plain text extraction if JSON dump fails
                    content = _extract_text_from_response(response)
                    metadata["function_emit_used"] = False
            else:
                content = _extract_text_from_response(response)
                metadata["function_emit_used"] = False

            # Grounding evidence + citations
            citations: List[Dict[str, Any]] = []
            tool_call_count = 0
            grounded_effective = False

            if request.grounded:
                citations, anchored_count, unlinked_count = _extract_citations_from_grounding(response)
                metadata["anchored_citations_count"] = anchored_count
                metadata["unlinked_sources_count"] = unlinked_count

                # Primary evidence signal for Vertex: grounding_metadata
                for cand in response.candidates or []:
                    grounding_meta = getattr(cand, "grounding_metadata", None)
                    if grounding_meta:
                        chunks = getattr(grounding_meta, "grounding_chunks", []) or []
                        queries = getattr(grounding_meta, "search_queries", []) or []
                        if chunks or queries:
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

            # Usage (includes thoughts if provided by SDK)
            usage = {}
            if hasattr(response, 'usage_metadata'):
                usage_meta = response.usage_metadata
                usage = {
                    "prompt_tokens": getattr(usage_meta, 'prompt_token_count', 0),
                    "completion_tokens": getattr(usage_meta, 'candidates_token_count', 0),
                    "total_tokens": getattr(usage_meta, 'total_token_count', 0)
                }
                metadata["usage"] = {
                    "thoughts_token_count": getattr(usage_meta, 'thoughts_token_count', None),
                    "input_token_count": getattr(usage_meta, 'prompt_token_count', 0),
                    "output_token_count": getattr(usage_meta, 'candidates_token_count', 0),
                    "total_token_count": getattr(usage_meta, 'total_token_count', 0)
                }

            # Finish reason
            if response and hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'finish_reason'):
                        metadata["finish_reason"] = str(candidate.finish_reason)
                        break

            # Latency
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            metadata["latency_ms"] = latency_ms

            return LLMResponse(
                content=content,
                model_version=model_id,
                model_fingerprint=None,
                grounded_effective=grounded_effective,
                usage=usage,
                latency_ms=latency_ms,
                raw_response=None,
                success=True,
                vendor="vertex",
                model=request.model,
                metadata=metadata,
                citations=citations
            )

        except GroundingRequiredFailedError:
            raise
        except Exception as e:
            logger.error(f"[vertex] API error: {str(e)[:200]}")
            raise

    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return "gemini" in model.lower()
