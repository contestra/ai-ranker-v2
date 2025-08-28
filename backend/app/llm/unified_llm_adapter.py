"""
Unified LLM adapter router for AI Ranker V2
Routes requests to appropriate provider and handles ALS, telemetry
"""

import hashlib
import json
import logging
import os
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.types import LLMRequest, LLMResponse, ALSContext
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter
from app.models.models import LLMTelemetry
from app.services.als.als_builder import ALSBuilder
from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)

# Timeout configuration
UNGROUNDED_TIMEOUT = int(os.getenv("LLM_TIMEOUT_UN", "60"))
GROUNDED_TIMEOUT = int(os.getenv("LLM_TIMEOUT_GR", "120"))

# Global proxy kill-switch (default: disabled)
DISABLE_PROXIES = os.getenv("DISABLE_PROXIES", "true").lower() in ("true", "1", "yes")


class UnifiedLLMAdapter:
    """
    Main router for LLM requests
    Responsibilities:
    - Route by vendor
    - Apply ALS (once, before routing)
    - Common timeout handling
    - Normalize responses
    - Emit telemetry
    """
    
    def __init__(self):
        self.openai_adapter = OpenAIAdapter()
        self.vertex_adapter = VertexAdapter()
        self.als_builder = ALSBuilder()
    
    async def complete(
        self,
        request: LLMRequest,
        session: Optional[AsyncSession] = None
    ) -> LLMResponse:
        """
        Main entry point for LLM completions
        
        Args:
            request: Unified LLM request
            session: Optional database session for telemetry
            
        Returns:
            Unified LLM response
        """
        
        # Step 1: ALS is now handled at template_runner level with proper message ordering
        # DO NOT apply ALS here - it's already in the messages with correct system prompt
        
        # Step 2: Infer vendor if missing
        if not request.vendor:
            request.vendor = self.get_vendor_for_model(request.model)
            if not request.vendor:
                raise ValueError(f"Cannot infer vendor for model: {request.model}")
        
        # Step 3: Validate vendor
        if request.vendor not in ("openai", "vertex"):
            raise ValueError(f"Unsupported vendor: {request.vendor}")
        
        # Step 3.5: Normalize vantage_policy - remove all proxy modes
        original_policy = str(getattr(request, 'vantage_policy', 'ALS_ONLY'))
        normalized_policy = original_policy
        proxies_normalized = False
        
        if DISABLE_PROXIES and original_policy in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
            # Normalize proxy policies to ALS_ONLY
            normalized_policy = "ALS_ONLY"
            proxies_normalized = True
            logger.info(f"[PROXY_DISABLED] Normalizing vantage_policy: {original_policy} -> {normalized_policy}")
            request.vantage_policy = normalized_policy
        
        # Set flag to prevent any proxy usage downstream
        request.proxies_disabled = DISABLE_PROXIES
        
        # Step 4: Calculate timeout based on grounding
        timeout = GROUNDED_TIMEOUT if request.grounded else UNGROUNDED_TIMEOUT
        
        logger.info(f"Routing LLM request: vendor={request.vendor}, model={request.model}, "
                   f"grounded={request.grounded}, timeout={timeout}s, "
                   f"template_id={request.template_id}, run_id={request.run_id}")
        
        try:
            if request.vendor == "openai":
                response = await self.openai_adapter.complete(request, timeout=timeout)
            else:  # vertex - NO SILENT FALLBACKS, auth errors should surface
                response = await self.vertex_adapter.complete(request, timeout=timeout)
                
        except Exception as e:
            # Convert adapter exceptions to LLM response format
            error_msg = str(e)
            logger.error(f"Adapter failed for vendor={request.vendor}: {error_msg}")
            
            # Return error response instead of letting exception bubble up
            from app.llm.types import LLMResponse
            return LLMResponse(
                content="",
                model_version=request.model,
                model_fingerprint=None,
                grounded_effective=False,
                usage={},
                latency_ms=0,
                raw_response=None,
                success=False,
                vendor=request.vendor,
                model=request.model,
                error_type=type(e).__name__,
                error_message=error_msg
            )
        
        # Step 3: Emit telemetry if session provided
        if session:
            await self._emit_telemetry(request, response, session)
        
        return response
    
    def _apply_als(self, request: LLMRequest) -> LLMRequest:
        """
        Apply Ambient Location Signals to the request
        Modifies the messages to include ALS context
        """
        als_context = request.als_context
        
        if not als_context or not isinstance(als_context, dict):
            return request
        
        # Build ALS block
        country_code = als_context.get('country_code', 'US')
        als_block = self.als_builder.build_als_block(
            country=country_code,
            max_chars=350,
            include_weather=True,
            randomize=True
        )
        
        # Prepend ALS to the first user message
        modified_messages = request.messages.copy()
        
        for i, msg in enumerate(modified_messages):
            if msg.get('role') == 'user':
                original_content = msg['content']
                msg['content'] = f"{als_block}\n\n{original_content}"
                break
        
        # Update request with modified messages
        request.messages = modified_messages
        return request
    
    async def _emit_telemetry(
        self,
        request: LLMRequest,
        response: LLMResponse,
        session: AsyncSession
    ):
        """Emit telemetry row to database"""
        try:
            # Log grounding telemetry
            if request.grounded:
                logger.info(
                    "Grounding telemetry: requested=%s effective=%s vendor=%s model=%s",
                    request.grounded, response.grounded_effective, 
                    request.vendor, request.model
                )
            
            telemetry = LLMTelemetry(
                vendor=request.vendor,
                model=request.model,
                grounded=request.grounded,
                grounded_effective=response.grounded_effective,
                json_mode=request.json_mode,
                latency_ms=response.latency_ms,
                prompt_tokens=response.usage.get('prompt_tokens', 0),
                completion_tokens=response.usage.get('completion_tokens', 0),
                total_tokens=response.usage.get('total_tokens', 0),
                success=response.success,
                error_type=response.error_type,
                template_id=request.template_id,
                run_id=request.run_id
            )
            
            session.add(telemetry)
            await session.flush()
            
        except Exception as e:
            # Log but don't fail the request
            print(f"Failed to emit telemetry: {e}")
    
    def validate_model(self, vendor: str, model: str) -> bool:
        """
        Validate that a model is supported by a vendor
        
        Args:
            vendor: Provider name (openai, vertex)
            model: Model identifier
            
        Returns:
            True if model is supported
        """
        if vendor == "openai":
            # ONLY GPT-5 is supported for OpenAI
            return model == "gpt-5"
        elif vendor == "vertex":
            return model.startswith("gemini-")
        return False
    
    def get_vendor_for_model(self, model: str) -> Optional[str]:
        """
        Infer vendor from model name
        
        Args:
            model: Model identifier
            
        Returns:
            Vendor name or None if unknown
        """
        # GPT-5 is our ONLY OpenAI model
        if model == "gpt-5":
            return "openai"
        elif model.startswith("gemini-"):
            return "vertex"
        else:
            return None  # Unsupported model