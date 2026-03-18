"""Checkpoint persistence for the workflow engine.

Provides checkpoint_save() and checkpoint_load() for durable state
across MCP server restarts.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from .core import PROTOCOL_VERSION, Frame, RunState
from .types import (
    Block,
    ConditionalBlock,
    GroupBlock,
    LoopBlock,
    ParallelEachBlock,
    RetryBlock,
    StepResult,
    WorkflowContext,
    WorkflowDef,
)
from .utils import workflow_hash

logger = logging.getLogger("workflow-engine")

# Checkpoint format version — separate from protocol_version.
# Bump when the checkpoint structure changes incompatibly.
CHECKPOINT_VERSION = 1


_SAFE_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def checkpoint_dir_from_run_id(cwd: Path, run_id: str) -> Path:
    """Map a (possibly composite) run_id to its checkpoint directory.

    Simple ID:    "aaa111bbb222"       → cwd/.workflow-state/aaa111bbb222/
    Composite ID: "aaa111bbb222>ccc333" → cwd/.workflow-state/aaa111bbb222/children/ccc333/
    Nested:       "aaa>bbb>ccc"        → cwd/.workflow-state/aaa/children/bbb/children/ccc/

    Raises ValueError if any segment contains path-traversal characters.
    """
    parts = run_id.split(">")
    for part in parts:
        if not part or not _SAFE_SEGMENT_RE.match(part):
            raise ValueError(
                f"Invalid run_id segment {part!r} in {run_id!r}: "
                f"must be non-empty alphanumeric (no path separators)"
            )
    path = cwd / ".workflow-state" / parts[0]
    for part in parts[1:]:
        path = path / "children" / part
    return path


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

    # Exclude ephemeral keys (resume_only + not resume_once) from checkpoint
    ephemeral = state._ephemeral_keys

    data = {
        "run_id": state.run_id,
        "status": state.status,
        "pending_exec_key": state.pending_exec_key,
        "child_run_ids": state.child_run_ids,
        "wf_hash": state.wf_hash,
        "protocol_version": state.protocol_version,
        "checkpoint_version": CHECKPOINT_VERSION,
        "warnings": state.warnings,
        "workflow_name": state.workflow_name,
        "started_at": state.started_at,
        "parallel_block_name": state.parallel_block_name,
        "lane_index": state.lane_index,
        "spawn_exec_key": state.spawn_exec_key,
        "ctx": {
            "results_scoped": {
                k: v.model_dump()
                for k, v in state.ctx.results_scoped.items()
                if k not in ephemeral
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
    checkpoint_dir = checkpoint_dir_from_run_id(cwd, run_id)
    checkpoint_file = checkpoint_dir / "state.json"

    if not checkpoint_file.is_file():
        return f"Checkpoint not found: {checkpoint_file}"

    try:
        data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"Failed to read checkpoint: {exc}"

    # Checkpoint version check
    saved_cv = data.get("checkpoint_version", 0)
    if saved_cv != CHECKPOINT_VERSION:
        return (
            f"Checkpoint version mismatch: saved={saved_cv}, "
            f"current={CHECKPOINT_VERSION}. Restart required."
        )

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
        child_run_ids=data.get("child_run_ids", []),
        wf_hash=data.get("wf_hash", ""),
        protocol_version=data.get("protocol_version", PROTOCOL_VERSION),
        checkpoint_dir=checkpoint_dir,
        warnings=data.get("warnings", []),
        workflow_name=data.get("workflow_name", ""),
        started_at=data.get("started_at", ""),
        parallel_block_name=data.get("parallel_block_name", ""),
        lane_index=data.get("lane_index", -1),
        spawn_exec_key=data.get("spawn_exec_key", ""),
    )

    return state


def _find_parallel_block(workflow: WorkflowDef, name: str) -> ParallelEachBlock | None:
    """Walk the workflow block tree to find a ParallelEachBlock by name."""

    def _walk(blocks: list[Block]) -> ParallelEachBlock | None:
        for block in blocks:
            if isinstance(block, ParallelEachBlock) and block.name == name:
                return block
            if isinstance(block, (GroupBlock, LoopBlock, RetryBlock)):
                found = _walk(block.blocks)
                if found:
                    return found
            elif isinstance(block, ConditionalBlock):
                for branch in block.branches:
                    found = _walk(branch.blocks)
                    if found:
                        return found
                if block.default:
                    found = _walk(block.default)
                    if found:
                        return found
        return None

    return _walk(workflow.blocks)


def _restore_child_context(
    data: dict,
    parent_state: RunState,
) -> WorkflowContext:
    """Reconstruct a child's WorkflowContext from checkpoint data."""
    ctx_data = data.get("ctx", {})
    child_ctx = WorkflowContext(
        variables=ctx_data.get("variables", {}),
        cwd=ctx_data.get("cwd", parent_state.ctx.cwd),
        dry_run=ctx_data.get("dry_run", False),
        prompt_dir=ctx_data.get("prompt_dir", ""),
    )

    # Restore results
    for k, v in ctx_data.get("results_scoped", {}).items():
        child_ctx.results_scoped[k] = StepResult(**v)
    for r in sorted(
        child_ctx.results_scoped.values(),
        key=lambda x: (x.order, x.exec_key),
    ):
        if r.results_key:
            child_ctx.results[r.results_key] = r

    # Restore scope — critical for children. Their scope was pushed before
    # stack creation, so advance() replay won't rebuild it.
    for part in ctx_data.get("scope", []):
        child_ctx.push_scope(part)
    child_ctx._order_seq = ctx_data.get("order_seq", 0)

    return child_ctx


