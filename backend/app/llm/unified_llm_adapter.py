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
from app.llm.models import validate_model, normalize_model
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
        
        # Step 1: Apply ALS if context is provided and not already in messages
        # Check if ALS is already applied using stable flag (not fragile string check)
        als_already_applied = getattr(request, 'als_applied', False)
        
        # Apply ALS if we have context and it's not already applied
        if hasattr(request, 'als_context') and request.als_context and not als_already_applied:
            request = self._apply_als(request)
        
        # Step 2: Infer vendor if missing
        if not request.vendor:
            request.vendor = self.get_vendor_for_model(request.model)
            if not request.vendor:
                raise ValueError(f"Cannot infer vendor for model: {request.model}")
        
        # Step 2.5: Strict model validation with guardrails
        # Normalize model
        request.model = normalize_model(request.vendor, request.model)
        
        # Hard guardrails for allowed models
        if request.vendor == "vertex":
            # Check against configurable allowlist
            allowed_models = os.getenv("ALLOWED_VERTEX_MODELS", 
                "publishers/google/models/gemini-2.5-pro,publishers/google/models/gemini-2.0-flash").split(",")
            if request.model not in allowed_models:
                raise ValueError(
                    f"Model not allowed: {request.model}\n"
                    f"Allowed models: {allowed_models}\n"
                    f"To use this model:\n"
                    f"1. Add to ALLOWED_VERTEX_MODELS env var\n"
                    f"2. Redeploy service\n"
                    f"Note: We don't silently rewrite models (Adapter PRD)"
                )
        elif request.vendor == "openai":
            # Check against configurable allowlist
            allowed_models = os.getenv("ALLOWED_OPENAI_MODELS", 
                "gpt-5,gpt-5-chat-latest").split(",")
            if request.model not in allowed_models:
                raise ValueError(
                    f"Model not allowed: {request.model}\n"
                    f"Allowed models: {allowed_models}\n"
                    f"To use this model:\n"
                    f"1. Add to ALLOWED_OPENAI_MODELS env var\n"
                    f"2. Redeploy service\n"
                    f"Note: We don't silently rewrite models (Adapter PRD)"
                )
        
        # Double-check with centralized validation
        is_valid, error_msg = validate_model(request.vendor, request.model)
        if not is_valid:
            raise ValueError(f"MODEL_NOT_ALLOWED: {error_msg}")
        
        # Step 3: Validate vendor
        if request.vendor not in ("openai", "vertex"):
            raise ValueError(f"Unsupported vendor: {request.vendor}")
        
        # Step 3.5: Normalize vantage_policy - remove all proxy modes
        original_policy = str(getattr(request, 'vantage_policy', 'ALS_ONLY'))
        normalized_policy = original_policy
        proxies_normalized = False
        
        # Store original for telemetry tracking
        request.original_vantage_policy = original_policy
        
        if DISABLE_PROXIES and original_policy in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
            # Normalize proxy policies to ALS_ONLY
            normalized_policy = "ALS_ONLY"
            proxies_normalized = True
            request.proxy_normalization_applied = True
            logger.info(f"[PROXY_DISABLED] Normalizing vantage_policy: {original_policy} -> {normalized_policy}")
            request.vantage_policy = normalized_policy
        else:
            request.proxy_normalization_applied = False
        
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
        Enforces ≤350 NFC chars, persists complete provenance
        
        ALS Deterministic Builder Contract:
        1. Canonicalize locale (ISO uppercase, region handling)
        2. Select variant deterministically with HMAC(seed_key_id, template_id)
        3. Build ALS text without any runtime date/time
        4. Normalize to NFC, enforce ≤350 chars (fail-closed, no truncation)
        5. Compute SHA256 over NFC text
        6. Persist all provenance fields
        7. Insert in order: system → ALS → user
        """
        als_context = request.als_context
        
        if not als_context or not isinstance(als_context, dict):
            return request
        
        # Step 1: Canonicalize locale (ISO uppercase)
        country_code = als_context.get('country_code', 'US').upper()
        locale = als_context.get('locale', f'en-{country_code}')
        
        # Step 2: Deterministic variant selection using HMAC
        import hmac
        # Use a stable seed key and template identifier
        seed_key_id = 'v1_2025'  # This should come from config in production
        template_id = f'als_template_{country_code}'  # Stable template identifier
        
        # Generate deterministic seed using HMAC
        seed_data = f"{seed_key_id}:{template_id}:{country_code}".encode('utf-8')
        hmac_hash = hmac.new(b'als_secret_key', seed_data, hashlib.sha256).hexdigest()
        
        # Convert hash to deterministic index
        # Get number of available variants from ALS builder
        tpl = self.als_builder.templates.TEMPLATES.get(country_code)
        if tpl and hasattr(tpl, 'phrases') and tpl.phrases:
            num_variants = len(tpl.phrases)
            # Use first 8 bytes of hash for variant selection
            variant_idx = int(hmac_hash[:8], 16) % num_variants
        else:
            variant_idx = 0
            num_variants = 1
        
        # Step 3: Build ALS block deterministically (no randomization, no timestamps)
        # Use a fixed date to ensure determinism (regulatory neutral date)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        # Fixed date for deterministic ALS generation (regulatory neutral)
        # This is a placeholder date that doesn't imply current time
        fixed_date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo('UTC'))
        
        # Build with specific variant using deterministic parameters
        from app.services.als.als_templates import ALSTemplates
        
        # For countries with multiple timezones, use deterministic selection
        # based on the HMAC hash to pick a consistent timezone
        tz_override = None
        tpl = self.als_builder.templates.TEMPLATES.get(country_code)
        if tpl and hasattr(tpl, 'timezone_samples') and tpl.timezone_samples:
            # Use HMAC to deterministically select timezone
            tz_idx = int(hmac_hash[8:12], 16) % len(tpl.timezone_samples)
            tz_override = tpl.timezone_samples[tz_idx]
        
        als_block = ALSTemplates.render_block(
            code=country_code,
            phrase_idx=variant_idx,
            include_weather=True,
            now=fixed_date,  # Pass fixed date for determinism
            tz_override=tz_override  # Pass deterministic timezone for multi-tz countries
        )
        
        # Step 4: NFC normalization and length check
        import unicodedata
        als_block_nfc = unicodedata.normalize('NFC', als_block)
        
        # Normalize whitespace: convert CRLF to LF, trim trailing whitespace
        als_block_nfc = als_block_nfc.replace('\r\n', '\n').rstrip()
        
        # Enforce 350 char limit - fail closed, no truncation
        if len(als_block_nfc) > 350:
            raise ValueError(
                f"ALS_BLOCK_TOO_LONG: {len(als_block_nfc)} chars exceeds 350 limit (NFC normalized)\n"
                f"No automatic truncation (immutability requirement)\n"
                f"Fix: Reduce ALS template configuration"
            )
        
        # Step 5: Compute SHA256 over final NFC text
        als_block_sha256 = hashlib.sha256(als_block_nfc.encode('utf-8')).hexdigest()
        
        # Use the deterministic variant info
        variant_id = f'variant_{variant_idx}'
        
        # Deep copy messages to avoid reference issues
        import copy
        modified_messages = copy.deepcopy(request.messages)
        
        # Prepend ALS to the first user message (maintains system → ALS → user order)
        for i, msg in enumerate(modified_messages):
            if msg.get('role') == 'user':
                original_content = msg['content']
                modified_messages[i] = {
                    'role': 'user',
                    'content': f"{als_block_nfc}\n\n{original_content}"
                }
                break
        
        # Update request with modified messages
        request.messages = modified_messages
        
        # Set flag to prevent reapplication
        request.als_applied = True
        
        # Step 6: Store complete ALS provenance metadata
        if not hasattr(request, 'metadata'):
            request.metadata = {}
        
        request.metadata.update({
            # Don't store raw ALS text to prevent location signal leaks
            # 'als_block_text': als_block_nfc,  # REMOVED for security
            'als_block_sha256': als_block_sha256,  # SHA256 of NFC text (sufficient for immutability)
            'als_variant_id': variant_id,  # Which variant was selected
            'seed_key_id': seed_key_id,  # Seed key used for HMAC
            'als_country': country_code,  # Canonicalized country
            'als_locale': locale,  # Full locale string
            'als_nfc_length': len(als_block_nfc),  # Length after NFC
            'als_present': True,
            'als_template_id': template_id  # Template identifier
        })
        
        return request
    
    async def _emit_telemetry(
        self,
        request: LLMRequest,
        response: LLMResponse,
        session: AsyncSession
    ):
        """Emit comprehensive telemetry row to database"""
        try:
            # Build comprehensive metadata JSON
            meta_json = {
                # ALS fields
                'als_present': request.metadata.get('als_present', False) if hasattr(request, 'metadata') else False,
                'als_block_sha256': request.metadata.get('als_block_sha256') if hasattr(request, 'metadata') else None,
                'als_variant_id': request.metadata.get('als_variant_id') if hasattr(request, 'metadata') else None,
                'seed_key_id': request.metadata.get('seed_key_id') if hasattr(request, 'metadata') else None,
                'als_country': request.metadata.get('als_country') if hasattr(request, 'metadata') else None,
                'als_nfc_length': request.metadata.get('als_nfc_length') if hasattr(request, 'metadata') else None,
                
                # Grounding fields
                'grounding_mode_requested': 'REQUIRED' if request.grounded else 'NONE',
                'grounded_effective': response.grounded_effective,
                'tool_call_count': response.metadata.get('tool_call_count', 0) if hasattr(response, 'metadata') else 0,
                'why_not_grounded': response.metadata.get('why_not_grounded') if hasattr(response, 'metadata') else None,
                
                # API versioning
                'response_api': response.metadata.get('response_api') if hasattr(response, 'metadata') else None,
                'provider_api_version': response.metadata.get('provider_api_version') if hasattr(response, 'metadata') else None,
                'region': response.metadata.get('region') if hasattr(response, 'metadata') else None,
                
                # Proxy normalization tracking
                'vantage_policy_before': getattr(request, 'original_vantage_policy', None),
                'vantage_policy_after': getattr(request, 'vantage_policy', 'ALS_ONLY'),
                'proxies_normalized': getattr(request, 'proxy_normalization_applied', False),
                
                # Model info
                'model_fingerprint': response.model_fingerprint if hasattr(response, 'model_fingerprint') else None,
                'normalized_model': request.model
            }
            
            # Log comprehensive telemetry
            logger.info(
                "LLM telemetry: vendor=%s model=%s grounded_requested=%s grounded_effective=%s "
                "als_present=%s tool_count=%s response_api=%s region=%s",
                request.vendor, request.model, request.grounded, response.grounded_effective,
                meta_json['als_present'], meta_json['tool_call_count'],
                meta_json['response_api'], meta_json['region']
            )
            
            # Store structured telemetry as JSON string for now (can be migrated to JSONB later)
            import json
            meta_str = json.dumps(meta_json)
            
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
            
            # Store meta_json in memory for later migration to JSONB column
            # For now, log it comprehensively
            logger.debug(f"Telemetry metadata: {meta_str}")
            
            session.add(telemetry)
            await session.flush()
            
        except Exception as e:
            # Log but don't fail the request
            logger.error(f"Failed to emit telemetry: {e}")
    
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
        Infer vendor from model name (supports fully-qualified Vertex IDs)
        
        Args:
            model: Model identifier
            
        Returns:
            Vendor name or None if unknown
        """
        if not model:
            return None
            
        # OpenAI models
        if model in ["gpt-5", "gpt-5-chat-latest"]:
            return "openai"
            
        # Vertex (Gemini) - support both shorthand and fully-qualified
        if "publishers/google/models/gemini-" in model:
            return "vertex"
        if model.startswith("gemini-"):
            return "vertex"
            
        return None  # Unsupported model