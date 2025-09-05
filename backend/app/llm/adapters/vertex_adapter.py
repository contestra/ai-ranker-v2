"""
vertex_adapter.py
Thin subclass of GoogleBaseAdapter for Vertex AI.
"""
import os
from typing import Optional
import google.genai as genai
from app.core.config import settings
from app.llm.adapters._google_base_adapter import GoogleBaseAdapter

VERTEX_PROJECT = os.getenv("VERTEX_PROJECT") or os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or settings.google_cloud_project
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION") or settings.vertex_location or "europe-west4"
VERTEX_MAX_OUTPUT_TOKENS = int(os.getenv("VERTEX_MAX_OUTPUT_TOKENS", "8192"))
VERTEX_GROUNDED_MAX_TOKENS = int(os.getenv("VERTEX_GROUNDED_MAX_TOKENS", "6000"))

class VertexAdapter(GoogleBaseAdapter):
    def _vendor_key(self) -> str:
        return "vertex"

    def _response_api(self) -> str:
        return "vertex_genai"

    def _init_client(self) -> genai.Client:
        if not VERTEX_PROJECT:
            raise ValueError("VERTEX_PROJECT, GCP_PROJECT, or GOOGLE_CLOUD_PROJECT not set")
        return genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)

    def _normalize_for_validation(self, model: str) -> str:
        m = model
        if m.startswith("publishers/google/models/"):
            return m
        if m.startswith("models/"):
            m = m.split("models/", 1)[1]
        return f"publishers/google/models/{m}"

    def _normalize_for_sdk(self, model: str) -> str:
        # Vertex requires the full publishers path
        return self._normalize_for_validation(model)

    def _region(self) -> Optional[str]:
        return VERTEX_LOCATION

    def _grounded_cap(self) -> int:
        return VERTEX_GROUNDED_MAX_TOKENS

    def _ungrounded_cap(self) -> int:
        return VERTEX_MAX_OUTPUT_TOKENS
