# ruff: noqa: E501, T201
"""Merge protocol helpers for the workflow engine.

CLI with subcommands for prerequisite checks, verification, merge, and cleanup.
All output is JSON for consumption by ShellStep result_var.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: str | Path = ".") -> subprocess.CompletedProcess[str]:
    """Run a command, capture output."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)  # noqa: PLW1510, S603 — trusted git commands


def _fail(message: str) -> None:
    """Print error JSON and exit."""
    print(json.dumps({"error": message}))
    sys.exit(1)


# ---------------------------------------------------------------------------
# check-prereqs
# ---------------------------------------------------------------------------


def check_prereqs(protocol_dir: str) -> None:
    """Validate plan.md steps, worktree existence, develop cleanliness."""
    pdir = Path(protocol_dir)
    plan_path = pdir / "plan.md"

    if not plan_path.is_file():
        _fail(f"plan.md not found in {protocol_dir}")

    text = plan_path.read_text(encoding="utf-8")

    # Check all progress markers are [x]
    marker_re = re.compile(r"^\s*-\s+\[([ x~\-])\]", re.MULTILINE)
    markers = marker_re.findall(text)
    if not markers:
        _fail("No progress markers found in plan.md")

    incomplete = [m for m in markers if m != "x"]
    if incomplete:
        _fail(
            f"{len(incomplete)} of {len(markers)} steps not complete. "
            "Finish remaining steps before merging."
        )

    # Derive protocol name and number from directory name
    dir_name = pdir.resolve().name
    num_match = re.match(r"(\d+)", dir_name)
    protocol_num = num_match.group(1) if num_match else dir_name
    protocol_name = dir_name

    # Find worktree
    branch = f"protocol-{protocol_num}"
    worktree_path = f".worktrees/{branch}"
    if not Path(worktree_path).is_dir():
        _fail(
            f"Worktree not found at {worktree_path}. "
            "Branch may already be merged — check plan.md status."
        )

    # Check develop is clean
    result = _run(["git", "status", "--porcelain"])
    if result.stdout.strip():
        _fail("develop has uncommitted changes. Commit or stash before merging.")

    # Count files changed
    diff_result = _run(["git", "diff", "--stat", "develop"], cwd=worktree_path)
    lines = [ln for ln in diff_result.stdout.strip().splitlines() if ln.strip()]
    files_changed = max(0, len(lines) - 1)  # last line is summary

    print(
        json.dumps(
            {
                "branch": branch,
                "worktree_path": worktree_path,
                "protocol_name": protocol_name,
                "protocol_num": protocol_num,
                "files_changed": files_changed,
                "step_count": len(markers),
            }
        )
    )


# ---------------------------------------------------------------------------
# diff-stats
# ---------------------------------------------------------------------------


def diff_stats(worktree_path: str) -> None:
    """Git diff develop --stat, return structured JSON."""
    result = _run(["git", "diff", "develop", "--stat"], cwd=worktree_path)
    output = result.stdout.strip()

    files = 0
    insertions = 0
    deletions = 0

    # Parse summary line: " N files changed, N insertions(+), N deletions(-)"
    for line in output.splitlines():
        summary_match = re.search(
            r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?",
            line,
        )
        if summary_match:
            files = int(summary_match.group(1))
            insertions = int(summary_match.group(2) or 0)
            deletions = int(summary_match.group(3) or 0)
            break

    summary = f"{files} files, +{insertions}/-{deletions}"
    print(
        json.dumps(
            {
                "files": files,
                "insertions": insertions,
                "deletions": deletions,
                "summary": summary,
                "raw": output,
            }
        )
    )


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def verify(target_dir: str) -> None:
    """Run dev-tools.py test + lint in the target directory."""
    target = Path(target_dir)
    project_root = Path.cwd()

    # Find dev-tools.py from project root
    dev_tools = project_root / ".workflows" / "develop" / "dev-tools.py"
    if not dev_tools.is_file():
        # Fallback: check if target dir itself has it
        alt = target / ".workflows" / "develop" / "dev-tools.py"
        if alt.is_file():
            dev_tools = alt
        else:
            _fail(
                "dev-tools.py not found at .workflows/develop/dev-tools.py. "
                "Ensure the develop workflow is deployed."
            )

    dt = str(dev_tools.resolve())

    # Run tests
    test_result = _run([sys.executable, dt, "test"], cwd=target)
    test_ok = test_result.returncode == 0

    # Run lint
    lint_result = _run([sys.executable, dt, "lint"], cwd=target)
    lint_ok = lint_result.returncode == 0

    status = "PASSED" if (test_ok and lint_ok) else "FAILED"

    if not test_ok and not lint_ok:
        detail = f"Tests: FAILED\n{test_result.stderr or test_result.stdout}\nLint: FAILED\n{lint_result.stderr or lint_result.stdout}"
    elif not test_ok:
        detail = f"Tests: FAILED\n{test_result.stderr or test_result.stdout}"
    elif not lint_ok:
        detail = f"Lint: FAILED\n{lint_result.stderr or lint_result.stdout}"
    else:
        detail = "Tests: PASSED, Lint: PASSED"

    if status == "FAILED":
        _fail(f"Verification failed.\n{detail}")

    print(json.dumps({"status": status, "detail": detail}))


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


