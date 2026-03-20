"""Typed protocol models for workflow engine action responses.

All action dicts returned by advance() / apply_submit() are now Pydantic
models.  The 8 action types are:

  shell, ask_user, prompt, subagent, parallel, completed, error, cancelled

``action_to_dict`` serialises any model to the wire-format dict that the
MCP JSON transport expects (aliases honoured, None fields omitted).
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field

PROTOCOL_VERSION = 1


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class ActionBase(BaseModel):
    """Fields shared by every action response."""

    action: str
    run_id: str
    protocol_version: int = PROTOCOL_VERSION
    display: str = Field(default="", serialization_alias="_display")
    shell_log: list[dict[str, Any]] | None = Field(
        default=None, serialization_alias="_shell_log"
    )
    warnings: list[str] = Field(default_factory=list)
    resumed: bool | None = Field(default=None, serialization_alias="_resumed")


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
    timeout: int = 120  # subprocess timeout in seconds
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
    retry_confirm: bool | None = Field(
        default=None, serialization_alias="_retry_confirm"
    )
    dry_run: bool | None = None


class PromptAction(ActionBase):
    action: Literal["prompt"] = "prompt"
    exec_key: str = ""
    prompt: str = ""
    tools: list[str] | None = None
    model: str | None = None
    json_schema: dict[str, Any] | None = None
    output_schema_name: str | None = None
    context_files: list[str] | None = None
    result_dir: str | None = None
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
    totals: dict[str, Any] = Field(default_factory=dict)


class ErrorAction(ActionBase):
    action: Literal["error"] = "error"
    exec_key: str | None = None
    message: str = ""
    expected_exec_key: str | None = None
    got: str | None = None


class HaltedAction(ActionBase):
    action: Literal["halted"] = "halted"
    reason: str = ""
    halted_at: str = ""


class CancelledAction(ActionBase):
    action: Literal["cancelled"] = "cancelled"


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------


# When False (default), _shell_log is stripped from action responses to save
# context window tokens.  Toggled by MCP tool parameters or tests.
INCLUDE_SHELL_LOG: bool = os.environ.get("MEMENTO_SHELL_LOG", "") == "1"


def action_to_dict(
    action: ActionBase, include_shell_log: bool | None = None
) -> dict[str, Any]:
    """Serialise an action model to a plain dict (wire format).

    Uses serialization aliases (``_display``, ``_shell_log``, ``_retry_confirm``)
    and drops ``None`` values.

    ``_shell_log`` is excluded by default to save context window tokens.
    Override with ``include_shell_log=True`` or the ``INCLUDE_SHELL_LOG`` global.
    """
    include = include_shell_log if include_shell_log is not None else INCLUDE_SHELL_LOG
    exclude = {"shell_log"} if not include else set()
    d = action.model_dump(by_alias=True, exclude_none=True, exclude=exclude)
    # Omit empty warnings list to keep wire format compact
    if "warnings" in d and not d["warnings"]:
        del d["warnings"]
    return d


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
HaltedAction.model_rebuild()
CancelledAction.model_rebuild()
