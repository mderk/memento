#!/usr/bin/env python3
# ruff: noqa: E501, T201
"""Development workflow shell tool.

Reads project-analysis.json for commands, runs lint/test/typecheck,
parses output into compact JSON for the workflow engine.

Usage:
    python dev-tools.py test [--scope all|changed|specific] [--files FILE...]
    python dev-tools.py lint [--scope all|changed]
    python dev-tools.py typecheck
    python dev-tools.py commands
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_LOG_DIR = Path("/tmp/memento-dev-tools")  # noqa: S108 — debug log dir, not sensitive


def compact_output(text: str, max_lines: int = 60, label: str = "output") -> str:
    """Strip ANSI codes and apply head/tail truncation.

    When output exceeds max_lines, saves the full text to a log file
    and returns head + tail with a truncation marker including the path.
    """
    text = _ANSI_RE.sub("", text)
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / f"{label}-{os.getpid()}.log"
    log_file.write_text("\n".join(lines), encoding="utf-8")
    head_n = max_lines // 4
    tail_n = max_lines - head_n
    truncated = len(lines) - head_n - tail_n
    return "\n".join(
        lines[:head_n]
        + [f"... ({truncated} lines truncated, full output: {log_file}) ..."]
        + lines[-tail_n:]
    )


def _resolve_workdir(workdir: str | None) -> str | None:
    """Resolve workdir from arg, env var, or None (use cwd).

    Handles unresolved template strings (e.g. '{{variables.workdir}}')
    by falling back to None.
    """
    if workdir and workdir.startswith("{{"):
        workdir = None
    if not workdir:
        workdir = os.environ.get("DEV_TOOLS_WORKDIR")
    if workdir and workdir.startswith("{{"):
        workdir = None
    if workdir and not Path(workdir).is_dir():
        workdir = None
    return workdir


def _adjust_paths_for_cd(cmd: str, files: list[str]) -> list[str]:
    """Adjust file paths when the command starts with 'cd <dir> &&'.

    Git returns paths relative to repo root. When the test/lint command
    changes into a subdirectory first, file paths must be made relative
    to that subdirectory. Files outside the target dir are excluded.
    """
    cd_match = re.match(r"cd\s+(\S+)\s*&&", cmd)
    if not cd_match:
        return files
    cd_dir = cd_match.group(1).rstrip("/")
    adjusted = []
    for f in files:
        if f.startswith(cd_dir + "/"):
            adjusted.append(f[len(cd_dir) + 1:])
    return adjusted


def _load_analysis(workdir: str | None = None) -> dict:
    """Load full project-analysis.json data.

    Handles both formats:
      - {"commands": {...}, ...}  (top-level)
      - {"status": "success", "data": {"commands": {...}, ...}}  (detect.py output)
    """
    base = Path(workdir) if workdir else Path.cwd()
    for candidate in [
        base / ".memory_bank" / "project-analysis.json",
        base / "project-analysis.json",
        # Fallback to engine cwd if workdir doesn't have it
        Path(".memory_bank/project-analysis.json"),
        Path("project-analysis.json"),
    ]:
        if candidate.exists():
            data = json.loads(candidate.read_text())
            return data.get("data") or data
    return {}


def load_commands(workdir: str | None = None) -> dict:
    """Load commands from project-analysis.json."""
    return _load_analysis(workdir).get("commands", {})


# File extensions a test runner accepts as path arguments (avoid pytest + .ts, etc.)
_TEST_RUNNER_EXTS: dict[str, tuple[str, ...]] = {
    "pytest": (".py",),
    "jest":   (".js", ".jsx", ".ts", ".tsx"),
    "vitest": (".js", ".jsx", ".ts", ".tsx"),
}

_TOOL_EXTS: dict[str, tuple[str, ...]] = {
    "ruff":     (".py",),
    "flake8":   (".py",),
    "black":    (".py",),
    "autopep8": (".py",),
    "mypy":     (".py",),
    "pyright":  (".py",),
    "pylint":   (".py",),
    "eslint":   (".js", ".jsx", ".ts", ".tsx"),
    "tsc":      (".ts", ".tsx"),
    "biome":    (".js", ".jsx", ".ts", ".tsx", ".json", ".jsonc", ".css"),
    "prettier": (".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".less",
                 ".html", ".vue", ".svelte", ".json", ".yaml", ".yml",
                 ".md", ".mdx", ".graphql"),
}


def _exts_for_command(cmd: str) -> tuple[str, ...] | None:
    """Return file extensions the tool supports, or None if unknown (don't filter)."""
    for p in cmd.split():
        if p in ("uv", "run", "npx", "npm", "pnpm", "yarn", "bunx", "bun", "python", "-m"):
            continue
        tool = p.split("/")[-1].split("@")[0]
        for name, exts in _TOOL_EXTS.items():
            if tool.startswith(name):
                return exts
        return None  # unknown tool — don't filter
    return None


def get_changed_files(ext: str | None = None, workdir: str | None = None) -> list[str]:
    """Get changed files from git (staged + unstaged)."""
    cwd = workdir or os.getcwd()
    result = subprocess.run(  # noqa: PLW1510 — check returncode manually
        ["git", "diff", "--name-only", "HEAD"],  # noqa: S607 — git is a trusted binary
        capture_output=True, text=True, timeout=30, cwd=cwd,
    )
    files = [f for f in result.stdout.strip().splitlines() if f]
    # Also staged files
    result2 = subprocess.run(  # noqa: PLW1510 — check returncode manually
        ["git", "diff", "--name-only", "--cached"],  # noqa: S607 — git is a trusted binary
        capture_output=True, text=True, timeout=30, cwd=cwd,
    )
    files.extend(f for f in result2.stdout.strip().splitlines() if f and f not in files)
    if ext:
        files = [f for f in files if f.endswith(ext)]
    return files


def run_command(cmd: str, extra_args: str = "", timeout: int = 300, workdir: str | None = None) -> dict:
    """Run a shell command and return structured result."""
    full_cmd = f"{cmd} {extra_args}".strip()
    cwd = workdir or os.getcwd()
    try:
        result = subprocess.run(  # noqa: PLW1510, S602 — shell=True needed for pipes/redirects in lint commands
            full_cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"Command timed out after {timeout}s"}


def parse_pytest_output(raw: dict) -> dict:  # noqa: C901 — inherent complexity of output parsing
    """Parse pytest output into structured result."""
    output = raw["stdout"] + raw["stderr"]
    result = {
        "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
        "failures": [], "summary": "",
    }

    # Parse summary line: "5 passed, 2 failed, 1 error in 3.45s"
    # Verbose: "===== 5 passed in 3.45s =====" / Quiet (-q): "5 passed in 3.45s"
    # Use findall + take last to skip section headers like "= FAILURES ="
    summary_match = None
    for m in re.finditer(r"=+ (\d+.*?\bin [\d.]+s) =+\s*$", output, re.MULTILINE):
        summary_match = m
    if not summary_match:
        # Quiet mode: bare "N passed, M failed in Xs" without ===== delimiters
        summary_match = re.search(
            r"^(\d+ (?:passed|failed|error).*?\bin \d+[\d.]*s)\s*$", output, re.MULTILINE,
        )
    if summary_match:
        result["summary"] = summary_match.group(1)
        counts = re.findall(r"(\d+) (passed|failed|error|skipped|warnings?)", summary_match.group(1))
        for count, kind in counts:
            if kind == "passed":
                result["passed"] = int(count)
            elif kind == "failed":
                result["failed"] = int(count)
            elif kind == "error":
                result["errors"] = int(count)
            elif kind == "skipped":
                result["skipped"] = int(count)

    # Extract failure details (FAILED lines)
    for match in re.finditer(r"FAILED ([\w/.:]+(?:::[\w]+)*)", output):
        result["failures"].append(match.group(1))

    # Extract failure excerpt from FAILURES/ERRORS section
    if result["failed"] > 0 or result["errors"] > 0:
        lines = output.splitlines()
        fail_start = None
        for i, line in enumerate(lines):
            if "= FAILURES =" in line or "= ERRORS =" in line:
                fail_start = i
                break
        if fail_start is not None:
            failure_text = "\n".join(lines[fail_start:])
            result["failure_excerpt"] = compact_output(
                failure_text, max_lines=60, label="pytest-failures",
            )

    if raw["exit_code"] == 0:
        result["status"] = "green"
    elif result["failed"] > 0 or result["errors"] > 0:
        result["status"] = "red"
    else:
        result["status"] = "error"

    return result


def parse_jest_output(raw: dict) -> dict:
    """Parse jest/vitest output into structured result."""
    output = raw["stdout"] + raw["stderr"]
    result = {
        "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
        "failures": [], "summary": "",
    }

    # Jest: "Tests: 2 failed, 5 passed, 7 total"
    tests_match = re.search(r"Tests:\s+(.+)", output)
    if tests_match:
        result["summary"] = tests_match.group(1)
        for match in re.finditer(r"(\d+) (failed|passed|skipped|todo)", tests_match.group(1)):
            count, kind = int(match.group(1)), match.group(2)
            if kind == "passed":
                result["passed"] = count
            elif kind == "failed":
                result["failed"] = count
            elif kind == "skipped":
                result["skipped"] = count

    # Extract FAIL lines
    for match in re.finditer(r"FAIL\s+(.+)", output):
        result["failures"].append(match.group(1).strip())

    if result["failed"] > 0 or result["errors"] > 0:
        result["failure_excerpt"] = compact_output(
            output, max_lines=60, label="jest-failures",
        )

    if raw["exit_code"] == 0:
        result["status"] = "green"
    elif result["failed"] > 0:
        result["status"] = "red"
    else:
        result["status"] = "error"

    return result


def parse_lint_output(raw: dict) -> dict:
    """Parse lint output into structured result."""
    output = raw["stdout"] + raw["stderr"]
    lines = output.strip().splitlines()

    if raw["exit_code"] == 0:
        return {"status": "clean", "errors": 0, "warnings": 0, "output": ""}

    # Count error/warning lines (works for ruff, eslint, flake8)
    error_count = len(re.findall(r":\d+:\d+: [EF]", output))  # ruff/flake8 errors
    error_count += len(re.findall(r"\d+ error", output))  # eslint summary
    warning_count = len(re.findall(r":\d+:\d+: W", output))
    warning_count += len(re.findall(r"\d+ warning", output))

    # Compact: first 30 issue lines
    issue_lines = [line for line in lines if re.match(r".+:\d+", line)][:30]

    return {
        "status": "errors" if raw["exit_code"] != 0 else "clean",
        "errors": max(error_count, 1 if raw["exit_code"] != 0 else 0),
        "warnings": warning_count,
        "output": compact_output(
            "\n".join(issue_lines) if issue_lines else "\n".join(lines),
            max_lines=40, label="lint",
        ),
    }


def parse_coverage_report(output: str, framework: str) -> dict:
    """Parse per-file coverage from test output."""
    files = []
    total_pct = None

    if framework == "pytest":
        # pytest term-missing: "src/module.py  50  5  90%  12-15, 42"
        for match in re.finditer(
            r"^([\w/._-]+\.py)\s+\d+\s+\d+\s+(\d+)%(?:\s+(\d[\d\-,\s]*))?$",
            output, re.MULTILINE,
        ):
            file_path, pct, missing = match.groups()
            entry = {"file": file_path, "coverage_pct": float(pct), "missing_lines": []}
            if missing and missing.strip():
                entry["missing_lines"] = [m.strip() for m in missing.split(",") if m.strip()]
            files.append(entry)
        total_match = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", output, re.MULTILINE)
        if total_match:
            total_pct = float(total_match.group(1))

    elif framework in ("jest", "vitest"):
        # jest: " file.ts | 85.71 | 100 | 66.67 | 85.71 | 15-20"
        for match in re.finditer(
            r"^\s*([\w/._-]+\.\w+)\s*\|\s*[\d.]+\s*\|\s*[\d.]+\s*\|\s*[\d.]+\s*\|\s*([\d.]+)\s*\|\s*([\d\-,\s]*)$",
            output, re.MULTILINE,
        ):
            file_path, line_pct, uncovered = match.groups()
            entry = {"file": file_path, "coverage_pct": float(line_pct), "missing_lines": []}
            if uncovered.strip():
                entry["missing_lines"] = [m.strip() for m in uncovered.split(",") if m.strip()]
            files.append(entry)
        total_match = re.search(
            r"All files\s*\|\s*[\d.]+\s*\|\s*[\d.]+\s*\|\s*[\d.]+\s*\|\s*([\d.]+)", output,
        )
        if total_match:
            total_pct = float(total_match.group(1))

    return {"coverage_pct": total_pct, "coverage_details": files}


def _framework_from_test_command(test_cmd: str) -> str:
    """Infer test framework from the shell command that will run."""
    low = test_cmd.lower()
    if "pytest" in low:
        return "pytest"
    if "vitest" in low:
        return "vitest"
    if "jest" in low:
        return "jest"
    return "unknown"


def detect_test_framework(commands: dict) -> str:
    """Detect test framework from commands (uses the same command as cmd_test)."""
    test_cmd = commands.get("test_backend") or commands.get("test_frontend") or ""
    return _framework_from_test_command(test_cmd)


def _filter_paths_for_test_runner(paths: list[str], framework: str) -> list[str]:
    """Keep only paths the test runner can collect (e.g. pytest → .py only)."""
    exts = _TEST_RUNNER_EXTS.get(framework)
    if not exts:
        return paths
    return [p for p in paths if any(p.endswith(e) for e in exts)]


def _normalize_target(raw: str | None) -> str:
    """Normalize target strings coming from workflow vars/templates."""
    target = (raw or "all").strip().lower()
    if target.startswith("{{") or target in ("fullstack",):
        return "all"
    if target not in ("all", "backend", "frontend"):
        return "all"
    return target


def _select_test_commands(commands: dict, target: str) -> dict[str, str]:
    """Select test commands to run, in stable order."""
    target = _normalize_target(target)
    selected: dict[str, str] = {}
    if target in ("all", "backend") and commands.get("test_backend"):
        selected["test_backend"] = commands["test_backend"]
    if target in ("all", "frontend") and commands.get("test_frontend"):
        selected["test_frontend"] = commands["test_frontend"]
    return selected


def _append_args(base: str, more: str) -> str:
    base = (base or "").strip()
    more = (more or "").strip()
    if not base:
        return more
    if not more:
        return base
    return f"{base} {more}"


def _pytest_cov_missing(output: str) -> bool:
    """Detect missing pytest-cov plugin (pytest rejects --cov args)."""
    # Common cases:
    # - "pytest: error: unrecognized arguments: --cov --cov-report=term-missing"
    # - "error: unrecognized arguments: --cov"
    return bool(re.search(r"unrecognized arguments:.*\B--cov\b", output, re.IGNORECASE))


def _list_git_files(workdir: str | None) -> list[str]:
    """List tracked files, or [] if not a git repo."""
    cwd = workdir or os.getcwd()
    try:
        result = subprocess.run(  # noqa: PLW1510 — check returncode manually
            ["git", "ls-files"],  # noqa: S607 — git is a trusted binary
            capture_output=True, text=True, timeout=30, cwd=cwd,
        )
    except Exception:  # noqa: BLE001 — best-effort discovery
        return []
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f]


