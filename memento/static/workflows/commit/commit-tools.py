#!/usr/bin/env python3
# ruff: noqa: E501, T201
"""Commit workflow shell tool.

Gathers git state, produces diffs, stages files, and commits —
all as JSON output for the workflow engine. The LLM never
touches these shell commands directly.

Usage:
    python commit-tools.py gather [--workdir DIR] [--amend-mode true|false]
    python commit-tools.py diff [--workdir DIR] [--scope staged|all|amend]
    python commit-tools.py stage --files-json '[...]' [--workdir DIR]
    python commit-tools.py unstage [--workdir DIR]
    python commit-tools.py commit [--amend-mode true|false] [--workdir DIR]  # reads JSON from stdin
    python commit-tools.py verify [--workdir DIR] [--count N]
    python commit-tools.py cleanup --path PATH
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _resolve_workdir(workdir: str | None) -> str | None:
    """Resolve workdir from arg, env var, or None (use cwd).

    Handles unresolved template strings (e.g. '{{variables.workdir}}')
    by falling back to None.
    """
    for candidate in [workdir, os.environ.get("COMMIT_TOOLS_WORKDIR")]:
        if candidate and not candidate.startswith("{{"):
            resolved = str(Path(candidate).resolve())
            if Path(resolved).is_dir():
                return resolved
    return None


def _git(args: list[str], cwd: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command, returning the CompletedProcess.

    Forces LANG=C / LC_ALL=C so localized git installations still produce
    English error messages.
    """
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    return subprocess.run(  # noqa: S603, S607
        ["git", *args],
        capture_output=True, text=True, timeout=timeout,
        cwd=cwd, env=env,
    )


def _is_root_commit(cwd: str | None) -> bool:
    """Check if HEAD is the root commit (has no parent)."""
    result = _git(["rev-parse", "--verify", "HEAD~1"], cwd=cwd)
    return result.returncode != 0


def _parse_porcelain(output: str) -> tuple[list[str], list[str], list[str]]:
    """Parse `git status --porcelain` into (staged, unstaged, untracked) file lists.

    Porcelain format: XY filename
      X = index status, Y = worktree status
      '?' in both = untracked
    """
    staged = []
    unstaged = []
    untracked = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        x, y = line[0], line[1]
        # Handle renames: "R  old -> new" — take the new name
        name = line[3:]
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        if x == "?" and y == "?":
            untracked.append(name)
        else:
            if x not in (" ", "?"):
                staged.append(name)
            if y not in (" ", "?"):
                unstaged.append(name)
    return staged, unstaged, untracked


def cmd_gather(args: argparse.Namespace) -> None:
    """Gather git state: status, diff stats, recent log."""
    cwd = _resolve_workdir(args.workdir) or os.getcwd()

    # git status --porcelain
    status_result = _git(["status", "--porcelain"], cwd=cwd)
    status_short = status_result.stdout.strip()
    staged, unstaged, untracked = _parse_porcelain(status_result.stdout)

    # Detect partial staging: file appears in both staged and unstaged
    has_partial_staging = bool(set(staged) & set(unstaged))

    all_changed = list(dict.fromkeys(staged + unstaged + untracked))

    # Diff stats
    diff_stat_result = _git(["diff", "--stat"], cwd=cwd)
    diff_cached_stat_result = _git(["diff", "--cached", "--stat"], cwd=cwd)

    # Recent log (handle no-HEAD gracefully)
    no_head = False
    recent_log = ""
    log_result = _git(["log", "--oneline", "-5"], cwd=cwd)
    if log_result.returncode != 0:
        no_head = True
    else:
        recent_log = log_result.stdout.strip()

    is_amend = getattr(args, "amend_mode", "false") == "true"
    nothing_to_commit = not staged and not unstaged and not untracked

    json.dump({
        "has_staged": bool(staged),
        "has_unstaged": bool(unstaged),
        "has_partial_staging": has_partial_staging,
        "staged_files": staged,
        "unstaged_files": unstaged,
        "untracked_files": untracked,
        "all_changed_files": all_changed,
        "status_short": status_short,
        "diff_stat": diff_stat_result.stdout.strip(),
        "diff_cached_stat": diff_cached_stat_result.stdout.strip(),
        "recent_log": recent_log,
        "nothing_to_commit": nothing_to_commit,
        "no_head": no_head,
        "diff_mode": "amend" if is_amend else "staged",
    }, sys.stdout, indent=2)


