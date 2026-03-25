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


def detect_test_framework(commands: dict) -> str:
    """Detect test framework from commands."""
    for key in ("test_backend", "test_frontend"):
        cmd = commands.get(key, "")
        if "pytest" in cmd:
            return "pytest"
        if "jest" in cmd or "vitest" in cmd:
            return "jest"
    return "unknown"


def cmd_test(args: argparse.Namespace) -> None:  # noqa: C901 — test command with many options
    workdir = _resolve_workdir(getattr(args, "workdir", None))
    commands = load_commands(workdir)
    test_cmd = commands.get("test_backend") or commands.get("test_frontend")
    if not test_cmd:
        json.dump({"status": "error", "error": "No test command found in project-analysis.json"}, sys.stdout)
        return

    framework = detect_test_framework(commands)

    extra = ""
    # --files-json takes precedence over --files
    files_from_json = getattr(args, "files_json", None)
    if args.scope == "specific" and files_from_json:
        try:
            file_list = json.loads(files_from_json)
            if isinstance(file_list, list):
                file_list = _adjust_paths_for_cd(test_cmd, file_list)
                extra = " ".join(shlex.quote(f) for f in file_list)
        except json.JSONDecodeError:
            extra = files_from_json
    elif args.scope == "specific" and args.files:
        adjusted = _adjust_paths_for_cd(test_cmd, list(args.files))
        extra = " ".join(shlex.quote(f) for f in adjusted)
    elif args.scope == "changed":
        changed = get_changed_files(workdir=workdir)
        test_files = [f for f in changed if "test" in f.lower() or "spec" in f.lower()]
        test_files = _adjust_paths_for_cd(test_cmd, test_files)
        if test_files:
            extra = " ".join(shlex.quote(f) for f in test_files)

    # Add coverage flags when requested (skip if command already includes them)
    if args.coverage and "--cov" not in test_cmd and "--coverage" not in test_cmd:
        if framework == "pytest":
            extra += " --cov --cov-report=term-missing"
        elif framework in ("jest", "vitest"):
            extra += " --coverage"

    raw = run_command(test_cmd, extra, workdir=workdir)

    if framework == "pytest":
        result = parse_pytest_output(raw)
    elif framework in ("jest", "vitest"):
        result = parse_jest_output(raw)
    else:
        # Generic: just report exit code
        if raw["exit_code"] == 0:
            result = {"status": "green", "exit_code": 0, "output": "All tests passed."}
        else:
            result = {
                "status": "red",
                "exit_code": raw["exit_code"],
                "output": compact_output(
                    raw["stdout"] + raw["stderr"], max_lines=60, label="test-generic",
                ),
            }

    # Parse coverage if requested
    if args.coverage:
        output = raw["stdout"] + raw["stderr"]
        cov = parse_coverage_report(output, framework)
        result.update(cov)
        # Flag changed files with <100% coverage
        changed = get_changed_files(workdir=workdir)
        if cov["coverage_details"] and changed:
            gaps = [
                f for f in cov["coverage_details"]
                if f["coverage_pct"] < 100
                and any(f["file"].endswith(c) or c.endswith(f["file"]) for c in changed)
            ]
            result["coverage_gaps"] = len(gaps) > 0
            result["gap_files"] = gaps

    result["command"] = f"{test_cmd} {extra}".strip()
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

    default_timeout = 30
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
    commands = load_commands(workdir)
    test_cmd = commands.get("test_backend") or commands.get("test_frontend")
    if not test_cmd:
        json.dump({"has_gaps": False, "error": "No test command found in project-analysis.json", "files": []}, sys.stdout)
        return

    framework = detect_test_framework(commands)

    # Add coverage flags
    extra = ""
    if "--cov" not in test_cmd and "--coverage" not in test_cmd:
        if framework == "pytest":
            extra = "--cov --cov-report=term-missing"
        elif framework in ("jest", "vitest"):
            extra = "--coverage"

    raw = run_command(test_cmd, extra, workdir=workdir)
    output = raw["stdout"] + raw["stderr"]
    cov = parse_coverage_report(output, framework)

    changed = get_changed_files(workdir=workdir)
    result_files = []
    has_gaps = False

    for detail in cov.get("coverage_details", []):
        # Only include files that match changed files
        if not any(detail["file"].endswith(c) or c.endswith(detail["file"]) for c in changed):
            continue
        entry = {
            "path": detail["file"],
            "coverage": detail["coverage_pct"],
            "missing_lines": detail.get("missing_lines", []),
        }
        result_files.append(entry)
        if detail["coverage_pct"] < 100:
            has_gaps = True

    result = {
        "has_gaps": has_gaps,
        "overall_coverage": cov.get("coverage_pct"),
        "files": result_files,
    }
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
