"""Universal recursive executor for the imperative workflow engine.

Dispatches blocks by type: llm step, prompt, shell, group, parallel-each,
loop, retry, conditional, and sub-workflow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
import time
import hashlib
import copy
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal
import contextvars

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

if TYPE_CHECKING:
    from typing import Protocol


# ---------------------------------------------------------------------------
# Result identity + storage helpers
# ---------------------------------------------------------------------------


def workflow_hash(workflow: WorkflowDef) -> str:
    """Hash the workflow's source file content (strict resume drift check)."""
    source = getattr(workflow, "source_path", "") or ""
    if not source:
        return ""
    try:
        data = Path(source).read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()


def _results_key(ctx: WorkflowContext, base: str) -> str:
    """Convenience key for ctx.results: dot-prefix subworkflow stack only."""
    subs: list[str] = []
    # Scope parts are strings like "sub:name", "loop:...", "retry:...", "par:..."
    for part in getattr(ctx, "_scope", []):
        if part.startswith("sub:"):
            subs.append(part.removeprefix("sub:"))
    if subs:
        return ".".join([*subs, base])
    return base


def _record_leaf_result(
    ctx: WorkflowContext,
    base: str,
    result: StepResult,
    *,
    update_last: bool = True,
    order: int | None = None,
) -> StepResult:
    """Record a leaf StepResult into scoped + convenience stores."""
    if not result.exec_key:
        result.exec_key = ctx.scoped_exec_key(base)
    result.base = base
    result.results_key = _results_key(ctx, base)
    if order is None:
        result.order = ctx.next_order()
    else:
        result.order = order

    ctx.results_scoped[result.exec_key] = result
    if update_last:
        ctx.results[result.results_key] = result
    return result


# ---------------------------------------------------------------------------
# Progress feedback
# ---------------------------------------------------------------------------

logger = logging.getLogger("workflow-engine")


def _emit(ctx: WorkflowContext, message: str) -> None:
    """Print an indented progress line based on current scope depth."""
    depth = len(getattr(ctx, "_scope", []))
    indent = "  " * (depth + 1)
    print(f"{indent}{message}")


# ---------------------------------------------------------------------------
# Interactive IO — IOHandler protocol + implementations
# ---------------------------------------------------------------------------


class StopForInput(Exception):
    """Signal that workflow needs user input."""

    def __init__(
        self,
        key: str,
        step_name: str,
        prompt_type: str,
        message: str,
        options: list[str],
        default: str | None,
        strict: bool = True,
    ):
        self.key = key
        self.step_name = step_name
        self.prompt_type = prompt_type
        self.message = message
        self.options = options
        self.default = default
        self.strict = strict
        super().__init__(f"Input needed at '{key}': {message}")


class StdinIOHandler:
    """Terminal: print question, read stdin."""

    def prompt(
        self,
        key: str,
        prompt_type: str,
        message: str,
        options: list[str],
        default: str | None,
        strict: bool = True,
    ) -> str:
        print(f"\n{message}")
        if options:
            for i, opt in enumerate(options, 1):
                print(f"  {i}. {opt}")
        if default:
            print(f"  [default: {default}]")
        answer = input("> ").strip()
        return answer or default or ""


class PresetIOHandler:
    """Non-interactive: return preset answers, or raise StopForInput for missing ask_user."""

    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    def prompt(
        self,
        key: str,
        prompt_type: str,
        message: str,
        options: list[str],
        default: str | None,
        strict: bool = True,
    ) -> str:
        if key in self.answers:
            return self.answers[key]
        # For ask_user (LLM) prompts without a preset answer, stop and ask for input.
        # For other prompts (PromptStep), return default if available.
        if prompt_type == "input" or prompt_type == "ask_user":
            raise StopForInput(key, key, prompt_type, message, options, default, strict=strict)
        return default or ""


class StopIOHandler:
    """Claude Code: raise StopForInput on first unanswered prompt."""

    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    def prompt(
        self,
        key: str,
        prompt_type: str,
        message: str,
        options: list[str],
        default: str | None,
        strict: bool = True,
    ) -> str:
        if key in self.answers:
            return self.answers[key]
        raise StopForInput(key, key, prompt_type, message, options, default, strict=strict)


#
# Note: LLM steps are non-interactive by default; user prompting is handled via PromptStep.
#


# ---------------------------------------------------------------------------
# Lazy SDK import — fails gracefully with install instructions
# ---------------------------------------------------------------------------

_sdk_available = False
try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        query,
    )

    _sdk_available = True
except ImportError:
    pass


_CURRENT_STEP_EXEC_KEY: contextvars.ContextVar[str] = contextvars.ContextVar(
    "workflow_engine_current_step_exec_key",
    default="",
)


class _EmergentAskUserCapture:
    def __init__(self) -> None:
        self.question_key: str = ""
        self.step_name: str = ""
        self.message: str = ""
        self.options: list[str] = []

    def capture(self, *, question_key: str, step_name: str, message: str, options: list[str]) -> None:
        if self.question_key:
            return
        self.question_key = question_key
        self.step_name = step_name
        self.message = message
        self.options = options


def _build_engine_mcp_server(
    io_handler: Any,
    capture: _EmergentAskUserCapture | None = None,
) -> Any:
    """Build an MCP server with the ask_user tool.

    When *capture* is provided (non-interactive StopIOHandler mode), the handler
    catches StopForInput and stores the question in capture instead of letting the
    exception propagate (the MCP framework would swallow it as a tool result text).
    The engine checks capture after query() finishes and raises StopForInput itself.
    """
    from claude_agent_sdk import create_sdk_mcp_server, tool

    _ASK_USER_SCHEMA = {"message": str, "options": list}

    @tool(
        "ask_user",
        "Ask the user a question to clarify preferences or ambiguity. Returns the user's answer as text.",
        _ASK_USER_SCHEMA,
    )
    async def ask_user(args: dict) -> dict:
        message = str(args.get("message", "") or "")
        options = args.get("options", [])
        if not isinstance(options, list):
            options = []
        options = [str(o) for o in options]

        step_exec_key = _CURRENT_STEP_EXEC_KEY.get() or "ask_user"
        q_key = _ask_user_key(step_exec_key, message, options)

        handler = io_handler or StdinIOHandler()
        try:
            answer = handler.prompt(q_key, "input", message, options, None, strict=False)
        except StopForInput:
            # Non-interactive mode: StopIOHandler raised StopForInput.
            # Store in capture so the engine can raise it after query() ends.
            if capture is not None:
                logger.debug("MCP ask_user: captured stop key=%s", q_key)
                capture.capture(
                    question_key=q_key,
                    step_name=step_exec_key.split("/")[-1] or step_exec_key,
                    message=message,
                    options=options,
                )
            return {"content": [{"type": "text", "text": f"STOP: user input required (key={q_key})"}]}
        return {"content": [{"type": "text", "text": answer}]}

    return create_sdk_mcp_server(
        name="engine",
        version="1.0.0",
        tools=[ask_user],
    )


