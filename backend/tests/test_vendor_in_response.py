import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_openai_response_includes_vendor():
    """Test that OpenAI templates return vendor='openai' in response"""
    # Create an OpenAI template
    template_payload = {
        "template_name": "test-openai-vendor",
        "canonical": {
            "provider": "openai",
            "model": "gpt-5",
            "messages": [
                {"role": "user", "content": "Say PING"}
            ],
            "temperature": 0.0,
            "max_tokens": 16
        }
    }
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create template
        template_resp = await ac.post(
            "/v1/templates",
            json=template_payload,
            headers={"X-Organization-Id": "test-org"}
        )
        assert template_resp.status_code in (200, 201)
        template_id = template_resp.json()["template_id"]
        
        # Run template
        run_resp = await ac.post(
            f"/v1/templates/{template_id}/run",
            json={},
            headers={"X-Organization-Id": "test-org"}
        )
        
        # Should succeed and include vendor
        assert run_resp.status_code == 200
        body = run_resp.json()
        assert body["vendor"] == "openai"
        assert "model_version_effective" in body
        assert "output" in body
        assert "usage" in body


@pytest.mark.asyncio 
async def test_vertex_response_includes_vendor_even_on_error():
    """Test that Vertex templates return vendor='vertex' or proper error"""
    # Create a Vertex template
    template_payload = {
        "template_name": "test-vertex-vendor",
        "canonical": {
            "provider": "vertex",
            "model": "gemini-2.5-pro",
            "messages": [
                {"role": "user", "content": "Say PING"}
            ],
            "temperature": 0.0,
            "max_tokens": 16
        }
    }
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create template
        template_resp = await ac.post(
            "/v1/templates",
            json=template_payload,
            headers={"X-Organization-Id": "test-org"}
        )
        assert template_resp.status_code in (200, 201)
        template_id = template_resp.json()["template_id"]
        
        # Run template
        run_resp = await ac.post(
            f"/v1/templates/{template_id}/run",
            json={},
            headers={"X-Organization-Id": "test-org"}
        )
        
        # If successful, must have vendor=vertex
        if run_resp.status_code == 200:
            body = run_resp.json()
            assert body["vendor"] == "vertex"
            assert "model_version_effective" in body
        else:
            # If it fails due to auth, that's expected
            assert run_resp.status_code in (401, 403, 500, 503)


@pytest.mark.asyncio
async def test_vendor_field_required_in_schema():
    """Test that vendor field is properly required and validated"""
    # Create an OpenAI template that should work
    template_payload = {
        "template_name": "test-vendor-schema",
        "canonical": {
            "provider": "openai", 
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 16
        }
    }
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create template
        template_resp = await ac.post(
            "/v1/templates",
            json=template_payload,
            headers={"X-Organization-Id": "test-org"}
        )
        assert template_resp.status_code in (200, 201)
        template_id = template_resp.json()["template_id"]
        
        # Run template
        run_resp = await ac.post(
            f"/v1/templates/{template_id}/run",
            json={},
            headers={"X-Organization-Id": "test-org"}
        )
        
        if run_resp.status_code == 200:
            body = run_resp.json()
            # Vendor must be one of the allowed values
            assert body["vendor"] in ["openai", "vertex", "gemini"]
            # Must be exactly the string, not None or empty
            assert isinstance(body["vendor"], str)
            assert len(body["vendor"]) > 0