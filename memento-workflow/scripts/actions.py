"""Action response builders for the workflow engine.

All _build_*_action() functions construct typed protocol models returned
by advance() and apply_submit().
"""

from __future__ import annotations

from pathlib import Path

from .artifacts import exec_key_to_artifact_path, write_llm_prompt_artifact
from .core import RunState
from .protocol import (
    ActionBase,
    AskUserAction,
    CompletedAction,
    ErrorAction,
    HaltedAction,
    PromptAction,
    ShellAction,
    SubagentAction,
)
from .types import Block, LLMStep, PromptStep, ShellStep
from .utils import schema_dict, substitute, substitute_with_files


def _build_shell_action(state: RunState, step: ShellStep, exec_key: str) -> ShellAction:
    """Build a shell action."""
    command = substitute(step.command, state.ctx) if step.command else ""
    script_path: str | None = None
    args: str | None = None
    env: dict[str, str] | None = None

    if step.env:
        env = {k: substitute(v, state.ctx) for k, v in step.env.items()}
    if step.script:
        workflow_dir = state.ctx.variables.get("workflow_dir", "")
        if workflow_dir:
            script_path = str(Path(workflow_dir) / step.script)
        else:
            script_path = step.script
        args = substitute(step.args, state.ctx) if step.args else ""

    display_cmd = command or step.script
    cmd_short = display_cmd[:80] + ("..." if len(display_cmd) > 80 else "")

    return ShellAction(
        run_id=state.run_id,
        exec_key=exec_key,
        command=command,
        script_path=script_path,
        args=args,
        env=env,
        result_var=step.result_var or None,
        stdin=step.stdin or None,
        display=f"Step [{exec_key}]: Running shell — {cmd_short}",
    )


def _build_prompt_action(state: RunState, step: LLMStep, exec_key: str) -> PromptAction:
    """Build a prompt action (inline LLM)."""
    context_files: list[str] = []

    # Read raw template
    if step.prompt_text:
        raw = step.prompt_text
    else:
        full = Path(state.ctx.prompt_dir) / step.prompt
        raw = full.read_text(encoding="utf-8")

    # Substitute: externalize large values to files when artifacts are available
    step_dir = state.artifacts_dir / exec_key_to_artifact_path(exec_key) if state.artifacts_dir else None
    if step_dir:
        prompt_text, context_files = substitute_with_files(raw, state.ctx, step_dir)
    else:
        prompt_text = substitute(raw, state.ctx)

    if state.artifacts_dir:
        write_llm_prompt_artifact(state.artifacts_dir, exec_key, prompt_text)

    js = schema_dict(step.output_schema)
    display_label = step.prompt or "(inline)"

    return PromptAction(
        run_id=state.run_id,
        exec_key=exec_key,
        prompt=prompt_text,
        tools=step.tools or None,
        model=step.model,
        json_schema=js or None,
        output_schema_name=step.output_schema.__name__ if js else None,
        context_files=context_files or None,
        result_dir=str(step_dir) if step_dir else None,
        display=f"Step [{exec_key}]: Processing prompt — {display_label}",
    )


def _build_ask_user_action(state: RunState, step: PromptStep, exec_key: str) -> AskUserAction:
    """Build an ask_user action."""
    message = substitute(step.message, state.ctx)
    options: list[str] | None = None
    if step.options:
        options = [substitute(o, state.ctx) for o in step.options]

    opts = ", ".join(options) if options else ""
    display = f"Step [{exec_key}]: Asking user — {message}" + (f" ({opts})" if opts else "")

    return AskUserAction(
        run_id=state.run_id,
        exec_key=exec_key,
        prompt_type=step.prompt_type,
        message=message,
        options=options,
        default=step.default,
        strict=False if not step.strict else None,
        result_var=step.result_var or None,
        display=display,
    )


def _build_retry_confirm(state: RunState, exec_key: str, step: PromptStep) -> AskUserAction:
    """Build a 'try again?' confirmation after an invalid strict answer."""
    message = substitute(step.message, state.ctx)
    return AskUserAction(
        run_id=state.run_id,
        exec_key=exec_key,
        prompt_type="confirm",
        message=f"Your answer didn't match the expected options for: {message}\nTry again? (if no, workflow will be stopped)",
        options=["yes", "no"],
        retry_confirm=True,
        display=f"Step [{exec_key}]: Invalid answer — try again?",
    )


