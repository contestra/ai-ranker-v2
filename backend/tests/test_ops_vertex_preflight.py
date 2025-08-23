from fastapi.testclient import TestClient
from app.main import app

def test_vertex_preflight_shape():
    client = TestClient(app)
    r = client.get("/ops/vertex-preflight")
    assert r.status_code == 200
    body = r.json()

    # Always-present fields
    assert isinstance(body.get("ready"), bool)
    assert "project" in body
    assert "location" in body
    assert isinstance(body.get("errors", []), list)

    if body["ready"]:
        # Success path: must expose identity details
        assert isinstance(body.get("credential_type"), str)
        assert isinstance(body.get("principal"), str)
        assert body["errors"] == []
    else:
        # Error path: allow missing identity fields, but if present they must be strings or null
        ct = body.get("credential_type", None)
        pr = body.get("principal", None)
        assert (ct is None) or isinstance(ct, str)
        assert (pr is None) or isinstance(pr, str)
        assert len(body["errors"]) >= 1