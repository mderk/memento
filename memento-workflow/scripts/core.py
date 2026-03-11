"""Core data structures for the workflow engine state machine.

Provides Frame, RunState, PROTOCOL_VERSION, and type aliases used by
all other state-machine modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from .protocol import PROTOCOL_VERSION, ActionBase
from .types import Block, WorkflowContext, WorkflowDef

class Frame:
    """A single stack frame in the cursor stack."""

    __slots__ = (
        "block", "block_index", "scope_label",
        "loop_items", "loop_index",
        "retry_attempt",
        "chosen_branch_index", "chosen_blocks",
        "saved_vars", "saved_prompt_dir",
    )

    def __init__(
        self,
        block: Block | WorkflowDef,
        block_index: int = 0,
        scope_label: str = "",
        loop_items: list[Any] | None = None,
        loop_index: int = 0,
        retry_attempt: int = 0,
        chosen_branch_index: int | None = None,
        chosen_blocks: list[Block] | None = None,
        saved_vars: dict[str, Any] | None = None,
        saved_prompt_dir: str | None = None,
    ):
        self.block = block
        self.block_index = block_index
        self.scope_label = scope_label
        self.loop_items = loop_items
        self.loop_index = loop_index
        self.retry_attempt = retry_attempt
        self.chosen_branch_index = chosen_branch_index
        self.chosen_blocks = chosen_blocks
        self.saved_vars = saved_vars
        self.saved_prompt_dir = saved_prompt_dir


class RunState:
    """Complete state for one workflow run (parent or child)."""

    def __init__(
        self,
        run_id: str,
        ctx: WorkflowContext,
        stack: list[Frame],
        registry: dict[str, WorkflowDef],
        status: str = "running",
        pending_exec_key: str | None = None,
        parent_run_id: str | None = None,
        child_run_ids: list[str] | None = None,
        wf_hash: str = "",
        protocol_version: int = PROTOCOL_VERSION,
        checkpoint_dir: Path | None = None,
        warnings: list[str] | None = None,
    ):
        self.run_id = run_id
        self.ctx = ctx
        self.stack = stack
        self.registry = registry
        self.status = status
        self.pending_exec_key = pending_exec_key
        self.parent_run_id = parent_run_id
        self.child_run_ids = child_run_ids if child_run_ids is not None else []
        self.wf_hash = wf_hash
        self.protocol_version = protocol_version
        self.checkpoint_dir = checkpoint_dir
        self.warnings = warnings if warnings is not None else []
        self._last_action: ActionBase | None = None
        self._submit_cache: dict[str, ActionBase] = {}  # exec_key -> post-submit action


AdvanceResult = tuple[ActionBase, list["RunState"]]