def _build_subagent_action(
    state: RunState, block: Block, exec_key: str,
    *,
    relay: bool = False,
    child_run_id: str | None = None,
    prompt: str = "",
) -> SubagentAction:
    """Build a subagent action."""
    hint = getattr(block, "context_hint", "") or None
    tools: list[str] | None = None
    if isinstance(block, LLMStep) and block.tools:
        tools = block.tools
    model = getattr(block, "model", None)
    mode = "relay" if relay else "single-task"

    return SubagentAction(
        run_id=state.run_id,
        exec_key=exec_key,
        prompt=prompt,
        relay=relay,
        child_run_id=child_run_id,
        context_hint=hint,
        tools=tools,
        model=model,
        display=f"Step [{exec_key}]: Launching {mode} agent — {block.name}",
    )


def _build_completed_action(state: RunState) -> CompletedAction:
    """Build a completed action."""
    has_artifacts = state.artifacts_dir is not None
    summary: dict[str, object] = {}
    for key, r in state.ctx.results.items():
        entry: dict[str, object] = {"status": r.status}
        if has_artifacts:
            entry["artifact"] = exec_key_to_artifact_path(r.exec_key)
            if r.status != "success" and r.output:
                entry["error"] = r.output[:200]
        else:
            if r.status != "success":
                entry["output"] = r.output[:2000] if r.output else ""
            elif r.output:
                entry["output"] = r.output[:120] + ("…" if len(r.output) > 120 else "")
        summary[key] = entry

    # Compute totals from all executed steps (results_scoped, not results)
    total_cost = 0.0
    total_duration = 0.0
    steps_by_type: dict[str, int] = {}
    has_cost = False
    for r in state.ctx.results_scoped.values():
        if r.status in ("skipped", "dry_run"):
            continue
        total_duration += r.duration
        if r.cost_usd is not None:
            total_cost += r.cost_usd
            has_cost = True
        if r.step_type:
            steps_by_type[r.step_type] = steps_by_type.get(r.step_type, 0) + 1

    totals: dict[str, object] = {
        "duration": round(total_duration, 3),
        "step_count": len([r for r in state.ctx.results_scoped.values() if r.status not in ("skipped", "dry_run")]),
    }
    if has_cost:
        totals["cost_usd"] = round(total_cost, 6)
    if steps_by_type:
        totals["steps_by_type"] = steps_by_type

    return CompletedAction(
        run_id=state.run_id,
        summary=summary,
        totals=totals,
        display=f"Workflow completed ({len(summary)} steps)",
    )


def _build_halted_action(state: RunState, reason: str, halted_at: str) -> HaltedAction:
    """Build a halted action — workflow stopped by a halt directive."""
    return HaltedAction(
        run_id=state.run_id,
        reason=reason,
        halted_at=halted_at,
        display=f"Workflow halted at [{halted_at}]: {reason}",
    )


def _build_error_action(
    state: RunState,
    message: str,
    *,
    expected_exec_key: str | None = None,
    got: str | None = None,
    exec_key: str | None = None,
) -> ErrorAction:
    """Build an error action."""
    return ErrorAction(
        run_id=state.run_id,
        message=message,
        exec_key=exec_key,
        expected_exec_key=expected_exec_key,
        got=got,
        display=f"Error: {message}",
    )


def _build_dry_run_action(state: RunState, block: Block, exec_key: str) -> ActionBase:
    """Build a dry-run action for a leaf block."""
    if isinstance(block, ShellStep):
        if block.script:
            workflow_dir = state.ctx.variables.get("workflow_dir", "")
            script_path = str(Path(workflow_dir) / block.script) if workflow_dir else block.script
            args = substitute(block.args, state.ctx) if block.args else ""
            env: dict[str, str] | None = None
            if block.env:
                env = {k: substitute(v, state.ctx) for k, v in block.env.items()}
            return ShellAction(
                run_id=state.run_id,
                exec_key=exec_key,
                command="",
                script_path=script_path,
                args=args,
                env=env,
                dry_run=True,
            )
        command = substitute(block.command, state.ctx)
        return ShellAction(
            run_id=state.run_id,
            exec_key=exec_key,
            command=command,
            dry_run=True,
        )
    if isinstance(block, PromptStep):
        message = substitute(block.message, state.ctx)
        return AskUserAction(
            run_id=state.run_id,
            exec_key=exec_key,
            prompt_type=block.prompt_type,
            message=message,
            options=block.options or None,
            dry_run=True,
        )
    if isinstance(block, LLMStep):
        label = block.prompt or "(inline)"
        js = schema_dict(block.output_schema)
        return PromptAction(
            run_id=state.run_id,
            exec_key=exec_key,
            prompt=f"[dry-run] {label}",
            json_schema=js or None,
            dry_run=True,
        )
    return ErrorAction(
        run_id=state.run_id,
        message=f"Unknown block type for dry-run: {type(block).__name__}",
        exec_key=exec_key,
        display=f"Error: unknown block type {type(block).__name__}",
    )
