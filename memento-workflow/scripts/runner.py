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
import platform
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, NamedTuple

from mcp.server.fastmcp import FastMCP

from .checkpoint import checkpoint_load, checkpoint_save
from .core import Frame, RunState
from .loader import discover_workflows
from .protocol import (
    ActionBase,
    CancelledAction,
    ErrorAction,
    ShellAction,
    action_to_dict,
)
from .state import advance, apply_submit, pending_action
from .types import WorkflowContext, WorkflowDef
from .utils import workflow_hash


class ShellResult(NamedTuple):
    """Result from _execute_shell()."""
    output: str
    status: str
    structured: dict[str, Any] | None
    error: str | None

logger = logging.getLogger("workflow-engine")

# In-memory storage for active runs (parent + child)
_runs: dict[str, RunState] = {}

# MCP server instance
mcp = FastMCP("memento-workflow")

# Engine root: runner.py → scripts → memento-workflow
ENGINE_ROOT = Path(__file__).resolve().parents[1]

# Sandbox: opt-out via MEMENTO_SANDBOX=off
SANDBOX_ENABLED = os.environ.get("MEMENTO_SANDBOX", "auto") != "off"


def _seatbelt_profile(write_paths: list[str]) -> str:
    """Generate a macOS Seatbelt sandbox profile.

    Default policy: allow all reads (deny sensitive dirs), deny all writes
    except to specified paths. Resolves symlinks for macOS (/tmp → /private/tmp).
    """
    resolved = [str(Path(p).resolve()) for p in write_paths]
    allow_clauses = "\n".join(f'  (subpath "{p}")' for p in resolved)
    return f"""(version 1)
(allow default)
(deny file-write*)
(allow file-write*
{allow_clauses}
  (literal "/dev/null")
  (regex #"^/dev/fd/"))
(deny file-read*
  (subpath "{Path.home() / '.ssh'}")
  (subpath "{Path.home() / '.aws'}")
  (subpath "{Path.home() / '.gnupg'}"))"""


def _sandbox_prefix(cwd: str) -> list[str]:
    """Return command prefix for sandboxed execution, or [] if unavailable.

    Skips if the process is already sandboxed (set by serve.py).
    """
    if not SANDBOX_ENABLED:
        return []
    if os.environ.get("_MEMENTO_SANDBOXED"):
        return []
    write_paths = [cwd, "/tmp"]
    if platform.system() == "Darwin":
        return ["sandbox-exec", "-p", _seatbelt_profile(write_paths)]
    if shutil.which("bwrap"):
        args = ["bwrap", "--ro-bind", "/", "/"]
        for wp in write_paths:
            p = Path(wp)
            if p.exists():
                args.extend(["--bind", str(p), str(p)])
        args.extend(["--dev", "/dev", "--proc", "/proc"])
        return args
    logger.warning("Sandbox not available (install bubblewrap on Linux)")
    return []


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

    logger.debug("Discovering workflows in %d paths: %s", len(search_paths), search_paths)
    registry = discover_workflows(*search_paths)
    logger.info("Discovered %d workflows: %s", len(registry), sorted(registry.keys()))
    return registry


def _cleanup_run(state: RunState) -> None:
    """Remove checkpoint files and in-memory state for a run and its children."""
    if state.checkpoint_dir and state.checkpoint_dir.exists():
        checkpoint_file = state.checkpoint_dir / "state.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
        try:
            state.checkpoint_dir.rmdir()
        except OSError:
            pass
    _runs.pop(state.run_id, None)
    for child_id in state.child_run_ids:
        child = _runs.pop(child_id, None)
        if child and child.checkpoint_dir:
            cp = child.checkpoint_dir / "state.json"
            if cp.exists():
                cp.unlink()
            try:
                child.checkpoint_dir.rmdir()
            except OSError:
                pass


def _store_run(state: RunState) -> None:
    """Store a run state and any child states."""
    _runs[state.run_id] = state


def _get_run(run_id: str) -> RunState | None:
    """Get a run state by ID."""
    return _runs.get(run_id)


def _verify_child_runs(state: RunState, submit_status: str) -> str | None:
    """Verify child runs completed before accepting a subagent/parallel submit.

    Returns an error message if verification fails, None if OK.
    Skips verification when:
      - The pending action is not a relay subagent or parallel
      - The agent reports failure (status != "success") — let it through
    """
    from .protocol import ParallelAction, SubagentAction

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
        if child.status != "completed":
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
            elif child.status != "completed":
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