def _build_noop_mcp_server() -> Any:
    """Build an MCP server with no tools.

    Used to keep stdin open for the control protocol (can_use_tool) even
    when the step doesn't need ask_user.  The SDK only keeps stdin open
    when sdk_mcp_servers is non-empty; without this, the inner CLI's
    permission requests fail with "Stream closed".
    """
    from claude_agent_sdk import create_sdk_mcp_server

    return create_sdk_mcp_server(name="engine", version="1.0.0", tools=[])


def _build_can_use_tool(
    *,
    allowed_tools: list[str],
    capture: _EmergentAskUserCapture | None = None,
    io_handler: Any = None,
) -> Callable[..., Any]:
    """Build SDK can_use_tool callback that respects user's permission mode.

    Instead of forcing bypassPermissions, we handle permission requests
    programmatically: allow tools in allowed_tools, deny everything else.
    For ask_user specifically, intercept to capture the question and stop.
    """
    allowed_set = set(allowed_tools)

    async def _guard(tool_name: str, tool_input: dict[str, Any], _context: Any) -> Any:
        logger.debug("can_use_tool called: tool=%s", tool_name)

        # ask_user interception (non-interactive stop/resume).
        if tool_name == "mcp__engine__ask_user" and capture is not None:
            step_exec_key = _CURRENT_STEP_EXEC_KEY.get() or ""

            message = str(tool_input.get("message", "") or "")
            options = tool_input.get("options", [])
            if not isinstance(options, list):
                options = []
            options = [str(o) for o in options]

            q_key = _ask_user_key(step_exec_key, message, options)
            # If preset answer exists, allow tool execution.
            if isinstance(io_handler, StopIOHandler) and q_key in getattr(io_handler, "answers", {}):
                logger.debug("can_use_tool: ALLOW (preset answer for %s)", q_key)
                return PermissionResultAllow()

            logger.debug("can_use_tool: DENY+interrupt, capturing key=%s", q_key)
            capture.capture(question_key=q_key, step_name=step_exec_key.split("/")[-1] or step_exec_key, message=message, options=options)
            return PermissionResultDeny(message="User input required.", interrupt=True)

        # Allow tools declared in the step's allowed_tools list.
        if tool_name in allowed_set:
            logger.debug("can_use_tool: ALLOW (in allowed_tools)")
            return PermissionResultAllow()

        # Deny anything not explicitly allowed.
        logger.debug("can_use_tool: DENY (not in allowed_tools: %s)", allowed_set)
        return PermissionResultDeny(message=f"Tool {tool_name} is not allowed for this step.", interrupt=False)

    return _guard


def _require_sdk() -> None:
    if not _sdk_available:
        raise RuntimeError(
            "claude-agent-sdk is required but not installed.\n"
            "Install it with:  uv pip install claude-agent-sdk\n"
            "  (or: pip install claude-agent-sdk)"
        )
    # The workflow engine runs as a Claude Code skill (child process).
    # The SDK spawns Claude Code as its own subprocess, which refuses to start
    # if it detects a parent session via CLAUDECODE env var.  Strip it so the
    # SDK subprocess can launch.  This only affects the engine's process, not
    # the parent Claude Code session.
    os.environ.pop("CLAUDECODE", None)


# ---------------------------------------------------------------------------
# Template substitution
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\{\{([\w.\-]+)\}\}")


def _substitute(template: str, ctx: WorkflowContext) -> str:
    """Replace {{results.X}} and {{variables.X}} in a string."""

    def _replace(m: re.Match) -> str:
        val = ctx.get_var(m.group(1))
        if val is None:
            return m.group(0)  # leave unresolved
        if isinstance(val, (dict, list)):
            return json.dumps(val, indent=2)
        return str(val)

    return _VAR_RE.sub(_replace, template)


# ---------------------------------------------------------------------------
# Prompt & schema loading
# ---------------------------------------------------------------------------


def load_prompt(path: str, ctx: WorkflowContext) -> str:
    """Read a prompt file and substitute template variables."""
    full = Path(ctx.prompt_dir) / path
    text = full.read_text(encoding="utf-8")
    return _substitute(text, ctx)


def _fake_sdk_enabled() -> bool:
    return os.environ.get("WORKFLOW_ENGINE_FAKE_SDK", "") == "1"


def _sdk_debug_enabled() -> bool:
    return os.environ.get("WORKFLOW_ENGINE_SDK_DEBUG", "") == "1"


def _apply_sdk_debug(opts_kwargs: dict[str, Any]) -> None:
    """Capture Claude Code CLI stderr (avoid polluting parent stdout/stderr).

    The SDK transport always runs Claude Code with `--verbose`. If we let the
    CLI inherit the parent's stderr, some hosts (notably agent "bash tools")
    can truncate/cap captured output and hide later engine prints (like the
    workflow_question JSON). Piping stderr into our logger keeps the runner's
    output small and makes failures diagnosable via `execution.log`.
    """

    def _stderr_cb(line: str) -> None:
        # Keep it terse; full CLI output can be noisy.
        logger.debug("[claude stderr] %s", line)

    # Always capture stderr to avoid drowning the host output capture.
    opts_kwargs.setdefault("stderr", _stderr_cb)

    # Optional extra verbosity (still routed through the stderr callback).
    if _sdk_debug_enabled():
        opts_kwargs.setdefault("extra_args", {})
        opts_kwargs["extra_args"]["debug-to-stderr"] = None

