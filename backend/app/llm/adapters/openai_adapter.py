"""
OpenAI Adapter (Live GPT-5 Implementation)
Uses Responses API for GPT-5
"""

import os
import time
import json
import logging
import httpx
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI

from app.llm.types import LLMRequest, LLMResponse

# Provider minimum output tokens requirement
PROVIDER_MIN_OUTPUT_TOKENS = 16

logger = logging.getLogger(__name__)


def _extract_text_from_responses_obj(r) -> str:
    """Robustly extract assistant text from Responses API objects."""
    # 0) canonical fast-path
    txt = getattr(r, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt

    collected: List[str] = []

    def _as_dict(obj):
        # Best-effort: prefer SDK's model_dump_json (typed models), then .json(), else dir-walk
        try:
            if hasattr(obj, "model_dump_json"):
                return json.loads(obj.model_dump_json())
        except Exception:
            pass
        try:
            if hasattr(obj, "json"):
                return json.loads(obj.json())
        except Exception:
            pass
        return None

    # 1) Try typed access first: r.output[*].content[*]
    out = getattr(r, "output", None)
    if isinstance(out, list) and out:
        for item in out:
            # Skip reasoning items - they don't contain user-facing text
            item_type = getattr(item, "type", None)
            if item_type == "reasoning":
                continue
                
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for blk in content:
                    # typed class: blk.text or blk.text.value
                    t = getattr(blk, "text", None)
                    if isinstance(t, str) and t.strip():
                        collected.append(t)
                        continue
                    if hasattr(t, "value") and isinstance(t.value, str) and t.value.strip():
                        collected.append(t.value)
                        continue
                    # dict-shaped block
                    if isinstance(blk, dict):
                        t = blk.get("text")
                        if isinstance(t, str) and t.strip():
                            collected.append(t)
                            continue
                        if isinstance(t, dict):
                            v = t.get("value")
                            if isinstance(v, str) and v.strip():
                                collected.append(v)
                                continue

    if collected:
        return "\n".join(collected).strip()

    # 2) As a last resort, inspect dict form
    as_dict = _as_dict(r)
    if isinstance(as_dict, dict):
        try:
            for item in as_dict.get("output", []):
                # Skip reasoning items in dict form too
                if item.get("type") == "reasoning":
                    continue
                    
                # Handle message items explicitly
                if item.get("type") == "message":
                    for blk in item.get("content", []):
                        if blk.get("type") in {"text", "output_text"}:
                            t = blk.get("text")
                            if isinstance(t, str) and t.strip():
                                collected.append(t)
                            elif isinstance(t, dict) and isinstance(t.get("value"), str) and t["value"].strip():
                                collected.append(t["value"])
                else:
                    # Generic content extraction
                    for blk in item.get("content", []):
                        t = blk.get("text")
                        if isinstance(t, str) and t.strip():
                            collected.append(t)
                        elif isinstance(t, dict) and isinstance(t.get("value"), str) and t["value"].strip():
                            collected.append(t["value"])
            if collected:
                return "\n".join(collected).strip()
        except Exception:
            pass

    # 3) Still nothing — log a compact dump
    safe_dump = None
    try:
        safe_dump = as_dict or _as_dict(r)
    except Exception:
        safe_dump = None
    logger.info("Responses extract: no text found. dump=%s",
                (json.dumps(safe_dump)[:2000] if isinstance(safe_dump, dict) else "unavailable"))
    return ""


def _split_messages(messages: List[Dict[str, Any]]) -> tuple[Optional[str], str]:
    """Split messages into instructions (system) and input (user) for Responses API"""
    sys_parts, user_parts = [], []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            sys_parts.append(content)
        elif role == "assistant":
            # Assistant messages become part of conversation context
            user_parts.append(f"Assistant: {content}")
        else:  # user
            user_parts.append(content)
    
    instructions = "\n\n".join(p for p in sys_parts if p).strip() or None
    user_input = "\n".join(p for p in user_parts if p).strip() or ""
    
    # Ensure there's always user input to trigger text generation
    if not user_input:
        user_input = "Please answer now in plain text."
    
    return instructions, user_input


def _is_empty(s: str | None) -> bool:
    """Check if string is empty or whitespace only"""
    return not s or not s.strip()


def _nudge_plain_text(user_input: str) -> str:
    """Add explicit instruction for plain text output"""
    return (user_input + "\n\n"
            "Answer in plain, concise text. Do not include tool plans or hidden reasoning.").strip()


def _had_reasoning_only(response) -> bool:
    """Check if response contains only reasoning items with no text"""
    output = getattr(response, "output", None)
    if not output:
        return False
    
    # Check if ALL items are reasoning type
    for item in output:
        item_type = getattr(item, "type", None)
        if not item_type:
            # Check dict form
            if isinstance(item, dict):
                item_type = item.get("type")
        if item_type != "reasoning":
            return False  # Found non-reasoning item
    
    # All items were reasoning type
    return True


class OpenAIAdapter:
    """Live OpenAI adapter using Responses API for GPT-5"""
    
    def __init__(self):
        # API Key required
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY required - set in backend/.env")
        
        # Configure timeouts
        connect_s = float(os.getenv("OPENAI_CONNECT_TIMEOUT_MS", "2000")) / 1000.0
        read_s = float(os.getenv("OPENAI_READ_TIMEOUT_MS", "60000")) / 1000.0
        
        # Create client with timeouts
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(
                connect=connect_s,
                read=read_s,
                write=read_s,
                pool=read_s
            )
        )
        
        # Parse and clean allowlist
        raw_allow = os.getenv("OPENAI_MODELS_ALLOWLIST", "gpt-5").split(",")
        self.allowlist = {m.strip() for m in raw_allow if m.strip()}
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Execute OpenAI API call with GPT-5 specific requirements.
        Uses Responses API with adaptive error handling and retry logic.
        """
        # Enforce model allowlist
        if request.model not in self.allowlist:
            raise ValueError(
                f"MODEL_NOT_ALLOWED: {request.model} not in {sorted(self.allowlist)}"
            )
        
        # Split messages properly for Responses API
        instructions, user_input = _split_messages(request.messages)
        
        # Token configuration with environment defaults
        DEFAULT_MAX = int(os.getenv("OPENAI_DEFAULT_MAX_OUTPUT_TOKENS", "512"))
        CAP = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS_CAP", "4000"))
        
        requested_tokens = request.max_tokens or DEFAULT_MAX
        effective_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, requested_tokens))
        
        # Build base parameters
        params: Dict[str, Any] = {
            "model": request.model,
            "input": user_input,
            "max_output_tokens": effective_tokens,
        }
        
        # Add instructions if present
        if instructions:
            params["instructions"] = instructions
        
        # GPT-5 specific parameters
        if request.model == "gpt-5":
            params["temperature"] = 1.0  # MANDATORY for GPT-5
        else:
            if request.temperature is not None:
                params["temperature"] = request.temperature
        
        # JSON mode
        if request.json_mode:
            params["response_format"] = {"type": "json_object"}
        else:
            params["text"] = {"verbosity": "medium"}
        
        # Track timing and retries
        t0 = time.perf_counter()
        retry_mode = "none"
        attempts = 0
        reasoning_only = False
        metadata = {
            "max_output_tokens_requested": requested_tokens,
            "max_output_tokens_effective": effective_tokens,
            "temperature_used": params.get("temperature"),
        }
        
        # Internal call function with error handling
        async def _call(call_params):
            try:
                return await self.client.responses.create(
                    **{k: v for k, v in call_params.items() if v is not None}
                )
            except Exception as e:
                error_msg = str(e)
                # Handle unknown parameter errors by removing problematic params
                if "unexpected keyword argument" in error_msg or "Unknown parameter" in error_msg:
                    # Extract the problematic parameter name
                    import re
                    match = re.search(r"'(\w+)'", error_msg)
                    if match:
                        bad_param = match.group(1)
                        logger.info(f"Removing unsupported parameter: {bad_param}")
                        call_params = dict(call_params)
                        call_params.pop(bad_param, None)
                        # Retry without the bad parameter
                        return await self.client.responses.create(
                            **{k: v for k, v in call_params.items() if v is not None}
                        )
                raise RuntimeError(f"OPENAI_CALL_FAILED: {e}") from e
        
        # First attempt
        response = await _call(params)
        content = _extract_text_from_responses_obj(response)
        
        # Check if initial response had reasoning only
        if _had_reasoning_only(response):
            reasoning_only = True
        
        # First retry - only if NOT in JSON mode and content is empty
        if _is_empty(content) and "response_format" not in params:
            attempts = 1
            metadata["retry_reason"] = "reasoning_only" if reasoning_only else "no_text"
            metadata["reasoning_only_detected"] = reasoning_only
            
            # Bump token budget and add text nudge
            bumped_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, effective_tokens * 2))
            retry_params = dict(params)
            retry_params["max_output_tokens"] = bumped_tokens
            retry_params["input"] = _nudge_plain_text(user_input)
            retry_params["text"] = {"verbosity": "low"}
            
            try:
                r2 = await _call(retry_params)
                content2 = _extract_text_from_responses_obj(r2)
                if not _is_empty(content2):
                    content = content2
                    response = r2
                    effective_tokens = bumped_tokens
                    retry_mode = "responses_retry1"
                    reasoning_only = _had_reasoning_only(r2)
                    metadata["max_output_tokens_effective"] = bumped_tokens
            except Exception as e:
                logger.warning(f"First retry failed: {e}")
        
        # Second retry - only if still empty AND not in JSON mode
        if _is_empty(content) and "response_format" not in params:
            attempts = 2
            
            # Triple token budget and add stronger text instruction
            final_tokens = max(PROVIDER_MIN_OUTPUT_TOKENS, min(CAP, effective_tokens * 3))
            retry2_params = dict(params)
            retry2_params["max_output_tokens"] = final_tokens
            retry2_params["input"] = _nudge_plain_text(user_input) + " Respond with plain text only."
            retry2_params["text"] = {"verbosity": "low"}
            
            try:
                r3 = await _call(retry2_params)
                content3 = _extract_text_from_responses_obj(r3)
                if not _is_empty(content3):
                    content = content3
                    response = r3
                    effective_tokens = final_tokens
                    retry_mode = "responses_retry2"
                    reasoning_only = _had_reasoning_only(r3)
                    metadata["max_output_tokens_effective"] = final_tokens
            except Exception as e:
                logger.warning(f"Second retry failed: {e}")
        
        # Calculate final latency
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Extract usage
        usage = {}
        if hasattr(response, 'usage'):
            resp_usage = response.usage
            if resp_usage:
                usage = {
                    "prompt_tokens": getattr(resp_usage, 'input_tokens', 0) or getattr(resp_usage, 'prompt_tokens', 0),
                    "completion_tokens": getattr(resp_usage, 'output_tokens', 0) or getattr(resp_usage, 'completion_tokens', 0),
                    "total_tokens": getattr(resp_usage, 'total_tokens', 0),
                }
        
        # Get system fingerprint
        sys_fp = getattr(response, "system_fingerprint", None)
        
        # Add complete tracking to metadata
        metadata["retry_mode"] = retry_mode
        metadata["attempts"] = attempts
        metadata["reasoning_only_detected"] = reasoning_only
        metadata["had_text_after_retry"] = not _is_empty(content)
        metadata["response_format"] = params.get("response_format")
        
        # Build response
        return LLMResponse(
            content=content,
            model_version=getattr(response, 'model', request.model),
            model_fingerprint=sys_fp,
            grounded_effective=request.grounded if request.grounded else False,
            usage=usage,
            latency_ms=latency_ms,
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else None,
            success=True,
            vendor="openai",
            model=request.model,
            metadata=metadata
        )
    
    def supports_model(self, model: str) -> bool:
        """Check if model is in allowlist"""
        return model in self.allowlist