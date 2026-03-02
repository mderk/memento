#!/usr/bin/env python3
"""Entry point for workflow engine. Sets up package context for relative imports."""
import sys
from pathlib import Path

# Add this directory to sys.path so 'scripts' is importable as a package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.runner import main  # noqa: E402

main()