_FAKE_ASK_USER_RE = re.compile(r"\[\[ASK_USER\s+(?P<payload>\{.*\})\s*\]\]")


def _fake_extract_ask_user(prompt_text: str) -> dict[str, Any] | None:
    """Extract [[ASK_USER {...json...}]] marker from a prompt."""
    m = _FAKE_ASK_USER_RE.search(prompt_text)
    if not m:
        return None
    try:
        payload = json.loads(m.group("payload"))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _ask_user_key(step_exec_key: str, message: str, options: list[str]) -> str:
    payload = {"message": message, "options": options}
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:10]
    return f"{step_exec_key}/ask:{fingerprint}"


async def _as_stream(prompt_text: str) -> Any:
    """Wrap a string prompt into a streaming-mode input iterable.

    Required for can_use_tool callback (SDK needs streaming mode for the
    bidirectional control protocol).
    """
    yield {
        "type": "user",
        "session_id": "",
        "message": {"role": "user", "content": prompt_text},
        "parent_tool_use_id": None,
    }



def _schema_dict(model: type | None) -> dict[str, Any] | None:
    """Convert a Pydantic model class to a JSON Schema dict."""
    if model is None:
        return None
    return model.model_json_schema()


def _dry_run_structured_output(model: Any) -> Any:
    """Generate minimal structured output for LLMStep dry-runs.

    This helps downstream blocks (loops/parallel) that depend on structured_output
    avoid failing purely due to dry-run placeholders.
    """
    if model is None:
        return None
    if not hasattr(model, "model_fields"):
        return None

    try:
        from pydantic_core import PydanticUndefined  # type: ignore
    except Exception:  # pragma: no cover
        PydanticUndefined = object()  # type: ignore[assignment]

    data: dict[str, Any] = {}
    for name, field in model.model_fields.items():  # type: ignore[attr-defined]
        ann = getattr(field, "annotation", None)
        default = getattr(field, "default", None)
        if default is not None and default is not PydanticUndefined:
            data[name] = default
            continue

        origin = getattr(ann, "__origin__", None)
        args = getattr(ann, "__args__", ())

        # Basic containers
        if origin is list:
            data[name] = []
            continue
        if origin is dict:
            data[name] = {}
            continue

        # Literals: pick the first option
        if origin is Literal and args:
            data[name] = args[0]
            continue

        # Common scalars
        if ann in (str,):
            data[name] = ""
        elif ann in (int,):
            data[name] = 0
        elif ann in (float,):
            data[name] = 0.0
        elif ann in (bool,):
            data[name] = False
        else:
            # Nested BaseModel (best-effort)
            if hasattr(ann, "model_fields"):
                data[name] = _dry_run_structured_output(ann)
            else:
                data[name] = None

    try:
        return model.model_validate(data).model_dump()
    except Exception:
        return data


def _parse_structured_output(
    output_text: str,
    output_schema: Any,
) -> Any:
    """Best-effort structured output parsing/validation.

    In atomic LLMStep execution, the SDK may populate ResultMessage.structured_output.
    In shared-session execution (GroupBlock step_segments), structured_output may be
    missing even when the model outputs JSON. This helper provides a consistent
    fallback so downstream workflows can rely on structured_output when a schema
    was declared.
    """
    if not output_text.strip():
        return None
    try:
        data = json.loads(output_text)
    except (json.JSONDecodeError, ValueError):
        return None

    # If a pydantic model class was provided, validate and return a dict.
    try:
        if output_schema is not None and hasattr(output_schema, "model_validate"):
            return output_schema.model_validate(data).model_dump()
    except Exception:
        # If validation fails, keep raw parsed JSON to avoid losing information.
        return data

    return data


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def evaluate_condition(
    cond: Callable[[WorkflowContext], bool] | None,
    ctx: WorkflowContext,
) -> bool:
    """Call a condition callable, or return True if None."""
    if cond is None:
        return True
    return cond(ctx)


# ---------------------------------------------------------------------------
# Block executors
# ---------------------------------------------------------------------------