def merge(worktree_path: str, branch: str, protocol_name: str) -> None:
    """Rebase onto develop, then merge --no-ff."""
    wt = Path(worktree_path)
    if not wt.is_dir():
        _fail(f"Worktree not found at {worktree_path}")

    # Rebase onto develop
    rebase = _run(["git", "rebase", "develop"], cwd=worktree_path)
    if rebase.returncode != 0:
        _fail(
            f"Rebase failed — resolve conflicts in {worktree_path} and retry.\n"
            f"{rebase.stderr}"
        )

    # Switch to develop and merge
    checkout = _run(["git", "checkout", "develop"])
    if checkout.returncode != 0:
        _fail(f"Failed to checkout develop: {checkout.stderr}")

    merge_msg = f"merge: {protocol_name} into develop"
    merge_result = _run(["git", "merge", "--no-ff", branch, "-m", merge_msg])
    if merge_result.returncode != 0:
        _fail(f"Merge failed: {merge_result.stderr}")

    # Get merge commit hash
    log = _run(["git", "rev-parse", "HEAD"])
    commit_hash = log.stdout.strip()

    print(json.dumps({"commit_hash": commit_hash, "message": merge_msg}))


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


def cleanup(worktree_path: str, branch: str, protocol_dir: str) -> None:
    """Remove worktree, delete branch, update plan.md status."""
    # Remove worktree
    _run(["git", "worktree", "remove", worktree_path, "--force"])

    # Delete branch
    _run(["git", "branch", "-d", branch])

    # Update plan.md status to Complete
    plan_path = Path(protocol_dir) / "plan.md"
    if plan_path.is_file():
        text = plan_path.read_text(encoding="utf-8")
        # Look for status line in frontmatter or body and update
        if "status:" in text.split("---")[1] if text.startswith("---") else False:
            text = re.sub(
                r"^(status:\s*).*$", r"\1Complete", text, count=1, flags=re.MULTILINE
            )
        else:
            # Append status line to end of frontmatter if present
            if text.startswith("---\n"):
                try:
                    end = text.index("\n---\n", 4)
                    text = text[:end] + "\nstatus: Complete" + text[end:]
                except ValueError:
                    pass
        plan_path.write_text(text, encoding="utf-8")

    print(json.dumps({"cleaned": True}))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:

    parser = argparse.ArgumentParser(description="Merge protocol helpers")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("check-prereqs")
    p.add_argument("protocol_dir")

    p = sub.add_parser("diff-stats")
    p.add_argument("worktree_path")

    p = sub.add_parser("verify")
    p.add_argument("target_dir")

    p = sub.add_parser("merge")
    p.add_argument("worktree_path")
    p.add_argument("branch")
    p.add_argument("protocol_name")

    p = sub.add_parser("cleanup")
    p.add_argument("worktree_path")
    p.add_argument("branch")
    p.add_argument("protocol_dir")

    args = parser.parse_args()

    if args.command == "check-prereqs":
        check_prereqs(args.protocol_dir)
    elif args.command == "diff-stats":
        diff_stats(args.worktree_path)
    elif args.command == "verify":
        verify(args.target_dir)
    elif args.command == "merge":
        merge(args.worktree_path, args.branch, args.protocol_name)
    elif args.command == "cleanup":
        cleanup(args.worktree_path, args.branch, args.protocol_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli()