_DEFAULT_EXCLUDED_TEST_DIRS = {
    ".git", ".venv", "venv", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "dist", "build", ".build", "out", ".out",
}
_DEFAULT_EXCLUDED_TEST_HINTS = {
    "e2e", "end_to_end", "end-to-end", "playwright", "cypress",
}


def _looks_like_pytest_test_file(path: str) -> bool:
    p = Path(path)
    if p.suffix != ".py":
        return False
    parts_low = [part.lower() for part in p.parts]
    if any(part in _DEFAULT_EXCLUDED_TEST_DIRS for part in parts_low):
        return False
    if any(part in _DEFAULT_EXCLUDED_TEST_HINTS for part in parts_low):
        return False
    name = p.name.lower()
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if any(part in ("tests", "test", "__tests__") for part in parts_low):
        return True
    return False


def _compress_dirs(dirs: list[str]) -> list[str]:
    """Remove directories already covered by a parent directory."""
    unique = sorted({d.strip().rstrip("/") for d in dirs if d and d.strip()}, key=lambda s: (len(Path(s).parts), s))
    kept: list[str] = []
    for d in unique:
        if any(d == k or d.startswith(k + "/") for k in kept):
            continue
        kept.append(d)
    return kept


def _discover_pytest_collection_paths(test_cmd: str, workdir: str | None) -> list[str]:
    """Discover pytest test roots to bypass restrictive testpaths defaults.

    Returns paths relative to the command's working directory (after `cd ... &&`).
    """
    files = _list_git_files(workdir)
    if not files:
        return []
    test_files = [f for f in files if _looks_like_pytest_test_file(f)]
    if not test_files:
        return []
    test_files = _adjust_paths_for_cd(test_cmd, test_files)
    if not test_files:
        return []

    roots: list[str] = []
    for f in test_files:
        p = Path(f)
        parts_low = [part.lower() for part in p.parts]
        root: Path
        try:
            idx = next(i for i, part in enumerate(parts_low) if part in ("tests", "test", "__tests__"))
            root = Path(*p.parts[: idx + 1])
        except StopIteration:
            # Root-level tests (e.g. "test_models.py") should be included explicitly,
            # not by passing "." (which would traverse the whole repo).
            root = Path(f) if str(p.parent) in ("", ".") else p.parent
        roots.append(str(root))

    roots = _compress_dirs(roots)
    return roots