def cmd_diff(args: argparse.Namespace) -> None:
    """Write full diff to temp file, return path + metadata."""
    cwd = _resolve_workdir(args.workdir) or os.getcwd()

    if args.scope == "amend":
        if _is_root_commit(cwd):
            # Root commit: show entire tree as diff
            diff_result = _git(["show", "--root", "--pretty=format:", "--patch", "HEAD"], cwd=cwd)
            name_args = ["diff-tree", "--root", "--name-only", "-r", "--no-commit-id", "HEAD"]
        else:
            diff_result = _git(["diff", "HEAD~1..HEAD"], cwd=cwd)
            name_args = ["diff", "--name-only", "HEAD~1..HEAD"]
        # Also append any newly staged changes
        staged = _git(["diff", "--cached"], cwd=cwd)
        if staged.stdout.strip():
            diff_result = subprocess.CompletedProcess(
                diff_result.args, 0,
                stdout=diff_result.stdout + "\n" + staged.stdout,
                stderr="",
            )
    elif args.scope == "staged":
        diff_result = _git(["diff", "--cached"], cwd=cwd)
        name_args = ["diff", "--cached", "--name-only"]
    else:
        # All changes: staged + unstaged
        diff_result = _git(["diff", "HEAD"], cwd=cwd)
        name_args = ["diff", "--name-only", "HEAD"]
        if diff_result.returncode != 0:
            # No HEAD yet — show all staged
            diff_result = _git(["diff", "--cached"], cwd=cwd)
            name_args = ["diff", "--cached", "--name-only"]

    diff_text = diff_result.stdout

    # Write to temp file
    fd, diff_path = tempfile.mkstemp(prefix="memento-commit-", suffix=".patch")
    with os.fdopen(fd, "w") as fh:
        fh.write(diff_text)

    # Extract file list from diff
    name_result = _git(name_args, cwd=cwd)
    if name_result.returncode != 0:
        name_result = _git(["diff", "--cached", "--name-only"], cwd=cwd)
    files_in_diff = [fname for fname in name_result.stdout.strip().splitlines() if fname]

    json.dump({
        "diff_path": diff_path,
        "diff_lines": len(diff_text.splitlines()),
        "files_in_diff": files_in_diff,
    }, sys.stdout, indent=2)


def cmd_stage(args: argparse.Namespace) -> None:
    """Stage files using git add -A -- <files>."""
    cwd = _resolve_workdir(args.workdir) or os.getcwd()

    try:
        files = json.loads(args.files_json)
    except (json.JSONDecodeError, TypeError):
        json.dump({"status": "error", "error": f"Invalid files JSON: {args.files_json}"}, sys.stdout)
        return

    if not files or not isinstance(files, list):
        json.dump({"status": "error", "error": "Empty or invalid file list"}, sys.stdout)
        return

    result = _git(["add", "-A", "--"] + files, cwd=cwd)
    if result.returncode != 0:
        json.dump({"status": "error", "error": result.stderr.strip()}, sys.stdout)
        return

    json.dump({"status": "ok", "staged": files}, sys.stdout, indent=2)


def cmd_unstage(args: argparse.Namespace) -> None:
    """Unstage all files (git reset HEAD)."""
    cwd = _resolve_workdir(args.workdir) or os.getcwd()

    result = _git(["reset", "HEAD", "--quiet"], cwd=cwd)
    if result.returncode != 0:
        json.dump({"status": "error", "error": result.stderr.strip()}, sys.stdout)
        return

    json.dump({"status": "ok"}, sys.stdout, indent=2)


