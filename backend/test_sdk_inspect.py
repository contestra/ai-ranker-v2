#!/usr/bin/env python3
"""
Inspect SDK to understand what fields it accepts.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path('.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

from openai import AsyncOpenAI
import inspect

client = AsyncOpenAI()

# Check the create method signature
sig = inspect.signature(client.responses.create)
print("AsyncResponses.create signature:")
print(f"  {sig}")

# Get parameter names
print("\nParameters:")
for param_name, param in sig.parameters.items():
    default = param.default
    default_str = f" = {default}" if default != inspect.Parameter.empty else ""
    print(f"  - {param_name}{default_str}")