async def execute_llm_step(step: LLMStep, ctx: WorkflowContext) -> StepResult:
    """Execute a single LLMStep via SDK query()."""
    if not evaluate_condition(step.condition, ctx):
        base = _substitute(step.key or step.name, ctx)
        return _record_leaf_result(
            ctx, base, StepResult(name=step.name, status="skipped", exec_key=ctx.scoped_exec_key(base))
        )

    if ctx.dry_run:
        base = _substitute(step.key or step.name, ctx)
        structured = _dry_run_structured_output(step.output_schema)
        return _record_leaf_result(
            ctx,
            base,
            StepResult(
                name=step.name,
                status="dry_run",
                output=f"[dry-run] {step.prompt}",
                structured_output=structured,
                exec_key=ctx.scoped_exec_key(base),
            ),
        )

    base = _substitute(step.key or step.name, ctx)
    prompt_text = load_prompt(step.prompt, ctx)
    schema = _schema_dict(step.output_schema)

    # Test-only fake SDK path: allows deterministic ask_user + resume without network/SDK.
    if _fake_sdk_enabled():
        ask = _fake_extract_ask_user(prompt_text) if "ask_user" in step.tools else None
        if ask is not None:
            message = str(ask.get("message", "") or "")
            options = ask.get("options", [])
            if not isinstance(options, list):
                options = []
            options = [str(o) for o in options]

            step_exec_key = ctx.scoped_exec_key(base)
            q_key = _ask_user_key(step_exec_key, message, options)

            if isinstance(ctx.io_handler, StopIOHandler) and q_key not in getattr(ctx.io_handler, "answers", {}):
                raise StopForInput(q_key, step.name, "input", message, options, None, strict=False)

            handler = ctx.io_handler or StdinIOHandler()
            try:
                answer = handler.prompt(q_key, "input", message, options, None, strict=False)
            except StopForInput:
                raise StopForInput(q_key, step.name, "input", message, options, None, strict=False)

            result = StepResult(
                name=step.name,
                output=f"answer: {answer}",
                structured_output=None,
                status="success",
                duration=0.0,
                cost_usd=None,
                exec_key=step_exec_key,
            )
            return _record_leaf_result(ctx, base, result)

        # No ask_user marker: return deterministic output.
        result = StepResult(
            name=step.name,
            output=prompt_text.strip() or f"fake:{step.name}",
            structured_output=None,
            status="success",
            duration=0.0,
            cost_usd=None,
            exec_key=ctx.scoped_exec_key(base),
        )
        return _record_leaf_result(ctx, base, result)

    _require_sdk()

    step_exec_key = ctx.scoped_exec_key(base)
    token = _CURRENT_STEP_EXEC_KEY.set(step_exec_key)

    # ask_user capture for non-interactive stop/resume.
    capture: _EmergentAskUserCapture | None = None

    resolved_tools = [("mcp__engine__ask_user" if t == "ask_user" else t) for t in step.tools]
    opts_kwargs: dict[str, Any] = {
        "allowed_tools": resolved_tools,
        "cwd": ctx.cwd,
        # Inherit user's permission settings so the inner CLI applies the same
        # allow/deny rules the user configured in their Claude Code session.
        "setting_sources": ["user", "project", "local"],
    }
    _apply_sdk_debug(opts_kwargs)
    if step.model:
        opts_kwargs["model"] = step.model
    if schema:
        opts_kwargs["output_format"] = {"type": "json_schema", "schema": schema}

    if "ask_user" in step.tools and ctx.io_handler is not None:
        if isinstance(ctx.io_handler, StopIOHandler):
            capture = _EmergentAskUserCapture()
        opts_kwargs["mcp_servers"] = {"engine": _build_engine_mcp_server(ctx.io_handler, capture=capture)}
    else:
        # Noop MCP server keeps stdin open so the control protocol
        # (can_use_tool) works.  Without an MCP server the SDK closes
        # stdin immediately after the prompt, breaking permission callbacks.
        opts_kwargs["mcp_servers"] = {"engine": _build_noop_mcp_server()}

    # can_use_tool handles permission requests programmatically:
    # allows tools in allowed_tools, intercepts ask_user for stop/resume.
    # Requires streaming mode prompt.
    prompt_arg: Any = _as_stream(prompt_text)
    opts_kwargs["can_use_tool"] = _build_can_use_tool(
        allowed_tools=resolved_tools,
        capture=capture,
        io_handler=ctx.io_handler,
    )

    options = ClaudeAgentOptions(**opts_kwargs)
    t0 = time.time()
    output_text = ""
    structured = None
    cost = None

    try:
        async for message in query(prompt=prompt_arg, options=options):
            logger.debug("SDK message: type=%s %r", type(message).__name__, message)
            if isinstance(message, ResultMessage):
                output_text = getattr(message, "result", "") or ""
                structured = getattr(message, "structured_output", None)
                cost = getattr(message, "total_cost_usd", None)
                logger.debug("Result output: %s", output_text[:500] if output_text else "(empty)")
    except Exception as exc:
        import traceback as _tb
        logger.debug("SDK query exception: %s\n%s", exc, _tb.format_exc())
        if capture and capture.question_key:
            _CURRENT_STEP_EXEC_KEY.reset(token)
            raise StopForInput(
                capture.question_key,
                step.name,
                "input",
                capture.message,
                capture.options,
                None,
                strict=False,
            )
        _CURRENT_STEP_EXEC_KEY.reset(token)
        return _record_leaf_result(
            ctx,
            base,
            StepResult(
                name=step.name,
                status="failure",
                error=str(exc),
                duration=time.time() - t0,
                exec_key=ctx.scoped_exec_key(base),
            ),
        )

    logger.debug("Post-query capture check: capture=%s, key=%r", capture is not None, capture.question_key if capture else "N/A")
    if capture and capture.question_key:
        _CURRENT_STEP_EXEC_KEY.reset(token)
        raise StopForInput(
            capture.question_key,
            step.name,
            "input",
            capture.message,
            capture.options,
            None,
            strict=False,
        )

    result = StepResult(
        name=step.name,
        output=output_text,
        structured_output=structured,
        status="success",
        duration=time.time() - t0,
        cost_usd=cost,
        exec_key=ctx.scoped_exec_key(base),
    )
    _CURRENT_STEP_EXEC_KEY.reset(token)
    return _record_leaf_result(ctx, base, result)


