"""
Vertex AI adapter for Gemini 2.5-pro ONLY.
Uses Vertex AI SDK (google-cloud-aiplatform), NOT google.genai.
Implements two-step grounded JSON policy as required.
"""
import json
import os
import time
import logging
import asyncio
import hashlib
from typing import Any, Dict, List, Optional

import vertexai
from vertexai import generative_models as gm
from starlette.concurrency import run_in_threadpool

from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import VERTEX_ALLOWED_MODELS, VERTEX_DEFAULT_MODEL, validate_model
from .grounding_detection_helpers import detect_vertex_grounding

logger = logging.getLogger(__name__)

# Force the ONLY allowed model - no rewrites or variants
GEMINI_MODEL = "publishers/google/models/gemini-2.5-pro"

class GroundingRequiredError(Exception):
    """Raised when grounding is REQUIRED but not achieved"""
    pass

def _extract_vertex_usage(resp: Any) -> Dict[str, int]:
    """Extract token usage from Vertex response."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    meta = getattr(resp, "usage_metadata", None)
    if meta:
        usage["prompt_tokens"] = getattr(meta, "prompt_token_count", 0)
        usage["completion_tokens"] = getattr(meta, "candidates_token_count", 0) 
        usage["total_tokens"] = getattr(meta, "total_token_count", 0)
    
    return usage

def _extract_text_from_candidates(resp: Any) -> str:
    """Extract text from Vertex response candidates."""
    try:
        # Try the standard path first
        if hasattr(resp, "candidates") and resp.candidates:
            candidate = resp.candidates[0]
            if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                parts = candidate.content.parts
                if parts and hasattr(parts[0], "text"):
                    return parts[0].text
        
        # Fallback to text property (may raise ValueError)
        if hasattr(resp, "text"):
            try:
                return resp.text
            except ValueError as e:
                # Handle safety filters or empty response
                logger.warning(f"Could not extract text: {e}")
                return ""
    except Exception as e:
        logger.warning(f"Error extracting text from response: {e}")
    
    return ""

def _sha256_text(text: str) -> str:
    """Generate SHA256 hash of text for attestation."""
    return hashlib.sha256(text.encode()).hexdigest()

class VertexAdapter:
    """
    Vertex AI adapter using ONLY publishers/google/models/gemini-2.5-pro.
    Implements two-step grounded JSON policy.
    """
    
    def __init__(self):
        """Initialize Vertex AI with project and location."""
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("VERTEX_PROJECT_ID"))
        self.location = os.getenv("VERTEX_LOCATION", "europe-west4")
        
        if not self.project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT or VERTEX_PROJECT_ID required - set in backend/.env"
            )
        
        # Initialize Vertex AI
        vertexai.init(project=self.project, location=self.location)
        logger.info(f"Vertex adapter initialized: project={self.project}, location={self.location}")
    
    def _build_content_with_als(self, messages: List[Dict], als_block: str = None) -> List[gm.Content]:
        """
        Build Vertex Content objects from messages.
        Combines system + ALS + user into single user message.
        MUST use vertexai.generative_models types, NOT google.genai.
        """
        contents = []
        combined_text = []
        
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            
            if not text:
                continue
            
            # Combine system and user messages into single user message
            if role in ["system", "user"]:
                # For first user message, prepend ALS if provided
                if role == "user" and als_block and not combined_text:
                    combined_text.append(als_block)
                combined_text.append(text)
            elif role == "assistant":
                # First, add any accumulated user text
                if combined_text:
                    # System → ALS → User ordering
                    user_part = gm.Part.from_text("\n\n".join(combined_text))
                    user_content = gm.Content(role="user", parts=[user_part])
                    contents.append(user_content)
                    combined_text = []
                
                # Then add assistant message as model role
                assistant_part = gm.Part.from_text(text)
                assistant_content = gm.Content(role="model", parts=[assistant_part])
                contents.append(assistant_content)
        
        # Add any remaining user text
        if combined_text:
            user_part = gm.Part.from_text("\n\n".join(combined_text))
            user_content = gm.Content(role="user", parts=[user_part])
            contents.append(user_content)
        
        return contents
    
    def _create_generation_config_step1(self, req: LLMRequest) -> gm.GenerationConfig:
        """Create generation config for Step 1 (grounded, NO JSON)."""
        config_dict = {
            "temperature": getattr(req, "temperature", 0.7),
            "top_p": getattr(req, "top_p", 0.95),
            "max_output_tokens": getattr(req, "max_tokens", 6000),
        }
        # Step 1: NO response_mime_type - we want prose with citations
        return gm.GenerationConfig(**config_dict)
    
    def _create_generation_config_step2_json(self) -> gm.GenerationConfig:
        """Create generation config for Step 2 (JSON reshape, NO tools)."""
        return gm.GenerationConfig(
            temperature=0.1,  # Low temp for consistent JSON
            max_output_tokens=6000,
            response_mime_type="application/json"  # JSON only in Step 2
        )
    
    async def _step1_grounded(self, model: gm.GenerativeModel, contents: List[gm.Content], 
                             generation_config: gm.GenerationConfig, timeout: int, 
                             mode: str = "AUTO") -> tuple[Any, bool, int]:
        """
        Step 1: Generate grounded response with GoogleSearch tool.
        Returns (response, grounded_effective, tool_call_count).
        """
        # Create GoogleSearch tool for grounding
        tools = [gm.Tool.from_google_search_retrieval()]
        
        try:
            response = await asyncio.wait_for(
                run_in_threadpool(
                    model.generate_content,
                    contents=contents,
                    generation_config=generation_config,
                    tools=tools
                ),
                timeout=timeout
            )
            
            # Check if grounding was actually used
            grounded_effective = detect_vertex_grounding(response)
            
            # Count tool calls (grounding citations)
            tool_call_count = 0
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "grounding_metadata"):
                    meta = candidate.grounding_metadata
                    if hasattr(meta, "grounding_attributions"):
                        tool_call_count = len(meta.grounding_attributions)
            
            # REQUIRED mode enforcement
            if mode == "REQUIRED" and not grounded_effective:
                raise GroundingRequiredError(
                    f"No Vertex grounding evidence found (mode=REQUIRED). "
                    f"tool_call_count={tool_call_count}"
                )
            
            return response, grounded_effective, tool_call_count
            
        except asyncio.TimeoutError:
            raise
        except GroundingRequiredError:
            raise
        except Exception as e:
            logger.error(f"Step 1 grounded generation failed: {e}")
            raise
    
    async def _step2_reshape_json(self, model: gm.GenerativeModel, step1_text: str, 
                                  original_request: str, timeout: int) -> tuple[Any, Dict]:
        """
        Step 2: Reshape to JSON without tools.
        Returns (response, attestation).
        """
        # Build reshape prompt
        reshape_prompt = f"""Based on this grounded answer, provide a structured JSON response.

