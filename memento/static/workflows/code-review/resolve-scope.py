#!/usr/bin/env python3
"""Resolve review scope: normalize user-provided scope to three-dot.

Usage: python resolve-scope.py [scope]

Behavior:
- Empty scope                        → "" (uncommitted + staged changes)
- Two-dot range (A..B)               → "A...B"
- Three-dot range (A...B)            → pass through
- Bare ref (origin/dev)              → "origin/dev...HEAD"

Outputs a JSON string with the resolved scope.
"""

import json
import sys


def main() -> None:
    scope = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""

    # Empty scope → uncommitted changes
    if not scope:
        json.dump(scope, sys.stdout)
        return

    # Already three-dot → pass through
    if "..." in scope:
        json.dump(scope, sys.stdout)
        return

    # Two-dot (A..B) → three-dot (A...B)
    if ".." in scope:
        json.dump(scope.replace("..", "...", 1), sys.stdout)
        return

    # Bare ref → three-dot with HEAD
    if not scope.startswith("-"):
        json.dump(f"{scope}...HEAD", sys.stdout)
        return

    json.dump(scope, sys.stdout)


if __name__ == "__main__":
    main()
