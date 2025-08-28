"""
Proxy Circuit Breaker for handling proxy failures
"""
import time
import logging
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Circuit tripped, failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class ProxyCircuitBreaker:
    """Circuit breaker for proxy connections per vendor"""
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 600, window_size: int = 300):
        """
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds before attempting recovery (10 minutes default)
            window_size: Time window for counting failures (5 minutes default)
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._window_size = window_size
        
        # Track state per vendor
        self._vendor_states: Dict[str, Dict] = {}
        
    def _get_vendor_state(self, vendor: str) -> Dict:
        """Get or create state for a vendor"""
        if vendor not in self._vendor_states:
            self._vendor_states[vendor] = {
                'state': CircuitState.CLOSED,
                'failures': [],
                'last_failure_time': 0,
                'open_until': 0,
            }
        return self._vendor_states[vendor]
    
    def record_failure(self, vendor: str, error_message: str) -> None:
        """Record a proxy failure for a vendor"""
        # Check if this is a proxy-related error
        proxy_errors = [
            "Server disconnected",
            "Connection error", 
            "proxy",
            "tunnel",
            "CONNECT",
        ]
        
        is_proxy_error = any(err in error_message for err in proxy_errors)
        if not is_proxy_error:
            return
        
        state = self._get_vendor_state(vendor)
        now = time.time()
        
        # Add failure timestamp
        state['failures'].append(now)
        state['last_failure_time'] = now
        
        # Remove old failures outside window
        cutoff = now - self._window_size
        state['failures'] = [t for t in state['failures'] if t > cutoff]
        
        # Check if we should open the circuit
        if len(state['failures']) >= self._failure_threshold:
            if state['state'] != CircuitState.OPEN:
                state['state'] = CircuitState.OPEN
                state['open_until'] = now + self._recovery_timeout
                logger.warning(
                    f"[CIRCUIT_BREAKER] Opening circuit for {vendor} after {len(state['failures'])} failures"
                )
    
    def should_use_proxy(self, vendor: str, original_policy: str) -> tuple[bool, str]:
        """
        Check if proxy should be used based on circuit state
        
        Returns:
            (should_use_proxy, adjusted_policy)
        """
        # Skip check for non-proxy policies
        if original_policy not in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
            return False, original_policy
        
        state = self._get_vendor_state(vendor)
        now = time.time()
        
        # Check if circuit is open
        if state['state'] == CircuitState.OPEN:
            if now > state['open_until']:
                # Try half-open state
                state['state'] = CircuitState.HALF_OPEN
                logger.info(f"[CIRCUIT_BREAKER] Circuit half-open for {vendor}, testing recovery")
            else:
                # Circuit still open - downgrade to ALS_ONLY
                logger.info(
                    f"[CIRCUIT_BREAKER] Circuit open for {vendor}, downgrading {original_policy} -> ALS_ONLY"
                )
                return False, "ALS_ONLY"
        
        # For Vertex, always downgrade proxy policies until stable
        if vendor == "vertex" and original_policy in ("PROXY_ONLY", "ALS_PLUS_PROXY"):
            logger.info(
                f"[CIRCUIT_BREAKER] Vertex proxy disabled by policy, downgrading {original_policy} -> ALS_ONLY"
            )
            return False, "ALS_ONLY"
        
        # OpenAI: for long outputs, force backbone mode
        # This is handled in the adapter itself
        
        return original_policy != "ALS_ONLY", original_policy
    
    def record_success(self, vendor: str) -> None:
        """Record successful proxy connection"""
        state = self._get_vendor_state(vendor)
        
        # If we were in half-open, close the circuit
        if state['state'] == CircuitState.HALF_OPEN:
            state['state'] = CircuitState.CLOSED
            state['failures'] = []
            logger.info(f"[CIRCUIT_BREAKER] Circuit closed for {vendor} after successful request")


# Global singleton instance
_circuit_breaker = ProxyCircuitBreaker()


def get_circuit_breaker() -> ProxyCircuitBreaker:
    """Get the global circuit breaker instance"""
    return _circuit_breaker