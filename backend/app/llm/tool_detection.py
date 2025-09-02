"""
Tool detection utilities for OpenAI and Vertex responses.
Provides normalized detection across streaming and non-streaming paths.
"""

from typing import Any, Dict, Iterable, List, Tuple, Optional, Set

# OpenAI web search tool configuration
WEB_TOOL_PREFIXES = ("web_search",)  # treat any type that starts with these as a web search tool
WEB_TOOL_NAMES = {"web_search", "web_search_preview"}  # some accounts/models expose the preview variant

# Vertex/Gemini grounding keys
GROUNDING_KEYS: Set[str] = {
    "grounding_metadata", "groundingMetadata",
    "grounding_chunks", "groundingChunks",
    "citations", "supportingEvidence", "supporting_evidence",
    "web_search_results", "searchResults", "search_results",
    "retrievals", "retrieveToolCalls", "groundingToolInvocations",
}

URL_KEYS: Set[str] = {"uri", "url", "link", "sourceUri", "source_url"}

def _as_list(x):
    """Helper to ensure we have a list"""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

def detect_openai_websearch_usage(
    *,
    response: Dict[str, Any] | None = None,
    stream_events: Iterable[Dict[str, Any]] | None = None,
) -> Tuple[bool, int, List[str]]:
    """
    Detect web search tool usage in OpenAI responses.
    
    Works for both non-streaming Responses and streaming events.
    Counts any OpenAI web search tool call (handles both web_search and preview variant).
    
    Args:
        response: Non-streaming OpenAI response JSON
        stream_events: Streaming event iterator/list
    
    Returns:
        Tuple of (tools_used, call_count, observed_kinds):
        - tools_used: True if we observed any web search tool call
        - call_count: Number of calls observed
        - observed_kinds: List of tool kinds seen (e.g., ["web_search", "web_search_call"])
    """
    tools_used = False
    call_count = 0
    kinds: List[str] = []

    # 1) Non-streaming OpenAI Responses: look at the top-level "output" list.
    #    Evidence rule: any item whose 'type' starts with "web_search" 
    #    (e.g., "web_search_call", "web_search_results").
    if isinstance(response, dict):
        output = _as_list(response.get("output")) or _as_list(response.get("response", {}).get("output"))
        for item in output:
            t = (item.get("type") or "").lower()
            if any(t.startswith(pfx) for pfx in WEB_TOOL_PREFIXES):
                tools_used = True
                call_count += 1
                kinds.append(t)

        # Fallback: if someone routed via Chat Completions, check message.tool_calls
        for choice in _as_list(response.get("choices")):
            msg = choice.get("message") or {}
            for tc in _as_list(msg.get("tool_calls")):
                # OpenAI function-tools path
                name = (tc.get("function", {}) or {}).get("name") or tc.get("name") or ""
                if name.lower() in WEB_TOOL_NAMES:
                    tools_used = True
                    call_count += 1
                    kinds.append(f"chat.{name.lower()}")

    # 2) Streaming Responses: scan each event for web_search* markers.
    #    We accept either event["type"] containing "web_search" or 
    #    an embedded item.type starting with "web_search".
    if stream_events is not None:
        for ev in stream_events:
            etype = (ev.get("type") or "").lower()
            if "web_search" in etype:
                tools_used = True
                call_count += 1
                kinds.append(etype)

            item = ev.get("item") or {}
            t = (item.get("type") or "").lower()
            if any(t.startswith(pfx) for pfx in WEB_TOOL_PREFIXES):
                tools_used = True
                call_count += 1
                kinds.append(t)

    return tools_used, call_count, kinds


def _walk(d: Any):
    """Walk through nested dict/list structures"""
    if isinstance(d, dict):
        yield d
        for v in d.values():
            yield from _walk(v)
    elif isinstance(d, list):
        for v in d:
            yield from _walk(v)

def extract_vertex_sources(payload: Dict[str, Any]) -> List[str]:
    """
    Heuristically flatten out source URLs from common Gemini/Vertex shapes:
    - groundingMetadata.sources[].web.uri
    - citations[].uri or citations[].url
    - any nested { uri|url|link|sourceUri|source_url }
    """
    urls: List[str] = []
    for node in _walk(payload):
        # Typical: groundingMetadata: { sources: [ { web: { uri: ... } } ] }
        if "web" in node and isinstance(node["web"], dict):
            for k in URL_KEYS:
                if k in node["web"] and isinstance(node["web"][k], str):
                    urls.append(node["web"][k])

        # Typical: citations: [ { uri|url|link } ]
        for k in URL_KEYS:
            if k in node and isinstance(node[k], str):
                urls.append(node[k])

    # Deduplicate preserving order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    return uniq