async def execute_llm_segment(steps: list[LLMStep], ctx: WorkflowContext) -> list[StepResult]:
    """Execute multiple LLM steps within a shared ClaudeSDKClient session.

    This is used by GroupBlock when llm_session_policy == "step_segments".
    """
    if ctx.dry_run:
        results: list[StepResult] = []
        for step in steps:
            r = await execute_llm_step(step, ctx)
            results.append(r)
        return results

    # Resume cache: if ALL steps already have cached results, skip SDK session entirely.
    _cached: list[tuple[str, StepResult]] = []
    _all_cached = True
    for step in steps:
        base = _substitute(step.key or step.name, ctx)
        exec_key = ctx.scoped_exec_key(base)
        if not evaluate_condition(step.condition, ctx):
            _cached.append((base, StepResult(name=step.name, status="skipped", exec_key=exec_key)))
            continue
        prior = ctx.injected_results_scoped.get(exec_key)
        if prior and prior.status == "success":
            _cached.append((base, prior))
        else:
            _all_cached = False
            break
    if _all_cached and _cached:
        results: list[StepResult] = []
        for base, prior in _cached:
            ctx.results_scoped[prior.exec_key] = prior
            ctx.results[_results_key(ctx, base)] = prior
            _emit(ctx, f"\u21a9 {base} (cached)")
            logger.info("[%s] resumed from cache", base)
            results.append(prior)
        return results

    # Fake SDK: fall back to atomic executor per step.
    if _fake_sdk_enabled():
        results: list[StepResult] = []
        for step in steps:
            r = await execute_llm_step(step, ctx)
            results.append(r)
        return results

    _require_sdk()

    # Union allowed tools across the segment.
    allowed_tools = list({("mcp__engine__ask_user" if t == "ask_user" else t) for s in steps for t in s.tools})

    # Pick a model for the segment (all steps in the segment should be compatible).
    seg_model = next((s.model for s in steps if s.model), None)

    opts_kwargs: dict[str, Any] = {
        "allowed_tools": allowed_tools,
        "cwd": ctx.cwd,
        "setting_sources": ["user", "project", "local"],
    }
    _apply_sdk_debug(opts_kwargs)
    if seg_model:
        opts_kwargs["model"] = seg_model

    # ask_user segment support (only if any step declares it).
    capture: _EmergentAskUserCapture | None = None
    if any("ask_user" in s.tools for s in steps) and ctx.io_handler is not None:
        if isinstance(ctx.io_handler, StopIOHandler):
            capture = _EmergentAskUserCapture()
        opts_kwargs["mcp_servers"] = {"engine": _build_engine_mcp_server(ctx.io_handler, capture=capture)}
    else:
        opts_kwargs["mcp_servers"] = {"engine": _build_noop_mcp_server()}

    # can_use_tool handles permission requests programmatically.
    opts_kwargs["can_use_tool"] = _build_can_use_tool(
        allowed_tools=allowed_tools,
        capture=capture,
        io_handler=ctx.io_handler,
    )

    results: list[StepResult] = []
    options = ClaudeAgentOptions(**opts_kwargs)

    async with ClaudeSDKClient(options=options) as client:
        for step in steps:
            if not evaluate_condition(step.condition, ctx):
                base = _substitute(step.key or step.name, ctx)
                r = _record_leaf_result(
                    ctx,
                    base,
                    StepResult(name=step.name, status="skipped", exec_key=ctx.scoped_exec_key(base)),
                )
                results.append(r)
                continue

            base = _substitute(step.key or step.name, ctx)
            step_exec_key = ctx.scoped_exec_key(base)
            token = _CURRENT_STEP_EXEC_KEY.set(step_exec_key)
            prompt_text = load_prompt(step.prompt, ctx)
            schema = _schema_dict(step.output_schema)

            if schema:
                # For structured output within a session, append schema instruction.
                prompt_text += (
                    "\n\nRespond with JSON matching this schema:\n"
                    f"```json\n{json.dumps(schema, indent=2)}\n```"
                )

            t0 = time.time()
            output_text = ""
            structured = None
            cost = None

            try:
                await client.query(prompt_text)
                async for message in client.receive_response():
                    if isinstance(message, ResultMessage):
                        output_text = getattr(message, "result", "") or ""
                        structured = getattr(message, "structured_output", None)
                        cost = getattr(message, "total_cost_usd", None)
            except Exception as exc:
                _CURRENT_STEP_EXEC_KEY.reset(token)
                if capture and capture.question_key:
                    raise StopForInput(
                        capture.question_key,
                        step.name,
                        "input",
                        capture.message,
                        capture.options,
                        None,
                        strict=False,
                    )
                r = _record_leaf_result(
                    ctx,
                    base,
                    StepResult(
                        name=step.name,
                        status="failure",
                        error=str(exc),
                        duration=time.time() - t0,
                        exec_key=ctx.scoped_exec_key(base),
                    ),
                )
                results.append(r)
                continue

            # Ensure consistent structured_output behavior in step_segments mode.
            if structured is None and step.output_schema is not None:
                structured = _parse_structured_output(output_text, step.output_schema)

            _CURRENT_STEP_EXEC_KEY.reset(token)

            if capture and capture.question_key:
                raise StopForInput(
                    capture.question_key,
                    step.name,
                    "input",
                    capture.message,
                    capture.options,
                    None,
                    strict=False,
                )

            r = _record_leaf_result(
                ctx,
                base,
                StepResult(
                    name=step.name,
                    output=output_text,
                    structured_output=structured,
                    status="success",
                    duration=time.time() - t0,
                    cost_usd=cost,
                    exec_key=ctx.scoped_exec_key(base),
                ),
            )
            results.append(r)

    return results


async def execute_parallel_each(
    block: ParallelEachBlock,
    ctx: WorkflowContext,
    *,
    registry: dict[str, WorkflowDef] | None = None,
) -> list[StepResult]:
    """Run a template (any blocks) concurrently for each item."""
    if not evaluate_condition(block.condition, ctx):
        return [StepResult(name=block.name, status="skipped")]

    items = ctx.get_var(block.parallel_for)
    if not isinstance(items, list):
        return [StepResult(name=block.name, status="failure", error=f"{block.parallel_for} is not a list")]

    semaphore: asyncio.Semaphore | None = None
    if block.max_concurrency and block.max_concurrency > 0:
        semaphore = asyncio.Semaphore(block.max_concurrency)

    async def _run_lane(item: Any, idx: int) -> dict[str, Any]:
        lane_results: list[StepResult] = []

        async def _run() -> None:
            # Create an isolated context copy with the item injected.
            child_vars = copy.deepcopy(ctx.variables)
            child_vars[block.item_var] = item
            child_vars[f"{block.item_var}_index"] = idx
            child_ctx = WorkflowContext(
                results=dict(ctx.results),
                results_scoped=dict(ctx.results_scoped),
                injected_results_scoped=dict(ctx.injected_results_scoped),
                variables=child_vars,
                cwd=ctx.cwd,
                dry_run=ctx.dry_run,
                prompt_dir=ctx.prompt_dir,
                io_handler=ctx.io_handler,
            )
            # Inherit scope from parent and add parallel scope.
            child_ctx._scope = list(getattr(ctx, "_scope", [])) + [f"par:{block.name}[i={idx}]"]  # type: ignore[attr-defined]

            for inner in block.template:
                r = await execute_block(inner, child_ctx, registry=registry)
                if isinstance(r, list):
                    lane_results.extend(r)
                else:
                    lane_results.append(r)

        try:
            if semaphore is None:
                await _run()
            else:
                async with semaphore:
                    await _run()
            return {"idx": idx, "results": lane_results, "stop": None, "error": None}
        except StopForInput as stop:
            return {"idx": idx, "results": lane_results, "stop": stop, "error": None}
        except Exception as exc:
            return {"idx": idx, "results": lane_results, "stop": None, "error": exc}

    outcomes = await asyncio.gather(*[_run_lane(item, i) for i, item in enumerate(items)])

    # Record all lane results deterministically (by lane index, then execution order).
    outcomes_sorted = sorted(outcomes, key=lambda o: o["idx"])
    collected: list[StepResult] = []
    stops: list[StopForInput] = []

    for o in outcomes_sorted:
        if o["error"] is not None:
            # Record as a single failure result for the parallel container itself.
            collected.append(
                StepResult(
                    name=block.name,
                    status="failure",
                    error=str(o["error"]),
                )
            )
            continue

        lane_results = o["results"]
        for r in lane_results:
            # Ensure base/exec_key are set; re-record in parent for deterministic ordering.
            base = r.base or r.name
            _record_leaf_result(ctx, base, r, update_last=True)
            collected.append(r)

        if o["stop"] is not None:
            stops.append(o["stop"])

    if block.merge_policy == "namespaced_variables":
        ctx.variables.setdefault(f"parallel:{block.name}", {})
        # Note: we currently do not merge lane variables; this is a placeholder for future enhancement.

    # After checkpointing all completed work, raise the first StopForInput deterministically.
    if stops:
        raise stops[0]

    return collected


