# Grounding Implementation Brief — Final v0.1

**TL;DR**
The adapters currently pass a `grounded` flag but do **not** enable web search / grounding. Implement real grounding in both providers, handle known quirks, and report whether grounding actually occurred (`grounded_effective`).

## Migration Path

* **Phase 1:** Implement grounding (this document). **← now**
* **Phase 2:** Frontend indicators (UN/GR) + telemetry surfacing.
* **Phase 3:** Introduce `GroundingMode` enum (breaking change).

## What's wrong today (must fix)

1. **No grounding implementation**

* OpenAI: no `tools` → no browsing.
* Vertex: no `GoogleSearchRetrieval` tool.
* `grounded_effective` mirrors request instead of reality.

2. **Provider quirks to respect**

* **GPT-5 + tools**

  * Temperature **must be 1.0** when tools are enabled.
  * With web search, the usual text path can be empty; content may be in a top-level `text` or in reasoning blocks → implement fallback extraction.
  * Keep `tool_choice="auto"` (avoid `"required"` for now).
* **Gemini (Vertex)**

  * **Structured JSON and GoogleSearch grounding cannot be combined.** If both requested, **fail closed** with a clear error (no silent degrade).
  * Use Google Search via `Tool.from_google_search_retrieval(...)`.
  * **Location** is **env-tunable**: default `"global"`, but if unsupported, switch to a regional endpoint (e.g., `us-central1`, `europe-west4`). Do **not** hard-require `"global"`.

## Modes (v0.1)

* **UN (Ungrounded)** — no web tools.
* **GR (Grounded, auto)** — enable web tools; let the model decide when to search.
  *(A "Forced" mode can be added later as a new enum value.)*

## API & Types (no breaking changes)

* Keep `request.grounded: bool`.
* Prepare for enum (future):

  ```python
  class GroundingMode(str, Enum):
      UN = "UN"
      GR = "GR"
  ```
* Continue returning `grounded_effective` based on **detected usage**, not just the request flag.

---

## File-by-file changes

### 1) `unified_llm_adapter.py`

* If `request.vendor` is missing, infer from model (existing helper) and set it (no silent fallbacks).
* Pass `request.grounded` through unchanged.
* **Timeouts (must be plumbed):**

  ```python
  UNGROUNDED_TIMEOUT = int(os.getenv("LLM_TIMEOUT_UN", "60"))
  GROUNDED_TIMEOUT   = int(os.getenv("LLM_TIMEOUT_GR", "120"))
  timeout = GROUNDED_TIMEOUT if request.grounded else UNGROUNDED_TIMEOUT

  # Pass timeout to provider adapter call
  response = await adapter.complete(request, timeout=timeout)  # use your adapter method name
  ```
* (Optional) Emit telemetry: `grounded_requested` vs `grounded_effective` (computed by the provider adapter).

### 2) `openai_adapter.py` (GPT-5 / Responses API)

**Enable tools when grounded**

```python
if request.grounded:
    tool_type = os.getenv("OPENAI_GROUNDING_TOOL", "web_search")  # e.g., "web_browser"
    params["tools"] = [{"type": tool_type}]
    params["tool_choice"] = os.getenv("OPENAI_TOOL_CHOICE", "auto")
```

**Enforce GPT-5 temperature quirk**
Keep `temperature = 1.0` whenever tools are present (you already enforce this for GPT-5).

**Plumb timeout properly** (pick the style your adapter uses):

```python
# If using AsyncOpenAI and per-call options:
client = client.with_options(timeout=timeout)  # or create with timeout=timeout
resp = await client.responses.create(**params)

# Or if your wrapper supports a per-call timeout kwarg:
resp = await client.responses.create(**params, timeout=timeout)
```

**Robust text extraction (handles "empty with tools")**

```python
# After your normal extraction:
if not output_text and request.grounded:
    # 1) top-level text
    output_text = (response_data.get("text") or "").strip() or output_text

    # 2) reasoning summaries
    if not output_text:
        for item in response_data.get("output", []) or []:
            if item.get("type") == "reasoning":
                summary = item.get("summary") or []
                if summary:
                    output_text = " ".join(s for s in summary if s).strip()
                    break

    if output_text:
        metadata["grounding_extraction_fallback"] = True
```

**Detect whether grounding actually ran**

* Heuristic: if any output item indicates `tool_use`, `tool_result`, `citations`, or similar → `grounded_effective = True`; else `False`.

**Debug logging (sanitized)**

```python
logger.info(
    "OpenAI Grounding: requested=%s effective=%s tool_calls=%s fallback=%s",
    request.grounded, grounded_effective, tool_call_count,
    bool(metadata.get("grounding_extraction_fallback"))
)
# Do NOT log full response bodies
```

### 3) `vertex_adapter.py` (Gemini / Vertex)

**Initialize with env-tunable location**

```python
def __init__(self, project: str | None = None, location: str | None = None):
    self.location = location or os.getenv("VERTEX_LOCATION", "global")
    self.project  = project  or os.getenv("VERTEX_PROJECT", "contestra-ai")
    logger.info("Vertex adapter initialized: project=%s location=%s", self.project, self.location)
    # If "global" is unsupported, switch to a supported region and document it.
```

**Helper: structured output detection**

```python
def is_structured_output(req) -> bool:
    return bool(
        getattr(req, "schema", None) or
        getattr(req, "response_schema", None) or
        getattr(req, "response_mime_type", None) == "application/json"
    )
```

**Guard: structured JSON + grounding is unsupported**

```python
if is_structured_output(request) and request.grounded:
    raise RuntimeError(
        "GROUNDED_JSON_UNSUPPORTED: Gemini cannot combine JSON schema with GoogleSearch grounding. "
        "Choose either grounding OR structured output, not both."
    )
```

