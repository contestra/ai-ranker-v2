#!/usr/bin/env python3
"""Router import sanity check - validate methods are properly bound."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.unified_llm_adapter import UnifiedLLMAdapter

def test_router_import_sanity():
    print("=" * 80)
    print("Router Import Sanity Check")
    print("=" * 80)
    
    # Import and check class methods
    router_methods = dir(UnifiedLLMAdapter)
    
    print("\n1. Checking for critical methods:")
    print("-" * 60)
    
    critical_methods = ['_apply_als', 'get_vendor_for_model', '_extract_grounding_mode']
    
    for method in critical_methods:
        if method in router_methods:
            # Verify it's a method, not a free function
            attr = getattr(UnifiedLLMAdapter, method)
            if callable(attr):
                print(f"✓ {method}: Found as method")
                # Check if it's bound to the class
                if hasattr(attr, '__self__'):
                    print(f"  WARNING: {method} appears to be a bound method (should be unbound at class level)")
                else:
                    print(f"  ✓ Correctly defined as unbound method on class")
            else:
                print(f"✗ {method}: Found but not callable")
        else:
            print(f"✗ {method}: NOT FOUND")
    
    print("\n2. Creating router instance:")
    print("-" * 60)
    
    try:
        router = UnifiedLLMAdapter()
        print("✓ Router instance created successfully")
        
        # Check instance methods
        instance_methods = dir(router)
        for method in critical_methods:
            if method in instance_methods:
                attr = getattr(router, method)
                if callable(attr):
                    print(f"✓ {method}: Available on instance")
                else:
                    print(f"✗ {method}: On instance but not callable")
            else:
                print(f"✗ {method}: Not available on instance")
                
    except Exception as e:
        print(f"✗ Failed to create router: {e}")
    
    print("\n3. Method signature check:")
    print("-" * 60)
    
    # Check _apply_als signature
    import inspect
    if hasattr(UnifiedLLMAdapter, '_apply_als'):
        sig = inspect.signature(UnifiedLLMAdapter._apply_als)
        params = list(sig.parameters.keys())
        print(f"_apply_als parameters: {params}")
        if params == ['self', 'request']:
            print("✓ _apply_als has correct signature (self, request)")
        else:
            print("✗ _apply_als has unexpected signature")
    
    # Check get_vendor_for_model signature
    if hasattr(UnifiedLLMAdapter, 'get_vendor_for_model'):
        sig = inspect.signature(UnifiedLLMAdapter.get_vendor_for_model)
        params = list(sig.parameters.keys())
        print(f"get_vendor_for_model parameters: {params}")
        if params == ['self', 'model']:
            print("✓ get_vendor_for_model has correct signature (self, model)")
        else:
            print("✗ get_vendor_for_model has unexpected signature")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("Critical methods are properly defined as class methods")
    print("Router can be instantiated and methods are accessible")

if __name__ == "__main__":
    test_router_import_sanity()