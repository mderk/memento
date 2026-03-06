#!/usr/bin/env python3
"""
Load shared context files for a protocol step.

Usage:
    python load-context.py <protocol-dir> <step-path>

Examples:
    python load-context.py .protocols/0001-feature 01-setup.md
    python load-context.py .protocols/0001-feature 02-infrastructure/01-database.md

Context resolution:
    Root-level step (01-setup.md):
        _context/*

    Grouped step (02-infrastructure/01-database.md):
        02-infrastructure/_context/*  then  _context/*

Outputs concatenated file contents with headers.
Per-step context belongs inline in the step file's ## Context section.
"""

import sys
from pathlib import Path
from typing import List


def collect_context_files(context_dir: Path) -> List[Path]:
    """Collect all .md files from a _context/ directory, sorted by name."""
    if not context_dir.is_dir():
        return []
    return sorted(f for f in context_dir.iterdir() if f.is_file() and f.suffix == ".md")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <protocol-dir> <step-path>", file=sys.stderr)
        sys.exit(1)

    protocol_dir = Path(sys.argv[1]).resolve()
    step_path = sys.argv[2]

    if not protocol_dir.is_dir():
        print(f"Protocol directory not found: {protocol_dir}", file=sys.stderr)
        sys.exit(1)

    step_file = protocol_dir / step_path
    if not step_file.is_file():
        print(f"Step file not found: {step_file}", file=sys.stderr)
        sys.exit(1)

    files: List[Path] = []
    step_parts = Path(step_path).parts

    # Group context (if step is in a group folder)
    if len(step_parts) > 1:
        group_context = protocol_dir / step_parts[0] / "_context"
        files.extend(collect_context_files(group_context))

    # Protocol-wide context
    files.extend(collect_context_files(protocol_dir / "_context"))

    if not files:
        print("No context files found.")
        sys.exit(0)

    for f in files:
        rel = f.relative_to(protocol_dir)
        print(f"── {rel} ──")
        print(f.read_text(encoding="utf-8"))
        print()


if __name__ == "__main__":
    main()
