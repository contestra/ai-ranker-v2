"""
Vertex AI adapter for Gemini 2.5-pro ONLY.
Supports both vertexai SDK and google-genai for API compatibility.
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
from vertexai.generative_models import grounding
from vertexai.generative_models import Tool
from starlette.concurrency import run_in_threadpool

# Import google-genai for new API support
try:
    import google.genai as genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import VERTEX_ALLOWED_MODELS, VERTEX_DEFAULT_MODEL, validate_model
from .grounding_detection_helpers import detect_vertex_grounding

logger = logging.getLogger(__name__)

# Force the ONLY allowed model - no rewrites or variants
GEMINI_MODEL = "publishers/google/models/gemini-2.5-pro"

async def _call_vertex_model(model, *args, **kwargs):
    """
    Use async API if available, otherwise call the sync method in a thread.
    """
    gen_async = getattr(model, "generate_content_async", None)
    if gen_async and asyncio.iscoroutinefunction(gen_async):
        return await gen_async(*args, **kwargs)
    # fall back to sync generate_content in a thread
    gen_sync = getattr(model, "generate_content", None)
    if not gen_sync:
        raise RuntimeError("Vertex model has neither generate_content_async nor generate_content")
    return await run_in_threadpool(gen_sync, *args, **kwargs)

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
                if parts:
                    # Try text first
                    if hasattr(parts[0], "text") and parts[0].text:
                        return parts[0].text
                    
                    # Try JSON data parts (for JSON mode responses)
                    if hasattr(parts[0], "json_data") and parts[0].json_data is not None:
                        import json
                        return json.dumps(parts[0].json_data, ensure_ascii=False)
                    
                    # Try inline_data (base64 encoded)
                    if hasattr(parts[0], "inline_data") and hasattr(parts[0].inline_data, "data"):
                        try:
                            import base64
                            raw = base64.b64decode(parts[0].inline_data.data)
                            # Try to parse as JSON first
                            parsed = json.loads(raw)
                            return json.dumps(parsed, ensure_ascii=False)
                        except:
                            try:
                                return raw.decode("utf-8", errors="ignore")
                            except:
                                pass
        
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

def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Remove SDK objects from metadata to prevent serialization issues."""
    clean_metadata = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            clean_metadata[key] = value
        elif isinstance(value, dict):
            clean_metadata[key] = _sanitize_metadata(value)
        elif isinstance(value, list):
            clean_metadata[key] = [
                item for item in value 
                if isinstance(item, (str, int, float, bool, type(None), dict))
            ]
        # Skip SDK objects like Tool, FunctionTool, GoogleSearch, etc.
    return clean_metadata