async def execute_group(
    block: GroupBlock,
    ctx: WorkflowContext,
    *,
    registry: dict[str, WorkflowDef] | None = None,
) -> list[StepResult]:
    """Execute a GroupBlock sequentially, optionally segmenting LLM steps."""
    if not evaluate_condition(block.condition, ctx):
        return [StepResult(name=block.name, status="skipped")]

    if block.llm_session_policy == "none":
        results: list[StepResult] = []
        for inner in block.blocks:
            r = await execute_block(inner, ctx, registry=registry)
            if isinstance(r, list):
                results.extend(r)
            else:
                results.append(r)
        return results

    # step_segments: execute contiguous LLMStep runs in shared session.
    results: list[StepResult] = []
    i = 0
    while i < len(block.blocks):
        b = block.blocks[i]
        if not isinstance(b, LLMStep):
            r = await execute_block(b, ctx, registry=registry)
            if isinstance(r, list):
                results.extend(r)
            else:
                results.append(r)
            i += 1
            continue

        # Build a compatible segment: contiguous LLMStep with compatible models
        # and consistent ask_user capability (opt-in stays true per step).
        seg: list[LLMStep] = []
        seg_model: str | None = None
        seg_ask_user: bool | None = None
        j = i
        while j < len(block.blocks) and isinstance(block.blocks[j], LLMStep):
            step = block.blocks[j]
            assert isinstance(step, LLMStep)
            step_model = step.model
            if seg_model and step_model and step_model != seg_model:
                break
            if seg_model is None and step_model:
                seg_model = step_model
            step_ask_user = "ask_user" in step.tools
            if seg_ask_user is None:
                seg_ask_user = step_ask_user
            elif step_ask_user != seg_ask_user:
                break
            seg.append(step)
            j += 1

        seg_results = await execute_llm_segment(seg, ctx)
        results.extend(seg_results)
        i = j

    return results


async def execute_loop(
    block: LoopBlock,
    ctx: WorkflowContext,
    *,
    registry: dict[str, WorkflowDef] | None = None,
) -> list[StepResult]:
    """Iterate over items from context, execute inner blocks per item."""
    if not evaluate_condition(block.condition, ctx):
        return [StepResult(name=block.name, status="skipped")]

    items = ctx.get_var(block.loop_over)
    if not isinstance(items, list):
        return [StepResult(name=block.name, status="failure", error=f"{block.loop_over} is not a list")]

    sentinel = object()
    loop_key = block.loop_var
    idx_key = f"{block.loop_var}_index"
    prev_loop_val = ctx.variables.get(loop_key, sentinel)
    prev_idx_val = ctx.variables.get(idx_key, sentinel)

    _emit(ctx, f"\u25b6 [LoopBlock] {block.name} ({len(items)} items)")
    logger.info("[%s] LoopBlock start: %d items", block.name, len(items))
    all_results: list[StepResult] = []
    try:
        for i, item in enumerate(items):
            ctx.variables[loop_key] = item
            ctx.variables[idx_key] = i
            _emit(ctx, f"  [{i+1}/{len(items)}] {item}")
            logger.info("[%s] iteration %d/%d: %s", block.name, i + 1, len(items), item)
            ctx.push_scope(f"loop:{block.name}[i={i}]")
            try:
                for inner in block.blocks:
                    inner_results = await execute_block(inner, ctx, registry=registry)
                    if isinstance(inner_results, list):
                        all_results.extend(inner_results)
                    else:
                        all_results.append(inner_results)
            finally:
                ctx.pop_scope()
    finally:
        if prev_loop_val is sentinel:
            ctx.variables.pop(loop_key, None)
        else:
            ctx.variables[loop_key] = prev_loop_val
        if prev_idx_val is sentinel:
            ctx.variables.pop(idx_key, None)
        else:
            ctx.variables[idx_key] = prev_idx_val

    return all_results


