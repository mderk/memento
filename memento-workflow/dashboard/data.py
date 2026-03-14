"""Data layer for the workflow dashboard.

Reads .workflow-state/<run_id>/ directories to produce API responses.
All reads, no writes. Safe for concurrent access.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any


def _exec_key_to_artifact_path(exec_key: str) -> str:
    """Map exec_key to relative artifact path.

    Must stay in sync with scripts/artifacts.py:exec_key_to_artifact_path().
    """
    path = exec_key.replace(":", "-")
    path = re.sub(r"\[(\w+)=(\d+)\]", r"/\1-\2", path)
    return _sanitize_rel_path(path)


def _sanitize_rel_path(path: str) -> str:
    """Ensure path is a safe relative path (no traversal or absolute)."""
    if path.startswith("/"):
        path = path.lstrip("/")
    parts = [p for p in path.split("/") if p and p != ".."]
    return "/".join(parts) or "unknown"


def _read_run_summary(entry: Path) -> dict[str, Any] | None:
    """Read run summary from meta.json, falling back to state.json for legacy runs."""
    meta: dict[str, Any] = {}
    state: dict[str, Any] = {}

    meta_path = entry / "meta.json"
    state_path = entry / "state.json"

    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if not meta and not state:
        return None

    step_count = len(state.get("ctx", {}).get("results_scoped", {}))

    # Resolve started_at: meta > state.json mtime as fallback
    started_at = meta.get("started_at", "")
    if not started_at:
        # Use oldest file mtime in the run directory as proxy
        for fname in ("state.json", "meta.json"):
            fpath = entry / fname
            if fpath.is_file():
                mtime = os.path.getmtime(fpath)
                started_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                break

    return {
        "run_id": meta.get("run_id", state.get("run_id", entry.name)),
        "workflow": meta.get("workflow", ""),
        "status": meta.get("status", state.get("status", "unknown")),
        "started_at": started_at,
        "completed_at": meta.get("completed_at"),
        "step_count": step_count,
        "cwd": meta.get("cwd", state.get("ctx", {}).get("cwd", "")),
        "parent_run_id": state.get("parent_run_id"),
        "child_run_ids": state.get("child_run_ids", []),
        "total_cost_usd": meta.get("total_cost_usd"),
        "total_duration": meta.get("total_duration"),
        "steps_by_type": meta.get("steps_by_type"),
    }


def _scan_children(parent_dir: Path) -> list[dict[str, Any]]:
    """Scan <parent>/children/*/ for child run summaries."""
    children_dir = parent_dir / "children"
    if not children_dir.is_dir():
        return []
    children: list[dict[str, Any]] = []
    for entry in sorted(children_dir.iterdir()):
        if not entry.is_dir():
            continue
        summary = _read_run_summary(entry)
        if summary:
            # Recurse for grandchildren
            summary["children"] = _scan_children(entry)
            children.append(summary)
    return children


def list_runs(state_dir: Path) -> list[dict[str, Any]]:
    """Scan .workflow-state/*/ and return run summaries with nested children."""
    runs: list[dict[str, Any]] = []
    if not state_dir.is_dir():
        return runs

    for entry in sorted(state_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        summary = _read_run_summary(entry)
        if summary:
            summary["children"] = _scan_children(entry)
            runs.append(summary)

    return runs


def _build_artifact_tree(base: Path, rel: str = "") -> list[dict[str, Any]]:
    """Recursively build artifact tree from a directory."""
    nodes: list[dict[str, Any]] = []
    if not base.is_dir():
        return nodes

    for entry in sorted(base.iterdir()):
        entry_rel = f"{rel}/{entry.name}" if rel else entry.name
        if entry.is_dir():
            children = _build_artifact_tree(entry, entry_rel)
            nodes.append({
                "name": entry.name,
                "path": entry_rel,
                "type": "directory",
                "children": children,
            })
        else:
            nodes.append({
                "name": entry.name,
                "path": entry_rel,
                "type": "file",
                "size": entry.stat().st_size,
            })

    return nodes


def _find_run_dir(state_dir: Path, run_id: str) -> Path | None:
    """Locate a run directory — top-level or nested under a parent's children/."""
    direct = state_dir / run_id
    if direct.is_dir():
        return direct
    # Search children/ of all top-level runs
    if state_dir.is_dir():
        for parent in state_dir.iterdir():
            candidate = parent / "children" / run_id
            if candidate.is_dir():
                return candidate
    return None