def _make_google_search_tool():
    """Create GoogleSearch tool using google-genai SDK for API v1 compatibility."""
    try:
        # Use google-genai SDK which supports the new google_search field
        from google.genai import types
        return types.Tool(google_search=types.GoogleSearch())
    except ImportError:
        logger.warning("google-genai SDK not available, falling back to deprecated method")
        # Fall back to old SDK (will likely fail with API v1)
        try:
            return Tool.from_google_search_retrieval(
                grounding.GoogleSearchRetrieval()
            )
        except TypeError:
            return Tool.from_google_search_retrieval(
                google_search_retrieval=grounding.GoogleSearchRetrieval()
            )

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
        
        # Initialize google-genai client if available and enabled
        self.use_genai = os.getenv("VERTEX_USE_GENAI_CLIENT", "true").lower() == "true" and GENAI_AVAILABLE
        self.genai_client = None
        
        if self.use_genai:
            try:
                # Create genai client in Vertex mode
                self.genai_client = genai.Client(
                    vertexai=True,
                    project=self.project,
                    location=self.location,
                    http_options=genai_types.HttpOptions(api_version="v1")
                )
                logger.info(f"Initialized google-genai client for Vertex (project={self.project}, location={self.location})")
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai client: {e}, falling back to vertexai SDK")
                self.use_genai = False
        
        # Log SDK version for debugging
        try:
            import google.cloud.aiplatform as aiplat
            sdk_info = f"google-cloud-aiplatform={aiplat.__version__}"
            if self.use_genai:
                sdk_info += f", google-genai={genai.__version__ if hasattr(genai, '__version__') else 'unknown'}"
            logger.info(f"Vertex adapter initialized: project={self.project}, location={self.location}, {sdk_info}")
        except:
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
        # Create GoogleSearch tool for grounding (Step-1 ONLY)
        # Use version-tolerant helper
        tools = [_make_google_search_tool()]
        
        # [WIRE_DEBUG] Log what we're sending
        logger.debug(f"[WIRE_DEBUG] Vertex Step-1 grounded call:")
        logger.debug(f"  Tool class: {type(tools[0])}")
        logger.debug("  Using: Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())")
        logger.debug(f"  Mode: {mode}")
        logger.debug(f"  Generation config has JSON mime: {hasattr(generation_config, 'response_mime_type')}")
        
        try:
            response = await asyncio.wait_for(
                _call_vertex_model(
                    model,
                    contents=contents,
                    generation_config=generation_config,
                    tools=tools
                ),
                timeout=timeout
            )
            
            # Check if grounding was actually used
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            
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
            
            return response, grounded_effective, grounding_count
            
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
        
        # [WIRE_DEBUG] Log Step-2 config
        logger.debug(f"[WIRE_DEBUG] Vertex Step-2 JSON reshape:")
        logger.debug(f"  Tools: None (enforced)")
        logger.debug(f"  Response mime type: application/json")
        logger.debug(f"  Temperature: {json_config.temperature if hasattr(json_config, 'temperature') else 'default'}")
        
        try:
            # Step 2 MUST have NO tools
            response = await asyncio.wait_for(
                _call_vertex_model(
                    model,
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
    
    async def _step1_grounded_genai(self, req: LLMRequest, contents: List[gm.Content], 
                                    generation_config: gm.GenerationConfig, timeout: int, 
                                    mode: str = "AUTO") -> tuple[Any, bool, int]:
        """
        Step 1 using google-genai: Generate grounded response with GoogleSearch tool.
        Returns (response, grounded_effective, tool_call_count).
        """
        # Build messages in genai format - extract system and combine user content
        system_instruction = None
        combined_text = []
        
        for content in contents:
            text = content.parts[0].text if content.parts else ""
            if text:
                # Check if this looks like a system message (first message often contains system prompt)
                if not system_instruction and ("You are" in text or "Act as" in text):
                    # Extract potential system instruction
                    lines = text.split('\n\n')
                    if len(lines) > 1 and ("You are" in lines[0] or "Act as" in lines[0]):
                        system_instruction = lines[0]
                        # Add remaining as user content
                        if len(lines) > 1:
                            combined_text.append('\n\n'.join(lines[1:]))
                    else:
                        combined_text.append(text)
                else:
                    combined_text.append(text)
        
        # Create genai contents format with parts
        final_text = "\n\n".join(combined_text)
        contents_genai = [{"role": "user", "parts": [{"text": final_text}]}]
        
        # Create GoogleSearch tool using genai
        tools = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
        
        # Create generation config
        config_params = {
            "temperature": generation_config.temperature if hasattr(generation_config, 'temperature') else 0.7,
            "top_p": generation_config.top_p if hasattr(generation_config, 'top_p') else 0.95,
            "max_output_tokens": generation_config.max_output_tokens if hasattr(generation_config, 'max_output_tokens') else 6000,
            "tools": tools,
            "tool_config": genai_types.ToolConfig(function_calling_config={"mode": mode})
        }
        
        # Add system instruction to config if available
        if system_instruction:
            config_params["system_instruction"] = system_instruction
            
        config = genai_types.GenerateContentConfig(**config_params)
        
        # Wire debug logging
        logger.debug(f"[GENAI] Step-1 grounded call:")
        logger.debug(f"  contents[0].keys(): {list(contents_genai[0].keys())}")
        logger.debug(f"  contents[0].role: {contents_genai[0]['role']}")
        logger.debug(f"  len(contents[0].parts): {len(contents_genai[0]['parts'])}")
        logger.debug(f"  text preview: {final_text[:120]}...")
        logger.debug(f"  tools: {[type(t).__name__ for t in tools]}")
        logger.debug(f"  system_instruction length: {len(system_instruction) if system_instruction else 0}")
        
        try:
            # Use genai client to generate
            response = await asyncio.wait_for(
                self.genai_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents_genai,
                    config=config
                ),
                timeout=timeout
            )
            
            # Check if grounding was actually used - use existing detector for genai responses
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            
            logger.debug(f"[GENAI] Step-1 grounding detection: used={grounded_effective}, count={grounding_count}")
            
            # REQUIRED mode enforcement
            if mode == "REQUIRED" and not grounded_effective:
                raise GroundingRequiredError(
                    f"No grounding evidence found (mode=REQUIRED). "
                    f"tool_call_count={grounding_count}"
                )
            
            return response, grounded_effective, grounding_count
            
        except asyncio.TimeoutError:
            raise
        except GroundingRequiredError:
            raise
        except Exception as e:
            logger.error(f"[GENAI] Step 1 grounded generation failed: {e}")
            raise
    
    async def _step2_reshape_json_genai(self, req: LLMRequest, step1_text: str, 
                                        original_request: str, timeout: int) -> tuple[Any, Dict]:
        """
        Step 2 using google-genai: Reshape to JSON without tools.
        Returns (response, attestation).
        """
        # Build reshape prompt
        reshape_prompt = f"""Based on this grounded answer, provide a structured JSON response.

Original Question: {original_request}

Grounded Answer: {step1_text}

Provide your response as valid JSON with appropriate keys for the information."""
        
        contents_genai = [{"role": "user", "parts": [{"text": reshape_prompt}]}]
        
        # JSON config for Step 2 - EXPLICITLY NO TOOLS
        config = genai_types.GenerateContentConfig(
            temperature=0.1,  # Low temp for consistent JSON
            max_output_tokens=6000,
            response_mime_type="application/json",
            tools=[]  # Explicitly empty tools list
        )
        
        logger.debug(f"[GENAI] Step-2 JSON reshape:")
        logger.debug(f"  tools explicitly set to: []")
        logger.debug(f"  response_mime_type: application/json")
        
        try:
            response = await asyncio.wait_for(
                self.genai_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents_genai,
                    config=config
                ),
                timeout=timeout
            )
            
            # Verify no tools were invoked using existing detector
            tools_invoked_result, tool_count = detect_vertex_grounding(response)
            tools_invoked = tools_invoked_result  # Should be False for Step-2
            
            if tools_invoked:
                logger.error(f"[GENAI] VIOLATION: Tools invoked in Step 2 (count={tool_count})")
            else:
                logger.debug(f"[GENAI] Step-2 verification: no tools invoked (as expected)")
            
            # Create attestation
            attestation = {
                "step2_tools_invoked": tools_invoked,  # Must be false
                "step2_source_ref": _sha256_text(step1_text)
            }
            
            return response, attestation
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"[GENAI] Step 2 JSON reshape failed: {e}")
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
            if self.use_genai and self.genai_client:
                step1_resp, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                    req, contents, generation_config, timeout, mode=grounding_mode
                )
            else:
                step1_resp, grounded_effective, tool_call_count = await self._step1_grounded(
                    model, contents, generation_config, timeout, mode=grounding_mode
                )
            
            step1_text = _extract_text_from_candidates(step1_resp)
            
            # Step 2: Reshape to JSON (NO TOOLS)
            original_request = req.messages[-1].get("content", "") if req.messages else ""
            if self.use_genai and self.genai_client:
                step2_resp, attestation = await self._step2_reshape_json_genai(
                    req, step1_text, original_request, timeout
                )
            else:
                step2_resp, attestation = await self._step2_reshape_json(
                    model, step1_text, original_request, timeout
                )
            
            # Use step2 response as final
            response = step2_resp
            text = _extract_text_from_candidates(step2_resp)
            
            # Update metadata
            metadata["two_step_used"] = True
            metadata["grounded_effective"] = grounded_effective
            metadata["grounding_count"] = tool_call_count
            metadata.update(attestation)
            
        elif is_grounded:
            # Single-step grounded (non-JSON)
            generation_config = self._create_generation_config_step1(req)
            if self.use_genai and self.genai_client:
                response, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                    req, contents, generation_config, timeout, mode=grounding_mode
                )
            else:
                response, grounded_effective, tool_call_count = await self._step1_grounded(
                    model, contents, generation_config, timeout, mode=grounding_mode
                )
            text = _extract_text_from_candidates(response)
            metadata["grounded_effective"] = grounded_effective
            metadata["grounding_count"] = tool_call_count
            
        else:
            # Regular generation (no grounding, may have JSON)
            if is_json_mode:
                generation_config = self._create_generation_config_step2_json()
            else:
                generation_config = self._create_generation_config_step1(req)
            
            try:
                response = await asyncio.wait_for(
                    _call_vertex_model(
                        model,
                        contents=contents,
                        generation_config=generation_config,
                        tools=None  # No tools for ungrounded
                    ),
                    timeout=timeout
                )
                text = _extract_text_from_candidates(response)
                metadata["grounded_effective"] = False
                metadata["grounding_count"] = 0
                
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
            f"tool_calls={metadata.get('grounding_count', 0)}, "
            f"usage={usage}"
        )
        
        # Sanitize metadata to remove SDK objects
        clean_metadata = _sanitize_metadata(metadata)
        
        return LLMResponse(
            content=text,
            model_version=model_id,
            usage=usage,
            metadata=clean_metadata
        )