def _load_subworkflow_child(
    data: dict,
    spawn_key: str,
    child_dir: Path,
    parent_state: RunState,
    registry: dict[str, WorkflowDef],
) -> RunState | None:
    """Load a SubWorkflow child from checkpoint data.

    Resolves the target workflow from the child's workflow_name,
    reconstructs context and stack.
    """
    child_wf_name = data.get("workflow_name", "")
    if not child_wf_name or child_wf_name not in registry:
        logger.warning(
            "SubWorkflow child '%s': workflow '%s' not in registry, skipping",
            child_dir.name, child_wf_name,
        )
        return None

    target_wf = registry[child_wf_name]
    child_ctx = _restore_child_context(data, parent_state)

    # Re-derive the sub-workflow scope label from spawn_key.
    # During original execution, _create_child_run pushes "sub:{base}" onto
    # the child's scope and sets it as the frame's scope_label.  When the child
    # completes, _pop_frame pops this scope — so the checkpoint saves the scope
    # WITHOUT the "sub:" prefix.  We must re-push it here so that exec_keys
    # generated during replay match the ones stored in results_scoped.
    # For active (non-completed) children the scope is still present — only
    # push when missing to avoid duplication.
    scope_label = ""
    if spawn_key:
        base = spawn_key.rsplit("/", 1)[-1]
        scope_label = f"sub:{base}"
        current_scope = list(getattr(child_ctx, "_scope", []))
        if not current_scope or current_scope[-1] != scope_label:
            child_ctx.push_scope(scope_label)

    # Ensure prompt_dir points to the target workflow's prompts, not the parent's.
    if target_wf.prompt_dir:
        child_ctx.prompt_dir = target_wf.prompt_dir

    # Build stack: target workflow as root
    child_stack = [Frame(block=target_wf, scope_label=scope_label)]

    child_state = RunState(
        run_id=data["run_id"],
        ctx=child_ctx,
        stack=child_stack,
        registry=registry,
        status=data.get("status", "running"),
        pending_exec_key=data.get("pending_exec_key"),
        child_run_ids=data.get("child_run_ids", []),
        wf_hash=data.get("wf_hash", ""),
        protocol_version=data.get("protocol_version", PROTOCOL_VERSION),
        checkpoint_dir=child_dir,
        warnings=data.get("warnings", []),
        workflow_name=child_wf_name,
        started_at=data.get("started_at", ""),
        spawn_exec_key=spawn_key,
    )
    child_state.is_resumed = True

    return child_state


