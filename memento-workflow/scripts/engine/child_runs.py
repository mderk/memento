"""Child run creation and result merging for subagent and parallel lanes.

Extracted from state.py to reduce file size. Contains:
- _create_child_run: create a child RunState
- _resolve_inject_value: resolve SubWorkflow inject values
- _merge_child_results / _collect_subworkflow_results_from_child
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

from ..infra.checkpoint import checkpoint_dir_from_run_id
from .core import Frame, RunState
from .types import (
    Block,
    GroupBlock,
    LoopBlock,
    SubWorkflow,
    WorkflowContext,
)
from ..utils import merge_child_results, substitute

logger = logging.getLogger("workflow-engine")


def _resolve_inject_value(ctx: WorkflowContext, value: str) -> Any:
    """Resolve an inject value: template string ({{...}}), dotpath, or literal.

    - Contains '{{' → template substitution
    - Starts with 'variables.' or 'results.' → dotpath resolution
    - Otherwise → literal string value
    """
    if "{{" in value:
        return substitute(value, ctx)
    if value.startswith("variables.") or value.startswith("results."):
        return ctx.get_var(value)
    return value


def _create_child_run(
    state: RunState,
    block: Block,
    child_run_id: str,
    base: str,
) -> RunState:
    """Create a child RunState for subagent relay or parallel lane.

    child_run_id should be composite: "parent_id>child_segment".
    """
    # Deep copy context for isolation
    child_ctx = WorkflowContext(
        results=dict(state.ctx.results),
        results_scoped=dict(state.ctx.results_scoped),
        variables=copy.deepcopy(state.ctx.variables),
        cwd=state.ctx.cwd,
        dry_run=state.ctx.dry_run,
        prompt_dir=state.ctx.prompt_dir,
    )
    # Copy scope
    for part in getattr(state.ctx, "_scope", []):
        child_ctx.push_scope(part)
    child_ctx._order_seq = state.ctx._order_seq

    # Build initial stack for the child
    if isinstance(block, SubWorkflow):
        # Resolve the sub-workflow
        wf = state.registry.get(block.workflow)
        if wf is None:
            # Return an error state
            child_state = RunState(
                run_id=child_run_id,
                ctx=child_ctx,
                stack=[],
                registry=state.registry,
                status="error",
            )
            return child_state
        # Inject variables (supports both template strings and dotpaths)
        for var_name, value in block.inject.items():
            child_ctx.variables[var_name] = _resolve_inject_value(child_ctx, value)
        scope = f"sub:{base}"
        child_ctx.push_scope(scope)
        child_ctx.prompt_dir = wf.prompt_dir or child_ctx.prompt_dir
        # Update workflow_dir so scripts resolve to the target workflow's directory
        if wf.source_path:
            child_ctx.variables["workflow_dir"] = str(Path(wf.source_path).parent)
        child_stack = [
            Frame(
                block=wf,
                scope_label=scope,
                saved_vars=copy.deepcopy(state.ctx.variables),
                saved_prompt_dir=state.ctx.prompt_dir,
            )
        ]
    elif isinstance(block, GroupBlock):
        child_stack = [Frame(block=block)]
    elif isinstance(block, LoopBlock):
        items = child_ctx.get_var(block.loop_over)
        if isinstance(items, list) and items:
            scope = f"loop:{base}[i=0]"
            child_ctx.push_scope(scope)
            child_ctx.variables[block.loop_var] = items[0]
            child_ctx.variables[f"{block.loop_var}_index"] = 0
            child_stack = [
                Frame(
                    block=block,
                    scope_label=scope,
                    loop_items=items,
                    loop_index=0,
                )
            ]
        else:
            child_stack = []
    else:
        child_stack = [Frame(block=block)]

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
    )
    return child_state


def _collect_subworkflow_results_from_child(state: RunState, child: RunState) -> None:
    """Merge child results into parent state (collision-safe)."""
    merge_child_results(
        state.ctx.results_scoped,
        state.ctx.results,
        child.ctx.results_scoped,
    )
    state.ctx._order_seq = max(state.ctx._order_seq, child.ctx._order_seq)