async def execute_retry(
    block: RetryBlock,
    ctx: WorkflowContext,
    *,
    registry: dict[str, WorkflowDef] | None = None,
) -> list[StepResult]:
    """Repeat inner blocks until condition met or max_attempts reached."""
    if not evaluate_condition(block.condition, ctx):
        return [StepResult(name=block.name, status="skipped")]

    sentinel = object()
    prev_attempt = ctx.variables.get("attempt", sentinel)

    _emit(ctx, f"\u25b6 [RetryBlock] {block.name} (max {block.max_attempts})")
    logger.info("[%s] RetryBlock start: max %d attempts", block.name, block.max_attempts)
    all_results: list[StepResult] = []
    try:
        for attempt in range(1, block.max_attempts + 1):
            ctx.variables["attempt"] = attempt
            _emit(ctx, f"  attempt {attempt}/{block.max_attempts}")
            logger.info("[%s] attempt %d/%d", block.name, attempt, block.max_attempts)
            ctx.push_scope(f"retry:{block.name}[attempt={attempt}]")
            try:
                for inner in block.blocks:
                    inner_results = await execute_block(inner, ctx, registry=registry)
                    if isinstance(inner_results, list):
                        all_results.extend(inner_results)
                    else:
                        all_results.append(inner_results)
            finally:
                ctx.pop_scope()

            if evaluate_condition(block.until, ctx):
                break
    finally:
        if prev_attempt is sentinel:
            ctx.variables.pop("attempt", None)
        else:
            ctx.variables["attempt"] = prev_attempt

    return all_results


async def execute_sub_workflow(
    block: SubWorkflow, ctx: WorkflowContext, registry: dict[str, WorkflowDef] | None = None,
) -> list[StepResult]:
    """Look up a workflow by name, inject variables, and recurse (isolated)."""
    if not evaluate_condition(block.condition, ctx):
        return [
            _record_leaf_result(
                ctx,
                block.name,
                StepResult(name=block.name, status="skipped", exec_key=ctx.scoped_exec_key(block.name)),
            )
        ]

    if registry is None:
        registry = {}

    wf = registry.get(block.workflow)
    if wf is None:
        return [
            _record_leaf_result(
                ctx,
                block.name,
                StepResult(
                    name=block.name,
                    status="failure",
                    error=f"Unknown workflow: {block.workflow}",
                    exec_key=ctx.scoped_exec_key(block.name),
                ),
            )
        ]

    # Execute the child workflow within this context, but isolate variable changes.
    _emit(ctx, f"\u25b6 [SubWorkflow] {block.name} \u2192 {block.workflow}")
    logger.info("[%s] SubWorkflow start: %s", block.name, block.workflow)
    saved_vars = dict(ctx.variables)
    saved_prompt_dir = ctx.prompt_dir
    ctx.push_scope(f"sub:{block.name}")
    try:
        for k, v in block.inject.items():
            ctx.variables[k] = _substitute(v, ctx) if isinstance(v, str) and "{{" in v else v
        if wf.prompt_dir:
            ctx.prompt_dir = wf.prompt_dir
        results = await execute_workflow(wf, ctx, registry=registry)
        _emit(ctx, f"\u2713 [SubWorkflow] {block.name} done")
        logger.info("[%s] SubWorkflow complete", block.name)
        return results
    finally:
        ctx.prompt_dir = saved_prompt_dir
        ctx.variables = saved_vars
        ctx.pop_scope()


async def execute_conditional(
    block: ConditionalBlock, ctx: WorkflowContext, registry: dict[str, WorkflowDef] | None = None,
) -> list[StepResult]:
    """Evaluate branches in order; first match wins, else default."""
    if not evaluate_condition(block.condition, ctx):
        return [StepResult(name=block.name, status="skipped")]

    chosen: list[Block] = block.default
    branch_label = "default"
    for idx, branch in enumerate(block.branches):
        if evaluate_condition(branch.condition, ctx):
            chosen = branch.blocks
            branch_label = f"branch {idx + 1}"
            break

    _emit(ctx, f"\u25b6 [ConditionalBlock] {block.name} \u2192 {branch_label}")
    logger.info("[%s] ConditionalBlock: chose %s", block.name, branch_label)

    results: list[StepResult] = []
    for inner in chosen:
        inner_results = await execute_block(inner, ctx, registry=registry)
        if isinstance(inner_results, list):
            results.extend(inner_results)
        else:
            results.append(inner_results)
    return results


def execute_shell(step: ShellStep, ctx: WorkflowContext) -> StepResult:
    """Run a shell command via subprocess.run()."""
    if not evaluate_condition(step.condition, ctx):
        return _record_leaf_result(
            ctx, step.name, StepResult(name=step.name, status="skipped", exec_key=ctx.scoped_exec_key(step.name))
        )

    command = _substitute(step.command, ctx)

    if ctx.dry_run:
        return _record_leaf_result(
            ctx,
            step.name,
            StepResult(
                name=step.name,
                status="dry_run",
                output=f"[dry-run] {command}",
                exec_key=ctx.scoped_exec_key(step.name),
            ),
        )

    _emit(ctx, f"\u25b6 [ShellStep] {step.name}")
    logger.info("[%s] ShellStep start: %s", step.name, command)
    t0 = time.time()
    structured: Any = None
    try:
        proc = subprocess.run(
            command,
            shell=True,  # noqa: S602
            capture_output=True,
            text=True,
            cwd=ctx.cwd,
            timeout=300,
        )
        output = proc.stdout + proc.stderr
        status = "success" if proc.returncode == 0 else "failure"
        error = proc.stderr if proc.returncode != 0 else None
        # Parse result_var inside try — proc is guaranteed to exist here
        if step.result_var and status == "success" and proc.stdout.strip():
            try:
                structured = json.loads(proc.stdout)
                ctx.variables[step.result_var] = structured
            except (json.JSONDecodeError, ValueError):
                pass  # non-JSON stdout is fine, just don't store
    except subprocess.TimeoutExpired:
        output = ""
        status = "failure"
        error = "Command timed out (300s)"
    except Exception as exc:
        output = ""
        status = "failure"
        error = str(exc)

    duration = time.time() - t0
    result = StepResult(
        name=step.name,
        output=output,
        structured_output=structured,
        status=status,
        error=error,
        duration=duration,
        exec_key=ctx.scoped_exec_key(step.name),
    )
    if status == "success":
        _emit(ctx, f"\u2713 {step.name} ({duration:.1f}s)")
        logger.info("[%s] ShellStep success (%.2fs)", step.name, duration)
    else:
        _emit(ctx, f"\u2717 {step.name}: {error}")
        logger.warning("[%s] ShellStep failure: %s", step.name, error)
    logger.debug("[%s] output: %s", step.name, output.rstrip())
    if step.result_var and structured is not None:
        logger.debug("[%s] result_var %s = %s", step.name, step.result_var, json.dumps(structured)[:200])
    return _record_leaf_result(ctx, step.name, result)