Original Question: {original_request}

Grounded Answer: {step1_text}

Provide your response as valid JSON with appropriate keys for the information."""
        
        # Create content for reshape - single user message
        reshape_part = gm.Part.from_text(reshape_prompt)
        reshape_content = gm.Content(role="user", parts=[reshape_part])
        
        # JSON config for Step 2
        json_config = self._create_generation_config_step2_json()
        
        try:
            # Step 2 MUST have NO tools
            response = await asyncio.wait_for(
                run_in_threadpool(
                    model.generate_content,
                    contents=[reshape_content],
                    generation_config=json_config,
                    tools=None  # NO TOOLS in step 2 - enforced
                ),
                timeout=timeout
            )
            
            # Verify no tools were invoked (they shouldn't be since we passed None)
            tools_invoked = False
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "function_calls") and candidate.function_calls:
                    tools_invoked = True
                    logger.error("VIOLATION: Tools invoked in Step 2 (should be impossible)")
            
            # Create attestation
            attestation = {
                "step2_tools_invoked": tools_invoked,  # Must be false
                "step2_source_ref": _sha256_text(step1_text)
            }
            
            return response, attestation
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Step 2 JSON reshape failed: {e}")
            raise
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """
        Complete request using Vertex AI with Gemini 2.5-pro ONLY.
        Implements two-step grounded JSON policy when needed.
        """
        t0 = time.perf_counter()
        
        # Hard-pin the ONLY allowed model (no rewrites)
        model_id = GEMINI_MODEL
        logger.info(f"Using hard-pinned model: {model_id}")
        
        # Validate model (will fail if not in allowed set)
        is_valid, error_msg = validate_model("vertex", model_id)
        if not is_valid:
            raise ValueError(f"MODEL_NOT_ALLOWED: {error_msg}")
        
        # Initialize metadata
        metadata = {
            "model": model_id,
            "response_api": "vertex_v1",
            "proxies_enabled": False,
            "proxy_mode": "disabled",
            "vantage_policy": str(getattr(req, "vantage_policy", "NONE"))
        }
        
        # Create model with hard-pinned ID
        model = gm.GenerativeModel(model_id)
        
        # Extract ALS block if present (should be in messages already)
        als_block = None
        # ALS is handled at template_runner level, included in messages
        
        # Build contents using Vertex SDK types (system + ALS + user)
        contents = self._build_content_with_als(req.messages, als_block)
        
        # Check if JSON mode is needed
        is_json_mode = getattr(req, "json_mode", False)
        is_grounded = getattr(req, "grounded", False)
        
        # Extract grounding mode (AUTO or REQUIRED)
        grounding_mode = getattr(req, "grounding_mode", "AUTO")
        if hasattr(req, "meta") and isinstance(req.meta, dict):
            grounding_mode = req.meta.get("grounding_mode", grounding_mode)
        
        # Determine two-step requirement
        needs_two_step = is_grounded and is_json_mode
        
        if needs_two_step:
            logger.info(f"Two-step grounded JSON mode activated (mode={grounding_mode})")
            
            # Step 1: Grounded generation (NO JSON)
            generation_config = self._create_generation_config_step1(req)
            step1_resp, grounded_effective, tool_call_count = await self._step1_grounded(
                model, contents, generation_config, timeout, mode=grounding_mode
            )
            
            step1_text = _extract_text_from_candidates(step1_resp)
            
            # Step 2: Reshape to JSON (NO TOOLS)
            original_request = req.messages[-1].get("content", "") if req.messages else ""
            step2_resp, attestation = await self._step2_reshape_json(
                model, step1_text, original_request, timeout
            )
            
            # Use step2 response as final
            response = step2_resp
            text = _extract_text_from_candidates(step2_resp)
            
            # Update metadata
            metadata["two_step_used"] = True
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = tool_call_count
            metadata.update(attestation)
            
        elif is_grounded:
            # Single-step grounded (non-JSON)
            generation_config = self._create_generation_config_step1(req)
            response, grounded_effective, tool_call_count = await self._step1_grounded(
                model, contents, generation_config, timeout, mode=grounding_mode
            )
            text = _extract_text_from_candidates(response)
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = tool_call_count
            
        else:
            # Regular generation (no grounding, may have JSON)
            if is_json_mode:
                generation_config = self._create_generation_config_step2_json()
            else:
                generation_config = self._create_generation_config_step1(req)
            
            try:
                response = await asyncio.wait_for(
                    run_in_threadpool(
                        model.generate_content,
                        contents=contents,
                        generation_config=generation_config,
                        tools=None  # No tools for ungrounded
                    ),
                    timeout=timeout
                )
                text = _extract_text_from_candidates(response)
                metadata["grounded_effective"] = False
                metadata["tool_call_count"] = 0
                
            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - t0
                logger.error(f"Vertex timeout after {elapsed:.2f}s")
                raise
        
        # Extract usage
        usage = _extract_vertex_usage(response)
        
        # Calculate latency
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Add model version if available (Gemini fingerprint)
        if hasattr(response, "_raw_response"):
            raw = response._raw_response
            if hasattr(raw, "model_version"):
                metadata["modelVersion"] = raw.model_version
        elif hasattr(response, "model_version"):
            metadata["modelVersion"] = response.model_version
        
        # Log telemetry
        logger.info(
            f"Vertex completed in {latency_ms}ms, "
            f"grounded={is_grounded}, grounded_effective={metadata.get('grounded_effective', False)}, "
            f"tool_calls={metadata.get('tool_call_count', 0)}, "
            f"usage={usage}"
        )
        
        return LLMResponse(
            content=text,
            usage=usage,
            metadata=metadata
        )