"""WorkflowRunner — drives a workflow run tree without MCP coupling.

Owns RunState (parent + children), provides typed start/submit/next/cancel API.
MCP runner.py becomes a thin JSON-serialization wrapper over this class.

Usage (relay style — typed, no JSON):
    runner = WorkflowRunner(wf, variables={...}, cwd=".", registry=registry)
    action = runner.start()
    while action.action not in ("completed", "error", "halted"):
        result = execute(action)  # external: relay, agent SDK, etc.
        action = runner.submit(action.run_id, action.exec_key, output=result)

Usage (library style — executor-driven):
    runner = WorkflowRunner(wf, variables={...}, cwd=".", registry=registry)
    result = await runner.run(my_executor)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import Frame, RunState
from .hooks import DryRunTreeHook
from .protocol import (
    ActionBase,
    CancelledAction,
    CompletedAction,
    DryRunCompleteAction,
    DryRunNode,
    DryRunSummary,
    ErrorAction,
    HaltedAction,
    ParallelAction,
    SubagentAction,
)
from .state import advance, apply_submit, pending_action
from .types import StructuredOutput, WorkflowContext, WorkflowDef
from ..infra.artifacts import (
    exec_key_to_artifact_path,
    write_llm_output_artifact,
    write_meta,
    write_shell_artifacts,
)
from ..infra.checkpoint import (
    checkpoint_dir_from_run_id,
    checkpoint_load_children,
    checkpoint_save,
)
from ..infra.shell_exec import _execute_shell
from ..utils import compute_totals, merge_child_results, workflow_hash

logger = logging.getLogger("workflow-engine")

# Terminal statuses — runs in these states are finished.
_TERMINAL_RUN_STATUSES = frozenset({"completed", "error", "halted", "cancelled"})
_TERMINAL_ACTION_TYPES = frozenset({"completed", "error", "halted"})

# Parallel auto-advance: execute shell-only lanes inline, skip relay.
_PARALLEL_AUTO_ADVANCE = os.environ.get("MEMENTO_PARALLEL_AUTO_ADVANCE", "on") != "off"
_PARALLEL_MAX_WORKERS = 16


class WorkflowRunner:
    """Manages a workflow run tree (parent + child states).

    Replaces the global ``_runs`` dict and all run-management functions
    previously in ``runner.py``.  All public methods return typed
    ``ActionBase`` objects — no JSON serialization here.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        wf: WorkflowDef,
        *,
        variables: dict[str, Any] | None = None,
        cwd: str = ".",
        registry: dict[str, WorkflowDef],
        checkpoint: bool = True,
        run_id: str = "",
        run_store: dict[str, RunState] | None = None,
    ):
        variables = dict(variables or {})
        cwd_path = Path(cwd).resolve()
        run_id = run_id or uuid.uuid4().hex[:12]

        variables["run_id"] = run_id
        variables.setdefault(
            "workflow_dir",
            str(Path(wf.source_path).parent) if wf.source_path else "",
        )
        chk_dir = checkpoint_dir_from_run_id(cwd_path, run_id) if checkpoint else None
        variables.setdefault(
            "clean_dir",
            str(chk_dir / "clean") if chk_dir else "",
        )

        ctx = WorkflowContext(
            variables=variables,
            cwd=str(cwd_path),
            prompt_dir=wf.prompt_dir,
        )

        self._root = RunState(
            run_id=run_id,
            ctx=ctx,
            stack=[Frame(block=wf)],
            registry=registry,
            wf_hash=workflow_hash(wf),
            checkpoint_dir=chk_dir,
            workflow_name=wf.name,
        )
        self._registry = registry
        self._workflow_name = wf.name
        # run_store: shared dict in MCP mode, fresh dict in library mode
        self._runs: dict[str, RunState] = run_store if run_store is not None else {}
        self._runs[run_id] = self._root

    @classmethod
    def from_state(
        cls,
        state: RunState,
        registry: dict[str, WorkflowDef],
        run_store: dict[str, RunState] | None = None,
    ) -> WorkflowRunner:
        """Create a runner from an existing RunState (checkpoint resume)."""
        runner = object.__new__(cls)
        runner._root = state
        runner._registry = registry
        runner._workflow_name = state.workflow_name
        runner._runs = run_store if run_store is not None else {}
        runner._runs[state.run_id] = state
        return runner

    @classmethod
    def from_run_store(
        cls,
        run_store: dict[str, RunState],
        registry: dict[str, WorkflowDef] | None = None,
    ) -> WorkflowRunner:
        """Create an ephemeral runner over a shared run store (MCP compat).

        No specific root state — used for submit/next/cancel on existing runs.
        """
        runner = object.__new__(cls)
        runner._root = None  # type: ignore[assignment]
        runner._registry = registry or {}
        runner._workflow_name = ""
        runner._runs = run_store
        return runner

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._root.run_id

    @property
    def status(self) -> str:
        return self._root.status

    @property
    def root_state(self) -> RunState:
        return self._root

    # ------------------------------------------------------------------
    # Run storage (local tree, no global dict)
    # ------------------------------------------------------------------

    def _store_run(self, state: RunState) -> None:
        self._runs[state.run_id] = state

    def _get_run(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    # ------------------------------------------------------------------
    # Public API — relay style
    # ------------------------------------------------------------------

    def start(self) -> ActionBase:
        """Advance to first action. Auto-advances through shell steps."""
        state = self._root

        if state.checkpoint_dir:
            write_meta(
                state.checkpoint_dir,
                state.run_id,
                self._workflow_name,
                state.ctx.cwd,
                "running",
                state.started_at,
            )

        action, children = advance(state)
        action, children = self._auto_advance(state, action, children)

        if state.checkpoint_dir:
            if not checkpoint_save(state) and action.action not in ("error", "completed"):
                action.warnings.append("checkpoint write failed")

        self._write_terminal_meta(state, action)
        return self._finalize_action(action, children)

    def resume(self) -> ActionBase:
        """Resume from checkpoint, re-advancing children and parent.

        Assumes self._root was loaded via checkpoint_load (e.g. from_state).
        Loads and re-advances child checkpoints, then advances the parent.
        """
        state = self._root
        state.is_resumed = True

        loaded_children = checkpoint_load_children(state, self._registry)
        if loaded_children:
            state._resume_children = loaded_children
            for block_children in loaded_children.values():
                for child in block_children:
                    child.is_resumed = True
                    # Skip terminal children — their results are already merged
                    if child.status not in ("completed", "cancelled"):
                        child_action, grandchildren = advance(child)
                        child_action, grandchildren = self._auto_advance(
                            child, child_action, grandchildren,
                        )
                        for gc in grandchildren:
                            self._store_run(gc)
                    self._store_run(child)
                    checkpoint_save(child)

        self._store_run(state)
        action, children = advance(state)

        # Handle cross-run-id actions (inline SubWorkflow resume)
        target = state
        if action.run_id != state.run_id:
            child_state = self._get_run(action.run_id)
            if child_state:
                target = child_state

        action, children = self._auto_advance(target, action, children)
        checkpoint_save(target)

        if target != state:
            checkpoint_save(state)
            # Check cascade: child completed → merge into parent
            if action.action == "completed" and target.parent_run_id:
                parent = self._get_run(target.parent_run_id)
                if parent is not None and parent.pending_exec_key:
                    action, children = self._cascade_to_parent(
                        target, parent.pending_exec_key,
                    )

        action.resumed = True
        return self._finalize_action(action, children)

    def submit(
        self,
        run_id: str,
        exec_key: str,
        output: str = "",
        structured_output: StructuredOutput = None,
        status: str = "success",
        error: str | None = None,
        duration: float = 0.0,
        cost_usd: float | None = None,
        model: str | None = None,
    ) -> ActionBase:
        """Submit result for an exec_key, return next action. Idempotent."""
        logger.info(
            "submit(run_id=%s, exec_key=%s, status=%s)",
            run_id, exec_key, status,
        )
        state = self._get_run(run_id)
        if state is None:
            return ErrorAction(run_id=run_id, message=f"Unknown run_id: {run_id}")

        # Transparent SubWorkflow: route to active inline child
        routed = self._route_to_inline_child(
            state, run_id, exec_key, output, structured_output,
            status, error, duration, cost_usd, model,
        )
        if routed is not None:
            return routed

        # Child-run verification (only for matching exec_key)
        if exec_key == state.pending_exec_key:
            verification_error = self._verify_child_runs(state, status)
            if verification_error:
                return ErrorAction(
                    run_id=run_id,
                    message=verification_error,
                    exec_key=state.pending_exec_key,
                    display=f"Error: {verification_error}",
                )

        # Halt propagation from child runs
        if exec_key == state.pending_exec_key and status == "success":
            halt_info = self._check_child_halt(state)
            if halt_info:
                child_reason, child_halted_at = halt_info
                action, _ = apply_submit(
                    state, exec_key, output=output, status=status,
                    halt_reason=child_reason, halt_origin=child_halted_at,
                )
                self._write_terminal_meta(state, action)
                checkpoint_save(state)
                return action

        # Capture action type before apply_submit overwrites _last_action
        prev_action_type = state._last_action.action if state._last_action else None

        # Auto-merge parallel lane results
        if prev_action_type == "parallel" and exec_key == state.pending_exec_key:
            merged = self._collect_parallel_results(state)
            if merged:
                structured_output = merged

        # Auto-merge SubWorkflow child results (subagent path)
        if (
            prev_action_type == "subagent"
            and exec_key == state.pending_exec_key
            and isinstance(state._last_action, SubagentAction)
            and state._last_action.relay
            and state._last_action.child_run_id
        ):
            self._collect_subworkflow_results(state, state._last_action.child_run_id)

        # File-based result: read structured_output from artifact file
        if (
            not output
            and structured_output is None
            and status == "success"
            and state.artifacts_dir
            and prev_action_type in ("prompt", "subagent")
        ):
            result_file = (
                state.artifacts_dir / exec_key_to_artifact_path(exec_key) / "result.json"
            )
            if result_file.is_file():
                try:
                    structured_output = json.loads(result_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass

        try:
            action, children = apply_submit(
                state,
                exec_key=exec_key,
                output=output,
                structured_output=structured_output,
                status=status,
                error=error,
                duration=duration,
                cost_usd=cost_usd,
                model=model,
            )
        except Exception:
            logger.exception(
                "submit: apply_submit failed for run_id=%s exec_key=%s", run_id, exec_key,
            )
            raise

        # Write LLM output artifact
        if (
            state.artifacts_dir
            and prev_action_type in ("prompt", "subagent")
            and (output or structured_output is not None)
        ):
            write_llm_output_artifact(
                state.artifacts_dir, exec_key, output, structured=structured_output,
            )

        # Handle cancellation
        if isinstance(action, CancelledAction):
            self._cleanup_run(state)
            return action

        # Handle halt
        if isinstance(action, HaltedAction):
            self._write_terminal_meta(state, action)
            checkpoint_save(state)
            return action

        try:
            action, children = self._auto_advance(state, action, children)
        except Exception:
            logger.exception("submit: auto_advance failed for run_id=%s", run_id)
            raise

        # Inline SubWorkflow child completed → cascade to parent
        if (
            action.action == "completed"
            and state._inline_parent_exec_key
            and state.parent_run_id
        ):
            checkpoint_save(state)
            parent_action, parent_children = self._cascade_to_parent(
                state, state._inline_parent_exec_key,
            )
            return self._finalize_action(parent_action, parent_children)

        if not checkpoint_save(state) and action.action not in ("error", "completed"):
            action.warnings.append("checkpoint write failed")

        self._write_terminal_meta(state, action)
        return self._finalize_action(action, children)

    def next(self, run_id: str = "") -> ActionBase:
        """Re-fetch pending action without mutation (recovery)."""
        run_id = run_id or self._root.run_id
        state = self._get_run(run_id)
        if state is None:
            return ErrorAction(run_id=run_id, message=f"Unknown run_id: {run_id}")

        # Transparent SubWorkflow: return child's action with parent run_id
        if state._active_inline_child_id:
            child = self._get_run(state._active_inline_child_id)
            if child and child.status not in _TERMINAL_RUN_STATUSES:
                child_action = pending_action(child)
                child_action.run_id = run_id
                return child_action

        return pending_action(state)

    def cancel(self) -> CancelledAction:
        """Cancel the run tree, clean up checkpoints."""
        self._root.status = "cancelled"
        self._cleanup_run(self._root)
        return CancelledAction(run_id=self._root.run_id)

    def dry_run(self) -> DryRunCompleteAction:
        """Run advance() to completion without side effects."""
        # Dry-run uses a temporary state — don't touch self._root
        wf = None
        for w in self._registry.values():
            if w.name == self._workflow_name:
                wf = w
                break
        if wf is None:
            return DryRunCompleteAction(
                run_id=self._root.run_id,
                error=f"Workflow '{self._workflow_name}' not in registry",
            )

        ctx = WorkflowContext(
            variables=dict(self._root.ctx.variables),
            cwd=self._root.ctx.cwd,
            dry_run=True,
            prompt_dir=wf.prompt_dir,
        )
        state = RunState(
            run_id=self._root.run_id,
            ctx=ctx,
            stack=[Frame(block=wf)],
            registry=self._registry,
            checkpoint_dir=None,
            workflow_name=self._workflow_name,
        )
        return self._collect_dry_run(state)

    def get_status(self) -> dict[str, Any]:
        """Return run status dict (for monitoring)."""
        state = self._root
        result: dict[str, Any] = {
            "run_id": state.run_id,
            "status": state.status,
            "pending_exec_key": state.pending_exec_key,
            "parent_run_id": state.parent_run_id,
            "child_run_ids": state.child_run_ids,
            "protocol_version": state.protocol_version,
            "results_count": len(state.ctx.results_scoped),
            "stack_depth": len(state.stack),
            "warnings": state.warnings,
        }
        child_statuses = {}
        for child_id in state.child_run_ids:
            child = self._get_run(child_id)
            if child:
                child_statuses[child_id] = {
                    "status": child.status,
                    "pending_exec_key": child.pending_exec_key,
                }
        if child_statuses:
            result["children"] = child_statuses
        return result

    # ------------------------------------------------------------------
    # Auto-advance — execute shell steps inline
    # ------------------------------------------------------------------

    def _auto_advance(
        self,
        state: RunState,
        action: ActionBase,
        children: list[RunState],
    ) -> tuple[ActionBase, list[RunState]]:
        """Auto-advance through shell steps, executing via subprocess."""
        from .protocol import ShellAction

        shell_log: list[dict[str, Any]] = []
        all_children = list(children)

        while isinstance(action, ShellAction):
            ek = action.exec_key
            logger.debug("auto-advance shell: exec_key=%s", ek)
            t0 = time.monotonic()

            # Resolve stdin from dotpath
            stdin_data: str | None = None
            if action.stdin:
                resolved = state.ctx.get_var(action.stdin)
                if resolved is not None:
                    stdin_data = (
                        json.dumps(resolved) if isinstance(resolved, (dict, list))
                        else str(resolved)
                    )

            output, sh_status, structured, sh_error = _execute_shell(
                action.command,
                state.ctx.cwd,
                env=action.env,
                script_path=action.script_path,
                args=action.args or "",
                stdin_data=stdin_data,
                timeout=action.timeout,
            )
            sh_duration = round(time.monotonic() - t0, 3)

            artifact_ref: str | None = None
            if state.artifacts_dir:
                artifact_ref = write_shell_artifacts(
                    state.artifacts_dir, ek, action.command,
                    output or "", sh_error, structured,
                )

            if artifact_ref is not None:
                shell_log.append({
                    "exec_key": ek, "status": sh_status,
                    "duration": sh_duration, "artifact": artifact_ref,
                })
            else:
                shell_log.append({
                    "exec_key": ek, "command": action.command,
                    "status": sh_status, "output": (output or "")[:2000],
                    "duration": sh_duration,
                })

            try:
                action, new_children = apply_submit(
                    state,
                    exec_key=ek,
                    output=output,
                    structured_output=structured,
                    status=sh_status,
                    error=sh_error,
                    duration=sh_duration,
                )
            except Exception:
                logger.exception("apply_submit failed for exec_key=%s", ek)
                raise
            all_children.extend(new_children)
            checkpoint_save(state)

        if shell_log:
            action.shell_log = shell_log

        return action, all_children

    # ------------------------------------------------------------------
    # Child run management
    # ------------------------------------------------------------------

    def _verify_child_runs(self, state: RunState, submit_status: str) -> str | None:
        """Verify child runs completed before accepting subagent/parallel submit."""
        last = state._last_action
        if not last:
            return None

        action_type = last.action
        if action_type not in ("subagent", "parallel"):
            return None
        if isinstance(last, SubagentAction) and not last.relay:
            return None
        if submit_status != "success":
            return None

        if isinstance(last, SubagentAction):
            child_id = last.child_run_id
            if not child_id:
                return None
            child = self._get_run(child_id)
            if child is None:
                return (
                    f"Child run {child_id} not found. "
                    "The sub-relay may not have executed. "
                    "Ensure the agent calls next() and submit() on the child_run_id."
                )
            if child.status not in ("completed", "halted"):
                return (
                    f"Child run {child_id} has status '{child.status}', expected 'completed'. "
                    "The sub-relay did not finish."
                )

        elif isinstance(last, ParallelAction):
            incomplete = []
            missing = []
            for lane in last.lanes:
                child_id = lane.child_run_id
                if not child_id:
                    continue
                child = self._get_run(child_id)
                if child is None:
                    missing.append(child_id)
                elif child.status not in ("completed", "halted"):
                    incomplete.append(f"{child_id} (status={child.status})")
            if missing:
                return f"Parallel lane child runs not found: {', '.join(missing)}."
            if incomplete:
                return f"Parallel lane child runs not completed: {', '.join(incomplete)}."

        return None

    def _collect_parallel_results(self, state: RunState) -> list[Any] | None:
        """Collect structured_output from parallel lane children."""
        last = state._last_action
        if not isinstance(last, ParallelAction):
            return None

        results: list[Any] = []
        for lane in last.lanes:
            child = self._get_run(lane.child_run_id)
            if child is None:
                continue
            for key, r in child.ctx.results_scoped.items():
                if key in state.ctx.results_scoped:
                    continue  # inherited from parent
                if r.structured_output is not None:
                    results.append(r.structured_output)
                elif r.output:
                    results.append(r.output)

        return results if results else None

    def _check_child_halt(self, state: RunState) -> tuple[str, str] | None:
        """Check if any child run halted. Returns (reason, halted_at) or None."""
        last = state._last_action
        if not last:
            return None

        child_ids: list[str] = []
        if isinstance(last, SubagentAction) and last.relay and last.child_run_id:
            child_ids = [last.child_run_id]
        elif isinstance(last, ParallelAction):
            child_ids = [lane.child_run_id for lane in last.lanes]

        for cid in child_ids:
            child = self._get_run(cid)
            if child and child.status == "halted":
                halted = child._last_action
                if isinstance(halted, HaltedAction):
                    return halted.reason, halted.halted_at

        return None

    def _collect_subworkflow_results(self, state: RunState, child_run_id: str) -> None:
        """Merge child results into parent state."""
        child = self._get_run(child_run_id)
        if child is None:
            return
        merge_child_results(
            state.ctx.results_scoped,
            state.ctx.results,
            child.ctx.results_scoped,
        )
        state.ctx._order_seq = max(state.ctx._order_seq, child.ctx._order_seq)

    # ------------------------------------------------------------------
    # Inline SubWorkflow routing & cascade
    # ------------------------------------------------------------------

    def _route_to_inline_child(
        self,
        state: RunState,
        run_id: str,
        exec_key: str,
        output: str,
        structured_output: StructuredOutput,
        status: str,
        error: str | None,
        duration: float,
        cost_usd: float | None,
        model: str | None,
    ) -> ActionBase | None:
        """Route submit to active inline child. Returns action or None."""
        if not state._active_inline_child_id:
            return None
        child = self._get_run(state._active_inline_child_id)
        if not child or child.status in _TERMINAL_RUN_STATUSES:
            return None

        logger.info("submit: routing to transparent child %s", child.run_id)
        result = self.submit(
            run_id=child.run_id,
            exec_key=exec_key,
            output=output,
            structured_output=structured_output,
            status=status,
            error=error,
            duration=duration,
            cost_usd=cost_usd,
            model=model,
        )
        if result.run_id == child.run_id:
            # Child still active — rewrite run_id to parent
            result.run_id = run_id
            state._active_inline_child_id = child.run_id
            checkpoint_save(state)
            return result
        # Child completed and cascaded
        if state._active_inline_child_id == child.run_id:
            state._active_inline_child_id = ""
        checkpoint_save(state)
        return result

    def _cascade_to_parent(
        self,
        child_state: RunState,
        parent_exec_key: str,
    ) -> tuple[ActionBase, list[RunState]]:
        """Cascade a completed inline SubWorkflow child to its parent."""
        parent_run_id = child_state.parent_run_id
        if parent_run_id is None:
            return ErrorAction(
                run_id=child_state.run_id,
                message=f"No parent_run_id for cascade from {child_state.run_id}",
            ), []
        parent = self._get_run(parent_run_id)
        if parent is None:
            return ErrorAction(
                run_id=parent_run_id,
                message=f"Parent run not found for cascade from {child_state.run_id}",
            ), []

        self._collect_subworkflow_results(parent, child_state.run_id)
        action, children = apply_submit(
            parent, parent_exec_key, output="child-completed", status="success",
        )
        action, children = self._auto_advance(parent, action, children)
        checkpoint_save(parent)

        # Nested cascade: parent itself is an inline child that just completed
        if (
            action.action == "completed"
            and parent._inline_parent_exec_key
            and parent.parent_run_id
        ):
            return self._cascade_to_parent(parent, parent._inline_parent_exec_key)

        return action, children

    # ------------------------------------------------------------------
    # Action finalization — advance children, handle fast paths
    # ------------------------------------------------------------------

    def _finalize_action(
        self,
        action: ActionBase,
        children: list[RunState] | None = None,
    ) -> ActionBase:
        """Store & advance children, handle parallel fast path / inline cascade."""
        if children and isinstance(action, ParallelAction) and _PARALLEL_AUTO_ADVANCE:
            return self._finalize_parallel(action, children)
        if children:
            return self._finalize_sequential(action, children)
        return action

    def _finalize_parallel(
        self,
        action: ParallelAction,
        children: list[RunState],
    ) -> ActionBase:
        """Advance parallel children in threads, attempt fast path."""
        n_workers = min(len(children), _PARALLEL_MAX_WORKERS)
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            results = list(pool.map(self._advance_single_child, children))

        # Store all runs
        for child, _ca, grandchildren in results:
            for gc in grandchildren:
                self._store_run(gc)
            self._store_run(child)

        # Attempt fast path (all terminal → auto-submit parent)
        fast = self._try_parallel_fast_path(action, results)
        if fast is not None:
            return fast

        return action

    def _finalize_sequential(
        self,
        action: ActionBase,
        children: list[RunState],
    ) -> ActionBase:
        """Advance sequential children (inline SubWorkflow etc.)."""
        for child in children:
            if child.checkpoint_dir:
                block_label = child.parallel_block_name
                if child.lane_index >= 0:
                    block_label = f"{block_label}[{child.lane_index}]"
                write_meta(
                    child.checkpoint_dir,
                    child.run_id,
                    block_label or child.workflow_name,
                    child.ctx.cwd,
                    "running",
                    child.started_at,
                )
            child_action, grandchildren = advance(child)
            child_action, grandchildren = self._auto_advance(
                child, child_action, grandchildren,
            )
            for gc in grandchildren:
                self._store_run(gc)
            self._store_run(child)
            checkpoint_save(child)

            # Inline SubWorkflow child
            if child._inline_parent_exec_key:
                return self._handle_inline_child(action, child, child_action)

        return action

    def _handle_inline_child(
        self,
        parent_action: ActionBase,
        child: RunState,
        child_action: ActionBase,
    ) -> ActionBase:
        """Handle inline SubWorkflow child: cascade or proxy."""
        prior_logs = (parent_action.shell_log or []) + (child_action.shell_log or [])

        if child_action.action == "completed":
            cascaded_action, cascaded_children = self._cascade_to_parent(
                child, child._inline_parent_exec_key,
            )
            if prior_logs:
                existing = cascaded_action.shell_log or []
                cascaded_action.shell_log = prior_logs + existing
            return self._finalize_action(cascaded_action, cascaded_children)

        # Child has pending action → proxy transparently through parent run_id
        parent_rid = child.parent_run_id
        if parent_rid:
            parent = self._get_run(parent_rid)
            if parent:
                parent._active_inline_child_id = child.run_id
                checkpoint_save(parent)
            child_action.run_id = parent_rid
        if prior_logs:
            child_action.shell_log = prior_logs
        return child_action

    # ------------------------------------------------------------------
    # Parallel helpers
    # ------------------------------------------------------------------

    def _advance_single_child(
        self,
        child: RunState,
    ) -> tuple[RunState, ActionBase, list[RunState]]:
        """Advance child to first action (thread-safe: only modifies child)."""
        try:
            if child.checkpoint_dir:
                block_label = child.parallel_block_name
                if child.lane_index >= 0:
                    block_label = f"{block_label}[{child.lane_index}]"
                write_meta(
                    child.checkpoint_dir,
                    child.run_id,
                    block_label or child.workflow_name,
                    child.ctx.cwd,
                    "running",
                    child.started_at,
                )
            child_action, grandchildren = advance(child)
            child_action, grandchildren = self._auto_advance(
                child, child_action, grandchildren,
            )
            checkpoint_save(child)
            return child, child_action, grandchildren
        except Exception as exc:
            logger.exception("_advance_single_child failed: %s", child.run_id)
            child.status = "error"
            try:
                checkpoint_save(child)
            except Exception:
                pass
            return (
                child,
                ErrorAction(
                    run_id=child.run_id,
                    message=f"Lane advance failed: {type(exc).__name__}: {exc}",
                ),
                [],
            )

    def _try_parallel_fast_path(
        self,
        action: ParallelAction,
        results: list[tuple[RunState, ActionBase, list[RunState]]],
    ) -> ActionBase | None:
        """Auto-submit parent when all parallel lanes are terminal."""
        if not all(ca.action in _TERMINAL_ACTION_TYPES for _, ca, _ in results):
            return None

        parent = self._get_run(action.run_id)
        if parent is None:
            return None

        # Write terminal meta for each child
        for child, child_action, _ in results:
            self._write_terminal_meta(child, child_action)

        # Halt propagation
        child_halt = self._check_child_halt(parent)
        if child_halt:
            reason, halted_at = child_halt
            parent_action, _ = apply_submit(
                parent, action.exec_key,
                output="parallel-halted", status="success",
                halt_reason=reason, halt_origin=halted_at,
            )
            self._write_terminal_meta(parent, parent_action)
            checkpoint_save(parent)
            all_logs = self._merge_shell_logs(action, results)
            if all_logs:
                parent_action.shell_log = all_logs
            return parent_action

        # Derive status, apply submit, auto-advance
        merged = self._collect_parallel_results(parent)
        parent_status = self._derive_parallel_status(parent, results)

        parent_action, parent_children = apply_submit(
            parent, action.exec_key,
            output="parallel-auto-completed",
            structured_output=merged,
            status=parent_status,
        )
        parent_action, parent_children = self._auto_advance(
            parent, parent_action, parent_children,
        )

        all_logs = self._merge_shell_logs(action, results)
        if all_logs:
            existing = list(parent_action.shell_log or [])
            parent_action.shell_log = all_logs + existing

        self._write_terminal_meta(parent, parent_action)
        checkpoint_save(parent)
        return self._finalize_action(parent_action, parent_children)

    @staticmethod
    def _derive_parallel_status(
        parent: RunState,
        results: list[tuple[RunState, ActionBase, list[RunState]]],
    ) -> str:
        for child, child_action, _ in results:
            if child_action.action == "error":
                return "failure"
            for key, r in child.ctx.results_scoped.items():
                if key in parent.ctx.results_scoped:
                    continue
                if r.status == "failure":
                    return "failure"
        return "success"

    @staticmethod
    def _merge_shell_logs(
        action: ActionBase,
        results: list[tuple[RunState, ActionBase, list[RunState]]],
    ) -> list[dict[str, Any]]:
        logs = list(action.shell_log or [])
        for _child, ca, _ in sorted(results, key=lambda r: r[0].lane_index):
            logs.extend(ca.shell_log or [])
        return logs

    # ------------------------------------------------------------------
    # Terminal meta & cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _write_terminal_meta(state: RunState, action: ActionBase) -> None:
        """Write meta.json on completed/error/halted."""
        if not isinstance(action, (CompletedAction, ErrorAction, HaltedAction)):
            return
        if not state.checkpoint_dir:
            return

        if isinstance(action, HaltedAction):
            terminal_status = "halted"
        elif isinstance(action, ErrorAction):
            terminal_status = "error"
        else:
            terminal_status = "completed"

        meta_workflow = state.workflow_name
        if state.parallel_block_name:
            meta_workflow = state.parallel_block_name
            if state.lane_index >= 0:
                meta_workflow = f"{meta_workflow}[{state.lane_index}]"

        totals = compute_totals(state.ctx.results_scoped)
        write_meta(
            state.checkpoint_dir,
            state.run_id,
            meta_workflow,
            state.ctx.cwd,
            terminal_status,
            state.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            total_cost_usd=totals.get("cost_usd"),
            total_duration=totals["duration"],
            steps_by_type=totals.get("steps_by_type"),
        )

    def _cleanup_run(self, state: RunState) -> None:
        """Remove checkpoint files and in-memory state for a run and its children."""
        if state.checkpoint_dir and state.checkpoint_dir.exists():
            shutil.rmtree(state.checkpoint_dir, ignore_errors=True)
        self._runs.pop(state.run_id, None)
        for child_id in state.child_run_ids:
            child = self._runs.pop(child_id, None)
            if child and child.checkpoint_dir and child.checkpoint_dir.exists():
                shutil.rmtree(child.checkpoint_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Dry-run
    # ------------------------------------------------------------------

    def _collect_dry_run(self, state: RunState) -> DryRunCompleteAction:
        """Collect dry-run tree by running advance() to completion."""
        hook = DryRunTreeHook()
        state._advance_hook = hook

        try:
            while True:
                action, children = advance(state)
                if isinstance(action, CompletedAction):
                    break
                if isinstance(action, (ErrorAction, HaltedAction)):
                    return self._build_dry_run_result(state, hook, terminal_action=action)

                if isinstance(action, (SubagentAction, ParallelAction)) and children:
                    parent_node = self._find_node(hook.root, action.exec_key)
                    for child in children:
                        child.ctx.dry_run = True
                        child_result = self._collect_dry_run(child)
                        if parent_node:
                            parent_node.children.extend(child_result.tree)

                if isinstance(action, (SubagentAction, ParallelAction)):
                    apply_submit(
                        state, action.exec_key,
                        output="[dry-run]", status="success",
                    )
        except Exception:
            logger.exception("dry-run collection failed")
            return DryRunCompleteAction(
                run_id=state.run_id,
                error="dry-run collection failed unexpectedly",
            )

        return self._build_dry_run_result(state, hook)

    @staticmethod
    def _find_node(root: DryRunNode, exec_key: str) -> DryRunNode | None:
        if root.exec_key == exec_key:
            return root
        for child in root.children:
            found = WorkflowRunner._find_node(child, exec_key)
            if found:
                return found
        return None

    @staticmethod
    def _build_dry_run_result(
        state: RunState,
        hook: DryRunTreeHook,
        terminal_action: ActionBase | None = None,
    ) -> DryRunCompleteAction:
        tree = hook.root.children
        summary = WorkflowRunner._compute_dry_run_summary(tree)
        error = None
        halted_at = None
        if isinstance(terminal_action, ErrorAction):
            error = terminal_action.message
        elif isinstance(terminal_action, HaltedAction):
            error = terminal_action.reason
            halted_at = terminal_action.halted_at
        return DryRunCompleteAction(
            run_id=state.run_id,
            tree=tree,
            summary=summary,
            error=error,
            halted_at=halted_at,
        )

    @staticmethod
    def _compute_dry_run_summary(nodes: list[DryRunNode]) -> DryRunSummary:
        steps_by_type: dict[str, int] = {}
        count = 0

        def _walk(ns: list[DryRunNode]) -> None:
            nonlocal count
            for n in ns:
                if n.children:
                    _walk(n.children)
                else:
                    count += 1
                    steps_by_type[n.type] = steps_by_type.get(n.type, 0) + 1

        _walk(nodes)
        return DryRunSummary(step_count=count, steps_by_type=steps_by_type)
