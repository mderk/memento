"""Checkpoint persistence for the workflow engine.

Provides checkpoint_save() and checkpoint_load() for durable state
across MCP server restarts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .core import PROTOCOL_VERSION, Frame, RunState
from .types import StepResult, WorkflowContext, WorkflowDef
from .utils import workflow_hash


def checkpoint_save(state: RunState) -> bool:
    """Atomically save run state to checkpoint file.

    Resume strategy: checkpoint stores results_scoped + variables (the deterministic
    outputs of all completed steps).  checkpoint_load() creates a fresh stack from the
    workflow root; advance() fast-forwards through completed blocks by checking
    exec_key in results_scoped, re-applying result_var side effects via _replay_skip().
    No block-path reconstruction is needed.

    Returns True on success, False on failure.
    """
    if state.checkpoint_dir is None:
        return False

    state.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = state.checkpoint_dir / "state.json"

    data = {
        "run_id": state.run_id,
        "parent_run_id": state.parent_run_id,
        "status": state.status,
        "pending_exec_key": state.pending_exec_key,
        "child_run_ids": state.child_run_ids,
        "wf_hash": state.wf_hash,
        "protocol_version": state.protocol_version,
        "warnings": state.warnings,
        "ctx": {
            "results_scoped": {
                k: v.model_dump() for k, v in state.ctx.results_scoped.items()
            },
            "variables": state.ctx.variables,
            "cwd": state.ctx.cwd,
            "dry_run": state.ctx.dry_run,
            "prompt_dir": state.ctx.prompt_dir,
            "scope": list(getattr(state.ctx, "_scope", [])),
            "order_seq": state.ctx._order_seq,
        },
        # Stack is NOT serialized — resume uses replay-based fast-forward.
        # checkpoint_load() creates a fresh stack from the workflow root and
        # advance() skips completed blocks by checking results_scoped.
    }

    tmp_file = checkpoint_file.with_suffix(".json.tmp")
    try:
        tmp_file.write_text(json.dumps(data, default=str), encoding="utf-8")
        os.replace(str(tmp_file), str(checkpoint_file))
        return True
    except OSError:
        return False


def checkpoint_load(
    run_id: str,
    cwd: Path,
    registry: dict[str, WorkflowDef],
    workflow: WorkflowDef,
) -> RunState | str:
    """Load a run state from checkpoint.

    Returns RunState on success, error string on failure.
    """
    checkpoint_dir = cwd / ".workflow-state" / run_id
    checkpoint_file = checkpoint_dir / "state.json"

    if not checkpoint_file.is_file():
        return f"Checkpoint not found: {checkpoint_file}"

    try:
        data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"Failed to read checkpoint: {exc}"

    # Drift check
    saved_hash = data.get("wf_hash", "")
    current_hash = workflow_hash(workflow)
    if saved_hash and current_hash and saved_hash != current_hash:
        return (
            f"Workflow source changed since checkpoint. "
            f"checkpoint_hash={saved_hash}, current_hash={current_hash}"
        )

    # Reconstruct context
    ctx_data = data.get("ctx", {})
    ctx = WorkflowContext(
        variables=ctx_data.get("variables", {}),
        cwd=ctx_data.get("cwd", str(cwd)),
        dry_run=ctx_data.get("dry_run", False),
        prompt_dir=ctx_data.get("prompt_dir", ""),
    )

    # Restore results
    for k, v in ctx_data.get("results_scoped", {}).items():
        ctx.results_scoped[k] = StepResult(**v)

    # Rebuild convenience results view
    for r in sorted(ctx.results_scoped.values(), key=lambda x: (x.order, x.exec_key)):
        if r.results_key:
            ctx.results[r.results_key] = r

    # Don't restore scope — advance() will rebuild it during replay
    # as it re-enters containers (loops, retries, subworkflows).
    ctx._order_seq = ctx_data.get("order_seq", 0)

    state = RunState(
        run_id=data["run_id"],
        ctx=ctx,
        stack=[Frame(block=workflow)],  # Fresh stack; advance() replays past completed blocks
        registry=registry,
        status=data.get("status", "running"),
        pending_exec_key=data.get("pending_exec_key"),
        parent_run_id=data.get("parent_run_id"),
        child_run_ids=data.get("child_run_ids", []),
        wf_hash=data.get("wf_hash", ""),
        protocol_version=data.get("protocol_version", PROTOCOL_VERSION),
        checkpoint_dir=checkpoint_dir,
        warnings=data.get("warnings", []),
    )

    return state
