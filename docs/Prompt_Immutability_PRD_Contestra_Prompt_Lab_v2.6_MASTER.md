# Prompt Immutability PRD — Contestra Prompt Lab (**v2.6 Master**)

**Status:** Ready for engineering sign‑off  
**Owners:** Platform Eng (Backend + Frontend), Data/Analytics  
**Reviewers:** Product, Infra/SRE, QA  
**Last updated:** 2025‑08‑22  
**Provenance:** v2.3 master spec, v2.4 numeric/output hashing fixes, upgraded to v2.6 with explicit Phase‑1/Phase‑2 stance and seven upgrade‑seam requirements made **normative**.

---

## Deployment Phases (normative)

- **Phase‑1 (Start here):** **FastAPI + Neon Postgres only.** No Redis, no Celery. Batch execution is in‑process with minimal concurrency. Idempotency and provider‑version cache live in Postgres.  
- **Phase‑2 (Add later without API/DB changes):** **Celery + Upstash/Redis + Fly.io.** Redis for TTL caches/mutex/idempotency mirror; Celery for async batches, pause/resume, retries; Fly for deployment/scale. **API and schema remain identical.**

**Acceptance:** CI must include a smoke suite that runs with `EXECUTION_MODE=sync` and `USE_REDIS=false` (Phase‑1) and another that flips to `EXECUTION_MODE=celery` and `USE_REDIS=true` (Phase‑2) without any code changes except configuration.

---

## 1) Problem & Context

Templates must be immutable; a hash must guarantee identical input conditions: canonical inputs, exact model pinning, ALS determinism, grounding semantics, strict JSON, full provenance, and batch invariants — for **OpenAI (Responses HTTP)** and **Gemini (Vertex)**.

---

## 2) Goals & Non‑Goals

### Goals
1. Deterministic template identity (`template_sha256`).  
2. Full execution provenance (`run_sha256`, strict JSON validity, output hash).  
3. Fail‑closed immutability with actionable diffs.  
4. Provider parity; Gemini two‑step grounded→JSON when strict JSON is required.  
5. Analytics‑ready (Postgres SOR; BigQuery streaming).  
6. **Phaseability:** Start FastAPI+Neon; add Redis/Celery/Fly later **with zero API/DB changes**.  
7. **Seven upgrade seams are requirements** (see §12).

### Non‑Goals
- Versionless hashing or floating model aliases.  
- Tool‑specific worker wiring (belongs in Implementation Plan).

---

## 3) Definitions

- **Template** → immutable recipe (`template_sha256`).  
- **Run** → execution with resolved runtime facts; produces `run_sha256`.  
- **ALS** → short ambient locale/time block (≤350 Unicode chars).  
- **Grounding Modes** → `UNGROUNDED`, `PREFERRED`, `REQUIRED`.  
- **Model fingerprint** → provider build identifier (`system_fingerprint` / `modelVersion`).

---

## 4) Canonical Template Config (hashed surface)

Same field groups as v2.3. Canonicalization is **JCS‑like**; see §5. Arrays are sorted/deduped **for template canonicalization only**; numbers normalized; schema minimized and hashed (Draft 2020‑12).

- **Provider pinning (strict):** exact `model_version_constraint` is mandatory; `model_fingerprint_allowlist` optional.  
- **ALS determinism:** `seed_key_id` in canonical JSON; rotation invariance guaranteed (see §9.1).  
- **Grounded JSON two‑step flag** for Gemini reshaping.

---

## 5) Canonicalization Rules (normative)

- **Strings:** trim edges; CRLF→LF; drop BOM; no internal whitespace collapse.  
- **Enums:** lower‑case providers; preserve model id casing.  
- **Numbers:** ≤6 fractional digits; **ROUND_HALF_UP**; trim zeros; **no scientific notation**; reject non‑finite; `-0→0`.  
- **Arrays (scalars):** sort/dedupe; ISO‑3166 normalization (UK→GB, `CC‑SS`).  
- **Arrays (objects):** sort/dedupe by canonical dump.  
- **JSON Schema hashing:** Draft 2020‑12; resolve `$ref` locally; **sort `required`**; forbid remote `$ref`; minimized then hashed.  
- **Hashing:** `template_sha256 = sha256(canonical_bytes)`.

---

## 6) Execution Provenance

Record and hash (`run_sha256`) the following: provider api/version, `model_version_effective`, `model_fingerprint`, region, adapter commit, retry index, locale selection & indices, grounding request/effective, ALS (`seed_key_id`, `als_block_text`, `als_block_sha256`, `als_variant_id`), `provoker_value`, **`response_output_sha256`**, `output_json_valid`, `why_not_grounded`, **Gemini Step‑2 attestation (`step2_tools_invoked=false`, `step2_source_ref`)**.

