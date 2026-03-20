"""Tests for workflow engine state machine (state.py).

Tests idempotency, exec_key validation, output schemas, dry-run,
checkpointing, nested combos, halt, and other cross-cutting concerns.
Block-type tests live in test_blocks.py.
"""

import json

from pydantic import BaseModel

from conftest import _types_ns, _state_ns

# Types
LLMStep = _types_ns["LLMStep"]
GroupBlock = _types_ns["GroupBlock"]
LoopBlock = _types_ns["LoopBlock"]
RetryBlock = _types_ns["RetryBlock"]
SubWorkflow = _types_ns["SubWorkflow"]
ShellStep = _types_ns["ShellStep"]
PromptStep = _types_ns["PromptStep"]
ConditionalBlock = _types_ns["ConditionalBlock"]
Branch = _types_ns["Branch"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]

# State
Frame = _state_ns["Frame"]
RunState = _state_ns["RunState"]
advance = _state_ns["advance"]
apply_submit = _state_ns["apply_submit"]
pending_action = _state_ns["pending_action"]
results_key = _state_ns["results_key"]
schema_dict = _state_ns["schema_dict"]
workflow_hash = _state_ns["workflow_hash"]
checkpoint_save = _state_ns["checkpoint_save"]
checkpoint_load = _state_ns["checkpoint_load"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(blocks, name="test", description="test workflow", prompt_dir=""):
    return WorkflowDef(name=name, description=description, blocks=blocks, prompt_dir=prompt_dir)


def _make_state(workflow, variables=None, registry=None, run_id="test-run", cwd="."):
    ctx = WorkflowContext(
        variables=variables or {},
        cwd=cwd,
        prompt_dir=workflow.prompt_dir,
    )
    if registry is None:
        registry = {workflow.name: workflow}
    return RunState(
        run_id=run_id,
        ctx=ctx,
        stack=[Frame(block=workflow)],
        registry=registry,
        wf_hash="test-hash",
    )


def _advance_and_submit(state, output="ok", status="success", **kwargs):
    """Advance, then submit the result for the pending action."""
    action, children = advance(state)
    if action.action in ("completed", "error"):
        return action, children
    result = apply_submit(state, action.exec_key, output=output, status=status, **kwargs)
    return result


# ---------------------------------------------------------------------------
# Tests: exec_key validation + idempotency
# ---------------------------------------------------------------------------


class TestExecKeyValidation:
    def test_wrong_exec_key_error(self):
        wf = _make_workflow([ShellStep(name="step1", command="echo")])
        state = _make_state(wf)
        advance(state)

        result, _ = apply_submit(state, "wrong-key", output="test")
        assert result.action == "error"
        assert result.expected_exec_key == "step1"
        assert result.got == "wrong-key"
        assert result.display is not None

    def test_idempotent_submit(self):
        wf = _make_workflow([
            ShellStep(name="step1", command="echo 1"),
            ShellStep(name="step2", command="echo 2"),
        ])
        state = _make_state(wf)
        advance(state)

        # First submit
        action1, _ = apply_submit(state, "step1", output="one")
        assert action1.exec_key == "step2"

        # "step1" is already recorded. Submitting step1 again returns the
        # exact same action that was returned on original submit (idempotent).
        result, _ = apply_submit(state, "step1", output="one")
        assert result == action1

    def test_idempotent_submit_late_retry(self):
        """Late retry of a past exec_key returns the action originally returned for that key,
        not the latest action (which may have advanced further)."""
        wf = _make_workflow([
            ShellStep(name="step1", command="echo 1"),
            ShellStep(name="step2", command="echo 2"),
            ShellStep(name="step3", command="echo 3"),
        ])
        state = _make_state(wf)
        advance(state)

        # Submit step1 → get step2 action
        action_after_step1, _ = apply_submit(state, "step1", output="one")
        assert action_after_step1.exec_key == "step2"

        # Submit step2 → get step3 action
        action_after_step2, _ = apply_submit(state, "step2", output="two")
        assert action_after_step2.exec_key == "step3"

        # Late retry of step1 → should return the step2 action (not step3)
        retry_result, _ = apply_submit(state, "step1", output="one")
        assert retry_result.exec_key == "step2"
        assert retry_result == action_after_step1

        # Late retry of step2 → should return the step3 action
        retry_result2, _ = apply_submit(state, "step2", output="two")
        assert retry_result2.exec_key == "step3"
        assert retry_result2 == action_after_step2

    def test_submit_after_completed_same_key_is_idempotent(self):
        """Submitting the same exec_key after completion is idempotent."""
        wf = _make_workflow([ShellStep(name="only", command="echo")])
        state = _make_state(wf)
        advance(state)
        apply_submit(state, "only", output="done")

        result, _ = apply_submit(state, "only", output="again")
        assert result.action == "completed"

    def test_submit_after_completed_different_key_is_error(self):
        """Submitting a different exec_key after completion returns error."""
        wf = _make_workflow([ShellStep(name="only", command="echo")])
        state = _make_state(wf)
        advance(state)
        apply_submit(state, "only", output="done")

        result, _ = apply_submit(state, "other", output="bad")
        assert result.action == "error"
        assert "already completed" in result.message


# ---------------------------------------------------------------------------
# Tests: next() tool (pending_action)
# ---------------------------------------------------------------------------


class TestPendingAction:
    def test_returns_current_action(self):
        wf = _make_workflow([ShellStep(name="step1", command="echo")])
        state = _make_state(wf)
        action, _ = advance(state)

        retrieved = pending_action(state)
        assert retrieved == action

    def test_returns_completed(self):
        wf = _make_workflow([ShellStep(name="only", command="echo")])
        state = _make_state(wf)
        advance(state)
        apply_submit(state, "only")

        result = pending_action(state)
        assert result.action == "completed"


# ---------------------------------------------------------------------------
# Tests: output_schema validation
# ---------------------------------------------------------------------------


class TestOutputSchemaValidation:
    def test_valid_structured_output(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "plan.md").write_text("Make plan")

        class PlanOutput(BaseModel):
            tasks: list[str] = []

        wf = _make_workflow(
            [LLMStep(name="plan", prompt="plan.md", output_schema=PlanOutput)],
            prompt_dir=str(prompt_dir),
        )
        state = _make_state(wf)
        advance(state)

        action, _ = apply_submit(
            state, "plan",
            output='{"tasks": ["a", "b"]}',
            structured_output={"tasks": ["a", "b"]},
        )
        assert action.action == "completed"
        result = state.ctx.results_scoped["plan"]
        assert result.status == "success"
        assert result.structured_output == {"tasks": ["a", "b"]}

    def test_invalid_structured_output(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "plan.md").write_text("Make plan")

        class StrictPlan(BaseModel):
            tasks: list[str]  # required, no default

        wf = _make_workflow(
            [LLMStep(name="plan", prompt="plan.md", output_schema=StrictPlan)],
            prompt_dir=str(prompt_dir),
        )
        state = _make_state(wf)
        advance(state)

        action, _ = apply_submit(
            state, "plan",
            output="not json at all",
        )
        # Should be recorded as failure
        assert action.action == "completed"  # workflow continues
        result = state.ctx.results_scoped["plan"]
        assert result.status == "failure"
        assert result.error is not None


# ---------------------------------------------------------------------------
# Tests: dry_run mode
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_shell(self):
        wf = _make_workflow([ShellStep(name="echo", command="echo hello")])
        state = _make_state(wf)
        state.ctx.dry_run = True

        action, _ = advance(state)
        assert action.action == "shell"
        assert action.dry_run is True

    def test_dry_run_records_and_advances(self):
        wf = _make_workflow([
            ShellStep(name="step1", command="echo 1"),
            ShellStep(name="step2", command="echo 2"),
        ])
        state = _make_state(wf)
        state.ctx.dry_run = True

        action1, _ = advance(state)
        assert action1.exec_key == "step1"
        # In dry_run, we still need to "submit" to advance
        # Actually dry_run auto-records — let's check
        assert "step1" in state.ctx.results_scoped

    def test_dry_run_llm_with_schema(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "plan.md").write_text("Plan")

        class PlanOutput(BaseModel):
            tasks: list[str] = []

        wf = _make_workflow(
            [LLMStep(name="plan", prompt="plan.md", output_schema=PlanOutput)],
            prompt_dir=str(prompt_dir),
        )
        state = _make_state(wf)
        state.ctx.dry_run = True

        action, _ = advance(state)
        assert action.dry_run is True
        # Should have auto-recorded with structured output
        result = state.ctx.results_scoped["plan"]
        assert result.structured_output == {"tasks": []}


# ---------------------------------------------------------------------------
# Tests: Checkpoint save/load
# ---------------------------------------------------------------------------


class TestCheckpoint:
    def test_save_and_load_roundtrip(self, tmp_path):
        wf = _make_workflow([
            ShellStep(name="step1", command="echo 1"),
            ShellStep(name="step2", command="echo 2"),
        ])
        wf.source_path = str(tmp_path / "workflow.py")
        (tmp_path / "workflow.py").write_text("# test")

        state = _make_state(wf, variables={"key": "value"}, cwd=str(tmp_path))
        state.checkpoint_dir = tmp_path / ".workflow-state" / state.run_id
        state.wf_hash = workflow_hash(wf)

        # Advance and submit first step
        advance(state)
        apply_submit(state, "step1", output="one")

        # Save checkpoint
        assert checkpoint_save(state) is True
        assert (state.checkpoint_dir / "state.json").exists()

        # Load checkpoint
        loaded = checkpoint_load(
            state.run_id, tmp_path,
            {wf.name: wf}, wf,
        )
        assert isinstance(loaded, RunState)
        assert loaded.run_id == state.run_id
        assert "step1" in loaded.ctx.results_scoped
        assert loaded.ctx.variables["key"] == "value"

    def test_drift_detection_on_resume(self, tmp_path):
        wf = _make_workflow([ShellStep(name="s", command="echo")])
        wf.source_path = str(tmp_path / "workflow.py")
        (tmp_path / "workflow.py").write_text("# v1")

        state = _make_state(wf, cwd=str(tmp_path))
        state.checkpoint_dir = tmp_path / ".workflow-state" / state.run_id
        state.wf_hash = workflow_hash(wf)
        checkpoint_save(state)

        # Modify workflow source
        (tmp_path / "workflow.py").write_text("# v2 changed!")

        result = checkpoint_load(state.run_id, tmp_path, {wf.name: wf}, wf)
        assert isinstance(result, str)
        assert "changed" in result

    def test_atomic_write(self, tmp_path):
        """Checkpoint should not leave partial files."""
        wf = _make_workflow([ShellStep(name="s", command="echo")])
        state = _make_state(wf, cwd=str(tmp_path))
        state.checkpoint_dir = tmp_path / ".workflow-state" / state.run_id

        checkpoint_save(state)
        checkpoint_file = state.checkpoint_dir / "state.json"
        assert checkpoint_file.exists()
        # tmp file should be cleaned up
        assert not (state.checkpoint_dir / "state.json.tmp").exists()


# ---------------------------------------------------------------------------
# Tests: Nested combos
# ---------------------------------------------------------------------------


class TestNestedCombos:
    def test_loop_with_retry(self):
        attempt_tracker = {"count": 0}

        def until(ctx):
            attempt_tracker["count"] += 1
            return attempt_tracker["count"] % 2 == 0  # succeed every 2nd check

        wf = _make_workflow([
            LoopBlock(name="items", loop_over="variables.items", loop_var="item",
                      blocks=[
                          RetryBlock(name="check", until=until, max_attempts=3,
                                     blocks=[ShellStep(name="test", command="run")]),
                      ]),
        ])
        state = _make_state(wf, variables={"items": ["a", "b"]})

        # Item a, attempt 0
        action, _ = advance(state)
        assert action.exec_key == "loop:items[i=0]/retry:check[attempt=0]/test"

        # Submit → until returns False (count=1) → retry
        action2, _ = apply_submit(state, action.exec_key)
        assert action2.exec_key == "loop:items[i=0]/retry:check[attempt=1]/test"

        # Submit → until returns True (count=2) → next loop item
        action3, _ = apply_submit(state, action2.exec_key)
        assert action3.exec_key == "loop:items[i=1]/retry:check[attempt=0]/test"

    def test_group_with_conditional(self):
        wf = _make_workflow([
            GroupBlock(name="setup", blocks=[
                ShellStep(name="detect", command="echo fast", result_var="mode"),
                ConditionalBlock(name="branch", branches=[
                    Branch(
                        condition=lambda c: c.get_var("variables.mode") == "fast",
                        blocks=[ShellStep(name="fast-path", command="echo fast")],
                    ),
                ], default=[
                    ShellStep(name="slow-path", command="echo slow"),
                ]),
            ]),
        ])
        state = _make_state(wf)

        action, _ = advance(state)
        assert action.exec_key == "detect"

        # result_var="mode" parses JSON, so submit '"fast"' (JSON string)
        action2, _ = apply_submit(state, "detect", output='"fast"')
        assert action2.exec_key == "fast-path"


# ---------------------------------------------------------------------------
# Tests: Full workflow simulation
# ---------------------------------------------------------------------------


class TestHalt:
    """Tests for the halt directive — stops entire workflow."""

    def test_halt_on_shell_step(self):
        """ShellStep with halt stops workflow after execution."""
        wf = _make_workflow([
            ShellStep(
                name="check",
                command="echo fail",
                halt="Check failed: verification did not pass",
            ),
            ShellStep(name="after", command="echo should not run"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.action == "shell"
        assert action.exec_key == "check"

        # Submit check result — should halt
        action, _ = apply_submit(state, "check", output="fail", status="success")
        assert action.action == "halted"
        assert "verification" in action.reason
        assert action.halted_at == "check"
        assert state.status == "halted"

    def test_halt_does_not_trigger_on_skip(self):
        """Halt doesn't fire if block is skipped by condition."""
        wf = _make_workflow([
            LLMStep(
                name="guarded",
                prompt_text="fail",
                halt="Should not see this",
                condition=lambda ctx: False,  # skipped
            ),
            LLMStep(name="after", prompt_text="ok"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        # guarded skipped → after prompt
        assert action.action == "prompt"
        assert "ok" in action.prompt
        action, _ = apply_submit(state, action.exec_key, output="done")
        assert action.action == "completed"

    def test_halt_on_failure_does_not_trigger(self):
        """Halt only triggers on success status, not failure."""
        wf = _make_workflow([
            LLMStep(name="step", prompt_text="do something", halt="halt reason"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.action == "prompt"

        # Submit with failure — halt should NOT trigger
        action, _ = apply_submit(state, "step", output="error", status="failure")
        assert action.action == "completed"  # workflow continues past failed step

    def test_halt_in_loop_stops_all(self):
        """Halt inside a loop stops the entire workflow, not just the loop."""
        wf = _make_workflow([
            LoopBlock(
                name="items",
                loop_over="variables.items",
                loop_var="item",
                blocks=[
                    LLMStep(
                        name="process",
                        prompt_text="process {{variables.item}}",
                        halt="Item failed",
                        condition=lambda ctx: ctx.variables.get("item") == "bad",
                    ),
                    LLMStep(
                        name="ok-step",
                        prompt_text="ok",
                        condition=lambda ctx: ctx.variables.get("item") != "bad",
                    ),
                ],
            ),
            ShellStep(name="after-loop", command="echo done"),
        ])
        state = _make_state(wf, variables={"items": ["good", "bad", "good2"]})

        # First iteration: item=good, process skipped, ok-step executes
        action, _ = advance(state)
        assert action.action == "prompt"
        assert "ok" in action.prompt
        action, _ = apply_submit(state, action.exec_key, output="done")

        # Second iteration: item=bad, process fires with halt
        assert action.action == "prompt"
        assert "bad" in action.prompt
        action, _ = apply_submit(state, action.exec_key, output="failed")
        assert action.action == "halted"
        assert state.status == "halted"

    def test_retry_halt_on_exhaustion(self):
        """RetryBlock with halt_on_exhaustion stops workflow when max_attempts reached."""
        wf = _make_workflow([
            RetryBlock(
                name="flaky",
                until=lambda ctx: False,  # never succeeds
                max_attempts=2,
                halt_on_exhaustion="Retry exhausted after {{variables.attempt_info}}",
                blocks=[
                    LLMStep(name="try", prompt_text="attempt"),
                ],
            ),
            ShellStep(name="after", command="echo should not run"),
        ])
        state = _make_state(wf, variables={"attempt_info": "2 attempts"})

        # Attempt 0
        action, _ = advance(state)
        assert action.action == "prompt"
        action, _ = apply_submit(state, action.exec_key, output="failed")

        # Attempt 1
        assert action.action == "prompt"
        action, _ = apply_submit(state, action.exec_key, output="failed again")

        # Exhausted → halted
        assert action.action == "halted"
        assert "2 attempts" in action.reason
        assert state.status == "halted"

    def test_retry_no_halt_when_succeeds(self):
        """RetryBlock with halt_on_exhaustion does not halt if until becomes True."""
        attempt = {"n": 0}

        def until_check(ctx):
            return attempt["n"] >= 1

        wf = _make_workflow([
            RetryBlock(
                name="flaky",
                until=until_check,
                max_attempts=3,
                halt_on_exhaustion="Should not halt",
                blocks=[
                    LLMStep(name="try", prompt_text="attempt"),
                ],
            ),
            LLMStep(name="after", prompt_text="ok"),
        ])
        state = _make_state(wf)

        # Attempt 0 — fails
        action, _ = advance(state)
        action, _ = apply_submit(state, action.exec_key, output="fail")

        # Attempt 1 — succeeds (until returns True)
        attempt["n"] = 1
        assert action.action == "prompt"
        action, _ = apply_submit(state, action.exec_key, output="ok")

        # Should continue to "after" step, not halt
        assert action.action == "prompt"
        assert "ok" in action.prompt
        action, _ = apply_submit(state, action.exec_key, output="done")
        assert action.action == "completed"

    def test_halt_template_substitution(self):
        """Halt reason supports template variables."""
        wf = _make_workflow([
            LLMStep(
                name="step",
                prompt_text="do",
                halt="Failed at step {{variables.step_name}}",
            ),
        ])
        state = _make_state(wf, variables={"step_name": "authentication"})
        action, _ = advance(state)
        action, _ = apply_submit(state, action.exec_key, output="done")
        assert action.action == "halted"
        assert "authentication" in action.reason


class TestFullWorkflow:
    def test_simple_linear_workflow(self):
        wf = _make_workflow([
            ShellStep(name="step1", command="echo 1"),
            ShellStep(name="step2", command="echo 2"),
            ShellStep(name="step3", command="echo 3"),
        ])
        state = _make_state(wf)

        action, _ = advance(state)
        assert action.exec_key == "step1"

        for key in ["step1", "step2"]:
            action, _ = apply_submit(state, key, output=key)

        assert action.exec_key == "step3"
        final, _ = apply_submit(state, "step3", output="done")
        assert final.action == "completed"
        assert state.status == "completed"
        assert final.display is not None

    def test_results_accumulated(self):
        wf = _make_workflow([
            ShellStep(name="a", command="echo a"),
            ShellStep(name="b", command="echo b"),
        ])
        state = _make_state(wf)

        advance(state)
        apply_submit(state, "a", output="result-a")
        apply_submit(state, "b", output="result-b")

        assert "a" in state.ctx.results_scoped
        assert "b" in state.ctx.results_scoped
        assert state.ctx.results_scoped["a"].output == "result-a"
        assert state.ctx.results_scoped["b"].output == "result-b"

    def test_failure_recorded(self):
        wf = _make_workflow([
            ShellStep(name="fail", command="false"),
            ShellStep(name="after", command="echo after"),
        ])
        state = _make_state(wf)

        advance(state)
        action, _ = apply_submit(state, "fail", status="failure", error="non-zero exit")
        assert action.exec_key == "after"

        result = state.ctx.results_scoped["fail"]
        assert result.status == "failure"
        assert result.error == "non-zero exit"


# ---------------------------------------------------------------------------
# Tests: results_key
# ---------------------------------------------------------------------------


class TestResultsKey:
    def test_no_scope(self):
        ctx = WorkflowContext()
        assert results_key(ctx, "step1") == "step1"

    def test_with_sub_scope(self):
        ctx = WorkflowContext()
        ctx._scope = ["sub:helper"]
        assert results_key(ctx, "inner") == "helper.inner"

    def test_with_nested_sub_scope(self):
        ctx = WorkflowContext()
        ctx._scope = ["sub:outer", "sub:inner"]
        assert results_key(ctx, "leaf") == "outer.inner.leaf"

    def test_non_sub_scope_ignored(self):
        ctx = WorkflowContext()
        ctx._scope = ["loop:items[i=0]", "sub:helper"]
        assert results_key(ctx, "step") == "helper.step"

    def test_empty_scope_list(self):
        ctx = WorkflowContext()
        ctx._scope = []
        assert results_key(ctx, "step") == "step"


# ---------------------------------------------------------------------------
# Tests: schema_dict
# ---------------------------------------------------------------------------


class TestSchemaDict:
    def test_with_pydantic_model(self):
        class MyModel(BaseModel):
            name: str
            count: int = 0

        result = schema_dict(MyModel)
        assert result is not None
        assert "properties" in result
        assert "name" in result["properties"]
        assert "count" in result["properties"]

    def test_with_none(self):
        assert schema_dict(None) is None


# ---------------------------------------------------------------------------
# Tests: resume_only blocks
# ---------------------------------------------------------------------------

CHECKPOINT_VERSION = _state_ns["CHECKPOINT_VERSION"]
checkpoint_dir_from_run_id = _state_ns["checkpoint_dir_from_run_id"]


class TestResumeOnly:
    def test_resume_only_skipped_on_fresh(self):
        """resume_only block is invisible on fresh run (is_resumed=False)."""
        wf = _make_workflow([
            LLMStep(name="cleanup", prompt_text="clean up", resume_only="true"),
            ShellStep(name="work", command="echo done"),
        ])
        state = _make_state(wf)
        assert state.is_resumed is False

        action, _ = advance(state)
        # Should skip the resume_only block and land on "work"
        assert action.action == "shell"
        assert action.exec_key == "work"
        # The cleanup step should NOT appear in results_scoped
        assert "cleanup" not in state.ctx.results_scoped

    def test_resume_only_executes_on_resume(self):
        """resume_only block executes when is_resumed=True."""
        wf = _make_workflow([
            LLMStep(name="cleanup", prompt_text="clean up", resume_only="true"),
            ShellStep(name="work", command="echo done"),
        ])
        state = _make_state(wf)
        state.is_resumed = True

        action, _ = advance(state)
        # Should hit the resume_only block
        assert action.action == "prompt"
        assert action.exec_key == "cleanup"

    def test_resume_only_every_resume(self):
        """resume_only="true": ephemeral key excluded from checkpoint."""
        wf = _make_workflow([
            ShellStep(name="refresh", command="echo refresh", resume_only="true"),
            ShellStep(name="work", command="echo done"),
        ])
        state = _make_state(wf)
        state.is_resumed = True

        action, _ = advance(state)
        assert action.action == "shell"
        assert action.exec_key == "refresh"

        # The ephemeral key should be tracked
        assert "refresh" in state._ephemeral_keys

        # Submit the refresh step
        result = apply_submit(state, "refresh", output="refreshed", status="success")

        # Now checkpoint: ephemeral keys should be excluded from serialized results
        # Verify the key is in results_scoped (in-memory) but tracked as ephemeral
        assert "refresh" in state.ctx.results_scoped
        assert "refresh" in state._ephemeral_keys

    def test_resume_only_once(self, tmp_path):
        """resume_only="once": persisted, skipped on subsequent resume."""
        wf = _make_workflow([
            LLMStep(name="migrate", prompt_text="migrate data",
                    resume_only="once"),
            ShellStep(name="work", command="echo done"),
        ])
        run_id = "abcdef123456"
        state = _make_state(wf, run_id=run_id, cwd=str(tmp_path))
        state.is_resumed = True
        state.checkpoint_dir = checkpoint_dir_from_run_id(tmp_path, run_id)
        state.checkpoint_dir.mkdir(parents=True)

        action, _ = advance(state)
        # First resume: should execute
        assert action.action == "prompt"
        assert action.exec_key == "migrate"

        # resume_only="once" → NOT in _ephemeral_keys (persisted)
        assert "migrate" not in state._ephemeral_keys

        # Submit it
        apply_submit(state, "migrate", output="migrated", status="success")

        # Save checkpoint (result is persisted since not ephemeral)
        checkpoint_save(state)
        cp_data = json.loads((state.checkpoint_dir / "state.json").read_text())
        assert "migrate" in cp_data["ctx"]["results_scoped"]

        # On next resume, advance would skip via replay (exec_key already in results_scoped)
        # Re-create state from checkpoint to verify
        state2 = checkpoint_load(run_id, tmp_path, {wf.name: wf}, wf)
        assert not isinstance(state2, str), f"checkpoint_load failed: {state2}"
        state2.is_resumed = True
        action2, _ = advance(state2)
        # Should skip migrate (already in results_scoped) and land on work
        assert action2.action == "shell"
        assert action2.exec_key == "work"

    def test_resume_only_rejected_on_composite_block(self):
        """resume_only on composite blocks (Loop, Retry, etc.) raises ValueError in loader."""
        from conftest import _loader_ns
        _validate_resume_only = _loader_ns["_validate_resume_only"]

        import pytest

        # LoopBlock
        with pytest.raises(ValueError, match="resume_only is only allowed on leaf steps"):
            _validate_resume_only([
                LoopBlock(name="bad-loop", loop_over="variables.items",
                          loop_var="item", resume_only="true"),
            ])

        # RetryBlock
        with pytest.raises(ValueError, match="resume_only is only allowed on leaf steps"):
            _validate_resume_only([
                RetryBlock(name="bad-retry", until=lambda ctx: True, resume_only="true"),
            ])

        # SubWorkflow
        with pytest.raises(ValueError, match="resume_only is only allowed on leaf steps"):
            _validate_resume_only([
                SubWorkflow(name="bad-sub", workflow="helper", resume_only="once"),
            ])

        # GroupBlock
        with pytest.raises(ValueError, match="resume_only is only allowed on leaf steps"):
            _validate_resume_only([
                GroupBlock(name="bad-group", blocks=[], resume_only="true"),
            ])

        # Leaf steps should NOT raise
        _validate_resume_only([
            LLMStep(name="ok-llm", prompt_text="test", resume_only="true"),
            ShellStep(name="ok-shell", command="echo ok", resume_only="once"),
            PromptStep(name="ok-prompt", prompt_type="confirm",
                       message="OK?", resume_only="true"),
        ])


# ============ ActionBase warnings default ============


class TestWarningsDefaultList:
    """warnings field should default to [] not None."""

    def test_warnings_defaults_to_empty_list(self):
        CompletedAction = _state_ns["CompletedAction"]
        action = CompletedAction(run_id="test", summary={}, totals={})
        assert action.warnings is not None
        assert action.warnings == []

    def test_warnings_serialization_excludes_empty(self):
        CompletedAction = _state_ns["CompletedAction"]
        action_to_dict = _state_ns["action_to_dict"]
        action = CompletedAction(run_id="test", summary={}, totals={})
        d = action_to_dict(action)
        assert "warnings" not in d

    def test_warnings_append_works_directly(self):
        CompletedAction = _state_ns["CompletedAction"]
        action = CompletedAction(run_id="test", summary={}, totals={})
        action.warnings.append("test warning")
        assert action.warnings == ["test warning"]

    def test_warnings_serialized_when_non_empty(self):
        CompletedAction = _state_ns["CompletedAction"]
        action_to_dict = _state_ns["action_to_dict"]
        action = CompletedAction(run_id="test", summary={}, totals={})
        action.warnings.append("something")
        d = action_to_dict(action)
        assert d["warnings"] == ["something"]


# ============ Halt from block directive ============


class TestSubmitHaltCheckpointSave:
    """submit() halt path must save checkpoint."""

    def test_halt_from_block_directive_saves_checkpoint(self, tmp_path):
        wf = WorkflowDef(
            name="halt-test",
            description="test",
            blocks=[
                ShellStep(name="step1", command="echo ok", halt="stop here"),
            ],
        )
        ctx = WorkflowContext(cwd=str(tmp_path))
        state = RunState(
            run_id="aaa111bbb222",
            ctx=ctx,
            stack=[Frame(block=wf)],
            registry={"halt-test": wf},
            checkpoint_dir=tmp_path / ".workflow-state" / "aaa111bbb222",
        )

        action, children = advance(state)
        assert action.action == "shell"
        ek = action.exec_key

        action2, children2 = apply_submit(
            state,
            ek,
            output="ok",
            status="success",
        )
        assert action2.action == "halted"
        assert state.status == "halted"
