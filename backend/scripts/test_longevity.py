#!/usr/bin/env python3
import os, asyncio, time, re
from typing import Any, Dict, Tuple, List

# If you have a unified router, prefer it:
# from app.llm.unified_llm_adapter import UnifiedLLMAdapter
from app.llm.adapters.openai_adapter import OpenAIAdapter
from app.llm.adapters.vertex_adapter import VertexAdapter
from app.llm.types import LLMRequest  # adjust if your project loc differs

PROMPT = "List the most trusted longevity supplement brands. Return a concise list."

# Keep this small & editable for quick SOV checks
BRANDS = [
    "AVEA", "Moleqlar", "Tally Health", "NOVOS", "Tru Niagen", "ChromaDex",
    "Renue By Science", "DoNotAge", "Thorne", "Life Extension", "Youth & Earth",
]

def norm_text(x: Any) -> str:
    # Accept dict, pydantic, or custom objects
    if isinstance(x, str):
        return x
    for key in ("text", "output_text", "content"):
        if isinstance(x, dict) and x.get(key):
            return str(x[key])
        if hasattr(x, key) and getattr(x, key):
            return str(getattr(x, key))
    return ""

def norm_usage(x: Any) -> Dict[str, int]:
    if isinstance(x, dict):
        return {
            "input_tokens": int(x.get("input_tokens", 0)),
            "output_tokens": int(x.get("output_tokens", 0)),
            "reasoning_tokens": int(x.get("reasoning_tokens", 0)),
        }
    if hasattr(x, "input_tokens") or hasattr(x, "output_tokens"):
        return {
            "input_tokens": int(getattr(x, "input_tokens", 0)),
            "output_tokens": int(getattr(x, "output_tokens", 0)),
            "reasoning_tokens": int(getattr(x, "reasoning_tokens", 0)),
        }
    return {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}

def norm_grounded(resp: Any) -> Tuple[bool, int]:
    ge = False
    tcc = 0
    for k in ("grounded_effective",):
        if isinstance(resp, dict) and k in resp:
            ge = bool(resp[k])
    if hasattr(resp, "grounded_effective"):
        ge = bool(getattr(resp, "grounded_effective"))
    # tool_call_count is optional
    if isinstance(resp, dict):
        tcc = int(resp.get("tool_call_count", 0))
    if hasattr(resp, "tool_call_count"):
        tcc = int(getattr(resp, "tool_call_count"))
    return ge, tcc

def count_brand_mentions(text: str) -> Dict[str, int]:
    hits = {}
    low = text.lower()
    for b in BRANDS:
        n = len(re.findall(r"\b" + re.escape(b.lower()) + r"\b", low))
        if n:
            hits[b] = n
    return hits

async def run_one(vendor: str, model: str, grounded: bool, timeout: int) -> Dict[str, Any]:
    req = LLMRequest(
        vendor=vendor,
        model=model,
        grounded=grounded,
        json_mode=False,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.2,
        max_tokens=6000,
    )
    t0 = time.perf_counter()
    try:
        if vendor == "openai":
            adapter = OpenAIAdapter()
            resp = await adapter.complete(req, timeout=timeout)
        else:
            adapter = VertexAdapter()
            resp = await adapter.complete(req, timeout=timeout)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        text = norm_text(resp)
        usage = norm_usage(getattr(resp, "usage", {}) if hasattr(resp, "usage") else (resp.get("usage", {}) if isinstance(resp, dict) else {}))
        grounded_eff, tool_calls = norm_grounded(resp)
        return {
            "ok": True,
            "vendor": vendor,
            "model": model,
            "grounded_requested": grounded,
            "grounded_effective": grounded_eff,
            "tool_call_count": tool_calls,
            "latency_ms": latency_ms,
            "usage": usage,
            "snippet": text[:600],
            "brand_hits": count_brand_mentions(text),
        }
    except Exception as e:
        return {"ok": False, "vendor": vendor, "model": model, "grounded_requested": grounded, "error": str(e)}

async def main():
    # Timeouts: match your router defaults
    t_un = int(os.getenv("LLM_TIMEOUT_UN", "60"))
    t_gr = int(os.getenv("LLM_TIMEOUT_GR", "180"))  # give grounded extra time
    model_openai = os.getenv("TEST_OPENAI_MODEL", "gpt-5-chat-latest")
    model_vertex = os.getenv("TEST_VERTEX_MODEL", "gemini-2.5-pro")

    combos = [
        ("openai", model_openai, False, t_un),
        ("openai", model_openai, True,  t_gr),
        ("vertex", model_vertex, False, t_un),
        ("vertex", model_vertex, True,  t_gr),
    ]
    print("\n=== LONGEVITY SUPPLEMENT BRANDS — 4-WAY CHECK ===")
    print(f"Prompt: {PROMPT}\n")

    results: List[Dict[str, Any]] = await asyncio.gather(*(run_one(*c) for c in combos))

    for r in results:
        tag = f"{r['vendor']} | grounded={r['grounded_requested']}"
        if not r["ok"]:
            print(f"✗ {tag}: ERROR → {r['error']}")
            continue
        print(f"✓ {tag}: latency={r['latency_ms']}ms, grounded_effective={r['grounded_effective']}, tool_calls={r['tool_call_count']}, tokens(out)={r['usage'].get('output_tokens',0)}")
        if r["brand_hits"]:
            hits = ", ".join(f"{k}({v})" for k,v in r["brand_hits"].items())
            print(f"  brands: {hits}")
        else:
            print("  brands: —")
        print(f"  snippet: {r['snippet']}\n")

if __name__ == "__main__":
    asyncio.run(main())