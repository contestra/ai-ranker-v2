#!/usr/bin/env python3
"""
Test lean Gemini and Vertex adapters - verify they work and are much smaller.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")


async def test_gemini_lean():
    """Test lean Gemini adapter."""
    print("\n" + "="*60)
    print("GEMINI LEAN ADAPTER TEST")
    print("="*60)
    
    from app.llm.adapters.gemini_adapter_lean import GeminiAdapter
    from app.llm.types import LLMRequest
    
    adapter = GeminiAdapter()
    
    # Test 1: Simple ungrounded
    print("\n[Test 1: Simple ungrounded]")
    request = LLMRequest(
        vendor="gemini_direct",
        model="publishers/google/models/gemini-2.5-pro",  # Use allowed model
        messages=[{"role": "user", "content": "What is 2+2?"}],
        grounded=False,
        max_tokens=50
    )
    
    try:
        response = await adapter.complete(request, timeout=30)
        print(f"✅ Success: {response.success}")
        print(f"Response: {response.content[:100]}")
        print(f"Latency: {response.latency_ms}ms")
        assert response.success is True
        assert "4" in response.content
    except Exception as e:
        print(f"❌ Error: {str(e)[:200]}")
        return False
    
    # Test 2: Grounded AUTO mode
    print("\n[Test 2: Grounded AUTO mode]")
    request2 = LLMRequest(
        vendor="gemini_direct",
        model="publishers/google/models/gemini-2.5-pro",
        messages=[{"role": "user", "content": "What is the current weather in Paris?"}],
        grounded=True,
        max_tokens=200,
        meta={"grounding_mode": "AUTO"}
    )
    
    try:
        response2 = await adapter.complete(request2, timeout=30)
        print(f"✅ Success: {response2.success}")
        print(f"Grounded effective: {response2.grounded_effective}")
        print(f"Citations: {len(response2.citations) if response2.citations else 0}")
        print(f"Response: {response2.content[:200]}")
        assert response2.success is True
    except Exception as e:
        print(f"❌ Error: {str(e)[:200]}")
        return False
    
    # Test 3: Flash model allowed through Direct API
    print("\n[Test 3: Flash model through Direct API]")
    request3 = LLMRequest(
        vendor="gemini_direct",
        model="publishers/google/models/gemini-2.0-flash",
        messages=[{"role": "user", "content": "What is 5+5?"}],
        grounded=False,
        max_tokens=50
    )
    
    try:
        response3 = await adapter.complete(request3, timeout=30)
        print(f"✅ Flash model allowed: {response3.success}")
        print(f"Response: {response3.content[:100]}")
        assert response3.success is True
    except Exception as e:
        print(f"❌ Error: {str(e)[:200]}")
        return False
    
    print("\n✅ All Gemini tests passed")
    return True


async def test_vertex_lean():
    """Test lean Vertex adapter."""
    print("\n" + "="*60)
    print("VERTEX LEAN ADAPTER TEST")
    print("="*60)
    
    from app.llm.adapters.vertex_adapter_lean import VertexAdapter
    from app.llm.types import LLMRequest
    
    adapter = VertexAdapter()
    
    # Test 1: Simple ungrounded with flash
    print("\n[Test 1: Simple ungrounded with flash]")
    request = LLMRequest(
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",
        messages=[{"role": "user", "content": "What is 3+3?"}],
        grounded=False,
        max_tokens=50
    )
    
    try:
        response = await adapter.complete(request, timeout=30)
        print(f"✅ Success: {response.success}")
        print(f"Response: {response.content[:100]}")
        print(f"Latency: {response.latency_ms}ms")
        assert response.success is True
        assert "6" in response.content
    except Exception as e:
        print(f"❌ Error: {str(e)[:200]}")
        return False
    
    # Test 2: Grounded with ALS
    print("\n[Test 2: Grounded with ALS]")
    request2 = LLMRequest(
        vendor="vertex",
        model="publishers/google/models/gemini-2.0-flash",
        messages=[{"role": "user", "content": "What are the top news stories today?"}],
        grounded=True,
        max_tokens=500,
        meta={"grounding_mode": "AUTO"},
        als_context={"country_code": "DE", "locale": "de-DE"}
    )
    
    try:
        response2 = await adapter.complete(request2, timeout=30)
        print(f"✅ Success: {response2.success}")
        print(f"Grounded effective: {response2.grounded_effective}")
        print(f"Citations: {len(response2.citations) if response2.citations else 0}")
        print(f"Response length: {len(response2.content)} chars")
        assert response2.success is True
    except Exception as e:
        print(f"❌ Error: {str(e)[:200]}")
        return False
    
    print("\n✅ All Vertex tests passed")
    return True


async def test_size_comparison():
    """Compare original vs lean adapter sizes."""
    print("\n" + "="*60)
    print("SIZE COMPARISON")
    print("="*60)
    
    import subprocess
    
    adapters = [
        ("Gemini original", "app/llm/adapters/gemini_adapter.py"),
        ("Gemini lean", "app/llm/adapters/gemini_adapter_lean.py"),
        ("Vertex original", "app/llm/adapters/vertex_adapter.py"),
        ("Vertex lean", "app/llm/adapters/vertex_adapter_lean.py"),
    ]
    
    for name, path in adapters:
        try:
            result = subprocess.run(['wc', '-l', path], capture_output=True, text=True)
            lines = int(result.stdout.split()[0])
            print(f"{name:20} {lines:5} lines")
        except Exception as e:
            print(f"{name:20} Error: {e}")
    
    # Calculate reduction
    try:
        gemini_orig = int(subprocess.run(['wc', '-l', 'app/llm/adapters/gemini_adapter.py'], 
                                        capture_output=True, text=True).stdout.split()[0])
        gemini_lean = int(subprocess.run(['wc', '-l', 'app/llm/adapters/gemini_adapter_lean.py'], 
                                        capture_output=True, text=True).stdout.split()[0])
        vertex_orig = int(subprocess.run(['wc', '-l', 'app/llm/adapters/vertex_adapter.py'], 
                                        capture_output=True, text=True).stdout.split()[0])
        vertex_lean = int(subprocess.run(['wc', '-l', 'app/llm/adapters/vertex_adapter_lean.py'], 
                                        capture_output=True, text=True).stdout.split()[0])
        
        gemini_reduction = ((gemini_orig - gemini_lean) / gemini_orig) * 100
        vertex_reduction = ((vertex_orig - vertex_lean) / vertex_orig) * 100
        total_removed = (gemini_orig - gemini_lean) + (vertex_orig - vertex_lean)
        
        print(f"\nGemini reduction: {gemini_reduction:.1f}% ({gemini_orig - gemini_lean} lines removed)")
        print(f"Vertex reduction: {vertex_reduction:.1f}% ({vertex_orig - vertex_lean} lines removed)")
        print(f"Total lines removed: {total_removed}")
    except:
        pass


async def main():
    """Run all tests."""
    print("="*60)
    print("LEAN ADAPTER TEST SUITE")
    print("="*60)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    
    # Size comparison first
    await test_size_comparison()
    
    # Test adapters
    gemini_ok = await test_gemini_lean()
    vertex_ok = await test_vertex_lean()
    
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(f"Gemini Lean: {'✅ PASS' if gemini_ok else '❌ FAIL'}")
    print(f"Vertex Lean: {'✅ PASS' if vertex_ok else '❌ FAIL'}")
    
    if gemini_ok and vertex_ok:
        print("\n✅ ALL TESTS PASSED - Lean adapters ready for deployment")
        return True
    else:
        print("\n❌ SOME TESTS FAILED - Review before deployment")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)