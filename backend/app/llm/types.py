"""
LLM adapter types for AI Ranker V2
Phase-0 implementation: FastAPI + Neon only
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class VantagePolicy(str, Enum):
    """Geographic vantage point policy for experimental control"""
    NONE = "NONE"                      # Direct connection, no ALS, no proxy (control)
    ALS_ONLY = "ALS_ONLY"              # Add ALS context, direct connection
    PROXY_ONLY = "PROXY_ONLY"          # Use proxy, no ALS context
    ALS_PLUS_PROXY = "ALS_PLUS_PROXY" # Both proxy and ALS context


@dataclass
class LLMRequest:
    """Unified request format for all LLM providers
    
    IMPORTANT CONTRACT - Meta vs Metadata:
    ======================================
    This class uses 'meta' for user configuration, while 'metadata' (added dynamically)
    is for router internal state. DO NOT CONFUSE THEM!
    
    request.meta: User-provided tuning knobs (grounding_mode, json_schema, reasoning_effort)
    request.metadata: Router-computed state (capabilities, thinking_budget_tokens, als_*)
    
    See app/llm/request_contract.py for full documentation and helper methods.
    """
    vendor: str                        # "openai" | "vertex"
    model: str                         # e.g., "gpt-4o", "gemini-1.5-pro"
    messages: List[Dict[str, str]]     # Message array
    grounded: bool = False             # Enable web search/grounding
    json_mode: bool = False            # Strict JSON output
    als_context: Optional[Dict] = None # ALS (Ambient Location Signals)
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    seed: Optional[int] = None
    tools: Optional[List[Dict]] = None # Tool definitions for function calling
    timeout_seconds: int = 60
    
    # Vantage policy for proxy/ALS control
    vantage_policy: Optional[VantagePolicy] = None
    country_code: Optional[str] = None  # ISO country code (e.g., "US", "DE", "GB")
    
    # USER CONFIGURATION (set by API caller, read by adapters)
    # Fields: grounding_mode, json_schema, reasoning_effort, reasoning_summary,
    #         thinking_budget, include_thoughts
    meta: Optional[Dict[str, Any]] = None  # User tuning knobs - DO NOT MODIFY in router/adapters!
    
    # Template tracking
    template_id: Optional[str] = None
    run_id: Optional[str] = None


@dataclass
class LLMResponse:
    """Unified response format from all LLM providers"""
    content: str                              # The actual response text
    model_version: str                        # Effective model version used
    model_fingerprint: Optional[str] = None   # OpenAI system_fingerprint or Vertex modelVersion
    grounded_effective: bool = False          # Whether grounding was actually used
    citations: Optional[List[Dict]] = None    # Grounding citations if available
    usage: Dict[str, int] = None             # Token usage stats
    latency_ms: int = 0                      # Response latency
    raw_response: Dict = None                 # Original provider response
    
    # Error tracking
    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    # Metadata
    vendor: Optional[str] = None
    model: Optional[str] = None
    timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.usage is None:
            self.usage = {}


@dataclass
class GroundingSource:
    """Represents a single grounding source/citation"""
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    source_id: Optional[str] = None


@dataclass
class ALSContext:
    """Ambient Location Signals context"""
    locale: str                    # e.g., "en-US", "de-DE"
    country_code: str              # e.g., "US", "DE"
    als_block: str                 # The formatted ALS text block
    als_variant_id: Optional[str] = None
    seed_key_id: Optional[str] = None  # Will be set by router using ALSConfig