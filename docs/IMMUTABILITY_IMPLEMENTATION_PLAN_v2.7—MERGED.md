# Prompt Immutability — Implementation Plan **v2.7 (Merged)**

**Purpose:** Implement PRD v2.6 with explicit **Phase‑1 = FastAPI + Neon** and **Phase‑2 = add Celery/Redis/Fly**; make the seven upgrade‑seams concrete with code, config, tests, and rollout.  
**Status:** Ready for implementation & QA sign‑off.  
**Owners:** Platform Eng (Backend + Frontend), Data/Analytics  
**Last Updated:** 2025‑08‑22

**Stack:** FastAPI, Pydantic, Neon Postgres (SOR), LangChain adapters; Phase‑2 adds Upstash/Redis + Celery; deployment target Fly.io (later).

---

## 0) Executive Summary

- **Phase‑1 deliverable:** Production‑ready API and DB with in‑process execution, strict immutability, model pinning, ALS determinism, grounding enforcement, strict JSON, idempotency, provider cache w/ TTL & **single‑flight**, complete provenance, analytics streaming.  
- **Phase‑2 deliverable:** Drop‑in Celery workers, Redis caches/mutex, pause/resume UI, Fly deployment — **no API/DB changes**.  
- **Seams enforced:** TaskRunner abstraction, DB‑driven orchestration, Postgres idempotency, single‑flight, config flags, containerization stance, invariant‑freezing tests.

---

## 1) Deployment Phases

- **Phase‑1 (Start):** No Redis/Celery. Neon Postgres only. In‑process executor. Provider version cache and idempotency live in Postgres.  
- **Phase‑2 (Add):** Introduce Redis (TTL caches, mutex/idempotency mirror) and Celery (async batches). Move to Fly for scale. API/schema unchanged.

---

## 2) Canonicalization & Output Hashing (unchanged technically; locked in tests)

- Numbers: ≤6 fractional digits, **ROUND_HALF_UP**, trim zeros, **no scientific notation**, `-0→0`.  
- Output hashing: **JSON** orders object keys only (arrays preserved); **Text** strips trailing whitespace, CRLF→LF, NFC.  
- Golden vectors maintained in both Python and TypeScript.

---

## 3) Provider Version Pinning & Cache (with single‑flight)

- **Cache table:** `provider_version_cache(provider, versions, current, last_checked_utc, expires_at_utc, etag, source)`; TTL default 300s.  
- **Single‑flight:**  
  - Phase‑1: Postgres advisory lock (`pg_try_advisory_lock(hash('provider:'+name))`).  
  - Phase‑2: Redis mutex (`SETNX` + expiry + watchdog).  
- **API:** `GET /v1/providers/{provider}/versions?force_refresh=` returns `source="cache|live"` and updates `etag/expires_at_utc` on live fetch.  
- **Run enforcement:** equality vs `model_version_constraint`; optional fingerprint allowlist.

---

## 4) ALS Determinism & Rotation

- `seed_key_id` plumbed through canonical JSON and runs; HMAC(server_secret[seed_key_id] | als.template_id).  
- NFC length counting only; hard limit **350**; fail‑closed; capture `als_block_text`, `als_block_sha256`, `als_variant_id`.  
- **Secret rotation procedure:** add `k2` to map; new templates default to `k2`; existing templates remain on prior key id; invariance test suite verifies no ALS changes for existing templates.

---

## 5) Grounding & Gemini Two‑Step (detectors)

- **OpenAI detector:** ≥1 non‑empty `web_search` tool result set + final citations payload.  
- **Gemini detector:** Step‑1 non‑empty GoogleSearch results + final `groundingMetadata/citedSources`.  
- **Attestation:** When strict JSON via Gemini two‑step, enforce `step2_tools_invoked=false` and capture `step2_source_ref=sha256(step1_text)`; otherwise **fail‑closed**.

---

## 6) API Endpoints (Phase‑1)

- `POST /v1/templates` — immutable create; idempotency (`org_id`, key); returns RFC‑6902 diff on conflict.  
- `POST /v1/templates/{id}/run` — version equality, optional fingerprint allowlist, strict JSON enforcement, grounding evidence checks; returns provenance and hashes.  
- `POST /v1/templates/{id}/batch-run` — preflight `{version,fingerprint}` lock; deterministic expansion; drift policy; limits.  
- `GET /v1/providers/{provider}/versions` — TTL + single‑flight; returns `expires_at_utc`, `etag`, `source`.  
- `GET /v1/templates/{id}/runs` — list/filter runs.

---

## 7) Storage & Migrations (Neon Postgres; dev‑only SQLite parity)

