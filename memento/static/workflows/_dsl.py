"""Workflow DSL type stubs for static analysis and linting.

At runtime, these names are injected by the workflow engine loader
into the exec namespace. The stubs here exist so that linters (ruff,
pyright) can validate workflow.py files without false positives.

Usage in workflow.py:
    from __future__ import annotations
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from _dsl import (
            WorkflowDef, LLMStep, ShellStep, PromptStep,
            ...
        )
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, Literal

    class WorkflowContext:
        variables: dict[str, Any]
        results: dict[str, Any]
        results_scoped: dict[str, Any]
        cwd: str
        dry_run: bool
        prompt_dir: str
        def get_var(self, dotpath: str) -> Any: ...
        def result_field(self, step: str, key: str) -> Any: ...

    class WorkflowDef:
        def __init__(
            self, *, name: str, description: str,
            blocks: list[Any] = ..., prompt_dir: str = ...,
            source_path: str = ..., **kwargs: Any,
        ) -> None: ...

    class LLMStep:
        def __init__(
            self, *, name: str,
            prompt: str = ..., prompt_text: str = ...,
            tools: list[str] = ..., model: str | None = ...,
            output_schema: Any = ..., result_var: str = ...,
            cache_prompt: bool = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class ShellStep:
        def __init__(
            self, *, name: str,
            command: str = ..., script: str = ..., args: str = ...,
            env: dict[str, str] = ..., result_var: str = ...,
            stdin: str = ..., timeout: int = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class SubWorkflow:
        def __init__(
            self, *, name: str,
            workflow: str, inject: dict[str, str] = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class LoopBlock:
        def __init__(
            self, *, name: str,
            loop_over: str, loop_var: str,
            blocks: list[Any] = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class RetryBlock:
        def __init__(
            self, *, name: str,
            until: Callable[[WorkflowContext], bool],
            max_attempts: int = ...,
            blocks: list[Any] = ...,
            halt_on_exhaustion: str = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class GroupBlock:
        def __init__(
            self, *, name: str,
            blocks: list[Any] = ..., model: str | None = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class ParallelEachBlock:
        def __init__(
            self, *, name: str,
            parallel_for: str, template: list[Any] = ...,
            item_var: str = ..., max_concurrency: int | None = ...,
            model: str | None = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class ConditionalBlock:
        def __init__(
            self, *, name: str,
            branches: list[Branch] = ...,
            default: list[Any] = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...

    class Branch:
        def __init__(
            self, *,
            condition: Callable[[WorkflowContext], bool],
            blocks: list[Any] = ..., **kwargs: Any,
        ) -> None: ...

    class PromptStep:
        def __init__(
            self, *, name: str,
            prompt_type: Literal["confirm", "choice", "input"],
            message: str, options: list[str] = ...,
            default: str | None = ..., result_var: str = ...,
            strict: bool = ...,
            condition: Callable[[WorkflowContext], bool] | None = ...,
            isolation: Literal["inline", "subagent"] = ...,
            context_hint: str = ..., halt: str = ...,
            key: str = ..., resume_only: Literal["", "true", "once"] = ...,
            **kwargs: Any,
        ) -> None: ...