def checkpoint_load_children(
    parent_state: RunState,
    registry: dict[str, WorkflowDef],
    max_depth: int = 10,
) -> dict[str, list[RunState]]:
    """Load child run states from parent's children/ directory.

    Scans checkpoint_dir/children/ for subdirs with state.json.
    Returns dict[key -> list[RunState]] where key is either:
      - parallel_block_name (for parallel lane children)
      - spawn_exec_key (for SubWorkflow children)

    Children get scope restored from checkpoint (unlike parents, children's
    scope was pre-set before stack creation and won't be rebuilt by replay).
    Loads grandchildren recursively up to max_depth levels.
    """
    if max_depth <= 0:
        logger.warning(
            "checkpoint_load_children: max recursion depth reached for %s, "
            "stopping child loading",
            parent_state.run_id,
        )
        return {}

    if parent_state.checkpoint_dir is None:
        return {}

    children_dir = parent_state.checkpoint_dir / "children"
    if not children_dir.is_dir():
        return {}

    # Find workflow definition for block tree walking
    workflow = None
    if parent_state.workflow_name and parent_state.workflow_name in registry:
        workflow = registry[parent_state.workflow_name]
    if workflow is None:
        logger.warning(
            "checkpoint_load_children: workflow '%s' not in registry",
            parent_state.workflow_name,
        )
        return {}

    result: dict[str, list[RunState]] = {}

    for child_dir in sorted(children_dir.iterdir()):
        if not child_dir.is_dir():
            continue
        checkpoint_file = child_dir / "state.json"
        if not checkpoint_file.is_file():
            continue

        try:
            data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read child checkpoint %s: %s", checkpoint_file, exc)
            continue

        # Check if this is a SubWorkflow child (has spawn_exec_key, no parallel metadata)
        spawn_key = data.get("spawn_exec_key", "")
        block_name = data.get("parallel_block_name", "")
        lane_index = data.get("lane_index", -1)

        if spawn_key and not block_name:
            # SubWorkflow child
            child_state = _load_subworkflow_child(
                data, spawn_key, child_dir, parent_state, registry,
            )
            if child_state:
                # Recursive: load grandchildren
                grandchildren = checkpoint_load_children(child_state, registry, max_depth - 1)
                if grandchildren:
                    child_state._resume_children = grandchildren
                result.setdefault(spawn_key, []).append(child_state)
            continue

        # Parallel lane child
        if not block_name or lane_index < 0:
            logger.warning(
                "Child checkpoint %s missing parallel metadata, skipping",
                child_dir.name,
            )
            continue

        parallel_block = _find_parallel_block(workflow, block_name)
        if parallel_block is None:
            logger.warning("ParallelEachBlock '%s' not found in workflow", block_name)
            continue

        child_ctx = _restore_child_context(data, parent_state)

        # Build stack: GroupBlock wrapping the parallel template
        child_stack = [Frame(
            block=GroupBlock(
                name=f"{block_name}[{lane_index}]",
                blocks=parallel_block.template,
            ),
            scope_label="",
        )]

        child_state = RunState(
            run_id=data["run_id"],
            ctx=child_ctx,
            stack=child_stack,
            registry=registry,
            status=data.get("status", "running"),
            pending_exec_key=data.get("pending_exec_key"),
            child_run_ids=data.get("child_run_ids", []),
            wf_hash=data.get("wf_hash", ""),
            protocol_version=data.get("protocol_version", PROTOCOL_VERSION),
            checkpoint_dir=child_dir,
            warnings=data.get("warnings", []),
            workflow_name=data.get("workflow_name", ""),
            started_at=data.get("started_at", ""),
            parallel_block_name=block_name,
            lane_index=lane_index,
        )

        # Recursive: load grandchildren (e.g. inline SubWorkflow inside parallel lane)
        grandchildren = checkpoint_load_children(child_state, registry, max_depth - 1)
        if grandchildren:
            child_state._resume_children = grandchildren

        result.setdefault(block_name, []).append(child_state)

    # Sort parallel lane groups by lane_index for deterministic ordering
    for _key, children in result.items():
        if children and children[0].lane_index >= 0:
            children.sort(key=lambda s: s.lane_index)

    if result:
        logger.info(
            "checkpoint_load_children: loaded %d children for %d keys",
            sum(len(v) for v in result.values()),
            len(result),
        )
    return result
