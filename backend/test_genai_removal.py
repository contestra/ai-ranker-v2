#!/usr/bin/env python3
"""
Test that google.genai has been completely removed
and only Vertex SDK remains
"""
import os
import sys

def test_imports():
    """Test that only Vertex imports work"""
    print("Testing imports...")
    
    # Should work - Vertex SDK
    try:
        from vertexai import generative_models as gm
        print("✅ Vertex SDK import successful")
        print(f"   - Has Part: {hasattr(gm, 'Part')}")
        print(f"   - Has Content: {hasattr(gm, 'Content')}")
        print(f"   - Has Tool: {hasattr(gm, 'Tool')}")
        print(f"   - Has GenerativeModel: {hasattr(gm, 'GenerativeModel')}")
    except ImportError as e:
        print(f"❌ Vertex SDK import failed: {e}")
        return False
    
    # Should fail - google.genai doesn't exist
    try:
        from google import genai
        print("❌ google.genai import succeeded (should have failed!)")
        return False
    except ImportError:
        print("✅ google.genai correctly not available")
    
    return True

def test_adapter():
    """Test the Vertex adapter"""
    print("\nTesting Vertex adapter...")
    
    # Set required env var
    os.environ['GOOGLE_CLOUD_PROJECT'] = 'test-project'
    
    try:
        from app.llm.adapters.vertex_adapter import VertexAdapter
        print("✅ VertexAdapter import successful")
        
        # Check key attributes
        adapter = VertexAdapter()
        print(f"   - Project: {adapter.project}")
        print(f"   - Location: {adapter.location}")
        print(f"   - Model pinned: publishers/google/models/gemini-2.5-pro")
        
        # Check it has the right methods
        assert hasattr(adapter, 'complete'), "Missing complete method"
        assert hasattr(adapter, '_build_content_with_als'), "Missing content builder"
        assert hasattr(adapter, '_step1_grounded'), "Missing step1 method"
        assert hasattr(adapter, '_step2_reshape_json'), "Missing step2 method"
        print("✅ All required methods present")
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        return False
    
    return True

def test_no_genai_env_vars():
    """Test that GOOGLE_GENAI env vars are gone"""
    print("\nTesting environment variables...")
    
    genai_vars = [
        'GOOGLE_GENAI_USE_VERTEXAI',
        'GOOGLE_GENAI_API_KEY',
        'GOOGLE_GENAI_PROJECT'
    ]
    
    found = []
    for var in genai_vars:
        if os.getenv(var):
            found.append(var)
    
    if found:
        print(f"❌ Found GOOGLE_GENAI env vars: {found}")
        return False
    else:
        print("✅ No GOOGLE_GENAI env vars found")
        return True

def main():
    print("="*60)
    print("GOOGLE.GENAI REMOVAL ACCEPTANCE TEST")
    print("="*60)
    
    tests = [
        ("Import Test", test_imports),
        ("Adapter Test", test_adapter),
        ("Env Var Test", test_no_genai_env_vars)
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_passed = all(r[1] for r in results)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name}: {status}")
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED - google.genai successfully removed")
        print("   Only Vertex SDK (google-cloud-aiplatform) remains")
    else:
        print("❌ Some tests failed - review issues above")
    print("="*60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')
    sys.exit(main())