#!/usr/bin/env python3
# ruff: noqa: E501, T201
"""Collect development result artifact for protocol mode.

Computes files_changed from git, merges findings from explore+plan structured
outputs (passed via env vars to avoid shell quoting), writes DevelopResult JSON
to both stdout and a file for parent workflow consumption.
Output path is specified via --output (required).

Usage:
    EXPLORE_FINDINGS='[...]' PLAN_FINDINGS='[...]' \
    python collect-result.py --workdir /path/to/worktree --output /tmp/result.json
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_files_changed(workdir: str) -> list[str]:
    """Get changed files from git diff in the given workdir."""
    try:
        result = subprocess.run(  # noqa: PLW1510 — check returncode manually
            ["git", "diff", "--name-only", "HEAD"],  # noqa: S607 — git is a trusted binary
            capture_output=True, text=True, timeout=30, cwd=workdir,
        )
        files = [f for f in result.stdout.strip().splitlines() if f]
        # Also staged files
        result2 = subprocess.run(  # noqa: PLW1510 — check returncode manually
            ["git", "diff", "--name-only", "--cached"],  # noqa: S607 — git is a trusted binary
            capture_output=True, text=True, timeout=30, cwd=workdir,
        )
        files.extend(f for f in result2.stdout.strip().splitlines() if f and f not in files)
        return files
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _parse_findings_env(env_var: str) -> list[dict]:
    """Parse findings from an environment variable (JSON array or empty)."""
    raw = os.environ.get(env_var, "")
    if not raw or raw.startswith("{{"):
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _parse_json_env(env_var: str):
    """Parse JSON from an environment variable, or return None.

    The workflow engine leaves unresolved templates as '{{...}}', which we ignore.
    """
    raw = os.environ.get(env_var, "")
    if not raw or raw.startswith("{{"):
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description="Collect development result")
    parser.add_argument("--workdir", default=os.getcwd(), help="Working directory for git operations")
    parser.add_argument("--output", required=True, help="Path to write result JSON")
    args = parser.parse_args()

    workdir = args.workdir
    # Validate workdir
    if workdir.startswith("{{") or not Path(workdir).is_dir():
        workdir = os.getcwd()

    files_changed = get_files_changed(workdir)

    # Merge findings from explore and plan steps (passed via env vars)
    findings: list[dict] = []
    findings.extend(_parse_findings_env("EXPLORE_FINDINGS"))
    findings.extend(_parse_findings_env("PLAN_FINDINGS"))

    verify_custom = _parse_json_env("VERIFY_CUSTOM")
    verify_lint = _parse_json_env("VERIFY_AFTER_CUSTOM_LINT")
    verify_test = _parse_json_env("VERIFY_AFTER_CUSTOM_TEST")
    acceptance = _parse_json_env("ACCEPTANCE_RESULT")

    custom_ok = True
    if isinstance(verify_custom, dict):
        custom_ok = verify_custom.get("status") == "pass"
    elif verify_custom is not None:
        custom_ok = False

    verify_fix_ok = True
    if verify_lint is not None or verify_test is not None:
        if isinstance(verify_lint, dict) and isinstance(verify_test, dict):
            lint_ok = verify_lint.get("status") in ("clean", "skipped")
            test_ok = verify_test.get("status") == "green"
            verify_fix_ok = lint_ok and test_ok
        else:
            verify_fix_ok = False

    acceptance_ok = True
    if isinstance(acceptance, dict):
        acceptance_ok = acceptance.get("passed", True) is True
    elif acceptance is not None:
        acceptance_ok = False

    passed = custom_ok and verify_fix_ok and acceptance_ok

    result = {
        "summary": (
            f"Completed development: {len(files_changed)} files changed"
            if passed
            else f"Development incomplete: verification failed ({len(files_changed)} files changed)"
        ),
        "passed": passed,
        "files_changed": files_changed,
        "findings": findings,
        "checks": {
            "verify_custom": verify_custom,
            "verify_fix": {
                "lint": verify_lint,
                "test": verify_test,
            },
            "acceptance": acceptance,
        },
    }

    # Write to file for parent workflow consumption (subagent isolation boundary)
    if args.output.startswith("{{"):
        print("ERROR: --output contains unresolved template: " + args.output, file=sys.stderr)
        sys.exit(1)
    result_path = Path(args.output)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Also output to stdout for ShellStep result_var
    json.dump(result, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
