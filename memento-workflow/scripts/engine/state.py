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

import json
import logging

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
    StructuredOutput,
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
    ActionBase,
    AskUserAction,
    CancelledAction,
)

from ..utils import (
    evaluate_condition,
    record_leaf_result,
    substitute,
    validate_structured_output,
)

from .subworkflow import (
    _handle_subagent_block,
    _handle_subworkflow,
)
from .parallel import (
    _auto_record_dry_run,
    _handle_parallel,
)

from .actions import (
    _build_ask_user_action,
    _build_completed_action,
    _build_dry_run_action,
    _build_error_action,
    _build_halted_action,
    _build_prompt_action,
    _build_retry_confirm,
    _build_shell_action,
)


__all__ = [
    "halt_workflow",
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

        # resume_only: invisible on fresh run, skip without recording
        if block.resume_only != "" and not state.is_resumed:
            frame.block_index += 1
            continue

        # Condition check
        if not evaluate_condition(block.condition, state.ctx):
            # Skip: record as skipped, advance index
            exec_key = _make_exec_key(state, base)
            if _is_leaf(block):
                record_leaf_result(
                    state.ctx,
                    base,
                    StepResult(
                        name=block.name,
                        status="skipped",
                        exec_key=exec_key,
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

        # Hook: notify block entry (dry-run tree builder, tracing, etc.)
        if state._advance_hook:
            state._advance_hook.on_block_enter(
                state, block, _make_exec_key(state, base)
            )

        # Dry-run mode: auto-record leaf and return dry-run action
        if state.ctx.dry_run and _is_leaf(block):
            exec_key = _make_exec_key(state, base)
            action = _build_dry_run_action(state, block, exec_key)
            _auto_record_dry_run(state, block, base, exec_key)
            frame.block_index += 1
            state.pending_exec_key = exec_key
            state._last_action = action
            return action, []

        # Check isolation for subagent dispatch
        is_child = state.parent_run_id is not None

        # SubWorkflow: always goes through _handle_subworkflow (both inline and subagent)
        if isinstance(block, SubWorkflow):
            return _handle_subworkflow(state, block, base, frame)

        if block.isolation == "subagent" and not is_child:
            return _handle_subagent_block(state, block, base)

        # Track ephemeral keys for resume_only="true" (every-resume, not "once")
        if block.resume_only == "true":
            exec_key = _make_exec_key(state, base)
            state._ephemeral_keys.add(exec_key)

        # Leaf blocks: emit action
        if isinstance(block, ShellStep):
            exec_key = _make_exec_key(state, base)
            cmd_display = (block.command or block.script or "")[:80]
            logger.debug(
                "advance: emit shell exec_key=%s cmd=%s", exec_key, cmd_display
            )
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
            logger.debug(
                "advance: emit prompt exec_key=%s prompt=%s", exec_key, block.prompt
            )
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
            state.stack.append(
                Frame(
                    block=block,
                    scope_label=scope,
                    loop_items=items,
                    loop_index=0,
                )
            )
            continue

        if isinstance(block, RetryBlock):
            scope = f"retry:{base}[attempt=0]"
            state.ctx.push_scope(scope)
            state.stack.append(
                Frame(
                    block=block,
                    scope_label=scope,
                    retry_attempt=0,
                )
            )
            continue

        if isinstance(block, ConditionalBlock):
            chosen_idx, chosen_blocks = _resolve_conditional(block, state.ctx)
            if chosen_blocks is None:
                frame.block_index += 1
                continue
            state.stack.append(
                Frame(
                    block=block,
                    chosen_branch_index=chosen_idx,
                    chosen_blocks=chosen_blocks,
                )
            )
            continue

        if isinstance(block, ParallelEachBlock):
            return _handle_parallel(state, block, base)

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
                i,
                block.name,
                exc_info=True,
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
            state.stack.append(
                Frame(
                    block=block,
                    scope_label=scope,
                    loop_items=frame.loop_items,
                    loop_index=next_idx,
                )
            )
            return None

    if isinstance(block, RetryBlock):
        # Check until condition
        try:
            done = block.until(state.ctx)
        except Exception:
            logger.warning(
                "until condition failed for retry '%s', treating as not done",
                block.name,
                exc_info=True,
            )
            done = False
        if not done:
            next_attempt = frame.retry_attempt + 1
            if next_attempt < block.max_attempts:
                base = substitute(_base_name(block), state.ctx)
                scope = f"retry:{base}[attempt={next_attempt}]"
                state.ctx.push_scope(scope)
                state.stack.append(
                    Frame(
                        block=block,
                        scope_label=scope,
                        retry_attempt=next_attempt,
                    )
                )
                return None
            # Exhausted — check halt_on_exhaustion
            if block.halt_on_exhaustion:
                reason = substitute(block.halt_on_exhaustion, state.ctx)
                base = substitute(_base_name(block), state.ctx)
                action, _ = halt_workflow(state, reason, base)
                return action

    # Hook: notify block exit
    if state._advance_hook:
        state._advance_hook.on_block_exit(state, block)

    # Restore variables and prompt_dir (saved by _handle_subworkflow on SubWorkflow entry).
    # The frame's block is WorkflowDef (the target), not SubWorkflow, so check saved_vars.
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
    if (
        isinstance(block, ShellStep)
        and block.result_var
        and recorded.status == "success"
    ):
        try:
            parsed = json.loads(recorded.output)
            state.ctx.variables[block.result_var] = parsed
        except (json.JSONDecodeError, ValueError):
            pass
    if isinstance(block, PromptStep) and block.result_var:
        state.ctx.variables[block.result_var] = recorded.output
    if isinstance(block, LLMStep) and block.result_var and recorded.status == "success":
        if recorded.structured_output is not None:
            state.ctx.variables[block.result_var] = recorded.structured_output
        elif recorded.output:
            try:
                state.ctx.variables[block.result_var] = json.loads(recorded.output)
            except (json.JSONDecodeError, ValueError):
                state.ctx.variables[block.result_var] = recorded.output


# ---------------------------------------------------------------------------
# Halt
# ---------------------------------------------------------------------------


def halt_workflow(state: RunState, reason: str, halted_at: str) -> AdvanceResult:
    """Halt the entire workflow — unwind stack and return HaltedAction."""
    action = _build_halted_action(state, reason, halted_at)
    state.status = "halted"
    state.stack.clear()
    state._last_action = action
    return action, []


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


def _handle_strict_prompt(
    state: RunState,
    block: PromptStep,
    exec_key: str,
    output: str,
) -> AdvanceResult | str:
    """Handle strict PromptStep validation.

    Returns an action tuple if intercepted, or the (possibly normalized)
    output string if validation passed.
    """
    is_retry_confirm = (
        isinstance(state._last_action, AskUserAction)
        and state._last_action.retry_confirm is True
    )

    if is_retry_confirm:
        answer = output.strip().lower()
        if answer == "yes":
            action = _build_ask_user_action(state, step=block, exec_key=exec_key)
            state._last_action = action
            return action, []
        elif answer == "no":
            state.status = "cancelled"
            state.pending_exec_key = None
            action = CancelledAction(
                run_id=state.run_id,
                display="Workflow cancelled by user",
            )
            state._last_action = action
            return action, []
        else:
            action = _build_retry_confirm(state, exec_key, block)
            state._last_action = action
            return action, []

    # Validate against original options
    if block.prompt_type == "confirm":
        normalized = _normalize_confirm(output)
        if normalized is None:
            action = _build_retry_confirm(state, exec_key, block)
            state._last_action = action
            return action, []
        return normalized
    elif block.options:
        valid_options = [substitute(o, state.ctx) for o in block.options]
        if valid_options and output not in valid_options:
            action = _build_retry_confirm(state, exec_key, block)
            state._last_action = action
            return action, []

    return output


def _apply_result_var(
    state: RunState,
    block: Block | None,
    output: str,
    structured_output: StructuredOutput,
    status: str,
) -> None:
    """Store result into context variable if block has result_var."""
    if not block:
        return
    if isinstance(block, ShellStep) and block.result_var and status == "success":
        try:
            state.ctx.variables[block.result_var] = json.loads(output)
        except (json.JSONDecodeError, ValueError):
            pass
    elif isinstance(block, PromptStep) and block.result_var:
        state.ctx.variables[block.result_var] = output
    elif isinstance(block, LLMStep) and block.result_var and status == "success":
        if structured_output is not None:
            state.ctx.variables[block.result_var] = structured_output
        elif output:
            try:
                state.ctx.variables[block.result_var] = json.loads(output)
            except (json.JSONDecodeError, ValueError):
                state.ctx.variables[block.result_var] = output


def apply_submit(  # noqa: C901
    state: RunState,
    exec_key: str,
    output: str = "",
    structured_output: StructuredOutput = None,
    status: str = "success",
    error: str | None = None,
    duration: float = 0.0,
    cost_usd: float | None = None,
    model: str | None = None,
    halt_reason: str | None = None,
    halt_origin: str | None = None,
) -> AdvanceResult:
    """Apply a submit to the run state and return the next action.

    If halt_reason is set, the workflow is halted (used for child halt propagation).
    halt_origin provides the halted_at chain from the child.
    Returns (action_dict, new_child_states).
    """
    logger.debug(
        "apply_submit: run_id=%s exec_key=%s status=%s pending=%s",
        state.run_id,
        exec_key,
        status,
        state.pending_exec_key,
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

    if state.status == "halted":
        return _build_error_action(state, "Workflow is halted"), []

    if state.status == "error":
        return _build_error_action(state, "Workflow in error state"), []

    # Halt propagation: child halt routed through apply_submit boundary
    if halt_reason is not None:
        halted_at = f"{exec_key}\u2190{halt_origin}" if halt_origin else exec_key
        return halt_workflow(state, halt_reason, halted_at)

    # Validate exec_key
    if exec_key != state.pending_exec_key:
        return _build_error_action(
            state,
            "Wrong exec_key",
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

    # Validate strict PromptStep
    if block and isinstance(block, PromptStep) and block.strict:
        strict_result = _handle_strict_prompt(state, block, exec_key, output)
        if isinstance(strict_result, tuple):
            return strict_result
        output = strict_result

    # Validate output_schema if present
    if block and isinstance(block, LLMStep) and block.output_schema:
        validated, validation_error = validate_structured_output(
            output,
            structured_output,
            block.output_schema,
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

    # Store result_var into context variables
    _apply_result_var(state, block, output, structured_output, status)

    # Advance past current block
    if frame:
        frame.block_index += 1

    state.status = "running"
    state.pending_exec_key = None

    # Check halt directive: if the block has halt set, stop the workflow
    if block and block.halt and status == "success":
        reason = substitute(block.halt, state.ctx)
        return halt_workflow(state, reason, exec_key)

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
    return _build_error_action(
        state, "State inconsistency: pending key but no cached action"
    )