def get_run_detail(state_dir: Path, run_id: str) -> dict[str, Any] | None:
    """Return full run detail: meta + steps + artifact tree."""
    run_dir = _find_run_dir(state_dir, run_id)
    if not run_dir:
        return None

    summary = _read_run_summary(run_dir)
    if not summary:
        return None

    # Parse steps from state.json
    steps: list[dict[str, Any]] = []
    state_path = run_dir / "state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            results_scoped = state.get("ctx", {}).get("results_scoped", {})

            # For child runs, exclude steps inherited from parent
            parent_keys: set[str] = set()
            parent_run_id = state.get("parent_run_id")
            if parent_run_id:
                parent_dir = _find_run_dir(state_dir, parent_run_id)
                if parent_dir:
                    parent_state_path = parent_dir / "state.json"
                    if parent_state_path.is_file():
                        try:
                            parent_state = json.loads(parent_state_path.read_text(encoding="utf-8"))
                            parent_keys = set(parent_state.get("ctx", {}).get("results_scoped", {}).keys())
                        except (json.JSONDecodeError, OSError):
                            pass

            artifacts_dir = run_dir / "artifacts"
            for exec_key, result in results_scoped.items():
                if exec_key in parent_keys:
                    continue
                # List artifact files for this step
                art_path = artifacts_dir / _exec_key_to_artifact_path(exec_key)
                artifact_files: list[str] = []
                if art_path.is_dir():
                    artifact_files = sorted(
                        f.name for f in art_path.iterdir() if f.is_file()
                    )
                steps.append({
                    "exec_key": exec_key,
                    "results_key": result.get("results_key", ""),
                    "name": result.get("name", exec_key),
                    "status": result.get("status", "unknown"),
                    "output_preview": (result.get("output", "") or "")[:200],
                    "duration": result.get("duration", 0),
                    "error": result.get("error"),
                    "cost_usd": result.get("cost_usd"),
                    "step_type": result.get("step_type", ""),
                    "model": result.get("model"),
                    "started_at": result.get("started_at", ""),
                    "order": result.get("order", 0),
                    "artifact_files": artifact_files,
                })
        except (json.JSONDecodeError, OSError):
            pass

    steps.sort(key=lambda s: s["order"])

    # Build artifact tree
    artifacts_dir = run_dir / "artifacts"
    artifact_tree = _build_artifact_tree(artifacts_dir)

    return {
        "meta": {**summary, "step_count": len(steps)},
        "steps": steps,
        "artifact_tree": artifact_tree,
    }


def get_artifact_content(state_dir: Path, run_id: str, path: str) -> str | None:
    """Read an artifact file's content. Returns None if not found."""
    run_dir = _find_run_dir(state_dir, run_id)
    if not run_dir:
        return None
    artifacts_base = (run_dir / "artifacts").resolve()
    file_path = (run_dir / "artifacts" / path).resolve()
    if not file_path.is_relative_to(artifacts_base):
        return None
    if not file_path.is_file():
        return None
    try:
        return file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def diff_runs(
    state_dir: Path, id1: str, id2: str,
) -> dict[str, Any] | None:
    """Compute diff between two runs by matching steps on exec_key."""
    detail1 = get_run_detail(state_dir, id1)
    detail2 = get_run_detail(state_dir, id2)
    if detail1 is None or detail2 is None:
        return None

    run_dir1 = _find_run_dir(state_dir, id1)
    run_dir2 = _find_run_dir(state_dir, id2)

    # Build maps: results_key → step info (use exec_key as fallback for empty keys)
    steps1 = {s["results_key"] or s["exec_key"]: s for s in detail1["steps"]}
    steps2 = {s["results_key"] or s["exec_key"]: s for s in detail2["steps"]}

    all_keys = sorted(set(steps1.keys()) | set(steps2.keys()))

    diffs: list[dict[str, Any]] = []
    for key in all_keys:
        s1 = steps1.get(key)
        s2 = steps2.get(key)

        entry: dict[str, Any] = {"results_key": key}

        if s1 and not s2:
            entry["change"] = "removed"
            entry["left"] = s1
        elif s2 and not s1:
            entry["change"] = "added"
            entry["right"] = s2
        else:
            assert s1 and s2
            # Compare artifact content
            artifact_diffs = _diff_step_artifacts(
                run_dir1, s1["exec_key"], run_dir2, s2["exec_key"],
            )
            entry["change"] = "modified" if artifact_diffs else "unchanged"
            entry["left"] = s1
            entry["right"] = s2
            if artifact_diffs:
                entry["artifact_diffs"] = artifact_diffs

        diffs.append(entry)

    return {
        "run1": detail1["meta"],
        "run2": detail2["meta"],
        "diffs": diffs,
    }


def _diff_step_artifacts(
    run_dir1: Path | None, exec_key1: str,
    run_dir2: Path | None, exec_key2: str,
) -> list[dict[str, str]]:
    """Diff artifact files between two steps."""
    if not run_dir1 or not run_dir2:
        return []
    path1 = run_dir1 / "artifacts" / _exec_key_to_artifact_path(exec_key1)
    path2 = run_dir2 / "artifacts" / _exec_key_to_artifact_path(exec_key2)

    results: list[dict[str, str]] = []

    files1 = {f.name for f in path1.iterdir()} if path1.is_dir() else set()
    files2 = {f.name for f in path2.iterdir()} if path2.is_dir() else set()

    for fname in sorted(files1 | files2):
        f1 = path1 / fname if fname in files1 else None
        f2 = path2 / fname if fname in files2 else None

        try:
            content1 = f1.read_text(encoding="utf-8").splitlines(keepends=True) if f1 else []
            content2 = f2.read_text(encoding="utf-8").splitlines(keepends=True) if f2 else []
        except (OSError, UnicodeDecodeError):
            continue

        if content1 == content2:
            continue

        diff_text = "".join(unified_diff(
            content1, content2,
            fromfile=f"{run_dir1.name}/{fname}",
            tofile=f"{run_dir2.name}/{fname}",
        ))
        if diff_text:
            results.append({"file": fname, "diff": diff_text})

    return results
