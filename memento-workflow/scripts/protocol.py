"""Typed protocol models for workflow engine action responses.

All action dicts returned by advance() / apply_submit() are now Pydantic
models.  The 8 action types are:

  shell, ask_user, prompt, subagent, parallel, completed, error, cancelled

``action_to_dict`` serialises any model to the wire-format dict that the
MCP JSON transport expects (aliases honoured, None fields omitted).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 1


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class ActionBase(BaseModel):
    """Fields shared by every action response."""

    model_config = ConfigDict(populate_by_name=True)

    action: str
    run_id: str
    protocol_version: int = PROTOCOL_VERSION
    display: str = Field(default="", alias="_display")
    shell_log: list[dict[str, Any]] | None = Field(default=None, alias="_shell_log")
    warnings: list[str] | None = None


# ---------------------------------------------------------------------------
# Concrete action types
# ---------------------------------------------------------------------------


class ShellAction(ActionBase):
    action: Literal["shell"] = "shell"
    exec_key: str = ""
    command: str = ""
    script_path: str | None = None
    args: str | None = None
    env: dict[str, str] | None = None
    result_var: str | None = None
    stdin: str | None = None  # dotpath resolved by auto-advance, not serialized
    dry_run: bool | None = None


class AskUserAction(ActionBase):
    action: Literal["ask_user"] = "ask_user"
    exec_key: str = ""
    prompt_type: str = ""
    message: str = ""
    options: list[str] | None = None
    default: str | None = None
    strict: bool | None = None
    result_var: str | None = None
    retry_confirm: bool | None = Field(default=None, alias="_retry_confirm")
    dry_run: bool | None = None


class PromptAction(ActionBase):
    action: Literal["prompt"] = "prompt"
    exec_key: str = ""
    prompt: str = ""
    tools: list[str] | None = None
    model: str | None = None
    json_schema: dict[str, Any] | None = None
    output_schema_name: str | None = None
    dry_run: bool | None = None


class SubagentAction(ActionBase):
    action: Literal["subagent"] = "subagent"
    exec_key: str = ""
    prompt: str = ""
    relay: bool = False
    child_run_id: str | None = None
    context_hint: str | None = None
    tools: list[str] | None = None
    model: str | None = None


class ParallelLane(BaseModel):
    """One lane inside a parallel action."""

    model_config = ConfigDict(populate_by_name=True)

    child_run_id: str
    exec_key: str
    prompt: str
    relay: bool = True


class ParallelAction(ActionBase):
    action: Literal["parallel"] = "parallel"
    exec_key: str = ""
    lanes: list[ParallelLane] = Field(default_factory=list)
    model: str | None = None


class CompletedAction(ActionBase):
    action: Literal["completed"] = "completed"
    summary: dict[str, Any] = Field(default_factory=dict)


class ErrorAction(ActionBase):
    action: Literal["error"] = "error"
    exec_key: str | None = None
    message: str = ""
    expected_exec_key: str | None = None
    got: str | None = None


class CancelledAction(ActionBase):
    action: Literal["cancelled"] = "cancelled"


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------


def action_to_dict(action: ActionBase) -> dict[str, Any]:
    """Serialise an action model to a plain dict (wire format).

    Uses aliases (``_display``, ``_shell_log``, ``_retry_confirm``) and
    drops ``None`` values to match the pre-model dict output.
    """
    return action.model_dump(by_alias=True, exclude_none=True)


# ---------------------------------------------------------------------------
# Resolve forward references (required with `from __future__ import annotations`)
# ---------------------------------------------------------------------------

ActionBase.model_rebuild()
ShellAction.model_rebuild()
AskUserAction.model_rebuild()
PromptAction.model_rebuild()
SubagentAction.model_rebuild()
ParallelLane.model_rebuild()
ParallelAction.model_rebuild()
CompletedAction.model_rebuild()
ErrorAction.model_rebuild()
CancelledAction.model_rebuild()
