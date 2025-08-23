# tests/test_openai_happy_path.py
import os, requests, pytest

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
RUN_E2E = os.getenv("RUN_E2E", "0") == "1"

pytestmark = pytest.mark.skipif(not RUN_E2E, reason="Set RUN_E2E=1 to enable E2E tests")

def test_preflight_ready():
    r = requests.get(f"{API_BASE}/ops/openai-preflight", timeout=30)
    assert r.ok, r.text
    data = r.json()
    assert data.get("ready") is True

def test_gpt5_simple_run():
    # make a tiny template
    r = requests.post(f"{API_BASE}/v1/templates", json={
        "name": "E2E 2+2",
        "messages": [{"role":"user","content":"What is 2+2?"}],
        "vendor": "openai", "model": "gpt-5"
    }, timeout=60)
    assert r.status_code in (200,201), r.text
    tid = r.json()["template_id"]

    run = requests.post(f"{API_BASE}/v1/templates/{tid}/run", json={"max_tokens":128}, timeout=120)
    assert run.ok, run.text
    body = run.json()
    assert "provider" in body and body["provider"] == "openai"
    assert "usage" in body and isinstance(body["usage"], dict)
    assert "content" in body  # may be empty for pathological prompts; adapter now retries