def cmd_test(args: argparse.Namespace) -> None:  # noqa: C901 — test command with many options
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    analysis = _load_analysis(workdir)
    commands = analysis.get("commands", {})

    target = _normalize_target(getattr(args, "target", "all"))
    test_cmds = _select_test_commands(commands, target)
    if not test_cmds:
        json.dump({"status": "error", "error": "No test command found in project-analysis.json"}, sys.stdout)
        return

    results: dict[str, dict] = {}
    ran_any = False
    passed = failed = errors = skipped = 0
    failures: list[str] = []
    commands_ran: list[str] = []

    coverage_requested = bool(getattr(args, "coverage", False))
    coverage_enabled_any = False
    coverage_details: list[dict] = []
    coverage_pcts: list[float] = []
    warnings: list[str] = []

    # --files-json takes precedence over --files
    files_from_json = getattr(args, "files_json", None)
    raw_file_list: list[str] | None = None
    if args.scope == "specific" and files_from_json:
        try:
            loaded = json.loads(files_from_json)
            if isinstance(loaded, list):
                raw_file_list = [str(x) for x in loaded]
        except json.JSONDecodeError:
            raw_file_list = None
    elif args.scope == "specific" and args.files:
        raw_file_list = list(args.files)

    for key, test_cmd in test_cmds.items():
        framework = _framework_from_test_command(test_cmd)

        selection_extra = ""
        used_discovered_paths = False

        if args.scope == "specific":
            file_list = raw_file_list or []
            adjusted = _adjust_paths_for_cd(test_cmd, file_list)
            adjusted = _filter_paths_for_test_runner(adjusted, framework)
            if not adjusted:
                results[key] = {
                    "status": "skipped",
                    "reason": "No matching test files for this runner",
                    "framework": framework,
                    "command": test_cmd,
                }
                continue
            selection_extra = " ".join(shlex.quote(f) for f in adjusted)
        elif args.scope == "changed":
            changed = get_changed_files(workdir=workdir)
            candidate = [f for f in changed if "test" in f.lower() or "spec" in f.lower()]
            candidate = _adjust_paths_for_cd(test_cmd, candidate)
            candidate = _filter_paths_for_test_runner(candidate, framework)
            if candidate:
                selection_extra = " ".join(shlex.quote(f) for f in candidate)

        # If we're about to run "all tests" under pytest, avoid restrictive testpaths.
        if framework == "pytest" and not selection_extra and args.scope in ("all", "changed"):
            discovered = _discover_pytest_collection_paths(test_cmd, workdir)
            if discovered:
                selection_extra = " ".join(shlex.quote(p) for p in discovered)
                used_discovered_paths = True

        extra = selection_extra
        coverage_enabled = False
        added_cov_flags = False

        # Add coverage flags when requested (skip if command already includes them)
        if coverage_requested:
            if "--cov" not in test_cmd and "--coverage" not in test_cmd:
                if framework == "pytest":
                    extra = _append_args(extra, "--cov --cov-report=term-missing")
                    coverage_enabled = True
                    added_cov_flags = True
                elif framework in ("jest", "vitest"):
                    extra = _append_args(extra, "--coverage")
                    coverage_enabled = True
                    added_cov_flags = True
            else:
                coverage_enabled = True

        raw = run_command(test_cmd, extra, workdir=workdir)
        output = raw["stdout"] + raw["stderr"]

        # Fallback: pytest-cov not installed → rerun without coverage flags
        if coverage_requested and framework == "pytest" and added_cov_flags and _pytest_cov_missing(output):
            warnings.append(
                "pytest-cov is not installed — re-running pytest without coverage flags. "
                "To enable coverage, install it (e.g. `uv add --dev pytest-cov`)."
            )
            raw = run_command(test_cmd, selection_extra, workdir=workdir)
            output = raw["stdout"] + raw["stderr"]
            coverage_enabled = False

        if framework == "pytest":
            parsed = parse_pytest_output(raw)
        elif framework in ("jest", "vitest"):
            parsed = parse_jest_output(raw)
        else:
            # Generic: just report exit code
            if raw["exit_code"] == 0:
                parsed = {"status": "green", "exit_code": 0, "output": "All tests passed."}
            else:
                parsed = {
                    "status": "red",
                    "exit_code": raw["exit_code"],
                    "output": compact_output(
                        output, max_lines=60, label="test-generic",
                    ),
                }

        parsed["framework"] = framework
        parsed["coverage_requested"] = coverage_requested
        parsed["coverage_enabled"] = coverage_enabled
        parsed["used_discovered_paths"] = used_discovered_paths
        parsed["command"] = f"{test_cmd} {extra}".strip()

        # Parse coverage if requested and enabled
        if coverage_requested and coverage_enabled:
            cov = parse_coverage_report(output, framework)
            parsed.update(cov)
            if cov.get("coverage_details"):
                coverage_details.extend(cov["coverage_details"])
            if cov.get("coverage_pct") is not None:
                coverage_pcts.append(float(cov["coverage_pct"]))
            coverage_enabled_any = True

        results[key] = parsed
        ran_any = True
        commands_ran.append(parsed["command"])

        passed += int(parsed.get("passed", 0) or 0)
        failed += int(parsed.get("failed", 0) or 0)
        errors += int(parsed.get("errors", 0) or 0)
        skipped += int(parsed.get("skipped", 0) or 0)
        failures.extend(parsed.get("failures", []) or [])

    if not ran_any:
        json.dump({"status": "error", "error": "No runnable tests matched the requested scope"}, sys.stdout)
        return

    # Worst status wins: error > red > green
    status_rank = {"green": 0, "red": 1, "error": 2, "skipped": -1}
    overall_status = "green"
    for r in results.values():
        s = r.get("status", "error")
        if status_rank.get(s, 2) > status_rank.get(overall_status, 0):
            overall_status = s

    result: dict = {
        "status": overall_status,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "failures": failures,
        "results": results,
        "command": " ; ".join(commands_ran),
    }

    if warnings:
        result["warnings"] = warnings

    if coverage_requested:
        result["coverage_requested"] = True
        result["coverage_enabled"] = coverage_enabled_any
        result["coverage_details"] = coverage_details
        result["coverage_pct"] = coverage_pcts[0] if len(coverage_pcts) == 1 else (sum(coverage_pcts) / len(coverage_pcts) if coverage_pcts else None)

        # Flag changed files with <100% coverage
        changed = get_changed_files(workdir=workdir)
        if coverage_details and changed:
            gaps = [
                f for f in coverage_details
                if f.get("coverage_pct", 100) < 100
                and any(f.get("file", "").endswith(c) or c.endswith(f.get("file", "")) for c in changed)
            ]
            result["coverage_gaps"] = len(gaps) > 0
            result["gap_files"] = gaps

    json.dump(result, sys.stdout, indent=2)


