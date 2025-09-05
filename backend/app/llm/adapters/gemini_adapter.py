"""
gemini_adapter.py
Thin subclass of GoogleBaseAdapter for Direct Gemini.
"""
import os
from typing import Optional
import google.genai as genai
from app.llm.adapters._google_base_adapter import GoogleBaseAdapter

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
GEMINI_GROUNDED_MAX_TOKENS = int(os.getenv("GEMINI_GROUNDED_MAX_TOKENS", "6000"))

class GeminiAdapter(GoogleBaseAdapter):
    def _vendor_key(self) -> str:
        return "gemini_direct"

    def _response_api(self) -> str:
        return "gemini_genai"

    def _init_client(self) -> genai.Client:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY not set")
        return genai.Client(api_key=GEMINI_API_KEY)

    def _normalize_for_validation(self, model: str) -> str:
        m = model
        if m.startswith("publishers/google/models/"):
            return m
        if m.startswith("models/"):
            m = m.split("models/", 1)[1]
        return f"publishers/google/models/{m}"

    def _normalize_for_sdk(self, model: str) -> str:
        m = model
        if m.startswith("publishers/google/models/"):
            m = m.split("publishers/google/models/", 1)[1]
        if m.startswith("models/"):
            m = m.split("models/", 1)[1]
        return f"models/{m}"

    def _region(self) -> Optional[str]:
        return None

    def _grounded_cap(self) -> int:
        return GEMINI_GROUNDED_MAX_TOKENS

    def _ungrounded_cap(self) -> int:
        return GEMINI_MAX_OUTPUT_TOKENS
