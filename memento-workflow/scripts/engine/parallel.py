"""Parallel block handling for the workflow engine.

Manages ParallelEachBlock execution: child run creation, lane setup,
batched execution with max_concurrency, and dry-run recording.
"""

from __future__ import annotations

import copy
import logging
import uuid
from pathlib import Path
from typing import Any

from .types import (
    Block,
    GroupBlock,
    LLMStep,
    LoopBlock,
    ParallelEachBlock,
    StepResult,
    WorkflowContext,
)
from .core import AdvanceResult, Frame, RunState
from .protocol import ParallelAction, ParallelLane
from ..utils import (
    dry_run_structured_output,
    record_leaf_result,
)
from ..infra.checkpoint import checkpoint_dir_from_run_id

logger = logging.getLogger("workflow-engine")


def _handle_parallel(
    state: RunState,
    block: ParallelEachBlock,
    base: str,
) -> AdvanceResult:
    """Handle ParallelEachBlock: create child runs for each lane."""
    from .state import _make_exec_key, advance

    items = state.ctx.get_var(block.parallel_for)
    if not isinstance(items, list) or not items:
        # Skip
        state.stack[-1].block_index += 1
        return advance(state)

    exec_key = _make_exec_key(state, base)

    # Batch if max_concurrency limits the number of concurrent lanes
    if block.max_concurrency and len(items) > block.max_concurrency:
        return _handle_parallel_batched(state, block, base, items)

    # Resume: reuse children loaded from checkpoint
    if block.name in state._resume_children:
        existing = state._resume_children.pop(block.name)
        lanes: list[ParallelLane] = []
        for child in existing:
            lane_exec_key = f"{exec_key}[i={child.lane_index}]"
            lanes.append(
                ParallelLane(
                    child_run_id=child.run_id,
                    exec_key=lane_exec_key,
                    prompt=f"Parallel lane {child.lane_index}: process '{block.name}' item.",
                    relay=True,
                )
            )
        action = ParallelAction(
            run_id=state.run_id,
            exec_key=exec_key,
            lanes=lanes,
            model=block.model,
            display=f"Step [{exec_key}]: Resuming {len(lanes)} parallel lanes",
        )
        state.pending_exec_key = exec_key
        state.status = "waiting"
        state._last_action = action
        return action, []  # children already in _runs

    # Parent run: create child runs for parallel lanes
    child_states: list[RunState] = []
    lanes: list[ParallelLane] = []

    for i, item in enumerate(items):
        child_segment = uuid.uuid4().hex[:12]
        child_run_id = f"{state.run_id}>{child_segment}"
        lane_scope = f"par:{base}[i={i}]"

        child_ctx = WorkflowContext(
            results=dict(state.ctx.results),
            results_scoped=dict(state.ctx.results_scoped),
            variables=copy.deepcopy(state.ctx.variables),
            cwd=state.ctx.cwd,
            dry_run=state.ctx.dry_run,
            prompt_dir=state.ctx.prompt_dir,
        )
        for part in getattr(state.ctx, "_scope", []):
            child_ctx.push_scope(part)
        child_ctx._order_seq = state.ctx._order_seq
        child_ctx.push_scope(lane_scope)
        child_ctx.variables[block.item_var] = item
        child_ctx.variables[f"{block.item_var}_index"] = i

        child_stack = [
            Frame(
                block=GroupBlock(name=f"{block.name}[{i}]", blocks=block.template),
                scope_label="",
            )
        ]

        child_checkpoint_dir = (
            checkpoint_dir_from_run_id(Path(state.ctx.cwd), child_run_id)
            if state.checkpoint_dir
            else None
        )
        child_state = RunState(
            run_id=child_run_id,
            ctx=child_ctx,
            stack=child_stack,
            registry=state.registry,
            status="running",
            wf_hash=state.wf_hash,
            checkpoint_dir=child_checkpoint_dir,
            workflow_name=state.workflow_name,
            parallel_block_name=block.name,
            lane_index=i,
        )
        child_states.append(child_state)

        lane_exec_key = f"{exec_key}[i={i}]"
        lanes.append(
            ParallelLane(
                child_run_id=child_run_id,
                exec_key=lane_exec_key,
                prompt=f"Parallel lane {i}: process '{block.name}' item.",
                relay=True,
            )
        )
        state.child_run_ids.append(child_run_id)

    action = ParallelAction(
        run_id=state.run_id,
        exec_key=exec_key,
        lanes=lanes,
        model=block.model,
        display=f"Step [{exec_key}]: Launching {len(lanes)} parallel lanes",
    )
    state.pending_exec_key = exec_key
    state.status = "waiting"
    state._last_action = action
    return action, child_states


def _handle_parallel_batched(
    state: RunState,
    block: ParallelEachBlock,
    base: str,
    items: list[Any],
) -> AdvanceResult:
    """Handle ParallelEachBlock with max_concurrency by chunking into batches.

    Creates a synthetic LoopBlock over chunks of items, where each chunk
    is a ParallelEachBlock with at most max_concurrency lanes. The loop
    executes batches sequentially; lanes within each batch run in parallel.
    """
    from .state import advance

    assert block.max_concurrency is not None
    chunk_size = block.max_concurrency
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

    # Variable names for the synthetic loop (sanitized to avoid dot-path issues)
    safe = base.replace("-", "_").replace(".", "_")
    chunks_var = f"_par_{safe}_chunks"
    chunk_var = f"_par_{safe}_chunk"
    state.ctx.variables[chunks_var] = chunks

    # Inner parallel block (no max_concurrency — each chunk is within limits)
    inner_parallel = ParallelEachBlock(
        name=block.name,
        parallel_for=f"variables.{chunk_var}",
        item_var=block.item_var,
        template=block.template,
        model=block.model,
    )

    # Wrap in a loop over chunks
    pseudo_loop = LoopBlock(
        name=block.name,
        loop_over=f"variables.{chunks_var}",
        loop_var=chunk_var,
        blocks=[inner_parallel],
    )

    scope = f"par-batch:{base}[i=0]"
    state.ctx.push_scope(scope)
    state.ctx.variables[chunk_var] = chunks[0]
    state.ctx.variables[f"{chunk_var}_index"] = 0
    state.stack.append(
        Frame(
            block=pseudo_loop,
            scope_label=scope,
            loop_items=chunks,
            loop_index=0,
        )
    )
    logger.debug(
        "parallel batched: %d items in %d batches of %d",
        len(items),
        len(chunks),
        chunk_size,
    )
    return advance(state)


def _auto_record_dry_run(
    state: RunState, block: Block, base: str, exec_key: str
) -> None:
    """Auto-record a dry-run result and advance."""
    from .state import _block_step_type

    structured = None
    if isinstance(block, LLMStep) and block.output_schema:
        structured = dry_run_structured_output(block.output_schema)
    record_leaf_result(
        state.ctx,
        base,
        StepResult(
            name=block.name,
            status="dry_run",
            output=f"[dry-run] {block.name}",
            structured_output=structured,
            exec_key=exec_key,
            step_type=_block_step_type(block),
        ),
    )