def cmd_format(args: argparse.Namespace) -> None:
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    analysis = _load_analysis(workdir)
    commands = analysis.get("commands", {})

    target = getattr(args, "target", "all") or "all"
    if target.startswith("{{") or target == "fullstack":
        target = "all"
    suffix = f"_{target}" if target != "all" else ""
    fmt_cmds = {k: v for k, v in commands.items()
                if k.startswith("format_") and v and (not suffix or k.endswith(suffix))}

    if not fmt_cmds:
        json.dump({"status": "skipped", "reason": "No format commands found"}, sys.stdout, indent=2)
        return

    results = {}
    for key, fmt_cmd in fmt_cmds.items():
        extra = ""
        if args.scope == "changed":
            changed = get_changed_files(workdir=workdir)
            exts = _exts_for_command(fmt_cmd)
            code_files = [f for f in changed if any(f.endswith(e) for e in exts)] if exts else changed
            code_files = _adjust_paths_for_cd(fmt_cmd, code_files)
            if not code_files:
                results[key] = {"status": "clean", "reason": "No changed files to format"}
                continue
            extra = " ".join(shlex.quote(f) for f in code_files)
        raw = run_command(fmt_cmd, extra, workdir=workdir)
        results[key] = {
            "status": "formatted" if raw["exit_code"] == 0 else "error",
            "exit_code": raw["exit_code"],
            "command": f"{fmt_cmd} {extra}".strip(),
        }

    has_errors = any(r.get("exit_code", 0) != 0 for r in results.values())
    results["status"] = "error" if has_errors else "formatted"
    json.dump(results, sys.stdout, indent=2)


