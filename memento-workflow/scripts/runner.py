#!/usr/bin/env python3
"""MCP server for the workflow engine.

Exposes tools: start, submit, next, cancel, list_workflows, status.
Claude Code acts as a relay, calling these tools to drive workflow execution.

Usage:
    python runner.py
    # Or via Claude Code:
    claude mcp add memento-workflow -- python path/to/runner.py
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
from .infra.loader import discover_workflows
from .engine.protocol import (
    ActionBase,
    CancelledAction,
    CompletedAction,
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


def _cleanup_run(state: RunState) -> None:
    """Remove checkpoint files and in-memory state for a run and its children."""
    if state.checkpoint_dir and state.checkpoint_dir.exists():
        shutil.rmtree(state.checkpoint_dir, ignore_errors=True)
    with _runs_lock:
        _runs.pop(state.run_id, None)
        children_to_clean = []
        for child_id in state.child_run_ids:
            child = _runs.pop(child_id, None)
            if child:
                children_to_clean.append(child)
    for child in children_to_clean:
        if child.checkpoint_dir and child.checkpoint_dir.exists():
            shutil.rmtree(child.checkpoint_dir, ignore_errors=True)


def _store_run(state: RunState) -> None:
    """Store a run state. Evicts terminal runs when threshold exceeded."""
    with _runs_lock:
        _runs[state.run_id] = state
        if len(_runs) > _EVICTION_THRESHOLD:
            _evict_terminal_runs()


def _evict_terminal_runs() -> None:
    """Remove terminal runs from _runs. Must be called with _runs_lock held."""
    # Collect all run_ids referenced by any parent's child_run_ids
    referenced: set[str] = set()
    for s in _runs.values():
        referenced.update(s.child_run_ids)

    to_remove = [
        rid
        for rid, s in _runs.items()
        if s.status in _TERMINAL_RUN_STATUSES
        and not s.child_run_ids  # don't evict parents with children still around
        and rid not in referenced  # don't evict children still referenced by a parent
    ]
    for rid in to_remove:
        del _runs[rid]
    if to_remove:
        logger.debug(
            "evicted %d terminal runs, %d remaining", len(to_remove), len(_runs)
        )


def _get_run(run_id: str) -> RunState | None:
    """Get a run state by ID."""
    with _runs_lock:
        return _runs.get(run_id)


def _verify_child_runs(state: RunState, submit_status: str) -> str | None:
    """Verify child runs completed before accepting a subagent/parallel submit.

    Returns an error message if verification fails, None if OK.
    Skips verification when:
      - The pending action is not a relay subagent or parallel
      - The agent reports failure (status != "success") — let it through
    """
    last = state._last_action
    if not last:
        return None

    action_type = last.action
    if action_type not in ("subagent", "parallel"):
        return None
    if isinstance(last, SubagentAction) and not last.relay:
        return None  # single-task subagent, no child run to verify
    if submit_status != "success":
        return None  # agent reported failure, accept it

    if isinstance(last, SubagentAction):
        child_id = last.child_run_id
        if not child_id:
            return None
        child = _get_run(child_id)
        if child is None:
            return (
                f"Child run {child_id} not found. "
                "The sub-relay may not have executed. "
                "Ensure the agent calls next() and submit() on the child_run_id."
            )
        if child.status not in ("completed", "halted"):
            return (
                f"Child run {child_id} has status '{child.status}', expected 'completed'. "
                "The sub-relay did not finish. Do not fabricate results — "
                "run the relay loop to completion or submit with status='failure'."
            )

    elif isinstance(last, ParallelAction):
        incomplete = []
        missing = []
        for lane in last.lanes:
            child_id = lane.child_run_id
            if not child_id:
                continue
            child = _get_run(child_id)
            if child is None:
                missing.append(child_id)
            elif child.status not in ("completed", "halted"):
                incomplete.append(f"{child_id} (status={child.status})")
        if missing:
            return (
                f"Parallel lane child runs not found: {', '.join(missing)}. "
                "The sub-relay agents may not have executed."
            )
        if incomplete:
            return (
                f"Parallel lane child runs not completed: {', '.join(incomplete)}. "
                "All lanes must finish before submitting to the parent."
            )

    return None


def _collect_parallel_results(state: RunState) -> list[Any] | None:
    """Collect structured_output from parallel lane child states.

    Child runs inherit a copy of the parent's results_scoped at spawn time.
    We filter those out to collect only child-produced leaf results.

    Returns a flat list of outputs (one per leaf step across all lanes),
    or None if no data is available.  Prefers structured_output; falls
    back to output text.
    """
    last = state._last_action
    if not isinstance(last, ParallelAction):
        return None

    results: list[Any] = []
    for lane in last.lanes:
        child = _get_run(lane.child_run_id)
        if child is None:
            continue
        # Collect leaf results that belong to the child (not inherited from parent)
        for key, r in child.ctx.results_scoped.items():
            if key in state.ctx.results_scoped:
                continue  # inherited from parent
            if r.structured_output is not None:
                results.append(r.structured_output)
            elif r.output:
                results.append(r.output)

    return results if results else None


def _check_child_halt(state: RunState) -> tuple[str, str] | None:
    """Check if any child run has halted. Returns (reason, halted_at) or None."""
    last = state._last_action
    if not last:
        return None

    child_ids: list[str] = []
    if isinstance(last, SubagentAction) and last.relay and last.child_run_id:
        child_ids = [last.child_run_id]
    elif isinstance(last, ParallelAction):
        child_ids = [lane.child_run_id for lane in last.lanes]

    for cid in child_ids:
        child = _get_run(cid)
        if child and child.status == "halted":
            halted = child._last_action
            if isinstance(halted, HaltedAction):
                return halted.reason, halted.halted_at
            logger.warning(
                "child %s is halted but _last_action is %s, not HaltedAction",
                cid,
                type(halted).__name__ if halted else "None",
            )

    return None


def _auto_advance(
    state: RunState,
    action: ActionBase,
    children: list[RunState],
) -> tuple[ActionBase, list[RunState]]:
    """Auto-advance through shell steps, executing them internally.

    Loops while the current action is "shell", executes each via subprocess,
    submits the result, and continues until a non-shell action is reached.
    Accumulates a _shell_log on the final returned action for debugging.
    """
    shell_log: list[dict[str, Any]] = []
    all_children = list(children)

    while isinstance(action, ShellAction):
        ek = action.exec_key
        logger.debug("auto-advance shell: exec_key=%s", ek)
        t0 = time.monotonic()

        # Resolve stdin content from dotpath if specified
        stdin_data: str | None = None
        if action.stdin:
            resolved = state.ctx.get_var(action.stdin)
            if resolved is not None:
                if isinstance(resolved, (dict, list)):
                    stdin_data = json.dumps(resolved)
                else:
                    stdin_data = str(resolved)

        output, status, structured, error = _execute_shell(
            action.command,
            state.ctx.cwd,
            env=action.env,
            script_path=action.script_path,
            args=action.args or "",
            stdin_data=stdin_data,
            timeout=action.timeout,
        )
        duration = round(time.monotonic() - t0, 3)

        artifact_ref: str | None = None
        if state.artifacts_dir:
            artifact_ref = write_shell_artifacts(
                state.artifacts_dir,
                ek,
                action.command,
                output or "",
                error,
                structured,
            )

        if artifact_ref is not None:
            shell_log.append(
                {
                    "exec_key": ek,
                    "status": status,
                    "duration": duration,
                    "artifact": artifact_ref,
                }
            )
        else:
            shell_log.append(
                {
                    "exec_key": ek,
                    "command": action.command,
                    "status": status,
                    "output": (output or "")[:2000],
                    "duration": duration,
                }
            )

        try:
            action, new_children = apply_submit(
                state,
                exec_key=ek,
                output=output,
                structured_output=structured,
                status=status,
                error=error,
                duration=duration,
            )
        except Exception:
            logger.exception("apply_submit failed for exec_key=%s", ek)
            raise
        all_children.extend(new_children)
        checkpoint_save(state)

    logger.debug(
        "auto-advance done: %d shell steps, next action=%s",
        len(shell_log),
        action.action,
    )
    if shell_log:
        action.shell_log = shell_log

    return action, all_children


def _collect_subworkflow_results(state: RunState, child_run_id: str) -> None:
    """Merge child results into parent state by looking up child run."""
    child = _get_run(child_run_id)
    if child is None:
        return
    merge_child_results(
        state.ctx.results_scoped,
        state.ctx.results,
        child.ctx.results_scoped,
    )
    state.ctx._order_seq = max(state.ctx._order_seq, child.ctx._order_seq)


def _cascade_to_parent(
    child_state: RunState,
    parent_exec_key: str,
) -> tuple[ActionBase, list[RunState]]:
    """Cascade a completed inline SubWorkflow child to its parent.

    Collects child results into parent, applies submit, auto-advances,
    and saves checkpoint. Returns the parent's next (action, children).
    """
    parent_run_id = child_state.parent_run_id
    if parent_run_id is None:
        return ErrorAction(
            run_id=child_state.run_id,
            message=f"No parent_run_id for cascade from {child_state.run_id}",
        ), []
    parent = _get_run(parent_run_id)
    if parent is None:
        return ErrorAction(
            run_id=parent_run_id,
            message=f"Parent run not found for cascade from {child_state.run_id}",
        ), []
    _collect_subworkflow_results(parent, child_state.run_id)
    action, children = apply_submit(
        parent,
        parent_exec_key,
        output="child-completed",
        status="success",
    )
    action, children = _auto_advance(parent, action, children)
    checkpoint_save(parent)

    # Nested cascade: if parent itself is an inline child and just completed,
    # cascade up to the grandparent. Without this, the parent's "completed"
    # action gets rewritten to the grandparent's run_id by _route_to_inline_child
    # without actually advancing the grandparent's state.
    if (
        action.action == "completed"
        and parent._inline_parent_exec_key
        and parent.parent_run_id
    ):
        return _cascade_to_parent(parent, parent._inline_parent_exec_key)

    return action, children


def _write_terminal_meta(state: RunState, action: ActionBase) -> None:
    """Write terminal meta.json with totals. Called on completed/error/halted.

    Extracts the logic previously inline in submit() so it can be reused
    by start() and the parallel fast path.
    """
    if not isinstance(action, (CompletedAction, ErrorAction, HaltedAction)):
        return
    if not state.checkpoint_dir:
        return

    if isinstance(action, HaltedAction):
        terminal_status = "halted"
    elif isinstance(action, ErrorAction):
        terminal_status = "error"
    else:
        terminal_status = "completed"

    # For children, use block label instead of workflow name
    meta_workflow = state.workflow_name
    if state.parallel_block_name:
        meta_workflow = state.parallel_block_name
        if state.lane_index >= 0:
            meta_workflow = f"{meta_workflow}[{state.lane_index}]"

    totals = compute_totals(state.ctx.results_scoped)

    write_meta(
        state.checkpoint_dir,
        state.run_id,
        meta_workflow,
        state.ctx.cwd,
        terminal_status,
        state.started_at,
        completed_at=datetime.now(timezone.utc).isoformat(),
        total_cost_usd=totals.get("cost_usd"),
        total_duration=totals["duration"],
        steps_by_type=totals.get("steps_by_type"),
    )


def _advance_single_child(
    child: RunState,
) -> tuple[RunState, ActionBase, list[RunState]]:
    """Advance child to first action, auto-advancing shell steps.

    Thread-safe: only modifies the child RunState and its checkpoint dir.
    Does NOT call _store_run — caller is responsible.
    On exception: catches, logs, returns ErrorAction for this lane.
    """
    try:
        if child.checkpoint_dir:
            block_label = child.parallel_block_name
            if child.lane_index >= 0:
                block_label = f"{block_label}[{child.lane_index}]"
            write_meta(
                child.checkpoint_dir,
                child.run_id,
                block_label or child.workflow_name,
                child.ctx.cwd,
                "running",
                child.started_at,
            )
        child_action, grandchildren = advance(child)
        child_action, grandchildren = _auto_advance(child, child_action, grandchildren)
        checkpoint_save(child)
        return child, child_action, grandchildren
    except Exception as exc:
        logger.exception("_advance_single_child failed: %s", child.run_id)
        child.status = "error"
        try:
            checkpoint_save(child)
        except Exception as save_exc:
            logger.warning(
                "checkpoint_save failed for errored child %s: %s",
                child.run_id,
                save_exc,
            )
        return (
            child,
            ErrorAction(
                run_id=child.run_id,
                message=f"Lane advance failed: {type(exc).__name__}: {exc}",
            ),
            [],
        )


def _derive_parallel_status(
    parent: RunState,
    results: list[tuple[RunState, ActionBase, list[RunState]]],
) -> str:
    """Derive parent submit status from lane results.

    Checks child-produced leaf StepResults (excluding inherited parent results).
    Returns "failure" if any lane has a failed leaf result or ErrorAction,
    "success" otherwise.
    """
    for child, child_action, _ in results:
        if child_action.action == "error":
            return "failure"
        for key, r in child.ctx.results_scoped.items():
            if key in parent.ctx.results_scoped:
                continue  # inherited from parent
            if r.status == "failure":
                return "failure"
    return "success"


def _merge_shell_logs(
    action: ActionBase,
    results: list[tuple[RunState, ActionBase, list[RunState]]],
) -> list[dict[str, Any]]:
    """Merge shell logs from parent action + all lanes, ordered by lane_index."""
    logs = list(action.shell_log or [])
    for _child, ca, _ in sorted(results, key=lambda r: r[0].lane_index):
        logs.extend(ca.shell_log or [])
    return logs


def _try_parallel_fast_path(
    action: ParallelAction,
    results: list[tuple[RunState, ActionBase, list[RunState]]],
) -> str | None:
    """Attempt to skip relay when all parallel lanes are terminal.

    Returns JSON response string if fast path succeeded, None to fall through.
    """
    if not all(ca.action in _TERMINAL_ACTION_TYPES for _, ca, _ in results):
        return None

    parent = _get_run(action.run_id)
    if parent is None:
        logger.error("parallel fast-path: parent %s not found", action.run_id)
        return None

    # Write terminal meta for each child
    for child, child_action, _ in results:
        _write_terminal_meta(child, child_action)

    # Check halt propagation — route through apply_submit boundary
    child_halt = _check_child_halt(parent)
    if child_halt:
        reason, halted_at = child_halt
        parent_action, _ = apply_submit(
            parent,
            action.exec_key,
            output="parallel-halted",
            status="success",
            halt_reason=reason,
            halt_origin=halted_at,
        )
        _write_terminal_meta(parent, parent_action)
        checkpoint_save(parent)
        _store_run(parent)
        all_logs = _merge_shell_logs(action, results)
        if all_logs:
            parent_action.shell_log = all_logs
        return json.dumps(action_to_dict(parent_action), default=str)

    # Derive parent status from lane leaf results
    merged = _collect_parallel_results(parent)
    parent_status = _derive_parallel_status(parent, results)

    parent_action, parent_children = apply_submit(
        parent,
        action.exec_key,
        output="parallel-auto-completed",
        structured_output=merged,
        status=parent_status,
    )
    parent_action, parent_children = _auto_advance(
        parent,
        parent_action,
        parent_children,
    )

    all_logs = _merge_shell_logs(action, results)
    if all_logs:
        existing = list(parent_action.shell_log or [])
        parent_action.shell_log = all_logs + existing

    _write_terminal_meta(parent, parent_action)
    checkpoint_save(parent)
    _store_run(parent)
    return _action_response(parent_action, parent_children)


def _action_response(action: ActionBase, children: list[RunState] | None = None) -> str:
    """Convert action model to JSON response, storing any child states.

    Child states are advanced to their first action (auto-advancing through
    any shell steps) so that next(child_run_id) returns the first pending
    non-shell action immediately.

    For ParallelAction with _PARALLEL_AUTO_ADVANCE enabled:
    - Children are advanced in parallel via ThreadPoolExecutor
    - If all children reach terminal state (shell-only lanes), auto-submits
      the parent, skipping the relay entirely

    For inline SubWorkflow children (_inline_parent_exec_key set):
    - Shell-only child auto-completes → cascade to parent
    - Child has pending action → return child's action to relay
    """
    if children and isinstance(action, ParallelAction) and _PARALLEL_AUTO_ADVANCE:
        return _action_response_parallel(action, children)
    if children:
        return _action_response_sequential(action, children)

    resp = json.dumps(action_to_dict(action), default=str)
    logger.debug("action_response: %s", resp[:300])
    return resp


def _action_response_parallel(
    action: ParallelAction,
    children: list[RunState],
) -> str:
    """Handle parallel children: advance in parallel, attempt fast path."""
    logger.debug("action_response: parallel auto-advance %d child(ren)", len(children))
    n_workers = min(len(children), _PARALLEL_MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        results = list(pool.map(_advance_single_child, children))

    # Store all under lock
    for child, _ca, grandchildren in results:
        for gc in grandchildren:
            _store_run(gc)
        _store_run(child)

    # Attempt fast path (all terminal → skip relay)
    fast = _try_parallel_fast_path(action, results)
    if fast is not None:
        return fast

    # Not all terminal → return ParallelAction for relay
    resp = json.dumps(action_to_dict(action), default=str)
    logger.debug("action_response: %s", resp[:300])
    return resp


def _action_response_sequential(
    action: ActionBase,
    children: list[RunState],
) -> str:
    """Handle sequential children (inline SubWorkflow etc.)."""
    logger.debug("action_response: advancing %d child run(s)", len(children))
    for child in children:
        # Write initial meta.json for child
        if child.checkpoint_dir:
            block_label = child.parallel_block_name
            if child.lane_index >= 0:
                block_label = f"{block_label}[{child.lane_index}]"
            write_meta(
                child.checkpoint_dir,
                child.run_id,
                block_label or child.workflow_name,
                child.ctx.cwd,
                "running",
                child.started_at,
            )
        # Advance child to its first action so next() works
        child_action, grandchildren = advance(child)
        child_action, grandchildren = _auto_advance(
            child,
            child_action,
            grandchildren,
        )
        for gc in grandchildren:
            _store_run(gc)
        _store_run(child)
        checkpoint_save(child)

        # Inline SubWorkflow child: handle shell-only cascade or return child's action
        if child._inline_parent_exec_key:
            return _handle_inline_child(action, child, child_action)

    resp = json.dumps(action_to_dict(action), default=str)
    logger.debug("action_response: %s", resp[:300])
    return resp


def _handle_inline_child(
    parent_action: ActionBase,
    child: RunState,
    child_action: ActionBase,
) -> str:
    """Handle inline SubWorkflow child: cascade or proxy."""
    prior_logs = (parent_action.shell_log or []) + (child_action.shell_log or [])

    if child_action.action == "completed":
        # Shell-only child auto-completed → cascade to parent
        cascaded_action, cascaded_children = _cascade_to_parent(
            child,
            child._inline_parent_exec_key,
        )
        if prior_logs:
            existing = cascaded_action.shell_log or []
            cascaded_action.shell_log = prior_logs + existing
        return _action_response(cascaded_action, cascaded_children)

    # Child has pending action → proxy transparently through parent run_id
    parent_rid = child.parent_run_id
    if parent_rid:
        parent = _get_run(parent_rid)
        if parent:
            parent._active_inline_child_id = child.run_id
            checkpoint_save(parent)
        child_action.run_id = parent_rid
    if prior_logs:
        child_action.shell_log = prior_logs
    resp = json.dumps(action_to_dict(child_action), default=str)
    logger.debug("action_response (transparent child): %s", resp[:300])
    return resp


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
        bool, "Include _shell_log in responses (off by default to save tokens)"
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
            # Successful resume
            result.is_resumed = True
            loaded_children = checkpoint_load_children(result, registry)
            if loaded_children:
                result._resume_children = loaded_children
                for block_children in loaded_children.values():
                    for child in block_children:
                        child.is_resumed = True
                        # Skip advancing terminal children — their results are
                        # already merged by _resume_subworkflow_child.  Advancing
                        # them would fail because the sub-workflow scope was
                        # popped on completion and is missing from the checkpoint.
                        if child.status not in ("completed", "cancelled"):
                            child_action, grandchildren = advance(child)
                            child_action, grandchildren = _auto_advance(
                                child,
                                child_action,
                                grandchildren,
                            )
                            for gc in grandchildren:
                                _store_run(gc)
                        _store_run(child)
                        checkpoint_save(child)

            _store_run(result)
            action, children = advance(result)
            # Handle cross-run-id actions (inline SubWorkflow resume)
            target = result
            if action.run_id != result.run_id:
                child_state = _get_run(action.run_id)
                if child_state:
                    target = child_state
            action, children = _auto_advance(target, action, children)
            checkpoint_save(target)
            if target != result:
                checkpoint_save(result)
                # Check cascade: child completed → merge into parent
                if action.action == "completed" and target.parent_run_id:
                    parent = _get_run(target.parent_run_id)
                    if parent is not None and parent.pending_exec_key:
                        action, children = _cascade_to_parent(
                            target,
                            parent.pending_exec_key,
                        )
            action.resumed = True
            return _action_response(action, children)

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
    run_id = uuid.uuid4().hex[:12]

    variables["run_id"] = run_id
    variables.setdefault(
        "workflow_dir", str(Path(wf.source_path).parent) if wf.source_path else ""
    )
    variables.setdefault(
        "clean_dir", str(checkpoint_dir_from_run_id(cwd_path, run_id) / "clean")
    )

    ctx = WorkflowContext(
        variables=variables,
        cwd=str(cwd_path),
        dry_run=dry_run,
        prompt_dir=wf.prompt_dir,
    )

    state = RunState(
        run_id=run_id,
        ctx=ctx,
        stack=[Frame(block=wf)],
        registry=registry,
        wf_hash=workflow_hash(wf),
        checkpoint_dir=checkpoint_dir_from_run_id(cwd_path, run_id),
        workflow_name=workflow,
    )
    _store_run(state)

    assert state.checkpoint_dir is not None
    write_meta(
        state.checkpoint_dir,
        run_id,
        workflow,
        str(cwd_path),
        "running",
        state.started_at,
    )

    action, children = advance(state)
    action, children = _auto_advance(state, action, children)
    if not checkpoint_save(state) and action.action not in ("error", "completed"):
        action.warnings.append("checkpoint write failed")
    if resume_warning:
        action.warnings.append(resume_warning)
    # Write terminal meta for workflows that complete entirely during start()
    _write_terminal_meta(state, action)
    return _action_response(action, children)


def _route_to_inline_child(
    state: RunState,
    run_id: str,
    exec_key: str,
    output: str,
    structured_output: StructuredOutput,
    status: str,
    error: str | None,
    duration: float,
    cost_usd: float | None,
    model: str | None,
) -> str | None:
    """Route submit to active inline child. Returns JSON response or None."""
    if not state._active_inline_child_id:
        return None
    child = _get_run(state._active_inline_child_id)
    if not child or child.status in ("completed", "error", "cancelled", "halted"):
        return None

    logger.info("submit: routing to transparent child %s", child.run_id)
    result_json = submit(
        run_id=child.run_id,
        exec_key=exec_key,
        output=output,
        structured_output=structured_output,
        status=status,
        error=error,
        duration=duration,
        cost_usd=cost_usd,
        model=model,
    )
    result = json.loads(result_json)
    if result.get("run_id") == child.run_id:
        # Child still active — rewrite run_id to parent
        result["run_id"] = run_id
        state._active_inline_child_id = child.run_id
        checkpoint_save(state)
        return json.dumps(result, default=str)
    # Child completed and cascaded
    if state._active_inline_child_id == child.run_id:
        state._active_inline_child_id = ""
    checkpoint_save(state)
    return result_json


@mcp.tool()
def submit(
    run_id: str,
    exec_key: str,
    output: str = "",
    structured_output: StructuredOutput = None,
    status: str = "success",
    error: str | None = None,
    duration: float = 0.0,
    cost_usd: float | None = None,
    model: str | None = None,
    shell_log: bool = False,
) -> str:
    """Submit result for an exec_key, return next action. Idempotent.

    Works on both parent and child run_ids.

    Args:
        run_id: The run ID (parent or child).
        exec_key: The exec_key of the action being submitted.
        output: Text output from the action.
        structured_output: Structured output (for schema validation).
        status: Result status ("success" or "failure").
        error: Error message if status is "failure".
        duration: Duration of the action in seconds.
        cost_usd: Cost of the action in USD.
        model: Model used for the step (for LLM steps).
        shell_log: Include _shell_log in response.
    """
    _set_shell_log(shell_log)
    logger.info(
        "submit(run_id=%s, exec_key=%s, status=%s, output=%s)",
        run_id,
        exec_key,
        status,
        (output[:100] if output else ""),
    )
    state = _get_run(run_id)
    if state is None:
        logger.error("submit: unknown run_id=%s", run_id)
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"Unknown run_id: {run_id}",
                )
            )
        )

    # Transparent SubWorkflow: route submit to active inline child
    routed = _route_to_inline_child(
        state,
        run_id,
        exec_key,
        output,
        structured_output,
        status,
        error,
        duration,
        cost_usd,
        model,
    )
    if routed is not None:
        return routed

    # Only run child-run verification when the exec_key actually matches
    # the pending action.  Wrong exec_key or idempotent replays are handled
    # by apply_submit, so we let those through without masking.
    verification_error = (
        _verify_child_runs(state, status)
        if exec_key == state.pending_exec_key
        else None
    )
    if verification_error:
        logger.warning(
            "submit: child run verification failed for run_id=%s: %s",
            run_id,
            verification_error,
        )
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=verification_error,
                    exec_key=state.pending_exec_key,
                    display=f"Error: {verification_error}",
                )
            )
        )

    # Halt propagation: if a child run halted, route through apply_submit
    if exec_key == state.pending_exec_key and status == "success":
        halt_info = _check_child_halt(state)
        if halt_info:
            child_reason, child_halted_at = halt_info
            action, _ = apply_submit(
                state,
                exec_key,
                output=output,
                status=status,
                halt_reason=child_reason,
                halt_origin=child_halted_at,
            )
            _write_terminal_meta(state, action)
            checkpoint_save(state)
            return json.dumps(action_to_dict(action), default=str)

    # Capture action type before apply_submit overwrites _last_action
    prev_action_type = state._last_action.action if state._last_action else None

    # Auto-merge parallel lane results: collect structured_output from
    # child states so downstream steps see all lane data, not just the
    # relay's text summary.
    if prev_action_type == "parallel" and exec_key == state.pending_exec_key:
        merged = _collect_parallel_results(state)
        if merged:
            structured_output = merged

    # Auto-merge SubWorkflow child results for subagent path
    if (
        prev_action_type == "subagent"
        and exec_key == state.pending_exec_key
        and isinstance(state._last_action, SubagentAction)
        and state._last_action.relay
        and state._last_action.child_run_id
    ):
        _collect_subworkflow_results(state, state._last_action.child_run_id)

    # File-based result: when relay writes result to result_dir instead of
    # passing inline, read structured_output from the artifact file.
    if (
        not output
        and structured_output is None
        and status == "success"
        and state.artifacts_dir
        and prev_action_type in ("prompt", "subagent")
    ):
        result_file = (
            state.artifacts_dir / exec_key_to_artifact_path(exec_key) / "result.json"
        )
        if result_file.is_file():
            try:
                structured_output = json.loads(result_file.read_text(encoding="utf-8"))
                logger.debug("submit: read structured_output from %s", result_file)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "submit: failed to read result file %s: %s", result_file, exc
                )

    try:
        action, children = apply_submit(
            state,
            exec_key=exec_key,
            output=output,
            structured_output=structured_output,
            status=status,
            error=error,
            duration=duration,
            cost_usd=cost_usd,
            model=model,
        )
    except Exception:
        logger.exception(
            "submit: apply_submit failed for run_id=%s exec_key=%s", run_id, exec_key
        )
        raise

    # Write LLM output artifact for prompt/subagent steps
    if (
        state.artifacts_dir
        and prev_action_type in ("prompt", "subagent")
        and (output or structured_output is not None)
    ):
        write_llm_output_artifact(
            state.artifacts_dir,
            exec_key,
            output,
            structured=structured_output,
        )

    # Handle cancellation from server-side validation (user picked "Stop workflow")
    if isinstance(action, CancelledAction):
        _cleanup_run(state)
        return json.dumps(action_to_dict(action), default=str)

    # Handle halt — workflow stopped by a halt directive
    if isinstance(action, HaltedAction):
        _write_terminal_meta(state, action)
        checkpoint_save(state)
        return json.dumps(action_to_dict(action), default=str)

    try:
        action, children = _auto_advance(state, action, children)
    except Exception:
        logger.exception("submit: auto_advance failed for run_id=%s", run_id)
        raise

    # Inline SubWorkflow child completed → cascade to parent
    # Only for inline SubWorkflow children (not parallel lanes)
    if (
        action.action == "completed"
        and state._inline_parent_exec_key
        and state.parent_run_id
    ):
        checkpoint_save(state)
        parent_action, parent_children = _cascade_to_parent(
            state,
            state._inline_parent_exec_key,
        )
        logger.info("submit: cascade to parent %s", state.parent_run_id)
        return _action_response(parent_action, parent_children)

    logger.info(
        "submit: next action=%s exec_key=%s",
        action.action,
        getattr(action, "exec_key", None),
    )
    if not checkpoint_save(state) and action.action not in ("error", "completed"):
        action.warnings.append("checkpoint write failed")

    # Update meta.json on terminal states
    _write_terminal_meta(state, action)

    return _action_response(action, children)


@mcp.tool()
def next(run_id: str, shell_log: bool = False) -> str:
    """Re-fetch current pending action without mutating state. Recovery tool.

    Args:
        run_id: The run ID to query.
        shell_log: Include _shell_log in response.
    """
    _set_shell_log(shell_log)
    logger.debug("next(run_id=%s)", run_id)
    state = _get_run(run_id)
    if state is None:
        logger.error("next: unknown run_id=%s", run_id)
        return json.dumps(
            action_to_dict(
                ErrorAction(
                    run_id=run_id,
                    message=f"Unknown run_id: {run_id}",
                )
            )
        )

    # Transparent SubWorkflow: return child's pending action with parent run_id
    if state._active_inline_child_id:
        child = _get_run(state._active_inline_child_id)
        if child and child.status not in ("completed", "error", "cancelled", "halted"):
            child_action = pending_action(child)
            child_action.run_id = run_id  # proxy through parent
            logger.debug("next (transparent child): action=%s", child_action.action)
            return json.dumps(action_to_dict(child_action), default=str)

    action = pending_action(state)
    logger.debug(
        "next: action=%s exec_key=%s", action.action, getattr(action, "exec_key", None)
    )
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

    state.status = "cancelled"
    _cleanup_run(state)

    return json.dumps(
        action_to_dict(
            CancelledAction(
                run_id=run_id,
            )
        )
    )


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

    result = {
        "run_id": state.run_id,
        "status": state.status,
        "pending_exec_key": state.pending_exec_key,
        "parent_run_id": state.parent_run_id,
        "child_run_ids": state.child_run_ids,
        "protocol_version": state.protocol_version,
        "results_count": len(state.ctx.results_scoped),
        "stack_depth": len(state.stack),
        "warnings": state.warnings,
    }

    # Include child run statuses
    child_statuses = {}
    for child_id in state.child_run_ids:
        child = _get_run(child_id)
        if child:
            child_statuses[child_id] = {
                "status": child.status,
                "pending_exec_key": child.pending_exec_key,
            }
    if child_statuses:
        result["children"] = child_statuses

    return json.dumps(result, default=str)


@mcp.tool()
def open_dashboard(cwd: str = "") -> str:
    """Open the workflow dashboard in a browser. Auto-selects a free port.

    Each project gets its own dashboard instance. Multiple projects can
    run dashboards simultaneously on different ports. Reuses an existing
    instance if one is already running.

    Args:
        cwd: Project directory containing .workflow-state/
    """
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
    from .infra.cleanup import cleanup

    result = cleanup(
        cwd or ".",
        before=before,
        status=status_filter,
        keep=keep,
        dry_run=dry_run,
        remove_all=remove_all,
    )
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