def _execute_shell(
    command: str, cwd: str,
    env: dict[str, str] | None = None,
    script_path: str | None = None,
    args: str = "",
    stdin_data: str | None = None,
) -> ShellResult:
    """Execute a shell command internally via subprocess.

    If script_path is set (absolute path), determines interpreter from extension
    (.py → python3, else bash) and runs as argv list (shell=False) for safety.
    If env is set, merges with os.environ.
    If stdin_data is set, pipes it as stdin to the subprocess.

    Commands run inside an OS-level sandbox (macOS Seatbelt / Linux bubblewrap)
    that restricts writes to cwd and /tmp. Disable with MEMENTO_SANDBOX=off.

    Returns (output, status, structured_output, error).
    """
    merged_env = None
    if env:
        merged_env = {**os.environ, **env}

    sandbox = _sandbox_prefix(cwd)

    cmd_argv: list[str]

    if script_path:
        ext = Path(script_path).suffix
        interpreter = "python3" if ext == ".py" else "bash"
        cmd_argv = [interpreter, script_path]
        if args:
            cmd_argv.extend(shlex.split(args))
        command = " ".join(cmd_argv)  # for logging/display only
    else:
        cmd_argv = ["bash", "-c", command]

    cmd_argv = [*sandbox, *cmd_argv]

    logger.debug("shell exec: %s (cwd=%s, sandbox=%s)", command[:200], cwd, bool(sandbox))
    try:
        proc = subprocess.run(
            cmd_argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cwd,
            env=merged_env,
            input=stdin_data,
        )
        output = proc.stdout.strip()
        error = proc.stderr.strip() if proc.returncode != 0 else None
        status = "success" if proc.returncode == 0 else "failure"
        structured: dict[str, Any] | None = None
        if output:
            try:
                structured = json.loads(output)
            except (json.JSONDecodeError, ValueError):
                pass
        logger.debug("shell result: status=%s output=%s", status, output[:200] if output else "")
        if error:
            logger.warning("shell stderr: %s", error[:300])
        return ShellResult(output, status, structured, error)
    except subprocess.TimeoutExpired:
        logger.error("shell timeout (120s): %s", command[:200])
        return ShellResult("", "failure", None, "Command timed out after 120s")
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("shell exception: %s", e)
        return ShellResult("", "failure", None, str(e))


def _auto_advance(
    state: RunState, action: ActionBase, children: list[RunState],
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
                stdin_data = str(resolved)

        output, status, structured, error = _execute_shell(
            action.command, state.ctx.cwd,
            env=action.env,
            script_path=action.script_path,
            args=action.args or "",
            stdin_data=stdin_data,
        )
        duration = round(time.monotonic() - t0, 3)

        shell_log.append({
            "exec_key": ek,
            "command": action.command,
            "status": status,
            "output": output[:500] if output else "",
            "duration": duration,
        })

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
        len(shell_log), action.action,
    )
    if shell_log:
        action.shell_log = shell_log

    return action, all_children


def _action_response(action: ActionBase, children: list[RunState] | None = None) -> str:
    """Convert action model to JSON response, storing any child states.

    Child states are advanced to their first action (auto-advancing through
    any shell steps) so that next(child_run_id) returns the first pending
    non-shell action immediately.
    """
    if children:
        logger.debug("action_response: advancing %d child run(s)", len(children))
        for child in children:
            # Advance child to its first action so next() works
            child_action, grandchildren = advance(child)
            # Auto-advance through shell steps in child
            child_action, grandchildren = _auto_advance(
                child, child_action, grandchildren,
            )
            # Store grandchildren too (shouldn't happen — no subagent from child)
            for gc in grandchildren:
                _store_run(gc)
            _store_run(child)
    resp = json.dumps(action_to_dict(action), default=str)
    logger.debug("action_response: %s", resp[:300])
    return resp


@mcp.tool()
def start(
    workflow: str,
    variables: dict[str, Any] | None = None,
    cwd: str = "",
    workflow_dirs: list[str] | None = None,
    resume_run_id: str = "",
    dry_run: bool = False,
) -> str:
    """Start a workflow (or resume from checkpoint). Returns the first action with exec_key.

    Args:
        workflow: Name of the workflow to run.
        variables: Variables to inject into the workflow context.
        cwd: Working directory (defaults to current directory).
        workflow_dirs: Additional directories to search for workflows.
        resume_run_id: If set, resume an existing run from checkpoint.
        dry_run: If True, show steps without executing.
    """
    logger.info(
        "start(workflow=%s, cwd=%s, resume=%s, dry_run=%s, dirs=%s)",
        workflow, cwd, resume_run_id, dry_run, workflow_dirs,
    )
    variables = variables or {}
    workflow_dirs = workflow_dirs or []
    cwd = cwd or "."
    cwd_path = Path(cwd).resolve()

    if not cwd_path.is_dir():
        return json.dumps(action_to_dict(ErrorAction(
            run_id="",
            message=f"cwd is not an existing directory: {cwd}",
        )))

    registry = _discover(str(cwd_path), workflow_dirs)

    if resume_run_id:
        # Resume from checkpoint
        if workflow not in registry:
            return json.dumps(action_to_dict(ErrorAction(
                run_id=resume_run_id,
                message=f"Workflow '{workflow}' not found for resume",
            )))
        wf = registry[workflow]
        result = checkpoint_load(resume_run_id, cwd_path, registry, wf)
        if isinstance(result, str):
            return json.dumps(action_to_dict(ErrorAction(
                run_id=resume_run_id,
                message=result,
            )))
        _store_run(result)
        # Fast-forward past completed blocks (advance replays via results_scoped)
        action, children = advance(result)
        action, children = _auto_advance(result, action, children)
        checkpoint_save(result)
        return _action_response(action, children)

    # Fresh run
    if workflow not in registry:
        available = sorted(registry.keys())
        return json.dumps(action_to_dict(ErrorAction(
            run_id="",
            message=f"Workflow '{workflow}' not found. Available: {available}",
        )))

    wf = registry[workflow]
    run_id = uuid.uuid4().hex[:12]

    variables["run_id"] = run_id
    variables.setdefault("workflow_dir", str(Path(wf.source_path).parent) if wf.source_path else "")

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
        checkpoint_dir=cwd_path / ".workflow-state" / run_id,
    )
    _store_run(state)

    action, children = advance(state)
    action, children = _auto_advance(state, action, children)
    if not checkpoint_save(state) and action.action not in ("error", "completed"):
        if action.warnings is None:
            action.warnings = []
        action.warnings.append("checkpoint write failed")
    return _action_response(action, children)