def cmd_lint(args: argparse.Namespace) -> None:
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    analysis = _load_analysis(workdir)
    commands = analysis.get("commands", {})

    # Collect lint and typecheck commands, filtered by --target
    target = getattr(args, "target", "all") or "all"
    if target.startswith("{{") or target == "fullstack":
        target = "all"
    suffix = f"_{target}" if target != "all" else ""
    lint_cmds = {k: v for k, v in commands.items()
                 if k.startswith("lint_") and v and (not suffix or k.endswith(suffix))}
    typecheck_cmds = {k: v for k, v in commands.items()
                      if k.startswith("typecheck_") and v and (not suffix or k.endswith(suffix))}

    results = {}

    for key, lint_cmd in lint_cmds.items():
        extra = ""
        if args.scope == "changed":
            changed = get_changed_files(workdir=workdir)
            exts = _exts_for_command(lint_cmd)
            code_files = [f for f in changed if any(f.endswith(e) for e in exts)] if exts else changed
            code_files = _adjust_paths_for_cd(lint_cmd, code_files)
            if not code_files:
                results[key] = {"status": "clean", "errors": 0, "reason": "No changed code files"}
                results[key]["command"] = lint_cmd
                continue
            extra = " ".join(shlex.quote(f) for f in code_files)
        raw = run_command(lint_cmd, extra, workdir=workdir)
        results[key] = parse_lint_output(raw)
        results[key]["command"] = f"{lint_cmd} {extra}".strip()

    skip_typecheck = getattr(args, "skip_typecheck", False)
    for key, typecheck_cmd in typecheck_cmds.items():
        if skip_typecheck:
            results[key] = {"status": "skipped", "errors": 0, "reason": "typecheck skipped (--skip-typecheck)"}
            results[key]["command"] = typecheck_cmd
            continue
        # Skip npx-based typecheck if the tool isn't installed locally.
        # npx would try to download it, which is slow and fails in sandbox.
        if typecheck_cmd.startswith("npx "):
            tool = typecheck_cmd.split()[1]  # e.g. "tsc" from "npx tsc --noEmit"
            bin_path = Path(workdir or ".") / "node_modules" / ".bin" / tool
            if not bin_path.exists():
                results[key] = {"status": "skipped", "errors": 0, "reason": f"{tool} not installed locally — skipping typecheck"}
                results[key]["command"] = typecheck_cmd
                continue
        raw = run_command(typecheck_cmd, workdir=workdir)
        results[key] = parse_lint_output(raw)
        results[key]["command"] = typecheck_cmd

    if not results:
        recommendations = analysis.get("recommendations", [])
        lint_recs = [r for r in recommendations if r.get("category") in ("linter", "typecheck")]
        results: dict = {
            "status": "skipped",
            "reason": "No lint or typecheck commands found",
        }
        if lint_recs:
            results["recommendations"] = lint_recs
    else:
        has_errors = any(r.get("errors", 0) > 0 for r in results.values() if isinstance(r, dict))
        results["status"] = "errors" if has_errors else "clean"

    json.dump(results, sys.stdout, indent=2)


