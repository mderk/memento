#!/usr/bin/env python3
"""MCP server for the workflow engine.

Thin wrapper over WorkflowRunner. Exposes MCP tools that serialize
WorkflowRunner results to JSON for the Claude Code relay protocol.

Usage:
    python -m scripts.cli
    # Or via Claude Code:
    claude mcp add memento-workflow -- python -m scripts.cli
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from .infra.artifacts import (
    exec_key_to_artifact_path,
    write_llm_output_artifact,
    write_meta,
    write_shell_artifacts,
)
from .infra.checkpoint import (
    checkpoint_dir_from_run_id,
    checkpoint_load,
    checkpoint_load_children,
    checkpoint_save,
)
from .engine.core import Frame, RunState
from .engine.hooks import DryRunTreeHook
from .infra.loader import discover_workflows
from .engine.protocol import (
    ActionBase,
    CancelledAction,
    CompletedAction,
    DryRunCompleteAction,
    DryRunNode,
    DryRunSummary,
    ErrorAction,
    HaltedAction,
    ParallelAction,
    ShellAction,
    SubagentAction,
    action_to_dict,
)
from .infra.shell_exec import _execute_shell
from .engine.state import advance, apply_submit, pending_action
from .engine.types import StructuredOutput, WorkflowContext, WorkflowDef
from .engine.workflow_runner import WorkflowRunner
from .utils import compute_totals, merge_child_results, workflow_hash


def _set_shell_log(value: bool) -> None:
    """Toggle INCLUDE_SHELL_LOG (works with both package and exec() imports)."""
    import sys

    mod = sys.modules.get("memento_workflow.protocol") or sys.modules.get(__name__)
    if mod and hasattr(mod, "INCLUDE_SHELL_LOG"):
        mod.INCLUDE_SHELL_LOG = value  # type: ignore[attr-defined]
    # exec() namespace — protocol globals live in our own globals
    globals()["INCLUDE_SHELL_LOG"] = value


logger = logging.getLogger("workflow-engine")

# In-memory storage for active runs (parent + child)
_runs: dict[str, RunState] = {}
_runs_lock = threading.Lock()
_EVICTION_THRESHOLD = 100  # trigger eviction when _runs exceeds this
_TERMINAL_RUN_STATUSES = frozenset({"completed", "error", "halted", "cancelled"})

# Feature flag: parallel auto-advance for shell-only parallel lanes
_PARALLEL_AUTO_ADVANCE = os.environ.get("MEMENTO_PARALLEL_AUTO_ADVANCE", "on") != "off"
_PARALLEL_MAX_WORKERS = 16

# Terminal action types for parallel fast-path checks (excludes "cancelled")
_TERMINAL_ACTION_TYPES = frozenset({"completed", "error", "halted"})

# MCP server instance
mcp = FastMCP("memento-workflow")

_RUN_ID_RE = re.compile(r"^[a-f0-9]{12}(>[a-f0-9]{12})*$")

# Engine root: runner.py → scripts → memento-workflow
ENGINE_ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------
# Backward-compat module-level functions (used by test infrastructure)
# ------------------------------------------------------------------


def _store_run(state: RunState) -> None:
    """Store a run state. Evicts terminal runs when threshold exceeded."""
    with _runs_lock:
        _runs[state.run_id] = state
        if len(_runs) > _EVICTION_THRESHOLD:
            _evict_terminal_runs()


def _evict_terminal_runs() -> None:
    """Remove terminal runs from _runs. Must be called with _runs_lock held.

    Evicts terminal subtrees as a unit: if a parent and all its descendants
    are terminal, the whole component is removed. This prevents unevictable
    trees where parent is protected by having children and children are
    protected by being referenced.
    """

    def _all_terminal(rid: str) -> bool:
        """Return True if rid and all its descendants are terminal."""
        s = _runs.get(rid)
        if s is None or s.status not in _TERMINAL_RUN_STATUSES:
            return False
        return all(_all_terminal(cid) for cid in s.child_run_ids)

    def _collect_subtree(rid: str, out: list[str]) -> None:
        """Collect rid and all descendants into out."""
        out.append(rid)
        s = _runs.get(rid)
        if s:
            for cid in s.child_run_ids:
                _collect_subtree(cid, out)

    # Find root-level terminal subtrees (runs not referenced by any parent)
    referenced: set[str] = set()
    for s in _runs.values():
        referenced.update(s.child_run_ids)

    to_remove: list[str] = []
    for rid in _runs:
        if rid not in referenced and _all_terminal(rid):
            _collect_subtree(rid, to_remove)

    for rid in to_remove:
        _runs.pop(rid, None)
    if to_remove:
        logger.debug(
            "evicted %d terminal runs, %d remaining", len(to_remove), len(_runs)
        )


def _get_run(run_id: str) -> RunState | None:
    """Get a run state by ID."""
    with _runs_lock:
        return _runs.get(run_id)


def _cleanup_run(state: RunState) -> None:
    """Remove checkpoint files and in-memory state for a run and its children."""
    runner = WorkflowRunner.from_run_store(_runs)
    runner._cleanup_run(state)


# Re-export static WorkflowRunner methods for test access
_find_node = WorkflowRunner._find_node
_compute_dry_run_summary = WorkflowRunner._compute_dry_run_summary


def _try_parallel_fast_path(
    action: ParallelAction,
    results: list[tuple[RunState, ActionBase, list[RunState]]],
) -> str | None:
    """Attempt to skip relay when all parallel lanes are terminal.

    Backward-compat wrapper: returns JSON response string or None.
    """
    runner = WorkflowRunner.from_run_store(_runs)
    result = runner._try_parallel_fast_path(action, results)
    if result is None:
        return None
    return json.dumps(action_to_dict(result), default=str)


# ------------------------------------------------------------------
# MCP-specific helpers
# ------------------------------------------------------------------


def _discover(cwd: str, workflow_dirs: list[str]) -> dict[str, WorkflowDef]:
    """Discover workflows from engine-bundled + project + extra directories."""
    search_paths: list[Path] = []

    # Engine-bundled workflows
    skills_dir = ENGINE_ROOT / "skills"
    if skills_dir.is_dir():
        search_paths.append(skills_dir)

    # Project workflows (.workflows/)
    cwd_path = Path(cwd).resolve()
    project_wf = cwd_path / ".workflows"
    if project_wf.is_dir():
        search_paths.append(project_wf)

    # Extra dirs (plugin skills, etc.)
    for d in workflow_dirs:
        p = Path(d).resolve()
        if p.is_dir():
            search_paths.append(p)

    logger.debug(
        "Discovering workflows in %d paths: %s", len(search_paths), search_paths
    )
    registry = discover_workflows(*search_paths)
    logger.info("Discovered %d workflows: %s", len(registry), sorted(registry.keys()))
    return registry


def _cancel_stale_run(run_id: str, cwd_path: Path, reason: str) -> None:
    """Mark a stale run as cancelled in meta.json without deleting the directory."""
    meta_path = checkpoint_dir_from_run_id(cwd_path, run_id) / "meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "cancelled"
            meta["cancel_reason"] = reason
            # Atomic write: tmp + os.replace to avoid partial writes
            tmp_path = meta_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            os.replace(str(tmp_path), str(meta_path))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("failed to update meta for stale run %s: %s", run_id, exc)


def _load_resume_workflow_name(run_id: str, cwd_path: Path) -> str | None:
    """Return workflow name for a checkpointed run using state.json, then meta.json."""
    run_dir = checkpoint_dir_from_run_id(cwd_path, run_id)

    state_path = run_dir / "state.json"
    if state_path.is_file():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            name = data.get("workflow_name")
            if isinstance(name, str) and name:
                return name
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("failed reading workflow_name from %s: %s", state_path, exc)

    meta_path = run_dir / "meta.json"
    if meta_path.is_file():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            name = data.get("workflow")
            if isinstance(name, str) and name:
                return name
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("failed reading workflow from %s: %s", meta_path, exc)

    return None


# ------------------------------------------------------------------
# MCP Tools — delegate to WorkflowRunner
# ------------------------------------------------------------------


@mcp.tool()
def start(
    workflow: Annotated[str, "Name of the workflow to run"],
    variables: Annotated[
        dict[str, Any] | None, "Variables to inject into workflow context"
    ] = None,
    cwd: Annotated[str, "Working directory (defaults to current)"] = "",
    workflow_dirs: Annotated[
        list[str] | None, "Additional directories to search for workflows"
    ] = None,
    resume: Annotated[
        str, "Run ID to resume from checkpoint. Falls back to fresh start on failure."
    ] = "",
    dry_run: Annotated[bool, "Show steps without executing"] = False,
    shell_log: Annotated[
        bool, "Debug only — include _shell_log in response (bloats context)"
    ] = False,
) -> str:
    """Start a workflow or resume from checkpoint. Returns the first action with exec_key."""
    _set_shell_log(shell_log)
    logger.info(
        "start(workflow=%s, cwd=%s, resume=%s, dry_run=%s, dirs=%s)",
        workflow,
        cwd,
        resume,
        dry_run,
        workflow_dirs,
    )
    variables = variables or {}
    workflow_dirs = workflow_dirs or []
    cwd = cwd or "."
    cwd_path = Path(cwd).resolve()

    if not cwd_path.is_dir():
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id="",
                    message=f"cwd is not an existing directory: {cwd}",
                )
            )
        )

    registry = _discover(str(cwd_path), workflow_dirs)

    resume_warning: str | None = None

    if resume:
        if not _RUN_ID_RE.match(resume):
            return json.dumps(
                action_to_dict(
                    ErrorAction(
                        run_id=resume,
                        message=f"Invalid run_id format: {resume}",
                    )
                )
            )
        if workflow not in registry:
            return json.dumps(
                action_to_dict(
                    ErrorAction(
                        run_id=resume,
                        message=f"Workflow '{workflow}' not found for resume",
                    )
                )
            )
        wf = registry[workflow]
        result = checkpoint_load(resume, cwd_path, registry, wf)

        if isinstance(result, str):
            # checkpoint_load failed (drift, missing, corrupt) — fallback to fresh
            logger.warning("resume failed for %s: %s — starting fresh", resume, result)
            _cancel_stale_run(resume, cwd_path, reason=result)
            resume_warning = f"resume={resume} failed: {result}"
        elif result.status in ("completed", "cancelled"):
            # Terminal state — nothing to resume, start fresh
            logger.info(
                "resume skip: run %s is %s — starting fresh", resume, result.status
            )
            resume_warning = f"resume={resume} is {result.status}"
        else:
            # Successful resume — delegate to WorkflowRunner
            runner = WorkflowRunner.from_state(result, registry, run_store=_runs)
            action = runner.resume()
            return json.dumps(action_to_dict(action), default=str)

    # Fresh run
    if workflow not in registry:
        available = sorted(registry.keys())
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id="",
                    message=f"Workflow '{workflow}' not found. Available: {available}",
                )
            )
        )

    wf = registry[workflow]

    if dry_run:
        # Dry-run: use isolated run_store, no checkpoints
        runner = WorkflowRunner(
            wf,
            variables=variables,
            cwd=str(cwd_path),
            registry=registry,
            run_store={},
            checkpoint=False,
        )
        action = runner.dry_run()
    else:
        runner = WorkflowRunner(
            wf,
            variables=variables,
            cwd=str(cwd_path),
            registry=registry,
            run_store=_runs,
        )
        action = runner.start()

    if resume_warning:
        action.warnings.append(resume_warning)

    return json.dumps(action_to_dict(action), default=str)


@mcp.tool()
def resume(
    run_id: Annotated[str, "Run ID to resume from checkpoint"],
    cwd: Annotated[str, "Working directory (defaults to current)"] = "",
    workflow_dirs: Annotated[
        list[str] | None, "Additional directories to search for workflows"
    ] = None,
    shell_log: Annotated[
        bool, "Debug only — include _shell_log in response (bloats context)"
    ] = False,
) -> str:
    """Resume a workflow from checkpoint using workflow metadata stored on disk."""
    _set_shell_log(shell_log)
    logger.info("resume(run_id=%s, cwd=%s, dirs=%s)", run_id, cwd, workflow_dirs)
    workflow_dirs = workflow_dirs or []
    cwd = cwd or "."
    cwd_path = Path(cwd).resolve()

    if not cwd_path.is_dir():
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"cwd is not an existing directory: {cwd}",
                )
            )
        )

    if not _RUN_ID_RE.match(run_id):
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"Invalid run_id format: {run_id}",
                )
            )
        )

    workflow_name = _load_resume_workflow_name(run_id, cwd_path)
    if not workflow_name:
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=(
                        f"Could not determine workflow for run {run_id}. "
                        "Missing or corrupt checkpoint metadata."
                    ),
                )
            )
        )

    registry = _discover(str(cwd_path), workflow_dirs)
    if workflow_name not in registry:
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=(
                        f"Workflow '{workflow_name}' required by run {run_id} "
                        f"not found. Available: {sorted(registry.keys())}"
                    ),
                )
            )
        )

    wf = registry[workflow_name]
    result = checkpoint_load(run_id, cwd_path, registry, wf)
    if isinstance(result, str):
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"resume failed: {result}",
                )
            )
        )
    if result.status in ("completed", "cancelled"):
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"run {run_id} is {result.status} and cannot be resumed",
                )
            )
        )

    runner = WorkflowRunner.from_state(result, registry, run_store=_runs)
    action = runner.resume()
    return json.dumps(action_to_dict(action), default=str)


@mcp.tool()
def submit(
    run_id: Annotated[str, "Run ID (parent or child)"],
    exec_key: Annotated[str, "exec_key from the action being submitted"],
    output: Annotated[str, "Text output from the action"] = "",
    structured_output: Annotated[StructuredOutput, "Structured JSON output"] = None,
    status: Annotated[str, 'Result status ("success" or "failure")'] = "success",
    error: Annotated[str | None, "Error message if status is failure"] = None,
    duration: Annotated[float, "Duration of the action in seconds"] = 0.0,
    cost_usd: Annotated[float | None, "Cost of the action in USD"] = None,
    model: Annotated[str | None, "Model used for the step"] = None,
    shell_log: Annotated[
        bool, "Debug only — include _shell_log in response (bloats context)"
    ] = False,
) -> str:
    """Submit result for an exec_key, return next action. Idempotent."""
    _set_shell_log(shell_log)
    runner = WorkflowRunner.from_run_store(_runs)
    action = runner.submit(
        run_id,
        exec_key,
        output=output,
        structured_output=structured_output,
        status=status,
        error=error,
        duration=duration,
        cost_usd=cost_usd,
        model=model,
    )
    return json.dumps(action_to_dict(action), default=str)


@mcp.tool()
def next(
    run_id: Annotated[str, "Run ID to query"],
    shell_log: Annotated[
        bool, "Debug only — include _shell_log in response (bloats context)"
    ] = False,
) -> str:
    """Re-fetch current pending action without mutating state. Recovery tool."""
    _set_shell_log(shell_log)
    runner = WorkflowRunner.from_run_store(_runs)
    action = runner.next(run_id)
    return json.dumps(action_to_dict(action), default=str)


@mcp.tool()
def cancel(run_id: str) -> str:
    """Cancel a running workflow. Cleans up state.

    Args:
        run_id: The run ID to cancel.
    """
    logger.info("cancel(run_id=%s)", run_id)
    state = _get_run(run_id)
    if state is None:
        logger.error("cancel: unknown run_id=%s", run_id)
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"Unknown run_id: {run_id}",
                )
            )
        )

    runner = WorkflowRunner.from_state(state, {}, run_store=_runs)
    action = runner.cancel()
    return json.dumps(action_to_dict(action), default=str)


@mcp.tool()
def list_workflows(
    cwd: str = "",
    workflow_dirs: list[str] | None = None,
) -> str:
    """List discovered workflows from plugin + project + extra dirs.

    Args:
        cwd: Working directory for project workflow discovery.
        workflow_dirs: Additional directories to search.
    """
    cwd = cwd or "."
    workflow_dirs = workflow_dirs or []
    registry = _discover(str(Path(cwd).resolve()), workflow_dirs)

    workflows = []
    for name, wf in sorted(registry.items()):
        workflows.append(
            {
                "name": name,
                "description": wf.description,
                "blocks": len(wf.blocks),
                "source": wf.source_path,
            }
        )

    return json.dumps({"workflows": workflows})


@mcp.tool()
def status(run_id: str) -> str:
    """Get current workflow state (for debugging/monitoring).

    Args:
        run_id: The run ID to query.
    """
    state = _get_run(run_id)
    if state is None:
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"Unknown run_id: {run_id}",
                )
            )
        )

    runner = WorkflowRunner.from_state(state, {}, run_store=_runs)
    return json.dumps(runner.get_status(), default=str)


@mcp.tool()
def open_dashboard(cwd: str = "") -> str:
    """Open the workflow dashboard in a browser. Auto-selects a free port."""
    from .infra.dashboard_helpers import start_dashboard

    cwd = cwd or "."
    cwd_path = str(Path(cwd).resolve())
    return json.dumps(start_dashboard(cwd_path))


@mcp.tool()
def cleanup_runs(
    cwd: str = "",
    before: str | None = None,
    status_filter: str | None = None,
    keep: int = 0,
    dry_run: bool = False,
    remove_all: bool = False,
) -> str:
    """Clean up old workflow state directories.

    Args:
        cwd: Project directory containing .workflow-state/
        before: Remove runs started before this date (ISO 8601 or YYYY-MM-DD)
        status_filter: Only remove runs with this status (completed/running/error)
        keep: Keep the N most recent matching runs
        dry_run: Show what would be deleted without actually deleting
        remove_all: Remove ALL runs (ignores before/status filters)
    """
    from .infra.cleanup import cleanup, cleanup_stale_relay_markers

    result = cleanup(
        cwd or ".",
        before=before,
        status=status_filter,
        keep=keep,
        dry_run=dry_run,
        remove_all=remove_all,
    )
    stale_count = cleanup_stale_relay_markers(cwd or ".")
    if stale_count:
        result["stale_markers_removed"] = stale_count
    return json.dumps(result, indent=2, ensure_ascii=False)


_DEBUG = os.environ.get("WORKFLOW_DEBUG", "0") == "1"


def main() -> None:
    """Run the MCP server."""
    logging.basicConfig(
        level=logging.DEBUG if _DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logger.info("MCP server starting (debug=%s, engine_root=%s)", _DEBUG, ENGINE_ROOT)
    mcp.run()


if __name__ == "__main__":
    main()
