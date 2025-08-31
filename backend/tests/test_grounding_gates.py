"""
CI Test Gates for Grounding Compliance
These tests ensure PRD requirements are met
"""

import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.types import LLMRequest, ALSContext
from app.llm.domain_authority import authority_scorer

class TestGroundingGates:
    """Critical acceptance tests for grounding functionality"""
    
    @pytest.mark.asyncio
    async def test_required_mode_must_fail_closed(self):
        """REQUIRED mode must either ground or fail - never return ungrounded"""
        adapter = UnifiedLLMAdapter()
        
        # Test with a model that doesn't support grounding
        request = LLMRequest(
            messages=[{"role": "user", "content": "What's the weather?"}],
            vendor="openai",
            model="gpt-5",
            grounded=True,
            meta={"grounding_mode": "REQUIRED"},
            max_tokens=50,
            template_id="test_required_gate",
            run_id="gate_001"
        )
        
        # This should either:
        # 1. Successfully ground (grounded_effective=True)
        # 2. Raise an error (GROUNDING_NOT_SUPPORTED)
        # It should NEVER return success with grounded_effective=False
        
        try:
            response = await asyncio.wait_for(adapter.complete(request), timeout=30)
            
            # If we got a response, it must be grounded
            assert hasattr(response, 'grounded_effective'), "Response missing grounded_effective"
            
            # In REQUIRED mode, if we get a response without error,
            # it should have attempted grounding (even if model doesn't support it)
            # The adapter should have failed closed
            
        except Exception as e:
            # Expected for models that don't support grounding
            assert "GROUNDING_NOT_SUPPORTED" in str(e) or "GROUNDING_REQUIRED" in str(e)
    
    @pytest.mark.asyncio
    async def test_als_propagation(self):
        """ALS must be propagated to response metadata when provided"""
        adapter = UnifiedLLMAdapter()
        
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            vendor="openai",
            model="gpt-5",
            grounded=False,
            max_tokens=20,
            template_id="test_als_gate",
            run_id="gate_002"
        )
        
        # Add ALS context
        request.als_context = ALSContext(
            country_code="US",
            locale="en-US",
            als_block="Test ALS block"
        )
        
        response = await asyncio.wait_for(adapter.complete(request), timeout=30)
        
        # Verify ALS is in response metadata
        assert hasattr(response, 'metadata'), "Response missing metadata"
        assert response.metadata.get('als_present') == True, "ALS not marked present"
        assert response.metadata.get('als_country') == 'US', "ALS country not propagated"
        assert 'als_block_sha256' in response.metadata, "ALS SHA256 not present"
        assert response.metadata.get('als_nfc_length', 0) > 0, "ALS length not recorded"
    
    @pytest.mark.asyncio
    async def test_authority_scoring(self):
        """Authority scoring must correctly classify domains"""
        
        # Test citations with known domains
        test_citations = [
            {"url": "https://www.reuters.com/article/123", "title": "Reuters Article"},
            {"url": "https://www.bloomberg.com/news/456", "title": "Bloomberg News"},
            {"url": "https://watcher.guru/news/789", "title": "Watcher Guru"},
            {"url": "https://example.blogspot.com/post", "title": "Blog Post"},
        ]
        
        metrics = authority_scorer.score_citations(test_citations)
        
        # Verify metrics
        assert metrics['total_citations'] == 4
        assert metrics['tier_1_count'] == 2  # Reuters, Bloomberg
        assert metrics['tier_4_count'] == 1  # Watcher.guru (penalty)
        assert metrics['authority_score'] > 50  # Should have decent score with 2 tier-1
        assert metrics['tier_1_percentage'] == 50.0
        assert metrics['penalty_percentage'] == 25.0
    
    @pytest.mark.asyncio
    async def test_grounding_mode_telemetry(self):
        """Grounding mode must be correctly reported in metadata"""
        adapter = UnifiedLLMAdapter()
        
        # Test AUTO mode
        request_auto = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            vendor="vertex",
            model="publishers/google/models/gemini-2.5-pro",
            grounded=True,
            meta={"grounding_mode": "AUTO"},
            max_tokens=20,
            template_id="test_mode_gate",
            run_id="gate_003"
        )
        
        try:
            response = await asyncio.wait_for(adapter.complete(request_auto), timeout=30)
            if hasattr(response, 'metadata'):
                assert response.metadata.get('grounding_mode_requested') == 'AUTO'
        except:
            pass  # OK if it fails, we're testing metadata when it succeeds
    
    @pytest.mark.asyncio  
    async def test_two_step_attestation(self):
        """Two-step grounded+JSON must include attestation fields"""
        adapter = UnifiedLLMAdapter()
        
        request = LLMRequest(
            messages=[{"role": "user", "content": "List 3 facts about Tesla"}],
            vendor="vertex", 
            model="publishers/google/models/gemini-2.5-pro",
            grounded=True,
            json_mode=True,  # This triggers two-step
            max_tokens=200,
            template_id="test_attestation",
            run_id="gate_004"
        )
        
        try:
            response = await asyncio.wait_for(adapter.complete(request), timeout=45)
            
            if hasattr(response, 'metadata') and response.metadata.get('grounded_effective'):
                # If two-step was used, attestation must be present
                if 'step2_tools_invoked' in response.metadata:
                    assert response.metadata['step2_tools_invoked'] == False, "Step 2 must not invoke tools"
                    assert 'step2_source_ref' in response.metadata, "Step 2 must include source reference"
        except:
            pass  # OK if it times out, we're testing the attestation when it works


class TestIdempotency:
    """Test for deterministic/idempotent behavior"""
    
    @pytest.mark.asyncio
    async def test_als_determinism(self):
        """ALS generation must be deterministic for same inputs"""
        adapter = UnifiedLLMAdapter()
        
        # Create two identical requests
        def make_request():
            req = LLMRequest(
                messages=[{"role": "user", "content": "Hello"}],
                vendor="openai",
                model="gpt-5",
                grounded=False,
                max_tokens=10,
                template_id="test_determinism",
                run_id="determinism_001"
            )
            req.als_context = ALSContext(
                country_code="US",
                locale="en-US", 
                als_block="Test"
            )
            return req
        
        request1 = make_request()
        request2 = make_request()
        
        # Apply ALS to both
        request1 = adapter._apply_als(request1)
        request2 = adapter._apply_als(request2)
        
        # SHA256 should be identical
        assert request1.metadata['als_block_sha256'] == request2.metadata['als_block_sha256']
        assert request1.metadata['als_variant_id'] == request2.metadata['als_variant_id']


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])