def cmd_verify(args: argparse.Namespace) -> None:
    """Run protocol-specific verification commands."""
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    commands_json = getattr(args, "commands_json", "[]")
    # Prefer env var — avoids shell escaping issues with complex commands
    if commands_json == "[]" and os.environ.get("VERIFY_COMMANDS_JSON"):
        commands_json = os.environ["VERIFY_COMMANDS_JSON"]
    try:
        commands = json.loads(commands_json)
    except (json.JSONDecodeError, TypeError):
        json.dump({"status": "error", "error": "Invalid commands JSON"}, sys.stdout)
        return

    if not commands or not isinstance(commands, list):
        json.dump({"status": "pass", "results": []}, sys.stdout)
        return

    default_timeout = 120
    results = []
    all_pass = True
    for i, entry in enumerate(commands):
        # Support both "cmd" strings and {"cmd": "...", "timeout": N} objects
        if isinstance(entry, dict):
            cmd = entry.get("cmd", "")
            timeout = entry.get("timeout", default_timeout)
        else:
            cmd = entry
            timeout = default_timeout
        raw = run_command(cmd, workdir=workdir, timeout=timeout)
        passed = raw["exit_code"] == 0
        timed_out = raw["exit_code"] == -1
        if not passed:
            all_pass = False
        output = ""
        if timed_out:
            output = f"TIMEOUT: Custom verification command did not finish within {timeout}s. This usually means a missing dependency (database not running, service not started). To increase the timeout, use '# timeout:N' prefix in the step file's verification block. Command: {cmd}"
        elif not passed:
            output = compact_output(
                raw["stdout"] + raw["stderr"], max_lines=40, label=f"verify-{i}",
            )
        results.append({
            "command": cmd,
            "passed": passed,
            "timed_out": timed_out,
            "output": output,
        })

    json.dump({
        "status": "pass" if all_pass else "fail",
        "results": results,
    }, sys.stdout, indent=2)


