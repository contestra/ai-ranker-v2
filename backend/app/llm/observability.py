"""
Observability utilities for LLM adapters.
Provides structured logging and metrics emission.
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class LLMMetrics:
    """Centralized metrics collection for LLM operations"""
    
    def __init__(self):
        self.counters = {
            # Adapter-level metrics
            "adapter.requests.total": 0,
            "adapter.requests.grounded": 0,
            "adapter.tools.requested": 0,
            "adapter.tools.used": 0,
            "adapter.citations.anchored": 0,
            "adapter.citations.unlinked": 0,
            
            # Router-level metrics
            "router.required.total": 0,
            "router.required.pass": 0,
            "router.required.fail.no_tool": 0,
            "router.required.fail.no_anchor": 0,
            "router.grounded.effective": 0,
            
            # Error metrics
            "errors.grounding_not_supported": 0,
            "errors.timeout": 0,
            "errors.rate_limit": 0,
        }
        
        self.histograms = {
            "latency.total_ms": [],
            "latency.grounding_ms": [],
            "citations.count": [],
            "tokens.prompt": [],
            "tokens.completion": [],
        }
    
    def increment(self, metric: str, value: int = 1):
        """Increment a counter metric"""
        if metric in self.counters:
            self.counters[metric] += value
            self._emit_metric("counter", metric, self.counters[metric])
    
    def record(self, metric: str, value: float):
        """Record a histogram/gauge metric"""
        if metric in self.histograms:
            self.histograms[metric].append(value)
            self._emit_metric("histogram", metric, value)
    
    def emit_structured_log(self, 
                           event: str,
                           vendor: str,
                           model: str,
                           metadata: Dict[str, Any]):
        """Emit structured log for analysis"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "vendor": vendor,
            "model": model,
            **metadata
        }
        
        logger.info(f"[METRICS] {json.dumps(log_entry)}")
        
    def _emit_metric(self, metric_type: str, name: str, value: Any):
        """Emit metric to monitoring system (stub for integration)"""
        # This would integrate with your monitoring system
        # (Prometheus, Datadog, CloudWatch, etc.)
        pass
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of metrics for dashboard/reporting"""
        return {
            "counters": self.counters.copy(),
            "histograms": {
                k: {
                    "count": len(v),
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0,
                    "avg": sum(v) / len(v) if v else 0
                }
                for k, v in self.histograms.items()
            }
        }

# Global metrics instance
metrics = LLMMetrics()

def log_adapter_request(vendor: str, model: str, grounded: bool, metadata: Dict[str, Any]):
    """Log adapter request with metrics"""
    metrics.increment("adapter.requests.total")
    if grounded:
        metrics.increment("adapter.requests.grounded")
    
    if metadata.get("response_api_tool_type"):
        metrics.increment("adapter.tools.requested")
    
    metrics.emit_structured_log(
        event="adapter.request",
        vendor=vendor,
        model=model,
        metadata={
            "grounded": grounded,
            "grounding_mode": metadata.get("grounding_mode", "AUTO"),
            "tool_type": metadata.get("response_api_tool_type"),
        }
    )

def log_adapter_response(vendor: str, model: str, metadata: Dict[str, Any]):
    """Log adapter response with metrics"""
    if metadata.get("grounding_detected"):
        metrics.increment("adapter.tools.used")
    
    anchored = metadata.get("anchored_citations_count", 0)
    unlinked = metadata.get("unlinked_citations_count", 0)
    
    if anchored > 0:
        metrics.increment("adapter.citations.anchored", anchored)
    if unlinked > 0:
        metrics.increment("adapter.citations.unlinked", unlinked)
    
    metrics.record("citations.count", anchored + unlinked)
    
    if metadata.get("grounded_effective"):
        metrics.increment("router.grounded.effective")
    
    metrics.emit_structured_log(
        event="adapter.response",
        vendor=vendor,
        model=model,
        metadata={
            "tools_used": metadata.get("grounding_detected", False),
            "anchored_citations": anchored,
            "unlinked_citations": unlinked,
            "grounded_effective": metadata.get("grounded_effective", False),
            "latency_ms": metadata.get("latency_ms"),
        }
    )

def log_router_required_enforcement(vendor: str, model: str, passed: bool, reason: Optional[str] = None):
    """Log REQUIRED mode enforcement at router level"""
    metrics.increment("router.required.total")
    
    if passed:
        metrics.increment("router.required.pass")
    else:
        if reason and "no tool" in reason.lower():
            metrics.increment("router.required.fail.no_tool")
        elif reason and "no anchor" in reason.lower():
            metrics.increment("router.required.fail.no_anchor")
    
    metrics.emit_structured_log(
        event="router.required_enforcement",
        vendor=vendor,
        model=model,
        metadata={
            "passed": passed,
            "failure_reason": reason,
        }
    )