#!/usr/bin/env python3
"""
CI Guard for OpenAI Adapter - Prevents reintroduction of banned patterns.
Run this in CI to ensure the lean adapter stays lean.
"""
import sys
from pathlib import Path


def check_banned_patterns(file_path: Path) -> list:
    """Check for banned patterns in the adapter."""
    
    # Patterns that should never appear in the lean adapter
    banned_patterns = [
        # Custom HTTP/session management
        ("httpx", "Custom HTTP client - SDK should handle transport"),
        ("aiohttp", "Custom HTTP client - SDK should handle transport"),
        ("requests", "Sync HTTP client - use SDK async client"),
        
        # Custom retry/backoff/rate limiting
        ("CircuitBreaker", "Circuit breaker pattern - SDK handles failures"),
        ("RateLimiter", "Rate limiter - SDK handles rate limits"),
        ("BackoffManager", "Backoff manager - SDK handles retries"),
        ("_retry_with_backoff", "Custom retry logic - SDK handles retries"),
        ("exponential_backoff", "Custom backoff - SDK handles backoff"),
        
        # Health checks
        ("HealthCheck", "Health check - not needed with SDK"),
        ("_health_check", "Health check method - SDK manages connection"),
        ("health_check_done", "Health check state - unnecessary"),
        
        # Streaming (should use Responses API)
        ("stream=True", "Streaming mode - use Responses API"),
        ("async for chunk", "Stream iteration - use Responses API"),
        ("iter_lines", "Line iteration - use Responses API"),
        ("SSE", "Server-sent events - use Responses API"),
        
        # Chat Completions (should use Responses API)
        ("chat.completions", "Chat Completions API - use Responses API"),
        ("ChatCompletion", "Chat Completions type - use Responses API"),
        ("_call_chat_api", "Chat API method - use Responses API"),
        ("_call_with_streaming", "Streaming method - use Responses API"),
        
        # Session management
        ("Session", "Session management - SDK handles sessions"),
        ("session_pool", "Session pooling - SDK manages connections"),
        ("connection_pool", "Connection pooling - SDK manages connections"),
        
        # Complex state management
        ("global _", "Global state - avoid global state"),
        ("threading.Lock", "Thread locks - unnecessary complexity"),
        ("asyncio.Lock", "Async locks - unnecessary complexity"),
    ]
    
    violations = []
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')
            
        for pattern, reason in banned_patterns:
            for line_num, line in enumerate(lines, 1):
                if pattern in line and not line.strip().startswith('#'):
                    violations.append({
                        'pattern': pattern,
                        'reason': reason,
                        'line': line_num,
                        'content': line.strip()
                    })
    
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
    
    return violations


def main():
    """Main CI guard entry point."""
    adapter_path = Path(__file__).parent / "app" / "llm" / "adapters" / "openai_adapter.py"
    
    if not adapter_path.exists():
        print(f"Error: Adapter not found at {adapter_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("CI GUARD: Checking OpenAI Adapter for Banned Patterns")
    print("=" * 60)
    print(f"Checking: {adapter_path}")
    
    violations = check_banned_patterns(adapter_path)
    
    if violations:
        print("\n❌ BANNED PATTERNS DETECTED:")
        print("-" * 60)
        for v in violations:
            print(f"\nLine {v['line']}: {v['pattern']}")
            print(f"  Reason: {v['reason']}")
            print(f"  Code: {v['content'][:80]}...")
        
        print("\n" + "=" * 60)
        print("FAILED: Adapter contains banned patterns!")
        print("The adapter must remain lean and delegate to SDK.")
        print("=" * 60)
        sys.exit(1)
    else:
        print("\n✅ No banned patterns found")
        print("The adapter remains lean and properly uses SDK.")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()