**Output hashing (normative):**  
- **JSON** → order **object keys only**, preserve array order, apply numeric formatting (as §5), minify and hash.  
- **Text** → strip trailing whitespace, CRLF→LF, NFC, then hash.

---

## 7) API (stable across phases)

- **POST** `/v1/templates` → canonicalize; compute hash; idempotency by (`org_id`, `Idempotency‑Key`); immutable diffs on change.  
- **POST** `/v1/templates/{id}/run` → enforce version equality; optional fingerprint allowlist; grounding enforcement; strict JSON; return provenance and hashes.  
- **POST** `/v1/templates/{id}/batch-run` → single preflight lock `{version,fingerprint}`; deterministic expansion; drift policy `hard|fail|warn`.  
- **GET** `/v1/providers/{provider}/versions?force_refresh=` → returns `current`, `versions`, `last_checked_utc`, **`expires_at_utc`**, **`etag`**, **`source`**.  
- **GET** `/v1/templates/{id}/runs` → filterable history.

---

## 8) Storage (Neon Postgres SOR; dev‑only SQLite parity allowed)

Tables: `templates` (with **`record_hmac`**), `batches`, `runs`, `idempotency_keys`, `provider_version_cache`. Enable **RLS** for org scoping. Index `response_output_sha256` for dedup queries.

---

## 9) Grounding & Strict JSON

- **OpenAI:** `tool_choice="required"` for REQUIRED; strict JSON when requested.  
- **Gemini:** two‑step when strict JSON: Step‑1 grounded; Step‑2 **no tools**, reshape only; any tools/search in Step‑2 → fail‑closed.  
- **Evidence (normative):** Step‑1 must have a **non‑empty** grounding results set **and** final response must include citations referencing those results. Absence under REQUIRED → fail‑closed.

---

## 9.1 ALS Determinism & Rotation

HMAC seeds keyed by `seed_key_id` and `als.template_id`; rotation adds new key ids without altering existing templates’ outputs; NFC used for length counting only; **limit 350**; fail‑closed if over.

---

## 10) Security & Integrity

Compute `template_sha256` and `record_hmac` **server‑side**; enforce RLS; capture `response_api/provider_api_version` and `provoker_value` in runs.

---

## 11) Observability & Analytics

BigQuery streaming for runs/batches (at‑least‑once). Key metrics include version drift, ALS drift compliance, JSON validity, grounding effectiveness, **output dedup rate** by `response_output_sha256`.

---

## 12) **Seven upgrade‑seam requirements (normative)**

1. **TaskRunner abstraction:** The HTTP layer depends on an internal `TaskRunner` interface. A **CI import‑graph guard** must fail the build if `celery` is imported from any HTTP controller/router.  
2. **DB‑driven orchestration:** `templates/batches/runs` in Postgres are the **source of truth** in both phases; workers read/write the same records.  
3. **Idempotency in Postgres:** Org‑scoped TTL `idempotency_keys` table with 201/200/409 semantics. If Redis mirroring is introduced later, semantics must remain identical.  
4. **Provider cache single‑flight:** Live refresh operations must be serialized (Phase‑1: **Postgres advisory lock**; Phase‑2: **Redis mutex**). API returns `expires_at_utc`, `etag`, `source`.  
5. **Config flags:** `EXECUTION_MODE=sync|celery`, `USE_REDIS=false|true`, and TTL/limit envs. Flipping these must not change hashes or outputs.  
6. **Containerization stance:** Build a platform‑agnostic image; **no Fly‑specific code**. Moving to Fly later requires only deployment changes.  
7. **Invariant‑freezing tests:** CI includes golden vectors for numbers (ROUND_HALF_UP, `-0→0`, no sci‑notation), JSON output hashing (object‑key ordering only; array order preserved), ALS NFC length (≤350), Gemini Step‑2 attestation, SQLite↔Postgres parity, idempotency semantics, and provider cache single‑flight.

---

## 13) Acceptance Criteria (selected)

- Phase‑1/Phase‑2 config flip runs pass without code changes.  
- Import‑guard CI passes (no Celery in HTTP layer).  
- Single‑flight concurrency test shows only one live provider‑version fetch under parallel `force_refresh=true`.  
- Output hashing parity tests pass across languages.  
- Strict JSON & grounding evidence enforcement pass; Gemini Step‑2 attestation stored and validated.
