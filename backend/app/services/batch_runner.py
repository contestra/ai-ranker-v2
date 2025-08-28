"""
Batch execution service for running templates across multiple configurations
Implements deterministic expansion and ALS integration
"""

import asyncio
import hashlib
import time
import random
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Any, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import PromptTemplate, Batch, Run
from app.schemas.templates import BatchRunRequest, BatchRunResponse, RunTemplateRequest
from app.services.template_runner import execute_template_run
from app.services.als.als_builder import ALSBuilder
from app.services.als.country_codes import is_valid_country, get_all_countries
from app.core.canonicalization import compute_sha256
from app.core.config import get_settings
from app.prometheus_metrics import set_openai_active_concurrency, set_openai_next_slot_epoch, inc_stagger_delays, inc_tpm_deferrals


class BatchRunner:
    """Service for executing batch runs with ALS and grounding support"""
    
    def __init__(self):
        self.als_builder = ALSBuilder()
        # OpenAI gating (in-process)
        s = get_settings()
        self._openai_sem = asyncio.Semaphore(max(1, s.openai_max_concurrency))
        self._openai_active = 0
        self._openai_active_lock = asyncio.Lock()
        self._slot_lock = asyncio.Lock()
        self._next_slot_epoch = 0.0
        self._stagger_seconds = max(0, int(s.openai_stagger_seconds))
        self._tpm_limit = max(1000, int(s.openai_tpm_limit))
        self._tpm_headroom = max(0.0, min(0.9, float(s.openai_tpm_headroom)))
        self._tpm_est = max(1, int(s.openai_est_tokens_per_run))
        self._tpm_lock = asyncio.Lock()
        self._tpm_window_minute = int(time.time() // 60)
        self._tpm_used = 0
    
    def _extract_country_from_locale(self, locale: str) -> str:
        """Extract country code from locale (e.g., 'en-US' -> 'US')"""
        if '-' in locale:
            return locale.split('-')[1].upper()
        return 'NONE'
    
    def _build_als_context(self, locale: str) -> Dict[str, Any]:
        """Build ALS context for a locale"""
        country = self._extract_country_from_locale(locale)
        
        if not is_valid_country(country):
            return {}
        
        # Generate ALS block with rotation
        als_block = self.als_builder.build_als_block(
            country=country,
            max_chars=350,
            include_weather=True,
            randomize=True  # This enables template rotation
        )
        
        return {
            "country_code": country,
            "locale": locale,
            "als_block": als_block,
            "als_enabled": bool(als_block)
        }
    
    def _generate_run_configurations(self, request: BatchRunRequest) -> List[Dict[str, Any]]:
        """Generate all model×locale×grounding×replicate combinations"""
        configurations = []
        run_index = 0
        
        for model in request.models:
            for locale in request.locales:
                for grounding_mode in request.grounding_modes:
                    for replicate in range(request.replicates):
                        
                        # Build ALS context for this locale
                        als_context = self._build_als_context(locale)
                        
                        # Determine grounding
                        grounded = grounding_mode in ["GROUNDED", "REQUIRED"]
                        
                        config = {
                            "run_index": run_index,
                            "model": model,
                            "locale": locale,
                            "grounding_mode": grounding_mode,
                            "grounded": grounded,
                            "replicate": replicate + 1,
                            "als_context": als_context,
                            "inputs": request.inputs or {}
                        }
                        
                        configurations.append(config)
                        run_index += 1
        
        return configurations

    # --- OpenAI gating helpers ---
    def _is_openai_model(self, model: str) -> bool:
        return isinstance(model, str) and model.lower().startswith("gpt-")

    async def _await_openai_tpm_budget(self):
        now = time.time()
        minute = int(now // 60)
        async with self._tpm_lock:
            if minute != self._tpm_window_minute:
                self._tpm_window_minute = minute
                self._tpm_used = 0
            budget = int(self._tpm_limit * (1.0 - self._tpm_headroom))
            if self._tpm_used + self._tpm_est > budget:
                inc_tpm_deferrals()
                await asyncio.sleep(max(0.0, 60.0 - (now % 60.0)) + 0.05)
                self._tpm_window_minute = int(time.time() // 60)
                self._tpm_used = 0
            self._tpm_used += self._tpm_est

    async def _await_openai_launch_slot(self):
        if self._stagger_seconds <= 0:
            return
        async with self._slot_lock:
            now = time.time()
            next_slot = max(self._next_slot_epoch, now)
            delay = max(0.0, next_slot - now)
            if delay > 0.0:
                inc_stagger_delays()
            # jitter ±20% of stagger, capped 3s
            jitter = min(3.0, 0.2 * self._stagger_seconds)
            # flip sign by alternating (not necessary; use random if available).
            self._next_slot_epoch = next_slot + self._stagger_seconds + jitter
            set_openai_next_slot_epoch(int(self._next_slot_epoch))
        if delay > 0.0:
            await asyncio.sleep(delay)

    async def _openai_concurrency_context(self):
        await self._openai_sem.acquire()
        async with self._openai_active_lock:
            self._openai_active += 1
            set_openai_active_concurrency(self._openai_active)
        try:
            yield
        finally:
            async with self._openai_active_lock:
                self._openai_active = max(0, self._openai_active - 1)
                set_openai_active_concurrency(self._openai_active)
            self._openai_sem.release()
    
    def _compute_batch_hash(self, template_id: str, request: BatchRunRequest) -> str:
        """Compute deterministic hash for batch configuration"""
        batch_data = {
            "template_id": str(template_id),
            "models": sorted(request.models),
            "locales": sorted(request.locales), 
            "grounding_modes": sorted(request.grounding_modes),
            "replicates": request.replicates,
            "inputs": request.inputs or {}
        }
        return compute_sha256(batch_data)
    
    def _is_openai_model(self, model: str) -> bool:
        """Check if model is from OpenAI"""
        return model.lower().startswith(('gpt-', 'o1-', 'text-', 'davinci', 'curie', 'babbage', 'ada'))
    
    async def _await_openai_tpm_budget(self):
        """Wait until TPM budget allows next request"""
        async with self._tpm_lock:
            current_minute = int(time.time() // 60)
            
            # Reset counter if we're in a new minute
            if current_minute != self._tpm_window_minute:
                self._tpm_window_minute = current_minute
                self._tpm_used = 0
            
            # Check if we have budget
            effective_limit = int(self._tpm_limit * (1 - self._tpm_headroom))
            if self._tpm_used + self._tpm_est > effective_limit:
                # Wait until next minute
                inc_tpm_deferrals()
                wait_seconds = 60 - (time.time() % 60) + random.uniform(0.1, 0.5)
                await asyncio.sleep(wait_seconds)
                
                # Reset for new minute
                self._tpm_window_minute = int(time.time() // 60)
                self._tpm_used = 0
            
            # Reserve tokens
            self._tpm_used += self._tpm_est
    
    async def _await_openai_launch_slot(self):
        """Enforce stagger between OpenAI request launches"""
        if self._stagger_seconds <= 0:
            return
            
        async with self._slot_lock:
            now = time.time()
            if self._next_slot_epoch > now:
                wait_time = self._next_slot_epoch - now
                inc_stagger_delays()
                await asyncio.sleep(wait_time)
            
            # Set next slot with jitter
            self._next_slot_epoch = time.time() + self._stagger_seconds + random.uniform(0, 2)
            set_openai_next_slot_epoch(self._next_slot_epoch)
    
    @asynccontextmanager
    async def _openai_concurrency_context(self):
        """Context manager for OpenAI concurrency tracking"""
        await self._openai_sem.acquire()
        
        async with self._openai_active_lock:
            self._openai_active += 1
            set_openai_active_concurrency(self._openai_active)
        
        try:
            yield
        finally:
            async with self._openai_active_lock:
                self._openai_active -= 1
                set_openai_active_concurrency(self._openai_active)
            
            self._openai_sem.release()
    
    async def execute_batch(
        self,
        session: AsyncSession,
        template_id: str,
        request: BatchRunRequest,
        org_id: str,
        user_id: Optional[str] = None
    ) -> BatchRunResponse:
        """
        Execute a batch run with deterministic expansion
        
        Args:
            session: Database session
            template_id: Template UUID
            request: Batch run request
            org_id: Organization ID
            user_id: Optional user ID
            
        Returns:
            BatchRunResponse with batch details and run IDs
        """
        
        # Verify template exists
        result = await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.template_id == template_id,
                PromptTemplate.org_id == org_id
            )
        )
        template = result.scalar_one_or_none()
        
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # Generate run configurations
        configurations = self._generate_run_configurations(request)
        total_runs = len(configurations)
        
        # Create batch record
        batch_id = uuid4()
        batch_sha256 = self._compute_batch_hash(template_id, request)
        
        batch = Batch(
            batch_id=batch_id,
            template_id=template_id,
            batch_sha256=batch_sha256,
            parameters={
                "models": request.models,
                "locales": request.locales,
                "grounding_modes": request.grounding_modes,
                "replicates": request.replicates,
                "drift_policy": request.drift_policy,
                "inputs": request.inputs or {}
            },
            created_at=datetime.utcnow(),
            created_by=user_id
        )
        
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        
        # Execute runs (with limited parallelism)
        max_parallel = min(request.max_parallel or 10, 20)  # Cap at 20
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def execute_single_run(config: Dict[str, Any]) -> str:
            """Execute a single run configuration"""
            async with semaphore:
                try:
                    # Build run request
                    run_request = RunTemplateRequest(
                        variables=config["inputs"],
                        model=config["model"],
                        grounded=config["grounded"],
                        json_mode=False,  # TODO: Support from template
                        als_context=config["als_context"]
                    )
                    
                    # Execute the run
                    s = get_settings()
                    if s.openai_gate_in_batch and self._is_openai_model(config["model"]):
                        await self._await_openai_tpm_budget()
                        await self._await_openai_launch_slot()
                        async with self._openai_concurrency_context():
                            response = await execute_template_run(
                                session=session,
                                template_id=template_id,
                                request=run_request,
                                org_id=org_id,
                                user_id=user_id
                            )
                    else:
                        response = await execute_template_run(
                            session=session,
                            template_id=template_id,
                            request=run_request,
                            org_id=org_id,
                            user_id=user_id
                        )
                    
                    # Update run with batch information
                    from sqlalchemy import update
                    await session.execute(
                        update(Run).where(Run.run_id == response.run_id).values(
                            batch_id=batch_id,
                            batch_run_index=config['run_index'],
                            grounding_mode=config['grounding_mode']
                        )
                    )
                    
                    return response.run_id
                    
                except Exception as e:
                    print(f"Failed to execute run {config['run_index']}: {e}")
                    return None
        
        # Execute all runs concurrently
        run_ids = await asyncio.gather(
            *[execute_single_run(config) for config in configurations],
            return_exceptions=True
        )
        
        # Filter successful runs
        successful_runs = [rid for rid in run_ids if rid and not isinstance(rid, Exception)]
        
        await session.commit()
        
        # Build response
        return BatchRunResponse(
            batch_id=batch_id,
            template_id=template_id,
            batch_sha256=batch_sha256,
            status="completed" if len(successful_runs) == total_runs else "partial",
            total_runs=total_runs,
            successful_runs=len(successful_runs),
            failed_runs=total_runs - len(successful_runs),
            created_at=batch.created_at,
            run_ids=successful_runs
        )