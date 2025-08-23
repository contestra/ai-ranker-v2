import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_vertex_template_routes_or_errors():
    # Test that vertex templates route to vertex or fail with auth errors, never fallback to OpenAI
    template_id = "bdbc0d07-0ac3-43b3-af0e-512186dc5e6c"
    async with AsyncClient(app=app, base_url="http://test") as ac:
        try:
            r = await ac.post(f"/v1/templates/{template_id}/run", json={},
                              headers={"X-Organization-Id": "test-org"})
            body = r.json()
            # If it succeeds, it must be from vertex
            assert body.get("vendor") == "vertex"
        except Exception as e:
            # If it fails, it should be an auth error, not a silent fallback to OpenAI
            error_str = str(e)
            assert "DefaultCredentialsError" in error_str or "credentials" in error_str.lower()
            # The key point: we never get an OpenAI response when requesting vertex