@mcp.tool()
def submit(
    run_id: str,
    exec_key: str,
    output: str = "",
    structured_output: dict[str, Any] | None = None,
    status: str = "success",
    error: str | None = None,
    duration: float = 0.0,
    cost_usd: float | None = None,
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
    """
    logger.info(
        "submit(run_id=%s, exec_key=%s, status=%s, output=%s)",
        run_id, exec_key, status, (output[:100] if output else ""),
    )
    state = _get_run(run_id)
    if state is None:
        logger.error("submit: unknown run_id=%s", run_id)
        return json.dumps(action_to_dict(ErrorAction(
            run_id=run_id,
            message=f"Unknown run_id: {run_id}",
        )))

    # Only run child-run verification when the exec_key actually matches
    # the pending action.  Wrong exec_key or idempotent replays are handled
    # by apply_submit, so we let those through without masking.
    verification_error = (
        _verify_child_runs(state, status)
        if exec_key == state.pending_exec_key
        else None
    )
    if verification_error:
        logger.warning("submit: child run verification failed for run_id=%s: %s", run_id, verification_error)
        return json.dumps(action_to_dict(ErrorAction(
            run_id=run_id,
            message=verification_error,
            exec_key=state.pending_exec_key,
            display=f"Error: {verification_error}",
        )))

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
        )
    except Exception:
        logger.exception("submit: apply_submit failed for run_id=%s exec_key=%s", run_id, exec_key)
        raise
    # Handle cancellation from server-side validation (user picked "Stop workflow")
    if isinstance(action, CancelledAction):
        _cleanup_run(state)
        return json.dumps(action_to_dict(action), default=str)

    try:
        action, children = _auto_advance(state, action, children)
    except Exception:
        logger.exception("submit: auto_advance failed for run_id=%s", run_id)
        raise
    logger.info("submit: next action=%s exec_key=%s", action.action, getattr(action, "exec_key", None))
    if not checkpoint_save(state) and action.action not in ("error", "completed"):
        if action.warnings is None:
            action.warnings = []
        action.warnings.append("checkpoint write failed")
    return _action_response(action, children)


@mcp.tool()
def next(run_id: str) -> str:
    """Re-fetch current pending action without mutating state. Recovery tool.

    Args:
        run_id: The run ID to query.
    """
    logger.debug("next(run_id=%s)", run_id)
    state = _get_run(run_id)
    if state is None:
        logger.error("next: unknown run_id=%s", run_id)
        return json.dumps(action_to_dict(ErrorAction(
            run_id=run_id,
            message=f"Unknown run_id: {run_id}",
        )))

    action = pending_action(state)
    logger.debug("next: action=%s exec_key=%s", action.action, getattr(action, "exec_key", None))
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
        return json.dumps(action_to_dict(ErrorAction(
            run_id=run_id,
            message=f"Unknown run_id: {run_id}",
        )))

    state.status = "cancelled"
    _cleanup_run(state)

    return json.dumps(action_to_dict(CancelledAction(
        run_id=run_id,
    )))


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
        workflows.append({
            "name": name,
            "description": wf.description,
            "blocks": len(wf.blocks),
            "source": wf.source_path,
        })

    return json.dumps({"workflows": workflows})


@mcp.tool()
def status(run_id: str) -> str:
    """Get current workflow state (for debugging/monitoring).

    Args:
        run_id: The run ID to query.
    """
    state = _get_run(run_id)
    if state is None:
        return json.dumps(action_to_dict(ErrorAction(
            run_id=run_id,
            message=f"Unknown run_id: {run_id}",
        )))

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
