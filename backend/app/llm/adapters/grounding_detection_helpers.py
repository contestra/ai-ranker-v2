"""
Grounding detection helpers for OpenAI and Vertex adapters.
Pure functions for testable, reusable detection logic.
"""
from __future__ import annotations
from typing import Any, Tuple, Iterable

# -----------------------------
# OpenAI (Responses API) helper
# -----------------------------
SEARCH_TYPES = {
    "web_search_call", "web_search_result", "web_search",
    "web_search_preview", "web_search_preview_call", "web_search_preview_result",
    "tool_use", "tool_result", "function_call", "function_result",
}

CITATION_ANNOTATION_TYPES = {
    "url_citation", "web_result", "citation", "url", "reference"
}

def _iter_output(resp: Any) -> Iterable[Any]:
    """Safely iterate over response output items."""
    if hasattr(resp, "output") and resp.output is not None:
        return resp.output
    if hasattr(resp, "model_dump"):
        try:
            d = resp.model_dump()
            return d.get("output", []) or []
        except Exception:
            pass
    if isinstance(resp, dict):
        return resp.get("output", []) or []
    return []

def detect_openai_grounding(resp: Any) -> Tuple[bool, int]:
    """
    Return (grounded_effective, tool_call_count) from an OpenAI Responses-style object/dict.
    
    Detects:
    - output[*].type in {web_search_call, web_search_result, tool_use, etc}
    - URL citation annotations in message content blocks
    """
    grounded, tool_calls = False, 0
    output_types_seen = set()
    annotation_types_seen = set()
    
    for item in _iter_output(resp):
        itype = item.get("type", "") if isinstance(item, dict) else getattr(item, "type", "") or ""
        if itype:
            output_types_seen.add(itype)
        
        # Enhanced tool/search call detection
        if (itype in SEARCH_TYPES or 
            ("search" in itype.lower()) or 
            ("tool" in itype.lower()) or
            ("function" in itype.lower()) or
            ("call" in itype.lower() and "web" in itype.lower())):
            tool_calls += 1
            grounded = True

        # Enhanced URL-citation annotations detection
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        if isinstance(content, list):
            for blk in content:
                anns = blk.get("annotations") if isinstance(blk, dict) else getattr(blk, "annotations", None)
                if isinstance(anns, list):
                    for a in anns:
                        atype = (a.get("type") or "").lower() if isinstance(a, dict) else str(a).lower()
                        if atype:
                            annotation_types_seen.add(atype)
                        
                        if (atype in CITATION_ANNOTATION_TYPES or
                            "url" in atype or "citation" in atype or "reference" in atype):
                            tool_calls += 1
                            grounded = True
    
    # Wire-debug logging for detection improvement
    if output_types_seen or annotation_types_seen:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"[OPENAI_GROUNDING] Output types: {output_types_seen}, Annotation types: {annotation_types_seen}, Grounded: {grounded}, Count: {tool_calls}")
    
    return grounded, tool_calls

# -----------------------------
# Vertex / Gemini helper
# -----------------------------
def detect_vertex_grounding(resp: Any) -> Tuple[bool, int]:
    """
    Return (grounded_effective, tool_call_count) across both snake_case and camelCase:
      - (web_search_queries | webSearchQueries)
      - (grounding_chunks | groundingChunks)
      - (search_entry_point | searchEntryPoint)
    """
    grounded, count = False, 0

    # Typed attribute path
    for cand in getattr(resp, "candidates", []) or []:
        gm = getattr(cand, "grounding_metadata", None) or getattr(cand, "groundingMetadata", None)
        if not gm:
            continue
        web_q = getattr(gm, "web_search_queries", None) or getattr(gm, "webSearchQueries", None) or []
        chunks = getattr(gm, "grounding_chunks", None) or getattr(gm, "groundingChunks", None) or []
        entry  = getattr(gm, "search_entry_point", None) or getattr(gm, "searchEntryPoint", None)
        # Additional genai-specific fields
        citations = getattr(gm, "citations", None) or getattr(gm, "grounding_attributions", None) or []
        contexts = getattr(gm, "retrieved_contexts", None) or getattr(gm, "retrievedContexts", None) or []
        evidence = getattr(gm, "supporting_evidence", None) or getattr(gm, "supportingEvidence", None) or []
        if web_q or chunks or entry or citations or contexts or evidence:
            grounded = True
            count = len(web_q) if isinstance(web_q, list) and web_q else 1
            return grounded, count  # short-circuit on first positive

    # Dict path
    if isinstance(resp, dict):
        for cand in resp.get("candidates", []) or []:
            gm = cand.get("grounding_metadata") or cand.get("groundingMetadata") or {}
            web_q = gm.get("web_search_queries") or gm.get("webSearchQueries") or []
            chunks = gm.get("grounding_chunks") or gm.get("groundingChunks") or []
            entry  = gm.get("search_entry_point") or gm.get("searchEntryPoint")
            # Additional genai-specific fields
            citations = gm.get("citations") or gm.get("grounding_attributions") or []
            contexts = gm.get("retrieved_contexts") or gm.get("retrievedContexts") or []
            evidence = gm.get("supporting_evidence") or gm.get("supportingEvidence") or []
            if web_q or chunks or entry or citations or contexts or evidence:
                grounded = True
                count = len(web_q) if isinstance(web_q, list) and web_q else 1
                return grounded, count

    # Proto/JSON fallback for Vertex
    if hasattr(resp, "_pb"):
        try:
            from google.protobuf.json_format import MessageToDict
            d = MessageToDict(resp._pb, preserving_proto_field_name=True)
            for cand in d.get("candidates", []) or []:
                gm = cand.get("grounding_metadata") or cand.get("groundingMetadata") or {}
                if gm.get("web_search_queries") or gm.get("webSearchQueries") \
                   or gm.get("grounding_chunks") or gm.get("groundingChunks") \
                   or gm.get("search_entry_point") or gm.get("searchEntryPoint") \
                   or gm.get("citations") or gm.get("grounding_attributions") \
                   or gm.get("retrieved_contexts") or gm.get("retrievedContexts") \
                   or gm.get("supporting_evidence") or gm.get("supportingEvidence"):
                    grounded = True
                    count = len(gm.get("web_search_queries") or gm.get("webSearchQueries") or []) or 1
                    return grounded, count
        except Exception:
            pass

    return grounded, count