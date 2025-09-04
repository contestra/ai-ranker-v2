"""
OpenAI Adapter - Lean implementation using Responses API only.
Focuses on shape conversion, policy enforcement, and telemetry.
Transport/retries/backoff handled by SDK.
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.llm.errors import GroundingRequiredFailedError
from app.llm.models import OPENAI_ALLOWED_MODELS, validate_model
from app.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)
settings = get_settings()

# Environment configuration
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "5"))
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
GROUNDED_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_GROUNDED_MAX_TOKENS", "6000"))
MIN_OUTPUT_TOKENS = 16  # Responses API minimum

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
        api_key = os.getenv("OPENAI_API_KEY") or settings.openai_api_key
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
    
    def _map_model(self, model: str) -> str:
        """Map chat variants to base model for Responses API."""
        if "-chat" in model:
            return model.replace("-chat", "")
        return model
    
    def _build_payload(self, request: LLMRequest, is_grounded: bool) -> Dict:
        """Build Responses API payload."""
        # Extract messages
        system_content = ""
        user_content = ""
        for msg in request.messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            elif msg["role"] == "user":
                user_content = msg["content"]
        
        # Build typed content blocks
        input_messages = []
        if system_content:
            input_messages.append({
                "role": "system",
                "content": [{"type": "input_text", "text": system_content}]
            })
        input_messages.append({
            "role": "user",
            "content": [{"type": "input_text", "text": user_content}]
        })
        
        # Base payload
        effective_model = self._map_model(request.model)
        max_tokens = request.max_tokens or 1024
        
        if is_grounded:
            # Grounded: include tools and use higher token limit
            max_tokens = GROUNDED_MAX_OUTPUT_TOKENS
            payload = {
                "model": effective_model,
                "input": input_messages,
                "tools": [{"type": "web_search"}],  # Will negotiate if needed
                "max_output_tokens": max(max_tokens, MIN_OUTPUT_TOKENS)
            }
            
            # Tool choice for grounding mode
            grounding_mode = request.meta.get("grounding_mode", "AUTO") if request.meta else "AUTO"
            if grounding_mode == "REQUIRED":
                # Note: API may not support non-auto, will handle error
                payload["tool_choice"] = "required"
            else:
                payload["tool_choice"] = "auto"
        else:
            # Ungrounded: no tools
            payload = {
                "model": effective_model,
                "input": input_messages,
                "tools": [],
                "max_output_tokens": max(max_tokens, MIN_OUTPUT_TOKENS)
            }
            
            # Honor router capabilities for reasoning hints
            caps = request.metadata.get("capabilities", {}) if hasattr(request, 'metadata') and request.metadata else {}
            if caps.get("supports_reasoning_effort", False):
                # Router says this model supports reasoning hints
                reasoning_effort = request.meta.get("reasoning_effort", "minimal") if request.meta else "minimal"
                payload["reasoning"] = {"effort": reasoning_effort}
        
        # Add JSON schema if requested
        json_schema = request.meta.get("json_schema") if request.meta else None
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
    
    async def _call_with_tool_negotiation(self, payload: Dict, timeout: int) -> Tuple[Any, str]:
        """Call Responses API with tool type negotiation for grounded."""
        web_tool_type = "web_search"
        
        try:
            # Try with web_search first
            response = await self.client.responses.create(**payload, timeout=timeout)
            return response, web_tool_type
        except Exception as e:
            error_str = str(e)
            # If web_search not supported, try fallback
            if "unsupported" in error_str.lower() or "web_search" in error_str:
                logger.info("[OAI] web_search unsupported, trying web_search_preview")
                payload["tools"] = [{"type": "web_search_preview"}]
                web_tool_type = "web_search_preview"
                response = await self.client.responses.create(**payload, timeout=timeout)
                return response, web_tool_type
            raise
    
    def _extract_content(self, response: Any) -> Tuple[str, str]:
        """Extract text content from response.
        Returns: (content, source)
        """
        # Try message items first
        if hasattr(response, 'output') and isinstance(response.output, list):
            for item in response.output:
                if hasattr(item, 'type') and item.type == 'message':
                    if hasattr(item, 'content') and isinstance(item.content, list):
                        texts = []
                        for content_item in item.content:
                            if hasattr(content_item, 'text'):
                                texts.append(content_item.text)
                        if texts:
                            return ''.join(texts), "message"
        
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
                    if 'search' in item.type and 'call' in item.type:
                        count += 1
                        types.append(item.type)
        
        return count, types
    
    async def complete(self, request: LLMRequest, timeout: int = 60) -> LLMResponse:
        """Complete request using Responses API only."""
        start_time = time.perf_counter()
        
        # Validate model
        ok, msg = validate_model("openai", request.model)
        if not ok:
            raise ValueError(f"Invalid OpenAI model: {msg}")
        
        # Prepare metadata
        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "vendor": "openai",
            "model": request.model,
            "response_api": "responses_sdk"
        }
        
        is_grounded = request.grounded
        grounding_mode = request.meta.get("grounding_mode", "AUTO") if request.meta and is_grounded else None
        
        try:
            # Build payload
            payload = self._build_payload(request, is_grounded)
            effective_model = payload["model"]
            if effective_model != request.model:
                metadata["mapped_model"] = effective_model
            
            # Make API call
            if is_grounded:
                # Grounded: negotiate tool type
                response, web_tool_type = await self._call_with_tool_negotiation(payload, timeout)
                metadata["web_tool_type"] = web_tool_type
                
                # Extract tool evidence
                tool_count, tool_types = self._count_tool_calls(response)
                metadata["tool_call_count"] = tool_count
                metadata["tool_types"] = tool_types
                metadata["grounded_evidence_present"] = tool_count > 0
                
                # REQUIRED mode enforcement
                if grounding_mode == "REQUIRED" and tool_count == 0:
                    metadata["fail_closed_reason"] = "no_tool_calls_with_required"
                    raise GroundingRequiredFailedError(
                        f"REQUIRED grounding specified but no tool calls made"
                    )
            else:
                # Ungrounded: direct call
                response = await self.client.responses.create(**payload, timeout=timeout)
                metadata["tool_call_count"] = 0
                metadata["grounded_evidence_present"] = False
                
                # Check if we need TextEnvelope fallback
                content, source = self._extract_content(response)
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
            if is_grounded:
                content, source = self._extract_content(response)
                metadata["fallback_used"] = False
            
            metadata["text_source"] = source
            
            # Extract usage
            usage = {}
            if hasattr(response, 'usage'):
                usage_obj = response.usage
                usage = {
                    "prompt_tokens": getattr(usage_obj, 'input_tokens', 0),
                    "completion_tokens": getattr(usage_obj, 'output_tokens', 0),
                    "reasoning_tokens": getattr(usage_obj, 'reasoning_tokens', 0),
                    "total_tokens": getattr(usage_obj, 'total_tokens', 0)
                }
            
            # Calculate latency
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            metadata["latency_ms"] = latency_ms
            
            return LLMResponse(
                content=content,
                model_version=effective_model,
                model_fingerprint=None,
                grounded_effective=metadata.get("grounded_evidence_present", False),
                usage=usage,
                latency_ms=latency_ms,
                raw_response=None,
                success=True,
                vendor="openai",
                model=request.model,
                metadata=metadata,
                citations=[]
            )
            
        except GroundingRequiredFailedError:
            raise
        except Exception as e:
            # Let SDK errors bubble up naturally
            logger.error(f"[OAI] API error: {str(e)[:200]}")
            raise
    
    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model in self.allowlist