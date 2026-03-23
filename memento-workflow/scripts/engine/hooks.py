"""Advance hooks for the workflow engine.

Provides an extension point for observing block entry/exit during
advance() traversal.  The state machine calls hook methods but has
no knowledge of what the hook does — dry-run tree building, tracing,
profiling, etc.
"""

from __future__ import annotations

from typing import Any

from .protocol import DryRunNode, DryRunNodeType
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
    SubWorkflow,
)
from ..utils import substitute


_BLOCK_TYPE_MAP: dict[str, DryRunNodeType] = {"llm_step": "llm"}


def _block_node_type(block_type: str) -> DryRunNodeType:
    """Map block.type to DryRunNodeType, with fallback cast."""
    return _BLOCK_TYPE_MAP.get(block_type, block_type)  # type: ignore[return-value]


class AdvanceHook:
    """Base class for hooks into the advance() state machine.

    Subclass and override methods to observe block traversal.
    Set on ``RunState._advance_hook`` before calling ``advance()``.
    """

    def on_block_enter(self, state: Any, block: Block, exec_key: str) -> None:
        """Called when advance() processes a block (leaf or container)."""

    def on_block_exit(self, state: Any, block: Block) -> None:
        """Called when _pop_frame() exits a container (not on loop/retry re-entry)."""


class DryRunTreeHook(AdvanceHook):
    """Builds a DryRunNode tree as advance() traverses blocks.

    Leaf blocks are appended as children of the current stack top.
    Container blocks that push frames (Group, Loop, Retry, Conditional)
    are also pushed onto the internal stack so their children nest correctly.
    SubWorkflow and ParallelEach are appended but not pushed (their children
    come from child runs, attached by the runner).
    """

    def __init__(self) -> None:
        self.root = DryRunNode(exec_key="__root__", type="group", name="root")
        self._stack: list[DryRunNode] = [self.root]

    def on_block_enter(self, state: Any, block: Block, exec_key: str) -> None:
        is_leaf = isinstance(block, (ShellStep, LLMStep, PromptStep))
        node = DryRunNode(
            exec_key=exec_key,
            type=_block_node_type(block.type),
            name=block.name,
            detail=self._detail(block, state) if is_leaf else "",
        )
        self._stack[-1].children.append(node)

        # Push for containers that push frames
        if isinstance(block, (GroupBlock, LoopBlock, RetryBlock, ConditionalBlock)):
            self._stack.append(node)

    def on_block_exit(self, state: Any, block: Block) -> None:
        if isinstance(block, (GroupBlock, LoopBlock, RetryBlock, ConditionalBlock)):
            if len(self._stack) > 1:
                self._stack.pop()

    @staticmethod
    def _detail(block: Block, state: Any) -> str:
        """Extract detail string from a leaf block."""
        if isinstance(block, ShellStep):
            if block.script:
                wd = state.ctx.variables.get("workflow_dir", "")
                return f"{wd}/{block.script}" if wd else block.script
            return substitute(block.command, state.ctx) if block.command else ""
        if isinstance(block, LLMStep):
            return block.prompt or "(inline)"
        if isinstance(block, PromptStep):
            return substitute(block.message, state.ctx) if block.message else ""
        return ""
