#!/usr/bin/env python3
"""
CI Guard: Prevent reintroduction of legacy Vertex SDK imports.
This script fails the build if vertexai classic imports are found.
Part of PRD-Adapter-Layer-V1 (Phase-0) migration.
"""
import os
import sys
import re
from pathlib import Path

# Patterns that indicate legacy Vertex SDK usage
FORBIDDEN_PATTERNS = [
    r'import\s+vertexai',
    r'from\s+vertexai\s+import',
    r'from\s+vertexai\.',
    r'google\.cloud\.aiplatform',
    r'vertexai\.generative_models',
    r'vertexai\.init\(',
    # Legacy env flags
    r'VERTEX_USE_GENAI_CLIENT',
    r'ALLOW_GEMINI_DIRECT',
    r'GENAI_AVAILABLE\s*=\s*(True|False)',  # The availability check pattern
]

# Files to check (adapter files only)
ADAPTER_FILES = [
    'app/llm/adapters/vertex_adapter.py',
    'app/llm/adapters/openai_adapter.py',
    'app/llm/unified_llm_adapter.py',
]

def check_file(filepath: Path) -> list:
    """Check a file for forbidden patterns."""
    violations = []
    
    if not filepath.exists():
        return violations
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    for line_num, line in enumerate(lines, 1):
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                # Skip comments
                if line.strip().startswith('#'):
                    continue
                violations.append({
                    'file': str(filepath),
                    'line': line_num,
                    'content': line.strip(),
                    'pattern': pattern
                })
    
    return violations

def main():
    """Main function to run the CI guard."""
    backend_dir = Path(__file__).parent
    violations = []
    
    for adapter_file in ADAPTER_FILES:
        filepath = backend_dir / adapter_file
        file_violations = check_file(filepath)
        violations.extend(file_violations)
    
    if violations:
        print("❌ CI Guard Failed: Legacy Vertex SDK imports detected!")
        print("\nThe following violations were found:")
        print("-" * 60)
        
        for v in violations:
            print(f"File: {v['file']}")
            print(f"Line {v['line']}: {v['content']}")
            print(f"Matched pattern: {v['pattern']}")
            print("-" * 60)
        
        print("\n⚠️  Legacy Vertex SDK has been removed per PRD-Adapter-Layer-V1 (Phase-0)")
        print("Please use only google-genai client for all Vertex/Gemini calls.")
        print("\nRequired imports:")
        print("  from google import genai")
        print("  from google.genai.types import HttpOptions, GenerateContentConfig, Tool, GoogleSearch")
        
        return 1
    
    print("✅ CI Guard Passed: No legacy Vertex SDK imports found in adapters")
    return 0

if __name__ == "__main__":
    sys.exit(main())