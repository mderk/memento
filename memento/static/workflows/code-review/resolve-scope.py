#!/usr/bin/env python3
"""Resolve review scope: auto-detect base branch, normalize to three-dot.

Usage: python resolve-scope.py [scope]

Behavior:
- Empty scope + on non-default branch → "origin/<default>...HEAD"
- Empty scope + on default branch     → "" (uncommitted changes)
- Two-dot range (A..B)                → "A...B"
- Three-dot range (A...B)             → pass through
- Bare ref (origin/dev)               → "origin/dev...HEAD"

Outputs a JSON string with the resolved scope.
"""

import json
import subprocess
import sys


def run(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


def detect_default_branch() -> str:
    """Detect the default branch (main or master)."""
    remote_head = run("git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null")
    if remote_head:
        return remote_head.split("/")[-1]
    # Fallback: check if main or master exists
    for branch in ("main", "master", "develop", "dev"):
        if run(f"git rev-parse --verify origin/{branch} 2>/dev/null"):
            return branch
    return "main"


def current_branch() -> str:
    return run("git branch --show-current")


def main() -> None:
    scope = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""

    # Empty scope: auto-detect
    if not scope:
        branch = current_branch()
        default = detect_default_branch()
        if branch and branch != default:
            scope = f"origin/{default}...HEAD"
        # else: empty → uncommitted changes
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
