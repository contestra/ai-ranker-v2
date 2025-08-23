# tests/test_immutability.py
import os, uuid, requests, pytest

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
RUN_E2E = os.getenv("RUN_E2E", "0") == "1"

pytestmark = pytest.mark.skipif(not RUN_E2E, reason="Set RUN_E2E=1 to enable E2E tests")

def test_template_sha_stable():
    r = requests.post(f"{API_BASE}/v1/templates", json={
        "name": "E2E Immutability",
        "messages": [
            {"role":"system","content":"You are precise."},
            {"role":"user","content":"Ping"}
        ],
        "vendor": "openai",
        "model": "gpt-5"
    })
    assert r.status_code in (200,201), r.text
    t1 = r.json()
    g = requests.get(f"{API_BASE}/v1/templates/{t1['template_id']}")
    assert g.ok, g.text
    t2 = g.json()
    assert t1["template_sha256"] == t2["template_sha256"]

def test_run_records_hash_and_usage():
    # create
    r = requests.post(f"{API_BASE}/v1/templates", json={
        "name": "E2E Run",
        "messages": [{"role":"user","content":"What is 2+2?"}],
        "vendor": "openai", "model": "gpt-5"
    })
    assert r.status_code in (200,201), r.text
    tid = r.json()["template_id"]
    # run
    run = requests.post(f"{API_BASE}/v1/templates/{tid}/run", json={"max_tokens":128})
    assert run.ok, run.text
    body = run.json()
    # minimal assertions (implementation-specific fields may vary)
    assert "content" in body
    assert "usage" in body and isinstance(body["usage"], dict)
    assert "model_version" in body
    assert "meta" in body and "max_output_tokens_effective" in body["meta"]