**Enable Google Search when grounded**

```python
from vertexai.generative_models import Tool, grounding, GenerativeModel

tools = None
if request.grounded:
    tools = [Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())]

model = GenerativeModel(model_name, tools=tools) if tools else GenerativeModel(model_name)
```

**Plumb timeout properly**

```python
response = model.generate_content(
    contents=...,
    generation_config=...,
    request_options={"timeout": timeout},  # ensure your SDK version supports this
)
```

**Detect whether grounding actually ran (scan ALL candidates)**

```python
grounded_effective = False
tool_call_count = 0
for cand in getattr(response, "candidates", []) or []:
    gm = getattr(cand, "grounding_metadata", None)
    if not gm:
        continue
    web_queries   = getattr(gm, "web_search_queries", []) or []
    chunks        = getattr(gm, "grounding_chunks", []) or []
    entry_point   = getattr(gm, "search_entry_point", None)
    if web_queries or chunks or entry_point:
        grounded_effective = True
        tool_call_count += len(web_queries) if web_queries else 1
        break
```

**Debug logging (sanitized)**

```python
logger.info(
    "Vertex Grounding: requested=%s effective=%s tool_calls=%s location=%s",
    request.grounded, grounded_effective, tool_call_count, self.location
)
# Do NOT log full response bodies
```

---

## Fail-closed & compatibility rules

* **Gemini:** `grounded && structured` → raise `GROUNDED_JSON_UNSUPPORTED` **before** making the API call.
* **OpenAI:** Allow `grounded && json_mode` unless the provider errors; bubble the provider error (no silent downgrades).
* **No re-execution** that changes semantics (immutability). Only extraction may fall back.
* **Timeouts:** env-tunable; default **60s (UN)** / **120s (GR)**, and must actually reach the SDK call.

---

## Acceptance checks (smoke tests)

1. **OpenAI UN vs GR**
   Ask a time-sensitive question. Assert **signals**, not literal content:

   * UN → `grounded_effective=False`, no tool usage indicators.
   * GR → `grounded_effective=True`, tool/citation signals present.
2. **Gemini UN vs GR**

   * UN → no `grounding_metadata`, `grounded_effective=False`.
   * GR → `grounding_metadata` present, `grounded_effective=True`.
3. **Gemini JSON + GR error**

   * Request both; assert `GROUNDED_JSON_UNSUPPORTED` raised **before** API call.
4. **Telemetry**

   * Logs show `grounded_requested` vs `grounded_effective`; GPT-5 shows `grounding_extraction_fallback=True` when used.
5. **Timeouts**

   * UN uses `LLM_TIMEOUT_UN`; GR uses `LLM_TIMEOUT_GR`; verify the timeout is actually applied to the SDK call.

---

## Environment variables

```
# OpenAI
OPENAI_GROUNDING_TOOL=web_search   # or "web_browser"
OPENAI_TOOL_CHOICE=auto            # keep "auto" for v0.1

# Vertex
VERTEX_LOCATION=global             # or "us-central1", "europe-west4" if "global" fails
VERTEX_PROJECT=contestra-ai        # your GCP project

# Timeouts
LLM_TIMEOUT_UN=60                  # seconds for ungrounded
LLM_TIMEOUT_GR=120                 # seconds for grounded
```

---

## Critical Implementation Checklist

* [ ] OpenAI: add `tools=[{"type": tool_type}]` when grounded.
* [ ] OpenAI: fallback text extraction (top-level `text`, then reasoning summaries).
* [ ] OpenAI: detect grounding via response signals (tool_use / citations).
* [ ] OpenAI: actually apply timeout to the Responses call.
* [ ] Vertex: env-tunable location (don't force `"global"`).
* [ ] Vertex: add `Tool.from_google_search_retrieval()` when grounded.
* [ ] Vertex: `is_structured_output()` helper + JSON+GR guard.
* [ ] Vertex: detect grounding via `grounding_metadata` (scan **all** candidates).
* [ ] Both: env-tunable timeouts; log requested vs effective (sanitized).
* [ ] Tests: smoke + unit tests asserting **signals**, not literal content.

---

## Deliverables

* PR touching only: `unified_llm_adapter.py`, `openai_adapter.py`, `vertex_adapter.py`.
* Unit tests:

  * OpenAI grounding detection and extraction fallback.
  * `is_structured_output()` helper.
  * Vertex JSON+GR guard.
* Smoke scripts:

  * `test_openai_grounding.py`: UN + GR cases (assert signals).
  * `test_vertex_grounding.py`: UN + GR + JSON+GR error (assert guard).
  * Log structured metadata only; no full bodies.

---

## Non-Goals / Out of Scope (for clarity)

* "Forced" search mode.
* Any changes to ALS/immutability or public request/response shapes.
* Provider-specific citation rendering in the final text (only detection signals).

---

## Success Criteria

1. Grounding actually works (web search configured and used when requested).
2. `grounded_effective` reflects reality.
3. GPT-5 extraction fallback works; Gemini JSON+grounding fails cleanly.
4. Timeouts respected (120s GR / 60s UN).
5. No breaking changes.
6. Unit + smoke tests pass.

---

## Implementation Notes

This version keeps the original intent, fixes the small API/timeout/location nits, and gives exact drop-in points so nothing gets lost in translation.

**Key Improvements from v0.1:**
- Env-tunable location for Vertex (don't hard-require "global")
- Proper timeout plumbing to SDK calls
- Fail-closed for Gemini JSON+grounding conflict
- Robust text extraction fallback for GPT-5 with tools
- Clear separation of detection vs request flags

---

Last Updated: 2025-01-23
Status: **Ready for Implementation**