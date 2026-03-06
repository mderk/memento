#!/usr/bin/env python3
"""Launcher for the memento-workflow MCP server.

This wrapper enables running the server from any directory while
preserving the relative imports inside the scripts/ package.

Usage (from .mcp.json or claude mcp add):
    python serve.py
"""

import sys
from pathlib import Path

# Ensure the scripts/ package is importable
engine_root = Path(__file__).resolve().parent
if str(engine_root) not in sys.path:
    sys.path.insert(0, str(engine_root))

from scripts.runner import main

if __name__ == "__main__":
    main()