# ---------------------------------------------------------------------------
# PromptStep executor
# ---------------------------------------------------------------------------


def execute_prompt_step(step: PromptStep, ctx: WorkflowContext) -> StepResult:
    """Execute a PromptStep — ask user a question via IOHandler."""
    if not evaluate_condition(step.condition, ctx):
        base = _substitute(step.key or step.name, ctx)
        exec_key = ctx.scoped_exec_key(base)
        return _record_leaf_result(ctx, base, StepResult(name=step.name, status="skipped", exec_key=exec_key))

    base = _substitute(step.key or step.name, ctx)
    exec_key = ctx.scoped_exec_key(base)
    message = _substitute(step.message, ctx)
    options = [_substitute(o, ctx) for o in step.options]

    if ctx.dry_run:
        # Dry run: simulate an answer deterministically so downstream conditions behave.
        simulated = step.default
        if simulated is None:
            if step.prompt_type == "choice" and options:
                simulated = options[0]
            else:
                simulated = ""
        if step.result_var:
            ctx.variables[step.result_var] = simulated
        return _record_leaf_result(
            ctx,
            base,
            StepResult(
                name=step.name,
                status="dry_run",
                output=str(simulated),
                structured_output={
                    "dry_run": True,
                    "prompt_type": step.prompt_type,
                    "message": message,
                    "simulated_answer": simulated,
                },
                exec_key=exec_key,
            ),
        )

    handler = ctx.io_handler or StdinIOHandler()
    try:
        raw_answer = handler.prompt(exec_key, step.prompt_type, message, options, step.default, strict=step.strict)
    except StopForInput:
        # Preserve a human-friendly step_name while using exec_key for --answer lookup.
        raise StopForInput(exec_key, step.name, step.prompt_type, message, options, step.default, strict=step.strict)

    _emit(ctx, f"\u25b6 [PromptStep] {step.name}")
    _emit(ctx, f"  {message}")
    if options:
        for i, opt in enumerate(options, 1):
            _emit(ctx, f"    {i}. {opt}")
    _emit(ctx, f"  \u2192 {raw_answer}")
    logger.info("[%s] PromptStep choice: %r \u2192 %s", base, message, raw_answer)

    # Normalize choice answers: map ordinal → option value
    answer = raw_answer
    structured: dict[str, Any] = {"answer": raw_answer}
    if step.prompt_type == "choice" and options:
        try:
            idx = int(raw_answer) - 1  # "2" → index 1
            if 0 <= idx < len(options):
                answer = options[idx]
                structured = {"answer": answer, "index": idx}
        except ValueError:
            # Already a string value — find its index
            if raw_answer in options:
                structured = {"answer": raw_answer, "index": options.index(raw_answer)}

        # Strict validation: reject answers not in the options list
        if step.strict and answer not in options:
            logger.error("[%s] invalid choice '%s', valid options: %s", base, answer, options)
            raise ValueError(
                f"PromptStep '{base}': answer '{answer}' is not a valid option. "
                f"Valid options: {options}"
            )

    if step.result_var:
        ctx.variables[step.result_var] = answer

    result = StepResult(name=step.name, output=answer, structured_output=structured, exec_key=exec_key)
    return _record_leaf_result(ctx, base, result)


#
# ask_user MCP tool: opt-in per LLMStep via tools=["ask_user"].
# In non-interactive mode, the engine captures the question and raises
# StopForInput for checkpoint/resume.  See _build_engine_mcp_server().
#


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


async def execute_block(
    block: Block, ctx: WorkflowContext, registry: dict[str, WorkflowDef] | None = None,
) -> StepResult | list[StepResult]:
    """Pattern-match on block type and dispatch to the right executor."""
    # Resume-only skip: leaf blocks are skipped only if an injected scoped result exists.
    if isinstance(block, (LLMStep, ShellStep, PromptStep)):
        base = _substitute(block.key or block.name, ctx)
        exec_key = ctx.scoped_exec_key(base)
        prior = ctx.injected_results_scoped.get(exec_key)
        if prior and prior.status == "success":
            # Ensure convenience view is available for templating during resume.
            ctx.results_scoped[exec_key] = prior
            ctx.results[_results_key(ctx, base)] = prior
            _emit(ctx, f"\u21a9 {base} (cached)")
            logger.info("[%s] resumed from cache", base)
            return prior

    if isinstance(block, LLMStep):
        return await execute_llm_step(block, ctx)
    if isinstance(block, GroupBlock):
        return await execute_group(block, ctx, registry=registry)
    if isinstance(block, ParallelEachBlock):
        return await execute_parallel_each(block, ctx, registry=registry)
    if isinstance(block, LoopBlock):
        return await execute_loop(block, ctx, registry=registry)
    if isinstance(block, RetryBlock):
        return await execute_retry(block, ctx, registry=registry)
    if isinstance(block, SubWorkflow):
        return await execute_sub_workflow(block, ctx, registry=registry)
    if isinstance(block, ShellStep):
        return execute_shell(block, ctx)
    if isinstance(block, PromptStep):
        return execute_prompt_step(block, ctx)
    if isinstance(block, ConditionalBlock):
        return await execute_conditional(block, ctx, registry=registry)
    raise TypeError(f"Unknown block type: {type(block)}")


async def execute_workflow(
    workflow: WorkflowDef,
    ctx: WorkflowContext,
    registry: dict[str, WorkflowDef] | None = None,
) -> list[StepResult]:
    """Execute all top-level blocks in a workflow sequentially."""
    if workflow.prompt_dir:
        ctx.prompt_dir = workflow.prompt_dir
    all_results: list[StepResult] = []
    for block in workflow.blocks:
        result = await execute_block(block, ctx, registry=registry)
        if isinstance(result, list):
            all_results.extend(result)
        else:
            all_results.append(result)
    return all_results