def cmd_coverage(args: argparse.Namespace) -> None:
    """Run tests with coverage and report gaps on changed files."""
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    analysis = _load_analysis(workdir)
    commands = analysis.get("commands", {})
    test_cmds = _select_test_commands(commands, target="all")
    if not test_cmds:
        json.dump({"has_gaps": False, "error": "No test command found in project-analysis.json", "files": []}, sys.stdout)
        return

    changed = get_changed_files(workdir=workdir)
    result_files: list[dict] = []
    has_gaps = False
    warnings: list[str] = []
    overall_pcts: list[float] = []
    commands_ran: dict[str, str] = {}

    # Collect coverage details from all relevant runners
    for key, test_cmd in test_cmds.items():
        framework = _framework_from_test_command(test_cmd)

        selection_extra = ""
        used_discovered_paths = False
        if framework == "pytest":
            discovered = _discover_pytest_collection_paths(test_cmd, workdir)
            if discovered:
                selection_extra = " ".join(shlex.quote(p) for p in discovered)
                used_discovered_paths = True

        extra = selection_extra
        added_cov_flags = False
        if "--cov" not in test_cmd and "--coverage" not in test_cmd:
            if framework == "pytest":
                extra = _append_args(extra, "--cov --cov-report=term-missing")
                added_cov_flags = True
            elif framework in ("jest", "vitest"):
                extra = _append_args(extra, "--coverage")
                added_cov_flags = True

        raw = run_command(test_cmd, extra, workdir=workdir)
        output = raw["stdout"] + raw["stderr"]
        commands_ran[key] = f"{test_cmd} {extra}".strip()

        if framework == "pytest" and added_cov_flags and _pytest_cov_missing(output):
            warnings.append(
                "pytest-cov is not installed — skipping coverage checks for pytest. "
                "To enable coverage, install it (e.g. `uv add --dev pytest-cov`)."
            )
            continue

        cov = parse_coverage_report(output, framework)
        if cov.get("coverage_pct") is not None:
            overall_pcts.append(float(cov["coverage_pct"]))

        for detail in cov.get("coverage_details", []):
            file_path = detail.get("file", "")
            # Only include files that match changed files
            if not any(file_path.endswith(c) or c.endswith(file_path) for c in changed):
                continue
            entry = {
                "path": file_path,
                "coverage": detail.get("coverage_pct"),
                "missing_lines": detail.get("missing_lines", []),
            }
            result_files.append(entry)
            if (detail.get("coverage_pct") or 100) < 100:
                has_gaps = True

        if used_discovered_paths:
            # Helpful breadcrumb for projects with restrictive pytest testpaths
            warnings.append("pytest: using explicit discovered test paths to avoid restrictive testpaths defaults.")

    result: dict = {
        "has_gaps": has_gaps,
        "overall_coverage": (sum(overall_pcts) / len(overall_pcts)) if overall_pcts else None,
        "files": result_files,
        "commands": commands_ran,
    }
    if warnings:
        result["warnings"] = warnings
    json.dump(result, sys.stdout, indent=2)


