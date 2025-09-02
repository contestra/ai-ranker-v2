"""
Vertex AI adapter for Gemini models via Vertex AI.
Uses single-call Forced Function Calling (FFC) strategy for grounded + structured output.
No two-step fallback, no prompt mutations beyond ALS placement.

This adapter uses only the google-genai client. Legacy Vertex SDK has been removed 
per PRD-Adapter-Layer-V1 (Phase-0).
"""
import json
import os
import re
import time
import logging
import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Tuple

# REQUIRED: google-genai is the only client for Vertex/Gemini calls
import google.genai as genai
from google.genai.types import (
    HarmCategory,
    HarmBlockThreshold,
    GenerateContentConfig,
    Content,
    Part,
    Tool,
    GoogleSearch,
    FunctionDeclaration,
    Schema,
    ToolConfig,
    FunctionCallingConfig,
    SafetySetting
)

from starlette.concurrency import run_in_threadpool

# Import settings for feature flags
from app.core.config import settings

from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import validate_model
from .grounding_detection_helpers import detect_vertex_grounding
from urllib.parse import urlparse, urlunparse, parse_qs
from app.llm.errors import GroundingRequiredFailedError

logger = logging.getLogger(__name__)

# Debug flag for citation extraction
DEBUG_GROUNDING = os.getenv("DEBUG_GROUNDING", "false").lower() == "true"
# Optional: emit unlinked (non-anchored) sources when no anchored citations were found.
EMIT_UNLINKED_SOURCES = os.getenv("CITATION_EXTRACTOR_EMIT_UNLINKED", "false").lower() == "true"

# Centralized citation type definitions
ANCHORED_CITATION_TYPES = {"direct_uri", "v1_join"}
UNLINKED_CITATION_TYPES = {"unlinked", "legacy", "text_harvest", "groundingChunks"}


