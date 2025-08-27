"""
Batch execution service for running templates across multiple configurations
Implements deterministic expansion and ALS integration
"""

import asyncio
import hashlib
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


class BatchRunner:
    """Service for executing batch runs with ALS and grounding support"""
    
    def __init__(self):
        self.als_builder = ALSBuilder()
    
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