def cmd_install(args: argparse.Namespace) -> None:
    """Run install commands (install_backend, install_frontend) from project-analysis.json."""
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    commands = load_commands(workdir)
    results = {}
    for key in ("install_backend", "install_frontend"):
        cmd = commands.get(key)
        if not cmd:
            continue
        raw = run_command(cmd, workdir=workdir)
        results[key] = {
            "status": "success" if raw["exit_code"] == 0 else "failure",
            "command": cmd,
            "exit_code": raw["exit_code"],
        }
        if raw["exit_code"] != 0:
            results[key]["error"] = raw["stderr"][:500]
    if not results:
        results = {"status": "skipped", "reason": "No install commands found"}
    json.dump(results, sys.stdout, indent=2)


def cmd_commands(args: argparse.Namespace) -> None:
    """Print detected commands."""
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    json.dump(load_commands(workdir), sys.stdout, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Development workflow tools")
    sub = parser.add_subparsers(dest="command")

    test_p = sub.add_parser("test", help="Run tests")
    test_p.add_argument("--scope", choices=["all", "changed", "specific"], default="all")
    test_p.add_argument("--target", default="all", help="Which tests to run: all, backend, frontend")
    test_p.add_argument("--files", nargs="*", default=[])
    test_p.add_argument("--files-json", default=None, help="JSON array of test files (avoids shell quoting)")
    test_p.add_argument("--coverage", action="store_true", help="Enable coverage reporting")
    test_p.add_argument("--workdir", default=None, help="Working directory for git/commands")

    fmt_p = sub.add_parser("format", help="Run code formatter")
    fmt_p.add_argument("--scope", choices=["all", "changed"], default="changed")
    fmt_p.add_argument("--target", default="all",
                       help="Filter by suffix: all, backend, frontend (unresolved templates fall back to all)")
    fmt_p.add_argument("--workdir", default=None, help="Working directory for git/commands")

    lint_p = sub.add_parser("lint", help="Run lint + typecheck")
    lint_p.add_argument("--scope", choices=["all", "changed"], default="all")
    lint_p.add_argument("--target", default="all",
                        help="Filter by suffix: all, backend, frontend (unresolved templates fall back to all)")
    lint_p.add_argument("--skip-typecheck", action="store_true", help="Skip typecheck commands (pyright, tsc)")
    lint_p.add_argument("--workdir", default=None, help="Working directory for git/commands")

    verify_p = sub.add_parser("verify", help="Run protocol verification commands")
    verify_p.add_argument("--commands-json", default="[]", help="JSON array of shell commands")
    verify_p.add_argument("--workdir", default=None, help="Working directory")

    cov_p = sub.add_parser("coverage", help="Run tests with coverage and report gaps on changed files")
    cov_p.add_argument("--workdir", default=None, help="Working directory")

    install_p = sub.add_parser("install", help="Run install commands for backend/frontend")
    install_p.add_argument("--workdir", default=None, help="Working directory")

    cmds_p = sub.add_parser("commands", help="Show detected commands")
    cmds_p.add_argument("--workdir", default=None, help="Working directory")

    args = parser.parse_args()

    if args.command == "test":
        cmd_test(args)
    elif args.command == "format":
        cmd_format(args)
    elif args.command == "lint":
        cmd_lint(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "coverage":
        cmd_coverage(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "commands":
        cmd_commands(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