def detect_vertex_grounding_usage(
    *,
    response: Dict[str, Any] | None = None,
    stream_events: Iterable[Dict[str, Any]] | None = None,
) -> Tuple[bool, int, List[str], List[str]]:
    """
    Detect grounding tool usage in Vertex/Gemini responses.
    
    Returns (tools_used, signal_count, signals, source_urls):
    - tools_used: True if any grounding/search/retrieval evidence is found
    - signal_count: number of distinct grounding signals seen
    - signals: list of key names we matched (e.g., ["groundingMetadata","citations"])
    - source_urls: flattened list of URLs discovered (deduped)
    """
    signals: List[str] = []
    tool = False

    def scan(obj: Dict[str, Any] | None):
        found = []
        if not isinstance(obj, dict):
            return found
        keys_lower = set(k for k in obj.keys())
        for k in GROUNDING_KEYS:
            if k in keys_lower or k in obj:
                found.append(k)
        return found

    # Non-streaming response scan
    if isinstance(response, dict):
        for node in _walk(response):
            hits = scan(node)
            if hits:
                tool = True
                signals.extend(hits)

    # Streaming event scan (Gemini often emits retrieval/grounding events)
    if stream_events is not None:
        for ev in stream_events:
            for node in _walk(ev):
                hits = scan(node)
                if hits:
                    tool = True
                    signals.extend(hits)

    # Normalize outputs
    source_urls = extract_vertex_sources(response or {})
    # collapse repeated signals, preserve order
    seen = set()
    uniq_signals = []
    for s in signals:
        if s not in seen:
            uniq_signals.append(s)
            seen.add(s)

    return tool, len(uniq_signals), uniq_signals, source_urls

def attest_two_step_vertex(
    *,
    step1_response: Dict[str, Any] | None = None,
    step1_events: Iterable[Dict[str, Any]] | None = None,
    step2_response: Dict[str, Any] | None = None,
    step2_events: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Enforce our two-step contract:
      - Step 1 (grounded): tools_used == True and sources >= 1
      - Step 2 (reshape to JSON): tools_used == False  (no retrieval/grounding)
    
    Returns attestation result with contract validation.
    """
    s1_used, _, s1_signals, s1_urls = detect_vertex_grounding_usage(
        response=step1_response, stream_events=step1_events
    )
    s2_used, _, s2_signals, s2_urls = detect_vertex_grounding_usage(
        response=step2_response, stream_events=step2_events
    )

    return {
        "step1_tools_used": bool(s1_used),
        "step1_sources_count": len(s1_urls),
        "step1_signals": s1_signals,
        "step2_tools_used": bool(s2_used),
        "step2_sources_count": len(s2_urls),
        "step2_signals": s2_signals,
        "contract_ok": bool(s1_used and len(s1_urls) > 0 and not s2_used),
    }


def normalize_tool_detection(
    vendor: str,
    response: Dict[str, Any] | None = None,
    stream_events: Iterable[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """
    Unified tool detection across vendors.
    
    Args:
        vendor: "openai" or "vertex"
        response: Response JSON (for non-streaming)
        stream_events: Event stream (for streaming)
    
    Returns:
        Normalized detection result:
        {
            "tools_used": bool,
            "tool_call_count": int,
            "vendor_specific": {...}
        }
    """
    if vendor == "openai":
        tools_used, call_count, kinds = detect_openai_websearch_usage(
            response=response,
            stream_events=stream_events
        )
        return {
            "tools_used": tools_used,
            "tool_call_count": call_count,
            "vendor_specific": {
                "observed_kinds": kinds
            }
        }
    
    elif vendor == "vertex":
        tools_used, signal_count, signals, source_urls = detect_vertex_grounding_usage(
            response=response,
            stream_events=stream_events
        )
        return {
            "tools_used": tools_used,
            "tool_call_count": signal_count,
            "vendor_specific": {
                "signals": signals,
                "source_urls": source_urls,
                "source_count": len(source_urls)
            }
        }
    
    else:
        return {
            "tools_used": False,
            "tool_call_count": 0,
            "vendor_specific": {}
        }