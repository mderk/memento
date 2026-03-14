"""CLI client for viewing workflow state.

Usage:
    python -m dashboard.cli [--cwd DIR] runs
    python -m dashboard.cli [--cwd DIR] run <run_id>
    python -m dashboard.cli [--cwd DIR] steps <run_id>
    python -m dashboard.cli [--cwd DIR] artifact <run_id> <path>
    python -m dashboard.cli [--cwd DIR] diff <id1> <id2>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .data import (
    diff_runs,
    get_artifact_content,
    get_run_detail,
    list_runs,
)


def _state_dir(cwd: str) -> Path:
    return Path(cwd) / ".workflow-state"


# ── Formatters ──


def _short_id(run_id: str) -> str:
    return run_id[:8]


def _fmt_status(status: str) -> str:
    symbols = {
        "completed": "+",
        "running": "~",
        "error": "!",
        "cancelled": "x",
        "unknown": "?",
    }
    return f"[{symbols.get(status, '?')} {status}]"


def _fmt_duration(start: str, end: str | None) -> str:
    if not start:
        return "—"
    from datetime import datetime

    s = datetime.fromisoformat(start)
    if end:
        e = datetime.fromisoformat(end)
    else:
        from datetime import timezone

        e = datetime.now(timezone.utc)
    sec = int((e - s).total_seconds())
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def _fmt_time(iso: str) -> str:
    if not iso:
        return "—"
    from datetime import datetime

    dt = datetime.fromisoformat(iso)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _exec_key_short(exec_key: str) -> str:
    """Short display name from exec_key, stripping type prefixes."""
    parts = exec_key.split("/")
    result = []
    for p in parts:
        name = re.sub(r"^[\w-]+:", "", p)
        name = re.sub(r"\[(\w+)=(\d+)\]", r"[\2]", name)
        result.append(name)
    return "/".join(result)


# ── Commands ──


def cmd_runs(state_dir: Path) -> None:
    runs = list_runs(state_dir)
    if not runs:
        print("No runs found.")
        return

    print(f"{'ID':>10}  {'STATUS':>14}  {'WORKFLOW':<24}  {'STARTED':<20}  {'DURATION':>8}  {'STEPS':>5}  {'COST':>8}")
    print("─" * 105)
    _print_run_rows(runs, depth=0)


def _print_run_rows(runs: list[dict[str, Any]], depth: int) -> None:
    indent = "  " * depth
    prefix = "└ " if depth > 0 else ""
    for r in runs:
        rid = _short_id(r["run_id"])
        status = _fmt_status(r["status"])
        wf = r.get("workflow", "") or "—"
        started = _fmt_time(r.get("started_at", ""))
        dur = _fmt_duration(r.get("started_at", ""), r.get("completed_at"))
        steps = r.get("step_count", 0)
        cost = f"${r['total_cost_usd']:.4f}" if r.get("total_cost_usd") is not None else "—"
        print(f"{indent}{prefix}{rid:>10}  {status:>14}  {wf:<24}  {started:<20}  {dur:>8}  {steps:>5}  {cost:>8}")
        children = r.get("children", [])
        if children:
            _print_run_rows(children, depth + 1)


def cmd_run(state_dir: Path, run_id: str) -> None:
    detail = get_run_detail(state_dir, run_id)
    if not detail:
        print(f"Run {run_id} not found.", file=sys.stderr)
        sys.exit(1)

    meta = detail["meta"]
    print(f"Run:      {meta['run_id']}")
    print(f"Workflow: {meta.get('workflow') or '—'}")
    print(f"Status:   {meta['status']}")
    print(f"Started:  {_fmt_time(meta.get('started_at', ''))}")
    print(f"Duration: {_fmt_duration(meta.get('started_at', ''), meta.get('completed_at'))}")
    print(f"Steps:    {meta.get('step_count', 0)}")
    if meta.get("total_cost_usd") is not None:
        print(f"Cost:     ${meta['total_cost_usd']:.4f}")
    if meta.get("steps_by_type"):
        parts = [f"{k}: {v}" for k, v in meta["steps_by_type"].items()]
        print(f"Types:    {', '.join(parts)}")
    print()

    steps = detail["steps"]
    if steps:
        print("Steps:")
        for s in steps:
            name = _exec_key_short(s["exec_key"])
            depth = s["exec_key"].count("/")
            indent = "  " * depth
            status_char = "+" if s["status"] == "success" else "!" if s["status"] == "failure" else "~"
            dur = f"{s['duration']:.1f}s" if s["duration"] >= 1 else f"{int(s['duration']*1000)}ms"
            cost = f"  ${s['cost_usd']:.4f}" if s.get("cost_usd") else ""
            stype = f"  [{s['step_type']}]" if s.get("step_type") else ""
            model = f"  ({s['model']})" if s.get("model") else ""
            files = f"  [{', '.join(s['artifact_files'])}]" if s.get("artifact_files") else ""
            err = f"  ERR: {s['error']}" if s.get("error") else ""
            print(f"  {indent}{status_char} {name}  ({dur}){cost}{stype}{model}{files}{err}")
    else:
        print("No steps.")


def cmd_steps(state_dir: Path, run_id: str) -> None:
    """Print steps as JSON for programmatic consumption."""
    detail = get_run_detail(state_dir, run_id)
    if not detail:
        print(f"Run {run_id} not found.", file=sys.stderr)
        sys.exit(1)
    json.dump(detail["steps"], sys.stdout, indent=2)
    print()


def cmd_artifact(state_dir: Path, run_id: str, path: str) -> None:
    content = get_artifact_content(state_dir, run_id, path)
    if content is None:
        print(f"Artifact not found: {run_id}/{path}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(content)


def cmd_diff(state_dir: Path, id1: str, id2: str) -> None:
    result = diff_runs(state_dir, id1, id2)
    if result is None:
        print("One or both runs not found.", file=sys.stderr)
        sys.exit(1)

    r1 = result["run1"]
    r2 = result["run2"]
    print(f"Diff: {_short_id(r1['run_id'])} vs {_short_id(r2['run_id'])}")
    print()

    for d in result["diffs"]:
        change = d["change"]
        key = d["results_key"]
        if change == "unchanged":
            continue
        marker = {"added": "+", "removed": "-", "modified": "~"}[change]
        print(f"  {marker} {key}  [{change}]")
        for ad in d.get("artifact_diffs", []):
            print(f"    --- {ad['file']} ---")
            print(ad["diff"])


def cmd_serve(cwd: str, host: str, port: int, open_browser: bool) -> None:
    """Start the dashboard web server."""
    import socket

    import uvicorn

    from .app import create_app

    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            port = s.getsockname()[1]

    app = create_app(cwd)
    url = f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}"
    print(f"Dashboard: {url}", file=sys.stderr)
    print(f"Project:   {cwd}", file=sys.stderr)
    if host == "0.0.0.0":
        print("WARNING: Binding to all interfaces — artifacts are accessible without auth.", file=sys.stderr)

    if open_browser:
        import webbrowser
        import threading

        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dashboard.cli",
        description="CLI client for viewing workflow run state",
    )
    parser.add_argument("--cwd", default=".", help="Project directory (default: .)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("runs", help="List all runs")

    p_run = sub.add_parser("run", help="Show run detail")
    p_run.add_argument("run_id", help="Run ID (prefix match supported)")

    p_steps = sub.add_parser("steps", help="Show steps as JSON")
    p_steps.add_argument("run_id", help="Run ID")

    p_art = sub.add_parser("artifact", help="Show artifact content")
    p_art.add_argument("run_id", help="Run ID")
    p_art.add_argument("path", help="Artifact path (e.g. check-context/result.json)")

    p_diff = sub.add_parser("diff", help="Diff two runs")
    p_diff.add_argument("id1", help="First run ID")
    p_diff.add_argument("id2", help="Second run ID")

    p_serve = sub.add_parser("serve", help="Start dashboard web server")
    p_serve.add_argument("--port", type=int, default=0, help="Port (0 = auto)")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host (0.0.0.0 for remote)")
    p_serve.add_argument("--no-open", action="store_true", help="Don't open browser")

    args = parser.parse_args()
    state_dir = _state_dir(args.cwd)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # serve doesn't need state_dir resolution
    if args.command == "serve":
        cmd_serve(args.cwd, args.host, args.port, not args.no_open)
        return

    # Resolve prefix matches for run IDs
    if args.command in ("run", "steps", "artifact"):
        args.run_id = _resolve_run_id(state_dir, args.run_id)
    if args.command == "diff":
        args.id1 = _resolve_run_id(state_dir, args.id1)
        args.id2 = _resolve_run_id(state_dir, args.id2)

    if args.command == "runs":
        cmd_runs(state_dir)
    elif args.command == "run":
        cmd_run(state_dir, args.run_id)
    elif args.command == "steps":
        cmd_steps(state_dir, args.run_id)
    elif args.command == "artifact":
        cmd_artifact(state_dir, args.run_id, args.path)
    elif args.command == "diff":
        cmd_diff(state_dir, args.id1, args.id2)


def _resolve_run_id(state_dir: Path, prefix: str) -> str:
    """Resolve a run ID prefix to a full ID. Returns as-is if exact or no match."""
    if not state_dir.is_dir():
        return prefix

    # Check top-level
    candidates: list[str] = []
    for entry in state_dir.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix):
            candidates.append(entry.name)
        # Also check children
        children_dir = entry / "children"
        if children_dir.is_dir():
            for child in children_dir.iterdir():
                if child.is_dir() and child.name.startswith(prefix):
                    candidates.append(child.name)

    if len(candidates) == 1:
        return candidates[0]
    if prefix in candidates:
        return prefix
    if len(candidates) > 1:
        print(f"Ambiguous prefix '{prefix}': {', '.join(sorted(candidates)[:5])}", file=sys.stderr)
        sys.exit(1)
    return prefix


if __name__ == "__main__":
    main()