- `templates` (incl. **`record_hmac`**), `batches`, `runs`, `idempotency_keys`, `provider_version_cache`.  
- RLS for org scoping.  
- Indexes: `runs(response_output_sha256)`, `runs(batch_id,batch_run_index)`, unique `templates(org_id, template_sha256)`.  
- **Alembic:** ensure runs contain `response_output_sha256`, `output_json_valid`, `why_not_grounded`, `response_api`, `step2_tools_invoked`, `step2_source_ref`, `seed_key_id`, `provoker_value`.  
- **SQLite parity:** CI job runs vectors on both backends and asserts identical results (hashes, idempotency, numeric/JSON rules).

---

## 8) Batch Executor (Phase‑1, in‑process)

- Deterministic expansion (`locales × modes × replicate_index`), stable ordering, assign `batch_run_index`.  
- Preflight lock once per batch; each run compares observed `{version,fingerprint}` to the lock.  
- Retries reuse locale/ALS indices.  
- Configurable rate limits and backoffs via env.

---

## 9) **Seven upgrade‑seams — concrete enforcement**

1) **TaskRunner abstraction**  
   - Create `app/core/tasks.py` defining `TaskRunner` with `run_cell(...)` and `run_batch(...)`.  
   - Provide `SyncTaskRunner` (Phase‑1) and `CeleryTaskRunner` (Phase‑2).  
   - **CI import‑guard**: script fails build if any module under `app/http` imports `celery` or references `CeleryTaskRunner`.

2) **DB‑driven orchestration**  
   - Controllers enqueue via `TaskRunner`; both runners read/write `batches/runs` rows as SOR.  
   - No ephemeral in‑memory queues in Phase‑1.

3) **Idempotency in Postgres**  
   - `idempotency_keys(org_id, key)` unique; TTL cleanup job.  
   - 201/200/409 semantics tested.  
   - Phase‑2 optional Redis mirror retains identical semantics; Postgres remains the truth.

4) **Provider cache single‑flight**  
   - Wrap live refresh with advisory lock (Phase‑1); Redis mutex (Phase‑2).  
   - Add metric `provider_cache_singleflight_locks_total{provider}`.

5) **Config flags**  
   - `EXECUTION_MODE=sync|celery`, `USE_REDIS=false|true`, `PROVIDER_VERSION_CACHE_TTL_SECONDS`, batch limits, ALS limit.  
   - Integration test flips modes and asserts **identical hashes/outputs** for the same inputs.

6) **Containerization stance**  
   - Dockerfile uses generic base; no Fly‑specific code.  
   - Fly launch in Phase‑2 references the same image and env flags only.

7) **Invariant‑freezing tests**  
   - Golden vectors: numeric ROUND_HALF_UP at 6 dp; `-0→0`; no sci‑notation.  
   - JSON output hashing: object‑key ordering only; array order preserved; `1/1.0/1.000000` hash‑equivalent.  
   - ALS NFC length ≤350 with combining sequences/emoji.  
   - Gemini two‑step attestation fields captured/enforced.  
   - SQLite↔Postgres parity suite.  
   - Provider cache single‑flight concurrency test.

---

## 10) Observability

Prometheus: version mismatch counters, batch drift pauses, ALS over‑limit, grounding required failures, **single‑flight locks**.  
BigQuery streaming (at‑least‑once) for runs/batches; include typed token counts when available.

---

## 11) Rollout Plan

**Week 1**: Numeric/output hashing vectors; Alembic migrations; Postgres idempotency; provider cache TTL.  
**Week 2**: Single‑flight (advisory lock); grounding detectors; Gemini Step‑2 attestation; RLS enforcement.  
**Week 3**: In‑process batch executor; drift policy; rate controls; dashboards/metrics.  
**Week 4**: SQLite↔Postgres parity CI; soak/perf; import‑guard CI; docs.  
**Weeks 5–6 (Phase‑2)**: Redis mutex/idempotency mirror, Celery workers, pause/resume UI, Fly deploy.  
**Week 7**: Secret rotation (`seed_key_id` → `k2`); invariance verification on existing templates; default new templates to `k2`.

---

## 12) Changelog — v2.6 → v2.7

- Made the **seven upgrade seams** explicit and enforced (TaskRunner, DB SOR, Postgres idempotency, single‑flight, config flags, containerization, invariant‑tests).  
- Locked Phase‑1 = FastAPI+Neon; Phase‑2 adds Celery/Redis/Fly with **no API/DB changes**.  
- Clarified acceptance around output hashing (object keys only), numeric formatting (ROUND_HALF_UP), and attestation capture.
