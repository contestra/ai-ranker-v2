import json
import os
import time
import logging
from typing import Any, Dict, List
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from starlette.concurrency import run_in_threadpool

from app.llm.types import LLMRequest, LLMResponse

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
    # 1) Newer clients expose a convenience .text
    t = getattr(resp, "text", None)
    if isinstance(t, str) and t.strip():
        return t.strip()

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

    def _ensure_init(self):
        if self._inited:
            return
        self._enforce_credential_policy()
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("VERTEX_LOCATION") or os.getenv("GOOGLE_CLOUD_REGION") or "europe-west4"
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT missing")
        vertexai.init(project=project, location=location)
        self._inited = True

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self._ensure_init()
        t0 = time.perf_counter()

        # Normalize model ID to short form
        raw_model = getattr(req, "model", None) or "gemini-2.5-pro"
        model_name = _normalize_model_id(raw_model)
        
        # Log for debugging
        logger.info(f"Vertex call: raw_model={raw_model}, normalized={model_name}, location={os.environ.get('VERTEX_LOCATION')}")
        
        gen_cfg = GenerationConfig(
            max_output_tokens=getattr(req, "max_tokens", None) or 64,
            temperature=getattr(req, "temperature", 0.2),
        )

        # naive message-to-text join for Phase-0
        msgs = getattr(req, "messages", None) or []
        prompt = "\n".join(m.get("content", "") if isinstance(m, dict) else str(m) for m in msgs) or "ping"

        model = GenerativeModel(model_name)
        
        # Call Vertex and handle potential SDK errors
        try:
            resp = await run_in_threadpool(model.generate_content, prompt, generation_config=gen_cfg)
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
                    grounded_effective=False
                )
            # Re-raise other errors
            raise RuntimeError(f"Vertex API error: {e}") from e

        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Use robust helpers for extraction
        usage = _extract_vertex_usage(resp)
        text = _extract_vertex_text(resp)
        finish = _extract_finish_info(resp)
        
        # Log diagnostics if text is empty
        if not text:
            logger.warning(f"Vertex empty text response - finish_info: {finish}")
            # If safety blocked, include that info
            if finish.get("blocked"):
                logger.error(f"Response was safety blocked: {finish.get('block_reason')}")

        return LLMResponse(
            vendor="vertex",
            model=model_name,
            content=text or "",
            usage=usage,
            success=True,
            latency_ms=latency_ms,
            model_version=model_name,
            model_fingerprint=None,
            grounded_effective=bool(getattr(req, "grounded", False)),
            metadata={},
        )