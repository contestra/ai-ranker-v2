"""Constants for LLM adapters."""

# Canonical web tool types for telemetry
WEB_TOOL_TYPES = {"google_search", "web_search", "web_search_preview", "none"}

# Default value when no web tool is used
WEB_TOOL_TYPE_NONE = "none"

# Map of vendor-specific tool types to canonical types
WEB_TOOL_TYPE_MAPPING = {
    "google_search": "google_search",
    "GoogleSearch": "google_search",
    "web_search": "web_search", 
    "web_search_preview": "web_search_preview",
    None: "none",
    "": "none"
}