"""Core data structures for the workflow engine state machine.

Provides Frame, RunState, PROTOCOL_VERSION, and type aliases used by
all other state-machine modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .protocol import PROTOCOL_VERSION, ActionBase
from .types import Block, WorkflowContext, WorkflowDef


class Frame:
    """A single stack frame in the cursor stack."""

    __slots__ = (
        "block",
        "block_index",
        "scope_label",
        "loop_items",
        "loop_index",
        "retry_attempt",
        "chosen_branch_index",
        "chosen_blocks",
        "saved_vars",
        "saved_prompt_dir",
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
        child_run_ids: list[str] | None = None,
        wf_hash: str = "",
        protocol_version: int = PROTOCOL_VERSION,
        checkpoint_dir: Path | None = None,
        warnings: list[str] | None = None,
        workflow_name: str = "",
        started_at: str = "",
        parallel_block_name: str = "",
        lane_index: int = -1,
        spawn_exec_key: str = "",
    ):
        self.run_id = run_id
        self.ctx = ctx
        self.stack = stack
        self.registry = registry
        self.status = status
        self.pending_exec_key = pending_exec_key
        self.child_run_ids = child_run_ids if child_run_ids is not None else []
        self.wf_hash = wf_hash
        self.protocol_version = protocol_version
        self.checkpoint_dir = checkpoint_dir
        self.warnings = warnings if warnings is not None else []
        self.workflow_name = workflow_name
        self.started_at = started_at or datetime.now(timezone.utc).isoformat()
        self.parallel_block_name = parallel_block_name
        self.lane_index = lane_index
        self.spawn_exec_key = spawn_exec_key
        self.is_resumed: bool = False
        self._ephemeral_keys: set[str] = set()
        self._last_action: ActionBase | None = None
        self._submit_cache: dict[str, ActionBase] = {}  # exec_key -> post-submit action
        self._resume_children: dict[
            str, list[RunState]
        ] = {}  # block_name/spawn_exec_key -> children
        self._inline_parent_exec_key: str = (
            ""  # set when this child is an inline SubWorkflow
        )
        self._artifacts_dir_override: Path | None = (
            None  # set for inline children to use parent's artifacts
        )
        self._active_inline_child_id: str = (
            ""  # child run_id being proxied transparently
        )
        self._advance_hook: Any = None  # AdvanceHook set during dry-run

    @property
    def parent_run_id(self) -> str | None:
        """Derive parent run_id from composite ID (parent>child)."""
        if ">" in self.run_id:
            return self.run_id.rsplit(">", 1)[0]
        return None

    @property
    def artifacts_dir(self) -> Path | None:
        """Return path to artifacts directory, or None if no checkpoint dir."""
        if self._artifacts_dir_override is not None:
            return self._artifacts_dir_override
        if self.checkpoint_dir is None:
            return None
        return self.checkpoint_dir / "artifacts"


AdvanceResult = tuple[ActionBase, list["RunState"]]
