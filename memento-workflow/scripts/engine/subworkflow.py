"""SubWorkflow handling for the workflow engine.

Manages SubWorkflow block execution: fresh creation, resume from checkpoint,
child result merging, and subagent block dispatch.
"""

from __future__ import annotations

import logging
import uuid

from .types import (
    Block,
    LLMStep,
    StepResult,
    SubWorkflow,
)
from .core import AdvanceResult, Frame, RunState
from .child_runs import (
    _collect_subworkflow_results_from_child,
    _create_child_run,
    set_relay_child_metadata,
)
from ..utils import (
    load_prompt,
    record_leaf_result,
    substitute,
)
from .actions import _build_error_action, _build_subagent_action


logger = logging.getLogger("workflow-engine")


def _handle_subagent_block(
    state: RunState,
    block: Block,
    base: str,
) -> AdvanceResult:
    """Handle a block with isolation="subagent" (only from parent runs)."""
    from .state import _make_exec_key

    exec_key = _make_exec_key(state, base)

    if isinstance(block, LLMStep):
        # Single-task subagent (no sub-relay)
        if block.prompt_text:
            prompt_text = substitute(block.prompt_text, state.ctx)
        else:
            prompt_text = load_prompt(block.prompt, state.ctx)
        action = _build_subagent_action(
            state,
            block,
            exec_key,
            relay=False,
            prompt=prompt_text,
        )
        state.pending_exec_key = exec_key
        state.status = "waiting"
        state._last_action = action
        return action, []

    if exec_key in state._resume_children:
        children = state._resume_children.pop(exec_key)
        child = children[0]  # Exactly 1 child per relay subagent exec_key
        prompt = f"Continue workflow steps for '{block.name}'."
        action = _build_subagent_action(
            state,
            block,
            exec_key,
            relay=True,
            child_run_id=child.run_id,
            prompt=prompt,
        )
        state.pending_exec_key = exec_key
        state.status = "waiting"
        state._last_action = action
        return action, []

    # Multi-step subagent with sub-relay (Group, Loop, etc.)
    child_segment = uuid.uuid4().hex[:12]
    child_run_id = f"{state.run_id}>{child_segment}"
    child_state = _create_child_run(state, block, child_run_id, base)
    set_relay_child_metadata(child_state, block, exec_key)

    prompt = f"Process workflow steps for '{block.name}'."
    action = _build_subagent_action(
        state,
        block,
        exec_key,
        relay=True,
        child_run_id=child_run_id,
        prompt=prompt,
    )
    state.pending_exec_key = exec_key
    state.status = "waiting"
    state.child_run_ids.append(child_run_id)
    state._last_action = action
    return action, [child_state]


def _merge_child_results(
    state: RunState, child: RunState, parent_exec_key: str
) -> None:
    """Merge child results into parent and record SubWorkflow step as completed."""
    _collect_subworkflow_results_from_child(state, child)
    # Record SubWorkflow step result in parent
    base = (
        parent_exec_key.rsplit("/", 1)[-1]
        if "/" in parent_exec_key
        else parent_exec_key
    )
    record_leaf_result(
        state.ctx,
        base,
        StepResult(
            name=base,
            status="success",
            exec_key=parent_exec_key,
            output="SubWorkflow completed",
        ),
    )


def _resume_subworkflow_child(
    state: RunState,
    block: SubWorkflow,
    exec_key: str,
    child: RunState,
    frame: Frame,
) -> AdvanceResult:
    """Handle SubWorkflow resume path: reuse child loaded from checkpoint."""
    from .state import advance, halt_workflow

    # Handle terminal child states (crash between child completion and parent submit)
    if child.status == "completed":
        _merge_child_results(state, child, exec_key)
        frame.block_index += 1
        return advance(state)
    if child.status in ("error", "halted"):
        reason = f"SubWorkflow '{block.name}' child {child.run_id} is {child.status}"
        return halt_workflow(state, reason, exec_key)
    if child.status == "cancelled":
        return _build_error_action(
            state, f"SubWorkflow child {child.run_id} was cancelled"
        ), []

    # Child is running — route by isolation mode
    state.pending_exec_key = exec_key
    state.status = "waiting"
    if block.isolation == "subagent" and not state.parent_run_id:
        action = _build_subagent_action(
            state,
            block,
            exec_key,
            relay=True,
            child_run_id=child.run_id,
            prompt=f"Continue workflow steps for '{block.name}'.",
        )
        state._last_action = action
        return action, []
    else:
        # Inline: return child for _action_response to handle
        child._inline_parent_exec_key = exec_key
        child._artifacts_dir_override = state.artifacts_dir
        action = _build_subagent_action(
            state,
            block,
            exec_key,
            relay=True,
            child_run_id=child.run_id,
            prompt=f"Continue inline workflow steps for '{block.name}'.",
        )
        state._last_action = action
        return action, [child]


def _create_fresh_subworkflow(
    state: RunState,
    block: SubWorkflow,
    exec_key: str,
    base: str,
) -> AdvanceResult:
    """Handle SubWorkflow fresh creation path: create a new child run."""
    child_segment = uuid.uuid4().hex[:12]
    composite_id = f"{state.run_id}>{child_segment}"
    child = _create_child_run(state, block, composite_id, base)
    set_relay_child_metadata(child, block, exec_key)
    child.workflow_name = block.workflow  # target workflow name
    state.child_run_ids.append(composite_id)

    state.pending_exec_key = exec_key
    state.status = "waiting"
    if block.isolation == "subagent" and not state.parent_run_id:
        # Subagent: emit handoff for Agent
        action = _build_subagent_action(
            state,
            block,
            exec_key,
            relay=True,
            child_run_id=composite_id,
            prompt=f"Process workflow steps for '{block.name}'.",
        )
        state._last_action = action
        return action, [child]
    else:
        # Inline: _action_response advances child + handles shell-only
        child._inline_parent_exec_key = exec_key
        # Inline children share parent's artifacts dir (scoped exec_keys prevent collisions)
        child._artifacts_dir_override = state.artifacts_dir
        action = _build_subagent_action(
            state,
            block,
            exec_key,
            relay=True,
            child_run_id=composite_id,
            prompt=f"Process inline workflow steps for '{block.name}'.",
        )
        state._last_action = action
        return action, [child]


def _handle_subworkflow(
    state: RunState,
    block: SubWorkflow,
    base: str,
    parent_frame: Frame,
) -> AdvanceResult:
    """Handle SubWorkflow: always creates a child run.

    Routes by isolation mode:
    - subagent (and not already a child): emit SubagentAction for relay Agent
    - inline (default, or forced when inside child): advance child directly

    Dispatches to _resume_subworkflow_child or _create_fresh_subworkflow.
    """
    from .state import _make_exec_key

    exec_key = _make_exec_key(state, base)
    logger.debug("subworkflow: '%s' exec_key=%s", block.workflow, exec_key)

    wf = state.registry.get(block.workflow)
    if wf is None:
        logger.error("subworkflow: '%s' not found in registry", block.workflow)
        return _build_error_action(state, f"Unknown workflow '{block.workflow}'"), []

    # Resume: reuse child loaded from checkpoint
    if exec_key in state._resume_children:
        children = state._resume_children.pop(exec_key)
        child = children[0]  # Exactly 1 child per SubWorkflow exec_key
        return _resume_subworkflow_child(state, block, exec_key, child, parent_frame)

    # Fresh: create child run
    return _create_fresh_subworkflow(state, block, exec_key, base)