def cmd_commit(args: argparse.Namespace) -> None:
    """Create a commit. Reads commit data from stdin as JSON: {"subject": "...", "body": "..."|null}."""
    cwd = _resolve_workdir(args.workdir) or os.getcwd()

    # Read commit data from stdin
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        json.dump({"status": "error", "error": "Invalid JSON on stdin"}, sys.stdout)
        return

    subject = data.get("subject", "").strip()
    if not subject:
        json.dump({"status": "error", "error": "Missing commit subject"}, sys.stdout)
        return

    body = data.get("body")
    if body:
        message = f"{subject}\n\n{body.strip()}"
    else:
        message = subject

    is_amend = getattr(args, "amend_mode", "false") == "true"

    # Locale-independent "nothing to commit" detection.
    # Skip this guard for --amend so message-only rewrites still work.
    if not is_amend:
        diff_check = _git(["diff", "--cached", "--quiet"], cwd=cwd)
        if diff_check.returncode == 0:
            json.dump({"status": "skipped", "reason": "nothing to commit"}, sys.stdout)
            return

    git_args = ["commit", "-m", message]
    if is_amend:
        git_args.append("--amend")

    result = _git(git_args, cwd=cwd)
    if result.returncode != 0:
        combined = (result.stderr + result.stdout).lower()
        if "nothing to commit" in combined or "nothing added to commit" in combined:
            json.dump({"status": "skipped", "reason": "nothing to commit"}, sys.stdout)
            return
        error = result.stderr.strip() or result.stdout.strip()
        json.dump({"status": "error", "error": error}, sys.stdout)
        return

    # Get the resulting commit SHA
    log_result = _git(["log", "--oneline", "-1"], cwd=cwd)
    oneline = log_result.stdout.strip()

    json.dump({
        "status": "ok",
        "sha": oneline.split(" ", 1)[0] if oneline else "",
        "oneline": oneline,
    }, sys.stdout, indent=2)


def cmd_verify(args: argparse.Namespace) -> None:
    """Verify commit state: recent log + working tree status."""
    cwd = _resolve_workdir(args.workdir) or os.getcwd()
    count = args.count or 3

    # Recent log (handle no-HEAD)
    log_result = _git(["log", "--oneline", f"-{count}"], cwd=cwd)
    if log_result.returncode != 0:
        log_text = "(no commits yet)"
    else:
        log_text = log_result.stdout.strip()

    # Working tree status
    status_result = _git(["status", "-s"], cwd=cwd)
    clean = not status_result.stdout.strip()

    json.dump({
        "status": "ok",
        "log": log_text,
        "clean": clean,
        "remaining_status": status_result.stdout.strip() if not clean else "",
    }, sys.stdout, indent=2)


def cmd_cleanup(args: argparse.Namespace) -> None:
    """Remove a temp file by path (e.g. diff patch file)."""
    path = args.path
    try:
        if path and Path(path).is_file():
            Path(path).unlink()
            json.dump({"status": "ok", "removed": path}, sys.stdout, indent=2)
        else:
            json.dump({"status": "ok", "removed": None}, sys.stdout, indent=2)
    except OSError as e:
        json.dump({"status": "error", "error": str(e)}, sys.stdout, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Commit workflow tools")
    sub = parser.add_subparsers(dest="command")

    gather_p = sub.add_parser("gather", help="Gather git state")
    gather_p.add_argument("--workdir", default=None)
    gather_p.add_argument("--amend-mode", default="false", help="'true' when amending")
    gather_p.set_defaults(func=cmd_gather)

    diff_p = sub.add_parser("diff", help="Write full diff to temp file")
    diff_p.add_argument("--workdir", default=None)
    diff_p.add_argument("--scope", choices=["staged", "all", "amend"], default="staged")
    diff_p.set_defaults(func=cmd_diff)

    stage_p = sub.add_parser("stage", help="Stage files")
    stage_p.add_argument("--files-json", required=True, help="JSON array of file paths")
    stage_p.add_argument("--workdir", default=None)
    stage_p.set_defaults(func=cmd_stage)

    unstage_p = sub.add_parser("unstage", help="Unstage all files")
    unstage_p.add_argument("--workdir", default=None)
    unstage_p.set_defaults(func=cmd_unstage)

    commit_p = sub.add_parser("commit", help="Create commit (reads JSON from stdin)")
    commit_p.add_argument("--amend-mode", default="false", help="'true' to amend HEAD")
    commit_p.add_argument("--workdir", default=None)
    commit_p.set_defaults(func=cmd_commit)

    verify_p = sub.add_parser("verify", help="Verify commit state")
    verify_p.add_argument("--workdir", default=None)
    verify_p.add_argument("--count", type=int, default=3)
    verify_p.set_defaults(func=cmd_verify)

    cleanup_p = sub.add_parser("cleanup", help="Remove a temp file")
    cleanup_p.add_argument("--path", required=True, help="Path to remove")
    cleanup_p.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
