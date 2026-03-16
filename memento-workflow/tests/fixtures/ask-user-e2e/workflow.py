from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from scripts.types import (  # noqa: F401
        LLMStep, PromptStep, ShellStep, WorkflowDef,
    )

WORKFLOW = WorkflowDef(
    name="ask-user-e2e",
    description="E2E ask_user test",
    blocks=[
        LLMStep(
            name="choose",
            prompt="ask.md",
            tools=["ask_user"],
            model="sonnet",
        )
    ],
)