def _get_registrable_domain(url: str) -> str:
    """Extract registrable domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return ""
        
        # Remove port if present
        domain = domain.split(':')[0]
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # For Vertex redirects, keep the full domain
        if 'vertexaisearch.cloud.google.com' in domain:
            return domain
        
        # For most domains, return as-is (keeps subdomains)
        parts = domain.split('.')
        if len(parts) >= 3:
            # Check if it's a known second-level TLD pattern
            if parts[-2] in ['co', 'ac', 'gov', 'edu', 'org', 'net', 'com'] and parts[-1] in ['uk', 'jp', 'au', 'nz', 'za']:
                return '.'.join(parts[-3:])
        
        return domain
    except:
        return ""


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower() if parsed.netloc else ""
        
        # Filter out UTM params
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in params.items() 
                       if not k.lower().startswith('utm_')}
            query = '&'.join([f"{k}={'&'.join(v)}" if v else k 
                             for k, v in filtered.items()])
        else:
            query = ""
        
        # Rebuild URL without fragment/anchor
        return urlunparse((
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            query,
            ""  # No fragment
        ))
    except:
        return url


def _extract_text_from_response(response) -> str:
    """Extract text from Vertex response."""
    if not response or not hasattr(response, 'candidates'):
        return ""
    
    texts = []
    for candidate in response.candidates:
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            for part in candidate.content.parts:
                if hasattr(part, 'text'):
                    texts.append(part.text)
    
    return ''.join(texts)


def _extract_function_call(response) -> tuple[Optional[str], Optional[Dict]]:
    """
    Extract the final function call from response.
    Returns (function_name, arguments_dict) or (None, None) if no function call.
    """
    if not response or not hasattr(response, 'candidates'):
        return None, None
    
    for candidate in response.candidates:
        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            for part in candidate.content.parts:
                if hasattr(part, 'function_call'):
                    fc = part.function_call
                    return fc.name, dict(fc.args) if hasattr(fc, 'args') else {}
    
    return None, None


def _extract_citations(response) -> tuple[List[Dict], Dict]:
    """
    Extract citations from Vertex response.
    Returns (citations_list, telemetry_dict).
    """
    citations = []
    telemetry = {
        "citation_extractor_version": "ffc",
        "anchored_count": 0,
        "unlinked_count": 0,
        "total_raw_count": 0,
        "vertex_tool_calls": 0
    }
    
    # Track unique URLs for deduplication
    seen_urls = set()
    
    if not response:
        return citations, telemetry
    
    # Extract from grounding metadata if available
    if hasattr(response, 'candidates'):
        for candidate in response.candidates:
            # Check for grounding metadata
            if hasattr(candidate, 'grounding_metadata'):
                gm = candidate.grounding_metadata
                
                # Extract web_search_queries
                if hasattr(gm, 'web_search_queries'):
                    for query in gm.web_search_queries:
                        telemetry["vertex_tool_calls"] += 1
                
                # Extract grounding_chunks (evidence snippets)
                if hasattr(gm, 'grounding_chunks'):
                    for chunk in gm.grounding_chunks:
                        if hasattr(chunk, 'web'):
                            web = chunk.web
                            if hasattr(web, 'uri') and web.uri:
                                normalized = _normalize_url(web.uri)
                                if normalized not in seen_urls:
                                    seen_urls.add(normalized)
                                    citations.append({
                                        "url": web.uri,
                                        "title": getattr(web, 'title', ''),
                                        "snippet": '',
                                        "type": "groundingChunks",
                                        "domain": _get_registrable_domain(web.uri)
                                    })
                                    telemetry["unlinked_count"] += 1
    
    telemetry["total_raw_count"] = len(citations)
    
    # Filter based on settings
    if not EMIT_UNLINKED_SOURCES and telemetry["anchored_count"] > 0:
        citations = [c for c in citations if c["type"] in ANCHORED_CITATION_TYPES]
        telemetry["filtered_unlinked"] = telemetry["unlinked_count"]
        telemetry["unlinked_count"] = 0
    
    return citations, telemetry


def _create_output_schema(req: LLMRequest) -> FunctionDeclaration:
    """
    Create a FunctionDeclaration that represents our desired JSON output schema.
    The function's parameters will be the structured output we want.
    """
    # Default schema for general structured output
    # This should be customized based on the specific request requirements
    schema = Schema(
        type="object",
        properties={
            "response": Schema(type="string", description="The main response content"),
            "data": Schema(
                type="object",
                description="Structured data extracted from the response",
                properties={}  # Dynamic based on request
            )
        },
        required=["response"]
    )
    
    # Create the function declaration
    return FunctionDeclaration(
        name="format_response",
        description="Format the response in the required structure",
        parameters=schema
    )


class VertexAdapter:
    """
    Vertex AI adapter using google-genai client with single-call FFC strategy.
    No two-step fallback, enforces prompt purity.
    """
    
    def __init__(self):
        """Initialize Vertex adapter with hard requirement for google-genai."""
        # Get project and location from environment
        self.project = os.getenv("VERTEX_PROJECT", os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT")))
        self.location = os.getenv("VERTEX_LOCATION", "europe-west4")
        
        if not self.project:
            raise ValueError(
                "VERTEX_PROJECT, GCP_PROJECT, or GOOGLE_CLOUD_PROJECT environment variable is required. "
                "Please set one of these variables to your GCP project ID."
            )
        
        # Initialize the google-genai client for Vertex AI backend
        try:
            self.genai_client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location
            )
            logger.info(
                f"[VERTEX_STARTUP] google-genai client initialized successfully. "
                f"Project: {self.project}, Location: {self.location}"
            )
        except Exception as e:
            error_msg = (
                f"Failed to initialize google-genai client: {e}\n"
                f"This is a REQUIRED dependency. Please ensure:\n"
                f"1. google-genai is installed: pip install google-genai>=0.8.3\n"
                f"2. Authentication is configured: gcloud auth application-default login\n"
                f"3. Project {self.project} and location {self.location} are valid"
            )
            logger.error(f"[VERTEX_STARTUP] {error_msg}")
            raise RuntimeError(error_msg)
        
        # Log version info
        try:
            genai_version = genai.__version__ if hasattr(genai, '__version__') else 'unknown'
            logger.info(f"Vertex adapter initialized: google-genai={genai_version}")
        except:
            logger.info("Vertex adapter initialized with google-genai")
    
    def _build_two_messages(self, req: LLMRequest, als_block: str = None) -> tuple[str, str]:
        """
        Build exactly two messages: system and user.
        Returns (system_content, user_content).
        
        System: canonical system instruction + optional ALS block (≤350 chars)
        User: naked user prompt (byte-for-byte)
        """
        system_parts = []
        user_text = ""
        
        # Process messages - we expect system + user only
        system_found = False
        user_found = False
        
        for msg in req.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if not content:
                continue
            
            if role == "system":
                if system_found:
                    # Multiple system messages - concatenate
                    system_parts.append(content)
                else:
                    system_parts.append(content)
                    system_found = True
            elif role == "user":
                if user_found:
                    # Multiple user messages - this violates our constraint
                    raise ValueError(
                        f"Multiple user messages not allowed for Vertex. "
                        f"Expected exactly 2 messages (system + user), got multiple user messages."
                    )
                user_text = content  # Keep byte-for-byte
                user_found = True
            elif role == "assistant":
                raise ValueError(
                    f"Assistant messages not allowed for Vertex single-call. "
                    f"Expected exactly 2 messages (system + user), got assistant message."
                )
        
        # Build system content
        system_content = "\n\n".join(system_parts) if system_parts else ""
        
        # Add ALS block to system if provided
        if als_block:
            # Validate ALS length
            if len(als_block) > 350:
                raise ValueError(f"ALS block exceeds 350 chars: {len(als_block)}")
            
            if system_content:
                system_content = f"{system_content}\n\n{als_block}"
            else:
                system_content = als_block
        
        # Ensure we have a user message
        if not user_text:
            raise ValueError("No user message found. Expected exactly 2 messages (system + user).")
        
        return system_content, user_text
    
    def _create_generation_config(self, req: LLMRequest, system_content: str = None, 
                                   tools: list = None, tool_config: dict = None,
                                   safety_settings: list = None) -> GenerateContentConfig:
        """Create generation config for single-call FFC with tools."""
        config_params = {
            "temperature": getattr(req, "temperature", 0.7),
            "topP": getattr(req, "top_p", 0.95),  # Note: camelCase for google-genai
            "maxOutputTokens": getattr(req, "max_tokens", 6000),  # Note: camelCase
        }
        
        # Add system instruction if present
        if system_content:
            config_params["systemInstruction"] = system_content
        
        # Add tools if present
        if tools:
            config_params["tools"] = tools
        
        # Add tool config if present
        if tool_config:
            config_params["toolConfig"] = ToolConfig(
                function_calling_config=FunctionCallingConfig(
                    mode=tool_config.get("function_calling_config", {}).get("mode", "AUTO"),
                    allowed_function_names=tool_config.get("function_calling_config", {}).get("allowed_function_names")
                )
            )
        
        # Add safety settings if present
        if safety_settings:
            config_params["safetySettings"] = [
                SafetySetting(
                    category=cat,
                    threshold=thresh
                )
                for cat, thresh in safety_settings.items()
            ]
        
        return GenerateContentConfig(**config_params)
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """
        Main entry point for Vertex adapter.
        Single-call FFC strategy for grounded + structured output.
        """
        start_time = time.time()
        
        # Validate model
        is_valid, error_msg = validate_model("vertex", req.model)
        if not is_valid:
            raise ValueError(f"Invalid model for Vertex: {error_msg}")
        model_id = req.model
        
        # Initialize metadata
        metadata = {
            "provider": "vertex",
            "model": model_id,
            "response_api": "vertex_genai",
            "provider_api_version": "vertex:genai-v1",
            "region": self.location,
            "grounding_attempted": False,
            "grounded_effective": False,
            "tool_call_count": 0,
            "final_function_called": None,
            "schema_args_valid": False,
            "why_not_grounded": None
        }
        
        # Build exactly two messages
        try:
            system_content, user_content = self._build_two_messages(req)
        except ValueError as e:
            logger.error(f"Message shape validation failed: {e}")
            raise
        
        # Runtime assert: exactly 2 messages
        message_count = sum([
            1 if system_content else 0,
            1 if user_content else 0
        ])
        assert message_count == 2, f"Expected exactly 2 messages, got {message_count}"
        
        # Check if grounding is requested
        is_grounded = getattr(req, "grounded", False)
        is_json_mode = getattr(req, "json_mode", False)
        
        # Extract grounding mode (AUTO or REQUIRED)
        grounding_mode = getattr(req, "grounding_mode", "AUTO")
        if hasattr(req, "meta") and isinstance(req.meta, dict):
            grounding_mode = req.meta.get("grounding_mode", grounding_mode)
        metadata["grounding_mode_requested"] = grounding_mode
        
        # Prepare model name for google-genai client
        model_name = req.model
        if not model_name.startswith("publishers/google/models/"):
            model_name = f"publishers/google/models/{model_name}"
        
        # Prepare tools for FFC
        tools = []
        schema_function = None
        tool_config = None
        
        if is_grounded or is_json_mode:
            # Add GoogleSearch for grounding
            if is_grounded:
                tools.append(Tool(google_search=GoogleSearch()))
                metadata["grounding_attempted"] = True
            
            # Add SchemaFunction for structured output
            if is_json_mode:
                schema_function = _create_output_schema(req)
                tools.append(Tool(function_declarations=[schema_function]))
            
            # Map Contestra mode to genai mode
            # AUTO → "AUTO", REQUIRED → "ANY" (Gemini doesn't accept "REQUIRED")
            tool_config = {
                "function_calling_config": {
                    "mode": "ANY" if grounding_mode == "REQUIRED" else "AUTO"
                }
            }
            
            # If we have a schema function, restrict final output to it
            if schema_function:
                tool_config["function_calling_config"]["allowed_function_names"] = [
                    schema_function.name
                ]
        
        # Configure safety settings
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # Configure generation with tools embedded
        generation_config = self._create_generation_config(
            req,
            system_content=system_content,
            tools=tools if tools else None,
            tool_config=tool_config,
            safety_settings=safety_settings
        )
        
        # Single call with FFC (tools embedded in config)
        try:
            # Build contents for google-genai (just user message since system is in config)
            contents = user_content  # google-genai accepts string directly
            
            response = await asyncio.wait_for(
                run_in_threadpool(
                    self.genai_client.models.generate_content,
                    model=model_name,
                    contents=contents,
                    config=generation_config  # Contains system instruction, tools, tool_config, safety settings
                ),
                timeout=timeout
            )
                
        except asyncio.TimeoutError:
            logger.error(f"Vertex FFC call timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Vertex FFC call failed: {e}")
            raise
        
        # Post-call verification
        grounded_effective = False
        schema_valid = False
        citations = []
        
        if is_grounded:
            # Check for grounding evidence
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = grounding_count
            
            if not grounded_effective:
                metadata["why_not_grounded"] = "No GoogleSearch usage detected"
            
            # Extract citations
            citations, citation_telemetry = _extract_citations(response)
            metadata.update(citation_telemetry)
        
        if is_json_mode and schema_function:
            # Check for valid schema function call
            func_name, func_args = _extract_function_call(response)
            metadata["final_function_called"] = func_name
            
            if func_name == schema_function.name and func_args is not None:
                schema_valid = True
                metadata["schema_args_valid"] = True
                # Use function arguments as the response
                response_text = json.dumps(func_args)
            else:
                metadata["schema_args_valid"] = False
                response_text = _extract_text_from_response(response)
        else:
            response_text = _extract_text_from_response(response)
        
        # Enforce REQUIRED mode post-hoc
        if grounding_mode == "REQUIRED":
            if is_grounded and not grounded_effective:
                raise GroundingRequiredFailedError(
                    f"REQUIRED grounding mode specified but no grounding evidence found. "
                    f"Tool calls: {metadata.get('tool_call_count', 0)}"
                )
            if is_json_mode and not schema_valid:
                raise ValueError(
                    f"REQUIRED mode specified but no valid schema function call found. "
                    f"Final function: {metadata.get('final_function_called', 'None')}"
                )
        
        # Add timing
        metadata["response_time_ms"] = int((time.time() - start_time) * 1000)
        
        # Add model version if available
        if hasattr(response, 'model_version'):
            metadata["modelVersion"] = response.model_version
        
        return LLMResponse(
            text=response_text,
            metadata=metadata,
            citations=citations if citations else None
        )