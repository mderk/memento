"""State machine for the workflow engine.

Provides advance(), apply_submit(), pending_action() — the core loop that
drives workflow execution.  Claude Code acts as a relay:

    action = start(workflow)
    while action["action"] != "completed":
        result = execute(action)       # shell, prompt, ask_user, subagent
        action = submit(run_id, exec_key, result)

Data structures (Frame, RunState) live in core.py.
Utility functions (substitute, evaluate_condition, etc.) live in utils.py.
Action builders (_build_*_action) live in actions.py.
Checkpoint persistence lives in checkpoint.py.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from typing import Any

from .types import (
    Block,
    ConditionalBlock,
    GroupBlock,
    LLMStep,
    LoopBlock,
    ParallelEachBlock,
    PromptStep,
    RetryBlock,
    ShellStep,
    StepResult,
    SubWorkflow,
    WorkflowContext,
    WorkflowDef,
)

from .core import (
    AdvanceResult,
    Frame,
    RunState,
)

from .protocol import (
    PROTOCOL_VERSION,
    ActionBase,
    AskUserAction,
    CancelledAction,
    ParallelAction,
    ParallelLane,
    action_to_dict,
)

from .utils import (
    evaluate_condition,
    dry_run_structured_output,
    load_prompt,
    record_leaf_result,
    results_key,
    schema_dict,
    substitute,
    validate_structured_output,
    workflow_hash,
)

from .actions import (
    _build_ask_user_action,
    _build_completed_action,
    _build_dry_run_action,
    _build_error_action,
    _build_prompt_action,
    _build_retry_confirm,
    _build_shell_action,
    _build_subagent_action,
)

from .checkpoint import checkpoint_load, checkpoint_save

__all__ = [
    "advance",
    "apply_submit",
    "pending_action",
]

logger = logging.getLogger("workflow-engine")


def _block_step_type(block: Block | None) -> str:
    """Return step_type string for a block."""
    if isinstance(block, LLMStep):
        return "llm_step"
    if isinstance(block, ShellStep):
        return "shell"
    if isinstance(block, PromptStep):
        return "prompt"
    return ""


# ---------------------------------------------------------------------------
# advance() — the heart of the state machine
# ---------------------------------------------------------------------------


def _make_exec_key(state: RunState, base: str) -> str:
    """Build exec_key from current scope stack + base name."""
    return state.ctx.scoped_exec_key(base)


def _base_name(block: Block) -> str:
    """Get the base name for a block (key or name, substituted)."""
    return block.key or block.name


def _is_leaf(block: Block) -> bool:
    """Check if a block is a leaf (directly executable, not a container)."""
    return isinstance(block, (LLMStep, ShellStep, PromptStep))


def advance(state: RunState) -> AdvanceResult:
    """Advance the state machine to the next action.

    Returns (action_dict, new_child_states) where new_child_states are
    RunStates for newly created child runs (subagent relay, parallel lanes).
    """
    logger.debug("advance: run_id=%s stack_depth=%d", state.run_id, len(state.stack))
    while state.stack:
        frame = state.stack[-1]
        children = _get_frame_children(frame, state)

        if children is None:
            # Frame setup needed (conditional resolution, etc.)
            # _get_frame_children handles pushing new frames
            continue

        if frame.block_index >= len(children):
            # Frame exhausted — pop and handle re-entry for loop/retry
            result = _pop_frame(state)
            if result is not None:
                return result, []
            continue

        block = children[frame.block_index]
        base = substitute(_base_name(block), state.ctx)

        # Condition check
        if not evaluate_condition(block.condition, state.ctx):
            # Skip: record as skipped, advance index
            exec_key = _make_exec_key(state, base)
            if _is_leaf(block):
                record_leaf_result(
                    state.ctx, base,
                    StepResult(
                        name=block.name, status="skipped", exec_key=exec_key,
                        step_type=_block_step_type(block),
                    ),
                )
            frame.block_index += 1
            continue

        # Checkpoint replay: skip blocks whose results are already recorded.
        # This enables resume from checkpoint — advance() fast-forwards through
        # completed blocks by checking results_scoped for each exec_key.
        if not state.ctx.dry_run:
            exec_key = _make_exec_key(state, base)
            if exec_key in state.ctx.results_scoped:
                _replay_skip(state, block, exec_key)
                frame.block_index += 1
                continue

        # Dry-run mode: emit dry_run actions for leaves
        if state.ctx.dry_run and _is_leaf(block):
            exec_key = _make_exec_key(state, base)
            action = _build_dry_run_action(state, block, exec_key)
            # Auto-record and advance
            _auto_record_dry_run(state, block, base, exec_key)
            frame.block_index += 1
            # For dry_run we keep going — collect all actions
            # Actually, in dry_run we still return one action at a time
            # so the runner can collect them all
            state.pending_exec_key = exec_key
            state._last_action = action
            return action, []

        # Check isolation for subagent dispatch
        is_child = state.parent_run_id is not None

        if block.isolation == "subagent" and not is_child:
            return _handle_subagent_block(state, block, base)

        # Leaf blocks: emit action
        if isinstance(block, ShellStep):
            exec_key = _make_exec_key(state, base)
            cmd_display = (block.command or block.script or "")[:80]
            logger.debug("advance: emit shell exec_key=%s cmd=%s", exec_key, cmd_display)
            action = _build_shell_action(state, exec_key=exec_key, step=block)
            state.pending_exec_key = exec_key
            state.status = "waiting"
            state._last_action = action
            return action, []

        if isinstance(block, PromptStep):
            exec_key = _make_exec_key(state, base)
            logger.debug("advance: emit ask_user exec_key=%s", exec_key)
            action = _build_ask_user_action(state, step=block, exec_key=exec_key)
            state.pending_exec_key = exec_key
            state.status = "waiting"
            state._last_action = action
            return action, []

        if isinstance(block, LLMStep):
            if block.isolation == "subagent" and is_child:
                state.warnings.append(
                    f"Downgraded isolation='subagent' to inline for '{block.name}' (inside child run)"
                )
            exec_key = _make_exec_key(state, base)
            logger.debug("advance: emit prompt exec_key=%s prompt=%s", exec_key, block.prompt)
            action = _build_prompt_action(state, step=block, exec_key=exec_key)
            state.pending_exec_key = exec_key
            state.status = "waiting"
            state._last_action = action
            return action, []

        # Container blocks: push frame and recurse
        if isinstance(block, GroupBlock):
            if block.isolation == "subagent" and is_child:
                state.warnings.append(
                    f"Downgraded isolation='subagent' to inline for '{block.name}' (inside child run)"
                )
            state.stack.append(Frame(block=block, scope_label=""))
            continue

        if isinstance(block, LoopBlock):
            items = state.ctx.get_var(block.loop_over)
            if not isinstance(items, list):
                # Not a list — skip
                frame.block_index += 1
                continue
            if not items:
                frame.block_index += 1
                continue
            scope = f"loop:{base}[i=0]"
            state.ctx.push_scope(scope)
            state.ctx.variables[block.loop_var] = items[0]
            state.ctx.variables[f"{block.loop_var}_index"] = 0
            state.stack.append(Frame(
                block=block,
                scope_label=scope,
                loop_items=items,
                loop_index=0,
            ))
            continue

        if isinstance(block, RetryBlock):
            scope = f"retry:{base}[attempt=0]"
            state.ctx.push_scope(scope)
            state.stack.append(Frame(
                block=block,
                scope_label=scope,
                retry_attempt=0,
            ))
            continue

        if isinstance(block, ConditionalBlock):
            chosen_idx, chosen_blocks = _resolve_conditional(block, state.ctx)
            if chosen_blocks is None:
                frame.block_index += 1
                continue
            state.stack.append(Frame(
                block=block,
                chosen_branch_index=chosen_idx,
                chosen_blocks=chosen_blocks,
            ))
            continue

        if isinstance(block, SubWorkflow):
            return _handle_subworkflow(state, block, base, frame)

        if isinstance(block, ParallelEachBlock):
            return _handle_parallel(state, block, base, is_child)

        # Unknown block type — skip
        frame.block_index += 1

    # Stack empty — workflow completed
    state.status = "completed"
    action = _build_completed_action(state)
    state._last_action = action
    return action, []


def _get_frame_children(frame: Frame, state: RunState) -> list[Block] | None:
    """Get the child blocks for the current frame."""
    block = frame.block

    if isinstance(block, WorkflowDef):
        return block.blocks
    if isinstance(block, GroupBlock):
        return block.blocks
    if isinstance(block, LoopBlock):
        return block.blocks
    if isinstance(block, RetryBlock):
        return block.blocks
    if isinstance(block, ConditionalBlock):
        if frame.chosen_blocks is not None:
            return frame.chosen_blocks
        return []
    if isinstance(block, SubWorkflow):
        # SubWorkflow pushes its own frame with the target workflow's blocks
        # This shouldn't be reached — SubWorkflow is handled specially
        return []
    if isinstance(block, ParallelEachBlock):
        return []

    return []


def _resolve_conditional(
    block: ConditionalBlock,
    ctx: WorkflowContext,
) -> tuple[int | None, list[Block] | None]:
    """Find the first matching branch or default."""
    for i, branch in enumerate(block.branches):
        try:
            if branch.condition(ctx):
                return i, branch.blocks
        except Exception:
            logger.warning(
                "Condition evaluation failed for branch %d in '%s'",
                i, block.name, exc_info=True,
            )
            continue
    if block.default:
        return -1, block.default
    return None, None


def _pop_frame(state: RunState) -> ActionBase | None:
    """Pop the top frame, handle loop/retry re-entry.

    Returns an action if re-entry produces one (shouldn't normally),
    or None to continue the advance loop.
    """
    frame = state.stack.pop()
    block = frame.block

    # Clean up scope
    if frame.scope_label:
        state.ctx.pop_scope()

    if isinstance(block, LoopBlock) and frame.loop_items is not None:
        next_idx = frame.loop_index + 1
        if next_idx < len(frame.loop_items):
            # Re-enter loop with next item
            base = substitute(_base_name(block), state.ctx)
            scope = f"loop:{base}[i={next_idx}]"
            state.ctx.push_scope(scope)
            state.ctx.variables[block.loop_var] = frame.loop_items[next_idx]
            state.ctx.variables[f"{block.loop_var}_index"] = next_idx
            state.stack.append(Frame(
                block=block,
                scope_label=scope,
                loop_items=frame.loop_items,
                loop_index=next_idx,
            ))
            return None

    if isinstance(block, RetryBlock):
        # Check until condition
        try:
            done = block.until(state.ctx)
        except Exception:
            logger.warning(
                "until condition failed for retry '%s', treating as not done",
                block.name, exc_info=True,
            )
            done = False
        if not done:
            next_attempt = frame.retry_attempt + 1
            if next_attempt < block.max_attempts:
                base = substitute(_base_name(block), state.ctx)
                scope = f"retry:{base}[attempt={next_attempt}]"
                state.ctx.push_scope(scope)
                state.stack.append(Frame(
                    block=block,
                    scope_label=scope,
                    retry_attempt=next_attempt,
                ))
                return None

    if isinstance(block, SubWorkflow):
        # Restore variables and prompt_dir
        if frame.saved_vars is not None:
            state.ctx.variables = frame.saved_vars
        if frame.saved_prompt_dir is not None:
            logger.debug("pop_frame: restoring prompt_dir to %s", frame.saved_prompt_dir)
            state.ctx.prompt_dir = frame.saved_prompt_dir

    # Advance parent frame's index
    if state.stack:
        state.stack[-1].block_index += 1

    return None


def _replay_skip(state: RunState, block: Block, exec_key: str) -> None:
    """Replay side effects when skipping an already-recorded block during checkpoint resume.

    Re-applies result_var assignments so that variables are correct for
    downstream condition evaluation and template substitution.
    """
    recorded = state.ctx.results_scoped[exec_key]
    if isinstance(block, ShellStep) and block.result_var and recorded.status == "success":
        try:
            parsed = json.loads(recorded.output)
            state.ctx.variables[block.result_var] = parsed
        except (json.JSONDecodeError, ValueError):
            pass
    if isinstance(block, PromptStep) and block.result_var:
        state.ctx.variables[block.result_var] = recorded.output


def _handle_subagent_block(
    state: RunState, block: Block, base: str,
) -> AdvanceResult:
    """Handle a block with isolation="subagent" (only from parent runs)."""
    exec_key = _make_exec_key(state, base)

    if isinstance(block, LLMStep):
        # Single-task subagent (no sub-relay)
        if block.prompt_text:
            prompt_text = substitute(block.prompt_text, state.ctx)
        else:
            prompt_text = load_prompt(block.prompt, state.ctx)
        action = _build_subagent_action(
            state, block, exec_key,
            relay=False,
            prompt=prompt_text,
        )
        state.pending_exec_key = exec_key
        state.status = "waiting"
        state._last_action = action
        return action, []

    # Multi-step subagent with sub-relay (Group, SubWorkflow, Loop, etc.)
    child_run_id = uuid.uuid4().hex[:12]
    child_state = _create_child_run(state, block, child_run_id, base)

    prompt = f"Process workflow steps for '{block.name}'."
    action = _build_subagent_action(
        state, block, exec_key,
        relay=True,
        child_run_id=child_run_id,
        prompt=prompt,
    )
    state.pending_exec_key = exec_key
    state.status = "waiting"
    state.child_run_ids.append(child_run_id)
    state._last_action = action
    return action, [child_state]


def _create_child_run(
    state: RunState,
    block: Block,
    child_run_id: str,
    base: str,
) -> RunState:
    """Create a child RunState for subagent relay or parallel lane."""
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
                parent_run_id=state.run_id,
            )
            return child_state
        # Inject variables (supports both template strings and dotpaths)
        for var_name, value in block.inject.items():
            child_ctx.variables[var_name] = _resolve_inject_value(child_ctx, value)
        scope = f"sub:{base}"
        child_ctx.push_scope(scope)
        child_ctx.prompt_dir = wf.prompt_dir or child_ctx.prompt_dir
        child_stack = [Frame(
            block=wf,
            scope_label=scope,
            saved_vars=copy.deepcopy(state.ctx.variables),
            saved_prompt_dir=state.ctx.prompt_dir,
        )]
    elif isinstance(block, GroupBlock):
        child_stack = [Frame(block=block)]
    elif isinstance(block, LoopBlock):
        items = child_ctx.get_var(block.loop_over)
        if isinstance(items, list) and items:
            scope = f"loop:{base}[i=0]"
            child_ctx.push_scope(scope)
            child_ctx.variables[block.loop_var] = items[0]
            child_ctx.variables[f"{block.loop_var}_index"] = 0
            child_stack = [Frame(
                block=block,
                scope_label=scope,
                loop_items=items,
                loop_index=0,
            )]
        else:
            child_stack = []
    else:
        child_stack = [Frame(block=block)]

    child_state = RunState(
        run_id=child_run_id,
        ctx=child_ctx,
        stack=child_stack,
        registry=state.registry,
        status="running",
        parent_run_id=state.run_id,
        wf_hash=state.wf_hash,
        workflow_name=state.workflow_name,
    )
    return child_state


def _resolve_inject_value(ctx: WorkflowContext, value: str) -> Any:
    """Resolve an inject value: template string ({{...}}) or dotpath."""
    if "{{" in value:
        return substitute(value, ctx)
    return ctx.get_var(value)


def _handle_subworkflow(
    state: RunState,
    block: SubWorkflow,
    base: str,
    parent_frame: Frame,
) -> AdvanceResult:
    """Handle SubWorkflow: load target, inject vars, push frame."""
    logger.debug("subworkflow: entering '%s' (base=%s)", block.workflow, base)
    wf = state.registry.get(block.workflow)
    if wf is None:
        logger.error("subworkflow: '%s' not found in registry", block.workflow)
        return _build_error_action(
            state, f"Unknown workflow '{block.workflow}'"
        ), []

    # Save current state for restore
    saved_vars = copy.deepcopy(state.ctx.variables)
    saved_prompt_dir = state.ctx.prompt_dir

    # Inject variables (supports both template strings and dotpaths)
    for var_name, value in block.inject.items():
        state.ctx.variables[var_name] = _resolve_inject_value(state.ctx, value)

    scope = f"sub:{base}"
    state.ctx.push_scope(scope)
    new_prompt_dir = wf.prompt_dir or state.ctx.prompt_dir
    logger.debug(
        "subworkflow: prompt_dir %s -> %s",
        state.ctx.prompt_dir, new_prompt_dir,
    )
    state.ctx.prompt_dir = new_prompt_dir

    state.stack.append(Frame(
        block=wf,
        scope_label=scope,
        saved_vars=saved_vars,
        saved_prompt_dir=saved_prompt_dir,
    ))

    # Continue advancing (recurse into subworkflow blocks)
    return advance(state)


def _handle_parallel(
    state: RunState,
    block: ParallelEachBlock,
    base: str,
    is_child: bool,
) -> AdvanceResult:
    """Handle ParallelEachBlock: create child runs for each lane."""
    items = state.ctx.get_var(block.parallel_for)
    if not isinstance(items, list) or not items:
        # Skip
        state.stack[-1].block_index += 1
        return advance(state)

    exec_key = _make_exec_key(state, base)

    if is_child:
        # Inside child run: downgrade to sequential inline execution
        state.warnings.append(
            f"Downgraded parallel '{block.name}' to sequential (inside child run)"
        )
        # Execute as a loop instead
        scope = f"par:{base}[i=0]"
        state.ctx.push_scope(scope)
        state.ctx.variables[block.item_var] = items[0]
        state.ctx.variables[f"{block.item_var}_index"] = 0

        # Create a pseudo-loop frame
        pseudo_loop = LoopBlock(
            name=block.name,
            loop_over=block.parallel_for,
            loop_var=block.item_var,
            blocks=block.template,
        )
        state.stack.append(Frame(
            block=pseudo_loop,
            scope_label=scope,
            loop_items=items,
            loop_index=0,
        ))
        return advance(state)

    # Batch if max_concurrency limits the number of concurrent lanes
    if block.max_concurrency and len(items) > block.max_concurrency:
        return _handle_parallel_batched(state, block, base, items)

    # Resume: reuse children loaded from checkpoint
    if block.name in state._resume_children:
        existing = state._resume_children.pop(block.name)
        lanes: list[ParallelLane] = []
        for child in existing:
            lane_exec_key = f"{exec_key}[i={child.lane_index}]"
            lanes.append(ParallelLane(
                child_run_id=child.run_id,
                exec_key=lane_exec_key,
                prompt=f"Parallel lane {child.lane_index}: process '{block.name}' item.",
                relay=True,
            ))
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
        child_run_id = uuid.uuid4().hex[:12]
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

        child_stack = [Frame(
            block=GroupBlock(name=f"{block.name}[{i}]", blocks=block.template),
            scope_label="",
        )]

        child_checkpoint_dir = (
            state.checkpoint_dir / "children" / child_run_id
            if state.checkpoint_dir else None
        )
        child_state = RunState(
            run_id=child_run_id,
            ctx=child_ctx,
            stack=child_stack,
            registry=state.registry,
            status="running",
            parent_run_id=state.run_id,
            wf_hash=state.wf_hash,
            checkpoint_dir=child_checkpoint_dir,
            workflow_name=state.workflow_name,
            parallel_block_name=block.name,
            lane_index=i,
        )
        child_states.append(child_state)

        lane_exec_key = f"{exec_key}[i={i}]"
        lanes.append(ParallelLane(
            child_run_id=child_run_id,
            exec_key=lane_exec_key,
            prompt=f"Parallel lane {i}: process '{block.name}' item.",
            relay=True,
        ))
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
    chunk_size = block.max_concurrency  # type: ignore[arg-type]
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

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
    state.stack.append(Frame(
        block=pseudo_loop,
        scope_label=scope,
        loop_items=chunks,
        loop_index=0,
    ))
    logger.debug(
        "parallel batched: %d items in %d batches of %d",
        len(items), len(chunks), chunk_size,
    )
    return advance(state)


def _auto_record_dry_run(state: RunState, block: Block, base: str, exec_key: str) -> None:
    """Auto-record a dry-run result and advance."""
    structured = None
    if isinstance(block, LLMStep) and block.output_schema:
        structured = dry_run_structured_output(block.output_schema)
    record_leaf_result(
        state.ctx, base,
        StepResult(
            name=block.name,
            status="dry_run",
            output=f"[dry-run] {block.name}",
            structured_output=structured,
            exec_key=exec_key,
            step_type=_block_step_type(block),
        ),
    )


# ---------------------------------------------------------------------------
# apply_submit() — process a submit and return next action
# ---------------------------------------------------------------------------


def _normalize_confirm(output: str) -> str | None:
    """Normalize confirm answer to 'yes'/'no', or None if invalid."""
    val = output.strip().lower()
    if val in ("yes", "1"):
        return "yes"
    if val in ("no", "2"):
        return "no"
    return None


def apply_submit(  # noqa: C901
    state: RunState,
    exec_key: str,
    output: str = "",
    structured_output: dict[str, Any] | None = None,
    status: str = "success",
    error: str | None = None,
    duration: float = 0.0,
    cost_usd: float | None = None,
    model: str | None = None,
) -> AdvanceResult:
    """Apply a submit to the run state and return the next action.

    Returns (action_dict, new_child_states).
    """
    logger.debug(
        "apply_submit: run_id=%s exec_key=%s status=%s pending=%s",
        state.run_id, exec_key, status, state.pending_exec_key,
    )
    # Idempotency check first: if exec_key was already recorded, return the
    # exact action that was returned when this exec_key was originally submitted.
    # This must precede the completed/error checks because auto-advance may
    # have driven the workflow to completion after the original submit.
    if exec_key in state.ctx.results_scoped and exec_key != state.pending_exec_key:
        cached = state._submit_cache.get(exec_key)
        if cached:
            return cached, []
        # Fallback: no cached action (e.g. restored from checkpoint)
        if state._last_action:
            return state._last_action, []

    if state.status == "completed":
        return _build_error_action(state, "Workflow already completed"), []

    if state.status == "error":
        return _build_error_action(state, "Workflow in error state"), []

    # Validate exec_key
    if exec_key != state.pending_exec_key:
        return _build_error_action(
            state,
            f"Wrong exec_key",
            expected_exec_key=state.pending_exec_key,
            got=exec_key,
        ), []

    # Find current block to get metadata
    frame = state.stack[-1] if state.stack else None
    block = None
    base = ""
    if frame:
        children = _get_frame_children(frame, state)
        if children and frame.block_index < len(children):
            block = children[frame.block_index]
            base = substitute(_base_name(block), state.ctx)

    # Handle cancellation (user picked "Stop workflow" on a retry prompt)
    if status == "cancelled":
        state.status = "cancelled"
        state.pending_exec_key = None
        action = CancelledAction(
            run_id=state.run_id,
            display="Workflow cancelled by user",
        )
        state._last_action = action
        return action, []

    # Validate strict PromptStep: 3-state flow
    #   1. Original question -> invalid answer -> send "try again?" confirm
    #   2. "try again?" -> yes -> re-send original question (goto 1)
    #   3. "try again?" -> no -> cancel workflow
    #   4. "try again?" -> anything else -> re-send "try again?" (goto itself)
    if block and isinstance(block, PromptStep) and block.strict:
        is_retry_confirm = (
            isinstance(state._last_action, AskUserAction)
            and state._last_action.retry_confirm is True
        )

        if is_retry_confirm:
            answer = output.strip().lower()
            if answer == "yes":
                # Re-send original question
                action = _build_ask_user_action(state, step=block, exec_key=exec_key)
                state._last_action = action
                return action, []
            elif answer == "no":
                # Cancel workflow
                state.status = "cancelled"
                state.pending_exec_key = None
                action = CancelledAction(
                    run_id=state.run_id,
                    display="Workflow cancelled by user",
                )
                state._last_action = action
                return action, []
            else:
                # Any other answer -> re-send "try again?"
                action = _build_retry_confirm(state, exec_key, block)
                state._last_action = action
                return action, []

        # Not in retry confirm — validate against original options
        if block.prompt_type == "confirm":
            normalized = _normalize_confirm(output)
            if normalized is None:
                action = _build_retry_confirm(state, exec_key, block)
                state._last_action = action
                return action, []
            output = normalized
        elif block.options:
            valid_options = [substitute(o, state.ctx) for o in block.options]
            if valid_options and output not in valid_options:
                action = _build_retry_confirm(state, exec_key, block)
                state._last_action = action
                return action, []

    # Validate output_schema if present
    if block and isinstance(block, LLMStep) and block.output_schema:
        validated, validation_error = validate_structured_output(
            output, structured_output, block.output_schema,
        )
        if validation_error:
            status = "failure"
            error = validation_error
            structured_output = None
        else:
            structured_output = validated

    # Derive step metadata
    step_type = _block_step_type(block)
    effective_model = model
    if not effective_model and isinstance(block, LLMStep) and block.model:
        effective_model = block.model
    started_at = ""
    if duration > 0:
        from datetime import datetime, timedelta, timezone
        completed_at = datetime.now(timezone.utc)
        started_at = (completed_at - timedelta(seconds=duration)).isoformat()

    # Record the result
    result = StepResult(
        name=block.name if block else exec_key,
        exec_key=exec_key,
        output=output,
        structured_output=structured_output,
        status=status,
        error=error,
        duration=duration,
        cost_usd=cost_usd,
        step_type=step_type,
        model=effective_model,
        started_at=started_at,
    )
    record_leaf_result(state.ctx, base or exec_key, result)

    # Handle result_var for shell steps
    if block and isinstance(block, ShellStep) and block.result_var and status == "success":
        try:
            parsed = json.loads(output)
            state.ctx.variables[block.result_var] = parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # Handle result_var for prompt steps
    if block and isinstance(block, PromptStep) and block.result_var:
        state.ctx.variables[block.result_var] = output

    # Advance past current block
    if frame:
        frame.block_index += 1

    state.status = "running"
    state.pending_exec_key = None

    # Get next action
    result = advance(state)
    # Cache the post-submit action for this exec_key (true idempotency)
    state._submit_cache[exec_key] = result[0]
    return result


def pending_action(state: RunState) -> ActionBase:
    """Re-fetch current pending action without mutating state (for next() tool)."""
    if state._last_action:
        return state._last_action
    if state.status == "completed":
        return _build_completed_action(state)
    if state.pending_exec_key is None:
        return _build_error_action(state, "No pending action")
    return _build_error_action(state, "State inconsistency: pending key but no cached action")
