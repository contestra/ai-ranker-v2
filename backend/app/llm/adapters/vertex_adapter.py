import json
import os
import time
import logging
import asyncio
import httpx
from typing import Any, Dict, List
from contextlib import contextmanager
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Tool, grounding
from starlette.concurrency import run_in_threadpool

from app.llm.types import LLMRequest, LLMResponse
from .grounding_detection_helpers import detect_vertex_grounding

# --- Proxy/vantage helpers (Webshare) ---
def _normalize_cc(cc: str) -> str:
    if not cc:
        return "US"
    cc = cc.strip().upper()
    return "GB" if cc == "UK" else cc

def _mask_proxy(uri: str) -> str:
    """Helper to mask proxy credentials for logging"""
    try:
        from urllib.parse import urlsplit
        p = urlsplit(uri)
        user = (p.username or "")
        host = (p.hostname or "")
        port = f":{p.port}" if p.port else ""
        return f"{p.scheme}://{user}:***@{host}{port}"
    except Exception:
        return "<masked>"

def _extract_country_from_request(req) -> str:
    for attr in ("country_code", "country", "locale_country"):
        val = getattr(req, attr, None)
        if isinstance(val, str) and val.strip():
            return _normalize_cc(val)
    for field in ("locale", "routing", "meta"):
        obj = getattr(req, field, None)
        if isinstance(obj, dict):
            for k in ("country_code", "country", "cc"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return _normalize_cc(v)
    return "US"

def _should_use_proxy(req) -> bool:
    vp = getattr(req, "vantage_policy", None)
    if not vp:
        meta = getattr(req, "meta", {}) if hasattr(req, "meta") else {}
        vp = meta.get("vantage_policy")
    if not vp:
        return False
    # Handle both enum and string representations
    vp_str = str(vp).upper().replace("VANTAGEPOLICY.", "")
    return vp_str in ("PROXY_ONLY", "ALS_PLUS_PROXY")

def _proxy_connection_mode(req) -> str:
    meta = getattr(req, "meta", {}) if hasattr(req, "meta") else {}
    return str(meta.get("proxy_connection", "rotating")).lower()

def _build_webshare_proxy_uri(country_code: str, mode: str = "rotating", use_socks5: bool = True) -> str | None:
    user = os.getenv("WEBSHARE_USERNAME")
    pwd = os.getenv("WEBSHARE_PASSWORD")
    host = os.getenv("WEBSHARE_HOST", "p.webshare.io")
    
    if not (user and pwd):
        return None
    
    cc = _normalize_cc(country_code)
    # Webshare format: rotating uses -rotate suffix, backbone uses numbered suffix (-1)
    suffix = f"{user}-{cc}-rotate" if mode == "rotating" else f"{user}-{cc}-1"
    
    if use_socks5:
        # Use SOCKS5 for better stability with residential proxies
        socks_port = os.getenv("WEBSHARE_SOCKS_PORT", "1080")
        return f"socks5://{suffix}:{pwd}@{host}:{socks_port}"
    else:
        # HTTP proxy fallback
        http_port = os.getenv("WEBSHARE_PORT", "80")
        return f"http://{suffix}:{pwd}@{host}:{http_port}"
# --- end proxy helpers ---

logger = logging.getLogger(__name__)

def _extract_vertex_usage(resp: Any) -> Dict[str, int]:
    """Return prompt/completion/total token counts, defaulting to 0."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # 1) Newer Generative API: resp.usage_metadata is an object with attributes
    meta = getattr(resp, "usage_metadata", None)
    if meta:
        for src, dst in [
            ("prompt_token_count", "prompt_tokens"),
            ("candidates_token_count", "completion_tokens"),
            ("total_token_count", "total_tokens"),
        ]:
            val = getattr(meta, src, None)
            if isinstance(val, (int, float)):  # int in practice
                usage[dst] = int(val)

        # Some SDKs expose a dict-like meta too (rare, but cheap to guard)
        if hasattr(meta, "get"):  # dict-style fallback
            usage["prompt_tokens"] = int(meta.get("prompt_token_count", usage["prompt_tokens"]))
            usage["completion_tokens"] = int(meta.get("candidates_token_count", usage["completion_tokens"]))
            usage["total_tokens"] = int(meta.get("total_token_count", usage["total_tokens"]))

        # Proto fallback: convert to dict if available
        try:
            from google.protobuf.json_format import MessageToDict
            pb = getattr(meta, "_pb", None)
            if pb is not None:
                d = MessageToDict(pb, preserving_proto_field_name=True)
                usage["prompt_tokens"] = int(d.get("prompt_token_count", d.get("promptTokenCount", usage["prompt_tokens"])))
                usage["completion_tokens"] = int(d.get("candidates_token_count", d.get("candidatesTokenCount", usage["completion_tokens"])))
                usage["total_tokens"] = int(d.get("total_token_count", d.get("totalTokenCount", usage["total_tokens"])))
        except Exception:
            pass

    # 2) Very old/alternate shape (Predict responses): tokenMetadata{inputTokenCount,outputTokenCount}
    try:
        md = getattr(resp, "raw_prediction_response", None) or getattr(resp, "raw_predict_response", None) or getattr(resp, "metadata", None)
        if isinstance(md, dict):
            tm = md.get("tokenMetadata") or md.get("token_metadata") or {}
            inp = tm.get("inputTokenCount") or tm.get("input_token_count") or {}
            out = tm.get("outputTokenCount") or tm.get("output_token_count") or {}
            it = inp.get("totalTokens") or inp.get("total_tokens")
            ot = out.get("totalTokens") or out.get("total_tokens")
            if isinstance(it, (int, float)):
                usage["prompt_tokens"] = int(it)
            if isinstance(ot, (int, float)):
                usage["completion_tokens"] = int(ot)
            if usage["total_tokens"] == 0 and (usage["prompt_tokens"] or usage["completion_tokens"]):
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    except Exception:
        pass

    return usage

def _extract_vertex_text(resp: Any) -> str:
    """Return concatenated text from the top candidate, handling SDK/proto shapes."""
    # 1) Newer clients expose a convenience .text but it can throw exceptions
    try:
        t = getattr(resp, "text", None)
        if isinstance(t, str) and t.strip():
            return t.strip()
    except (ValueError, AttributeError):
        # The .text property can raise ValueError if no parts
        pass

    texts: List[str] = []
    # 2) Standard: candidates -> content.parts[*].text
    for cand in (getattr(resp, "candidates", None) or []):
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in (getattr(content, "parts", None) or []):
            pt = getattr(part, "text", None)
            if isinstance(pt, str) and pt:
                texts.append(pt)

    if texts:
        return "".join(texts).strip()

    # 3) Proto/dict fallback
    try:
        from google.protobuf.json_format import MessageToDict
        pb = getattr(resp, "_pb", None)
        if pb is not None:
            d = MessageToDict(pb, preserving_proto_field_name=True)
            for cand in d.get("candidates", []) or []:
                for part in ((cand.get("content") or {}).get("parts") or []):
                    if "text" in part and part["text"]:
                        texts.append(part["text"])
            if texts:
                return "".join(texts).strip()
            # Some variants expose a top-level "text"/"output_text"
            for k in ("text", "output_text"):
                if d.get(k):
                    return str(d[k]).strip()
    except Exception:
        pass

    return ""  # nothing found

def _extract_finish_info(resp: Any) -> Dict[str, Any]:
    """Finish reasons, safety blocks—useful for diagnosing empty text."""
    info: Dict[str, Any] = {"finish_reasons": [], "blocked": False, "block_reason": None}
    try:
        for cand in (getattr(resp, "candidates", None) or []):
            fr = getattr(cand, "finish_reason", None)
            name = getattr(fr, "name", None) or (str(fr) if fr is not None else None)
            if name:
                info["finish_reasons"].append(name)
        pf = getattr(resp, "prompt_feedback", None)
        br = getattr(pf, "block_reason", None)
        if br:
            info["blocked"] = True
            info["block_reason"] = getattr(br, "name", None) or str(br)
        # consider safety blocks in finish reasons
        if any(x and ("SAFETY" in x or "PROHIBITED" in x or "RECITATION" in x) for x in info["finish_reasons"]):
            info["blocked"] = True
    except Exception:
        pass
    return info

def _normalize_model_id(m: str) -> str:
    """Normalize model ID to short form (e.g., 'gemini-2.5-pro')"""
    if not m:
        return m
    # strip any full resource or publisher prefix
    if "/models/" in m:
        m = m.split("/models/", 1)[1]
    if m.startswith("publishers/google/models/"):
        m = m[len("publishers/google/models/"):]
    return m

class VertexAdapter:
    _inited = False
    
    def __init__(self, project: str = None, location: str = None):
        """Initialize with configurable project and location"""
        self.project = project or os.getenv("VERTEX_PROJECT", "contestra-ai")
        self.location = location or os.getenv("VERTEX_LOCATION", "global")
        logger.info("Vertex adapter initialized: project=%s location=%s", self.project, self.location)
        # Ensure metadata endpoints are never proxied (safe on any platform)
        os.environ.setdefault("NO_PROXY", "metadata.google.internal,169.254.169.254,localhost,127.0.0.1")
    
    def _is_structured_output(self, req) -> bool:
        """Check if request wants structured JSON output"""
        return bool(
            getattr(req, "schema", None) or
            getattr(req, "response_schema", None) or
            getattr(req, "response_mime_type", None) == "application/json" or
            getattr(req, "json_mode", False)
        )

    def _enforce_credential_policy(self):
        """If ENFORCE_VERTEX_WIF=true, require an external_account JSON (WIF) instead of ADC."""
        if os.getenv("ENFORCE_VERTEX_WIF", "false").lower() == "true":
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not cred_path:
                raise RuntimeError("ENFORCE_VERTEX_WIF=true but GOOGLE_APPLICATION_CREDENTIALS is not set")
            try:
                with open(cred_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception as e:
                raise RuntimeError(f"Failed to read GOOGLE_APPLICATION_CREDENTIALS: {e}")
            if cfg.get("type") != "external_account":
                raise RuntimeError("ENFORCE_VERTEX_WIF=true expects an 'external_account' credentials JSON")

    def _ensure_init(self, use_grounding: bool = False):
        if self._inited:
            return
        self._enforce_credential_policy()
        if not self.project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT missing")
        # Use configured location (can be overridden for grounding)
        location = self.location
        if use_grounding and location == "global":
            # Global is preferred for grounding, keep it
            pass
        vertexai.init(project=self.project, location=location)
        self._inited = True

    def _detect_grounding(self, response) -> tuple[bool, int]:
        """Detect whether grounding actually ran. Delegates to helper for testability."""
        return detect_vertex_grounding(response)
    
    def _build_vertex_search_tools(self):
        """
        Build grounding tools - tries GenAI SDK first, then legacy Vertex SDK
        """
        # Try new Google GenAI SDK if GOOGLE_GENAI_USE_VERTEXAI is set
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true":
            try:
                from google.genai.types import GoogleSearch, Tool as GenAITool
                logger.info("Using Google GenAI SDK for grounding")
                return [GenAITool(google_search=GoogleSearch())]
            except Exception as e:
                logger.warning(f"GenAI SDK grounding failed: {e}")
        
        # Legacy fallback for regular Vertex SDK
        try:
            logger.info("Using legacy Vertex SDK google_search_retrieval")
            return [Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())]
        except Exception as e:
            logger.warning(f"Failed to create grounding tools: {e}")
            return []
    
    async def _complete_with_genai(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete using Google GenAI SDK with proper grounding and proxy support
        
        NOTE: The GenAI SDK has known issues with residential proxies (HTTP and SOCKS5),
        often resulting in "Server disconnected" errors. This is a documented httpx/HTTP2/
        keep-alive/proxy issue. For stable proxy support with Vertex, consider:
        1. Using environment variables (HTTPS_PROXY) with the regular Vertex SDK
        2. Using OpenAI adapter for proxy-required requests
        3. Relying on ALS (Ambient Location Signals) for geographic context
        """
        from google import genai
        from google.genai.types import GenerateContentConfig, GoogleSearch, Tool as GenAITool, HttpOptions
        
        t0 = time.perf_counter()
        
        # Initialize tracking variables for logging/telemetry
        vantage_policy = str(getattr(req, 'vantage_policy', 'NONE')).upper().replace("VANTAGEPOLICY.", "")
        proxy_mode = None
        country_code = None
        masked_proxy = None
        connect_s, read_s, total_s = 30, 60, timeout  # Default timeouts
        metadata = {}
        
        # Build per-run HTTP options (add proxies if vantage_policy includes PROXY)
        http_options = HttpOptions(api_version="v1")
        proxy_requested = _should_use_proxy(req)
        
        if proxy_requested:
            try:
                country_code = _extract_country_from_request(req)
                # Determine proxy mode based on token count
                max_tokens = getattr(req, "max_tokens", 6000)
                if max_tokens and max_tokens > 2000:
                    proxy_mode = "backbone"
                else:
                    proxy_mode = "rotating"
                
                _proxy_uri = _build_webshare_proxy_uri(country_code, proxy_mode)
                if _proxy_uri:
                    # Create masked proxy URL for logging
                    from urllib.parse import urlsplit
                    p = urlsplit(_proxy_uri)
                    masked_proxy = f"{p.scheme}://{p.username}:***@{p.hostname}:{p.port or ''}"
                    
                    # Update timeout values for proxy
                    connect_s, read_s, total_s = 60, 240, 300
                    timeout = max(timeout, 300)  # Ensure at least 300s for proxy requests
                    
                    # Use client_args and async_client_args to pass proxy to underlying httpx client
                    # Note: Google GenAI SDK uses httpx internally, which requires 'proxy' not 'proxies'
                    # Force HTTP/1.1 to avoid HTTP/2 proxy disconnect issues
                    http_options = HttpOptions(
                        api_version="v1",
                        client_args={
                            "proxy": _proxy_uri,
                            "http2": False,  # force HTTP/1.1 through proxy
                            "timeout": httpx.Timeout(connect=connect_s, read=read_s, write=60.0, pool=read_s),
                            "limits": httpx.Limits(max_keepalive_connections=0, keepalive_expiry=0),  # no keep-alive reuse
                            "trust_env": True
                        },
                        async_client_args={
                            "proxy": _proxy_uri,
                            "http2": False,
                            "timeout": httpx.Timeout(connect=connect_s, read=read_s, write=60.0, pool=read_s),
                            "limits": httpx.Limits(max_keepalive_connections=0, keepalive_expiry=0),
                            "trust_env": True
                        }
                    )
                    
                    # Also set OS-level proxy for any underlying Google auth calls
                    os.environ["HTTPS_PROXY"] = _proxy_uri
                    os.environ["HTTP_PROXY"] = _proxy_uri
                    logger.info(f"GenAI proxy configured: mode={proxy_mode}, country={country_code}")
            except Exception as _e:
                logger.warning(f"GenAI proxy setup failed; proceeding without proxy: {_e}")
        
        # [LLM_ROUTE] Log before API call
        route_info = {
            "vendor": "vertex",
            "model": getattr(req, "model", "gemini-2.5-pro"),
            "vantage_policy": vantage_policy,
            "proxy_mode": proxy_mode if proxy_mode else "direct",
            "country": country_code if country_code else "none",
            "grounded": req.grounded,
            "max_tokens": getattr(req, "max_tokens", 6000),
            "timeouts_s": {"connect": connect_s, "read": read_s, "total": total_s}
        }
        logger.info(f"[LLM_ROUTE] {json.dumps(route_info)}")
        
        # Initialize GenAI client
        try:
            client = genai.Client(
                project=self.project,
                location=self.location,
                http_options=http_options
            )
        finally:
            # Clean up OS-level proxy vars after client creation
            if proxy_requested:
                os.environ.pop("HTTPS_PROXY", None)
                os.environ.pop("HTTP_PROXY", None)
        
        # Get model name
        raw_model = getattr(req, "model", None) or "gemini-2.5-pro"
        model_name = _normalize_model_id(raw_model)
        
        # Build config
        config_dict = {
            "max_output_tokens": getattr(req, "max_tokens", None) or 6000,
            "temperature": getattr(req, "temperature", 0.2),
        }
        
        # Add grounding tools if requested
        if req.grounded:
            config_dict["tools"] = [GenAITool(google_search=GoogleSearch())]
            logger.info("GenAI SDK: Enabling Google Search grounding")
        
        config = GenerateContentConfig(**config_dict)
        
        # Build messages
        msgs = getattr(req, "messages", None) or []
        prompt = "\n".join(m.get("content", "") if isinstance(m, dict) else str(m) for m in msgs) or "ping"
        
        try:
            # Call with timeout
            # When using Vertex AI, model name doesn't need 'models/' prefix
            model_path = model_name if os.getenv('GOOGLE_GENAI_USE_VERTEXAI') == 'true' else f"models/{model_name}"
            resp = await asyncio.wait_for(
                run_in_threadpool(
                    client.models.generate_content,
                    model=model_path,
                    contents=prompt,
                    config=config
                ),
                timeout=timeout
            )
            
            # Extract text and usage
            text = ""
            if hasattr(resp, 'text'):
                text = resp.text
            elif hasattr(resp, 'candidates'):
                for cand in resp.candidates:
                    if hasattr(cand, 'content') and hasattr(cand.content, 'parts'):
                        for part in cand.content.parts:
                            if hasattr(part, 'text'):
                                text += part.text
            
            # Detect grounding
            grounded_effective, tool_call_count = self._detect_grounding(resp)
            
            # Extract usage
            usage = {}
            if hasattr(resp, 'usage_metadata'):
                meta = resp.usage_metadata
                usage = {
                    "prompt_tokens": getattr(meta, "prompt_token_count", 0),
                    "completion_tokens": getattr(meta, "candidates_token_count", 0),
                    "total_tokens": getattr(meta, "total_token_count", 0)
                }
            
            latency_ms = int((time.perf_counter() - t0) * 1000)
            
            if req.grounded:
                logger.info(
                    "GenAI Grounding: requested=%s effective=%s tool_calls=%s",
                    req.grounded, grounded_effective, tool_call_count
                )
            
            # Populate metadata with proxy telemetry
            if proxy_mode:
                metadata["vantage_policy"] = vantage_policy
                metadata["proxy_mode"] = proxy_mode
                metadata["proxy_country"] = country_code if country_code else "none"
                metadata["proxy_uri_masked"] = masked_proxy if masked_proxy else "none"
                metadata["timeouts_s"] = {
                    "connect": connect_s,
                    "read": read_s,
                    "total": total_s
                }
            
            # [LLM_RESULT] Log successful response
            result_info = {
                "vendor": "vertex",
                "model": model_name,
                "vantage_policy": vantage_policy,
                "proxy_mode": proxy_mode if proxy_mode else "direct",
                "country": country_code if country_code else "none",
                "grounded": req.grounded,
                "grounded_effective": grounded_effective,
                "latency_ms": latency_ms,
                "usage": usage,
                "content_length": len(text) if text else 0
            }
            logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
            
            return LLMResponse(
                vendor="vertex",
                model=model_name,
                content=text,
                usage=usage,
                success=True,
                latency_ms=latency_ms,
                model_version=model_name,
                grounded_effective=grounded_effective,
                metadata=metadata
            )
            
        except Exception as e:
            # [LLM_TIMEOUT] Log timeout/error
            is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()
            timeout_info = {
                "vendor": "vertex",
                "model": model_name,
                "vantage_policy": vantage_policy,
                "proxy_mode": proxy_mode if proxy_mode else "direct",
                "country": country_code if country_code else "none",
                "grounded": req.grounded,
                "max_tokens": config_dict.get("max_output_tokens", 6000),
                "timeouts_s": {"connect": connect_s, "read": read_s, "total": total_s},
                "error_type": "timeout" if is_timeout else "error",
                "error_msg": str(e)[:200]
            }
            logger.error(f"[LLM_TIMEOUT] {json.dumps(timeout_info)}")
            raise RuntimeError(f"GenAI SDK error: {e}") from e
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        # Guard: structured JSON + grounding is unsupported
        if self._is_structured_output(req) and req.grounded:
            raise RuntimeError(
                "GROUNDED_JSON_UNSUPPORTED: Gemini cannot combine JSON schema with GoogleSearch grounding. "
                "Choose either grounding OR structured output, not both."
            )
        
        # Determine if we need the GenAI SDK path
        use_genai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"
        proxy_requested = _should_use_proxy(req)
        
        # Check if we should use SDK with per-run environment proxy (fallback for unstable GenAI)
        use_sdk_env_proxy = proxy_requested and (not use_genai or os.getenv("VERTEX_PROXY_VIA_SDK", "false").lower() == "true")
        
        # Route to GenAI SDK if grounding or proxy (and GenAI enabled, not using SDK fallback)
        if use_genai and (req.grounded or proxy_requested) and not use_sdk_env_proxy:
            if req.grounded:
                logger.info("Using Google GenAI SDK for grounded request")
            elif proxy_requested:
                logger.info("Using Google GenAI SDK for proxy request")
            return await self._complete_with_genai(req, timeout)
        
        # If proxy requested but GenAI disabled and not using SDK env proxy, fail fast
        if proxy_requested and not use_genai and not use_sdk_env_proxy:
            logger.error("[LLM_ROUTE] vertex fail-fast: proxy requested but GOOGLE_GENAI_USE_VERTEXAI!=true")
            raise ValueError(
                "PROXY_REQUESTED_BUT_GENAI_DISABLED: Vertex SDK path does not support per-call proxies. "
                "Set GOOGLE_GENAI_USE_VERTEXAI=true (routes via GenAI) or VERTEX_PROXY_VIA_SDK=true "
                "(uses SDK with env proxy) or remove the proxy request (vantage_policy=ALS_ONLY/NONE)."
            )
        
        self._ensure_init(use_grounding=req.grounded)
        t0 = time.perf_counter()

        # Initialize tracking variables for logging/telemetry
        vantage_policy = str(getattr(req, 'vantage_policy', 'NONE')).upper().replace("VANTAGEPOLICY.", "")
        proxy_mode = None
        country_code = None
        masked_proxy = None
        metadata = {}
        
        # Helper to manage per-run proxy environment
        @contextmanager
        def proxy_environment():
            if use_sdk_env_proxy:
                # Build proxy URI
                nonlocal proxy_mode, country_code, masked_proxy
                country_code = _extract_country_from_request(req)
                max_tokens = getattr(req, "max_tokens", 6000)
                proxy_mode = "backbone" if max_tokens and max_tokens > 2000 else "rotating"
                proxy_uri = _build_webshare_proxy_uri(country_code, proxy_mode, use_socks5=False)  # Use HTTP for env proxy
                
                if proxy_uri:
                    # Create masked version for logging
                    masked_proxy = _mask_proxy(proxy_uri)
                    
                    # Save current env
                    old_https = os.environ.get("HTTPS_PROXY")
                    old_http = os.environ.get("HTTP_PROXY")
                    old_all = os.environ.get("ALL_PROXY")
                    
                    # Set proxy env vars
                    os.environ["HTTPS_PROXY"] = proxy_uri
                    os.environ["HTTP_PROXY"] = proxy_uri
                    os.environ["ALL_PROXY"] = proxy_uri
                    logger.info(f"SDK proxy environment set: mode={proxy_mode}, country={country_code}")
                    
                    try:
                        yield
                    finally:
                        # Restore original env
                        if old_https is not None:
                            os.environ["HTTPS_PROXY"] = old_https
                        else:
                            os.environ.pop("HTTPS_PROXY", None)
                        if old_http is not None:
                            os.environ["HTTP_PROXY"] = old_http
                        else:
                            os.environ.pop("HTTP_PROXY", None)
                        if old_all is not None:
                            os.environ["ALL_PROXY"] = old_all
                        else:
                            os.environ.pop("ALL_PROXY", None)
                else:
                    yield
            else:
                yield
        
        # Normalize model ID to short form
        raw_model = getattr(req, "model", None) or "gemini-2.5-pro"
        model_name = _normalize_model_id(raw_model)
        
        # [LLM_ROUTE] Log before API call
        route_info = {
            "vendor": "vertex",
            "model": model_name,
            "vantage_policy": vantage_policy,
            "proxy_mode": proxy_mode if proxy_mode else "direct",
            "country": country_code if country_code else "none",
            "grounded": req.grounded,
            "max_tokens": getattr(req, "max_tokens", 6000),
            "timeouts_s": {"connect": 30, "read": 60, "total": timeout},
            "sdk_env_proxy": use_sdk_env_proxy
        }
        logger.info(f"[LLM_ROUTE] {json.dumps(route_info)}")
        
        # Get max_tokens from request, default to 6000 to match OpenAI
        max_tokens = getattr(req, "max_tokens", None) or 6000
        logger.info(f"Vertex using max_tokens={max_tokens}")
        
        gen_cfg = GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=getattr(req, "temperature", 0.2),
        )

        # naive message-to-text join for Phase-0
        msgs = getattr(req, "messages", None) or []
        prompt = "\n".join(m.get("content", "") if isinstance(m, dict) else str(m) for m in msgs) or "ping"

        # Enable Google Search when grounded
        tools = None
        if req.grounded:
            tools = self._build_vertex_search_tools()
            if tools:
                model = GenerativeModel(model_name, tools=tools)
            else:
                logger.warning("Grounding requested but tool creation failed, proceeding without tools")
                model = GenerativeModel(model_name)
        else:
            model = GenerativeModel(model_name)
        
        # Call Vertex with timeout and handle potential SDK errors
        try:
            # Use proxy environment if requested
            with proxy_environment():
                # Enforce per-call timeout via asyncio
                resp = await asyncio.wait_for(
                    run_in_threadpool(
                        model.generate_content, 
                        prompt, 
                        generation_config=gen_cfg
                    ),
                    timeout=timeout
                )
        except Exception as e:
            error_msg = str(e)
            # Handle the specific "no parts" error from SDK
            if "no parts" in error_msg or "no text" in error_msg:
                logger.warning(f"Vertex returned response with no text parts: {error_msg}")
                # Return empty response with metadata
                return LLMResponse(
                    vendor="vertex",
                    model=model_name,
                    content="",
                    usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    success=True,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    model_version=model_name,
                    grounded_effective=False,
                    metadata=metadata
                )
            
            # [LLM_TIMEOUT] Log timeout/error
            is_timeout = "timeout" in error_msg.lower() or "timed out" in error_msg.lower()
            timeout_info = {
                "vendor": "vertex",
                "model": model_name,
                "vantage_policy": vantage_policy,
                "proxy_mode": "direct",
                "country": "none",
                "grounded": req.grounded,
                "max_tokens": getattr(req, "max_tokens", 6000),
                "timeouts_s": {"connect": 30, "read": 60, "total": timeout},
                "error_type": "timeout" if is_timeout else "error",
                "error_msg": str(e)[:200]
            }
            logger.error(f"[LLM_TIMEOUT] {json.dumps(timeout_info)}")
            raise RuntimeError(f"Vertex API error: {e}") from e

        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Use robust helpers for extraction
        usage = _extract_vertex_usage(resp)
        text = _extract_vertex_text(resp)
        finish = _extract_finish_info(resp)
        
        # Detect grounding if requested
        grounded_effective = False
        tool_call_count = 0
        if req.grounded:
            grounded_effective, tool_call_count = self._detect_grounding(resp)
        
        # Log diagnostics if text is empty
        if not text:
            logger.warning(f"Vertex empty text response - finish_info: {finish}")
            # If safety blocked, include that info
            if finish.get("blocked"):
                logger.error(f"Response was safety blocked: {finish.get('block_reason')}")
        
        # Debug logging for grounding
        if req.grounded:
            logger.info(
                "Vertex Grounding: requested=%s effective=%s tool_calls=%s location=%s",
                req.grounded, grounded_effective, tool_call_count, self.location
            )

        # Add proxy telemetry if used
        if use_sdk_env_proxy and proxy_mode:
            metadata["vantage_policy"] = vantage_policy
            metadata["proxy_mode"] = proxy_mode
            metadata["proxy_country"] = country_code if country_code else "none"
            metadata["proxy_uri_masked"] = masked_proxy if masked_proxy else "none"
            metadata["sdk_env_proxy"] = True
        
        # [LLM_RESULT] Log successful response
        result_info = {
            "vendor": "vertex",
            "model": model_name,
            "vantage_policy": vantage_policy,
            "proxy_mode": proxy_mode if proxy_mode else "direct",
            "country": country_code if country_code else "none",
            "grounded": req.grounded,
            "grounded_effective": grounded_effective,
            "latency_ms": latency_ms,
            "usage": usage,
            "content_length": len(text) if text else 0,
            "sdk_env_proxy": use_sdk_env_proxy
        }
        logger.info(f"[LLM_RESULT] {json.dumps(result_info)}")
        
        return LLMResponse(
            vendor="vertex",
            model=model_name,
            content=text or "",
            usage=usage,
            success=True,
            latency_ms=latency_ms,
            model_version=model_name,
            model_fingerprint=None,
            grounded_effective=grounded_effective,
            metadata=metadata,
        )