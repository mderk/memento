"""Tests for workflow engine state machine (state.py).

Tests advance() + apply_submit() for all block types, idempotency,
exec_key validation, child runs, parallel, and checkpointing.
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from conftest import _types_ns, _state_ns

# Types
LLMStep = _types_ns["LLMStep"]
GroupBlock = _types_ns["GroupBlock"]
ParallelEachBlock = _types_ns["ParallelEachBlock"]
LoopBlock = _types_ns["LoopBlock"]
RetryBlock = _types_ns["RetryBlock"]
SubWorkflow = _types_ns["SubWorkflow"]
ShellStep = _types_ns["ShellStep"]
PromptStep = _types_ns["PromptStep"]
ConditionalBlock = _types_ns["ConditionalBlock"]
Branch = _types_ns["Branch"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]
StepResult = _types_ns["StepResult"]
Block = _types_ns["Block"]

# State
Frame = _state_ns["Frame"]
RunState = _state_ns["RunState"]
advance = _state_ns["advance"]
apply_submit = _state_ns["apply_submit"]
pending_action = _state_ns["pending_action"]
substitute = _state_ns["substitute"]
evaluate_condition = _state_ns["evaluate_condition"]
load_prompt = _state_ns["load_prompt"]
results_key = _state_ns["results_key"]
record_leaf_result = _state_ns["record_leaf_result"]
schema_dict = _state_ns["schema_dict"]
validate_structured_output = _state_ns["validate_structured_output"]
dry_run_structured_output = _state_ns["dry_run_structured_output"]
workflow_hash = _state_ns["workflow_hash"]
checkpoint_save = _state_ns["checkpoint_save"]
checkpoint_load = _state_ns["checkpoint_load"]
PROTOCOL_VERSION = _state_ns["PROTOCOL_VERSION"]


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
# Tests: substitute + evaluate_condition
# ---------------------------------------------------------------------------


class TestSubstitute:
    def test_variable_substitution(self):
        ctx = WorkflowContext(variables={"task": "add login", "mode": "protocol"})
        result = substitute("Task: {{variables.task}}, Mode: {{variables.mode}}", ctx)
        assert result == "Task: add login, Mode: protocol"

    def test_result_substitution(self):
        ctx = WorkflowContext()
        ctx.results["detect"] = StepResult(name="detect", output="python")
        result = substitute("Detected: {{results.detect.output}}", ctx)
        assert result == "Detected: python"

    def test_cwd_substitution(self):
        ctx = WorkflowContext(cwd="/my/project")
        result = substitute("Working in {{cwd}}", ctx)
        assert result == "Working in /my/project"

    def test_unresolved_kept(self):
        ctx = WorkflowContext()
        result = substitute("{{results.missing.output}}", ctx)
        assert result == "{{results.missing.output}}"

    def test_dict_substitution(self):
        ctx = WorkflowContext(variables={"config": {"a": 1}})
        result = substitute("Config: {{variables.config}}", ctx)
        assert '"a": 1' in result


class TestEvaluateCondition:
    def test_none_is_true(self):
        ctx = WorkflowContext()
        assert evaluate_condition(None, ctx) is True

    def test_true_condition(self):
        ctx = WorkflowContext(variables={"mode": "fast"})
        assert evaluate_condition(lambda c: c.get_var("variables.mode") == "fast", ctx) is True

    def test_false_condition(self):
        ctx = WorkflowContext(variables={"mode": "slow"})
        assert evaluate_condition(lambda c: c.get_var("variables.mode") == "fast", ctx) is False

    def test_exception_is_false(self):
        def bad(ctx):
            raise ValueError("boom")
        ctx = WorkflowContext()
        assert evaluate_condition(bad, ctx) is False


# ---------------------------------------------------------------------------
# Tests: ShellStep
# ---------------------------------------------------------------------------


class TestShellStep:
    def test_basic_shell(self):
        wf = _make_workflow([ShellStep(name="echo", command="echo hello")])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.action == "shell"
        assert action.exec_key == "echo"
        assert action.command == "echo hello"
        assert action.protocol_version == PROTOCOL_VERSION
        assert action.display is not None
        assert "echo" in action.display

    def test_shell_with_substitution(self):
        wf = _make_workflow([ShellStep(name="greet", command="echo {{variables.name}}")])
        state = _make_state(wf, variables={"name": "world"})
        action, _ = advance(state)
        assert action.command == "echo world"

    def test_shell_result_var(self):
        wf = _make_workflow([
            ShellStep(name="detect", command="echo '{}'", result_var="data"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.result_var == "data"

        # Submit with JSON output
        next_action, _ = apply_submit(state, "detect", output='{"lang": "python"}')
        assert state.ctx.variables["data"] == {"lang": "python"}

    def test_shell_submit_advances(self):
        wf = _make_workflow([
            ShellStep(name="step1", command="echo 1"),
            ShellStep(name="step2", command="echo 2"),
        ])
        state = _make_state(wf)

        action1, _ = advance(state)
        assert action1.exec_key == "step1"

        action2, _ = apply_submit(state, "step1", output="one")
        assert action2.exec_key == "step2"

        action3, _ = apply_submit(state, "step2", output="two")
        assert action3.action == "completed"

    def test_shell_condition_skip(self):
        wf = _make_workflow([
            ShellStep(name="skip", command="echo nope", condition=lambda c: False),
            ShellStep(name="run", command="echo yes"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.exec_key == "run"


# ---------------------------------------------------------------------------
# Tests: LLMStep (prompt action)
# ---------------------------------------------------------------------------


class TestLLMStep:
    def test_basic_prompt(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "analyze.md").write_text("Analyze {{variables.task}}")

        wf = _make_workflow(
            [LLMStep(name="analyze", prompt="analyze.md")],
            prompt_dir=str(prompt_dir),
        )
        state = _make_state(wf, variables={"task": "bug fix"})
        action, _ = advance(state)
        assert action.action == "prompt"
        assert action.exec_key == "analyze"
        assert "Analyze bug fix" in action.prompt
        assert action.display is not None
        assert "analyze" in action.display

    def test_prompt_with_tools_and_model(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "code.md").write_text("Write code")

        wf = _make_workflow(
            [LLMStep(name="code", prompt="code.md", tools=["Bash", "Read"], model="sonnet")],
            prompt_dir=str(prompt_dir),
        )
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.tools == ["Bash", "Read"]
        assert action.model == "sonnet"

    def test_prompt_with_output_schema(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "plan.md").write_text("Make a plan")

        class PlanOutput(BaseModel):
            tasks: list[str] = []
            priority: str = "medium"

        wf = _make_workflow(
            [LLMStep(name="plan", prompt="plan.md", output_schema=PlanOutput)],
            prompt_dir=str(prompt_dir),
        )
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.json_schema is not None
        assert action.output_schema_name == "PlanOutput"

    def test_prompt_condition_skip(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "a.md").write_text("a")
        (prompt_dir / "b.md").write_text("b")

        wf = _make_workflow([
            LLMStep(name="skip", prompt="a.md", condition=lambda c: False),
            LLMStep(name="run", prompt="b.md"),
        ], prompt_dir=str(prompt_dir))
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.exec_key == "run"


# ---------------------------------------------------------------------------
# Tests: PromptStep (ask_user action)
# ---------------------------------------------------------------------------


class TestPromptStep:
    def test_basic_ask_user(self):
        wf = _make_workflow([
            PromptStep(name="confirm", prompt_type="confirm",
                       message="Continue?", options=["yes", "no"]),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.action == "ask_user"
        assert action.exec_key == "confirm"
        assert action.message == "Continue?"
        assert action.options == ["yes", "no"]
        assert action.prompt_type == "confirm"
        assert action.display is not None
        assert "confirm" in action.display

    def test_ask_user_with_result_var(self):
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"],
                       result_var="mode"),
            ShellStep(name="echo", command="echo {{variables.mode}}"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.exec_key == "mode"

        next_action, _ = apply_submit(state, "mode", output="fast")
        assert state.ctx.variables["mode"] == "fast"
        assert next_action.action == "shell"
        assert next_action.command == "echo fast"

    def test_ask_user_template_substitution(self):
        wf = _make_workflow([
            PromptStep(name="confirm", prompt_type="confirm",
                       message="Deploy {{variables.app}}?"),
        ])
        state = _make_state(wf, variables={"app": "myapp"})
        action, _ = advance(state)
        assert action.message == "Deploy myapp?"

    def test_ask_user_non_strict(self):
        wf = _make_workflow([
            PromptStep(name="input", prompt_type="input",
                       message="Enter value", strict=False),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.strict is False

    def test_strict_choice_invalid_answer_sends_retry_confirm(self):
        """Invalid answer to strict choice sends 'try again?' confirmation."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"],
                       result_var="mode"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.action == "ask_user"

        # Submit invalid answer → "try again?" confirm
        retry_confirm, _ = apply_submit(state, "mode", output="?")
        assert retry_confirm.action == "ask_user"
        assert retry_confirm.retry_confirm is True
        assert retry_confirm.prompt_type == "confirm"
        assert retry_confirm.exec_key == "mode"
        assert retry_confirm.display is not None
        # State should still be waiting — result not recorded
        assert "mode" not in state.ctx.variables

    def test_strict_choice_valid_answer_accepted(self):
        """Valid answer to strict choice is accepted normally."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"],
                       result_var="mode"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)

        next_action, _ = apply_submit(state, "mode", output="fast")
        assert state.ctx.variables["mode"] == "fast"
        assert next_action.action == "completed"

    def test_strict_confirm_invalid_sends_retry_confirm(self):
        """Invalid answer to strict confirm sends 'try again?' confirmation."""
        wf = _make_workflow([
            PromptStep(name="confirm", prompt_type="confirm",
                       message="Continue?"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)

        retry_confirm, _ = apply_submit(state, "confirm", output="sure")
        assert retry_confirm.action == "ask_user"
        assert retry_confirm.retry_confirm is True
        assert retry_confirm.prompt_type == "confirm"
        assert "try again" in retry_confirm.message.lower()

    def test_strict_confirm_valid_answer_accepted(self):
        """Valid 'yes'/'no' to strict confirm is accepted."""
        wf = _make_workflow([
            PromptStep(name="confirm", prompt_type="confirm",
                       message="Continue?"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)

        next_action, _ = apply_submit(state, "confirm", output="yes")
        assert next_action.action == "completed"

    def test_strict_confirm_case_insensitive(self):
        """Confirm accepts 'Yes'/'No'/'YES' without retry."""
        for answer in ["Yes", "NO", "YES"]:
            wf = _make_workflow([
                PromptStep(name="c", prompt_type="confirm", message="OK?"),
            ])
            state = _make_state(wf)
            advance(state)
            next_action, _ = apply_submit(state, "c", output=answer)
            assert next_action.action == "completed"

    def test_strict_confirm_numeric_aliases(self):
        """Confirm accepts '1' for yes, '2' for no."""
        for answer, expected in [("1", "yes"), ("2", "no")]:
            wf = _make_workflow([
                PromptStep(name="c", prompt_type="confirm", message="OK?",
                           result_var="ans"),
            ])
            state = _make_state(wf)
            advance(state)
            apply_submit(state, "c", output=answer)
            assert state.ctx.variables["ans"] == expected

    def test_retry_confirm_yes_resends_original(self):
        """'try again?' → yes → re-sends original question."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"],
                       result_var="mode"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.options == ["fast", "thorough"]

        # Invalid answer → "try again?"
        retry_confirm, _ = apply_submit(state, "mode", output="???")
        assert retry_confirm.retry_confirm is True

        # "yes" → re-sends original question
        original, _ = apply_submit(state, "mode", output="yes")
        assert original.action == "ask_user"
        assert original.options == ["fast", "thorough"]
        assert original.message == "Pick mode"
        assert original.retry_confirm is None

        # Now valid answer works
        next_action, _ = apply_submit(state, "mode", output="thorough")
        assert state.ctx.variables["mode"] == "thorough"
        assert next_action.action == "completed"

    def test_retry_confirm_no_cancels(self):
        """'try again?' → no → cancels workflow."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"]),
        ])
        state = _make_state(wf)
        action, _ = advance(state)

        # Invalid → "try again?"
        retry_confirm, _ = apply_submit(state, "mode", output="?")
        assert retry_confirm.retry_confirm is True

        # "no" → cancel
        cancelled, _ = apply_submit(state, "mode", output="no")
        assert cancelled.action == "cancelled"
        assert state.status == "cancelled"
        assert cancelled.display is not None

    def test_retry_confirm_garbage_resends_retry_confirm(self):
        """'try again?' → garbage → re-sends 'try again?'."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"]),
        ])
        state = _make_state(wf)
        action, _ = advance(state)

        # Invalid → "try again?"
        retry1, _ = apply_submit(state, "mode", output="?")
        assert retry1.retry_confirm is True

        # Garbage → same "try again?"
        retry2, _ = apply_submit(state, "mode", output="??")
        assert retry2.retry_confirm is True
        assert retry2.action == "ask_user"

        # Still can say "yes" to get back to original
        original, _ = apply_submit(state, "mode", output="yes")
        assert original.action == "ask_user"
        assert original.options == ["fast", "thorough"]

    def test_retry_confirm_case_insensitive(self):
        """'try again?' accepts Yes/YES/no/No etc."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"]),
        ])
        state = _make_state(wf)
        advance(state)

        # Invalid → "try again?"
        apply_submit(state, "mode", output="?")

        # "Yes" (capitalized) → re-sends original
        original, _ = apply_submit(state, "mode", output="Yes")
        assert original.action == "ask_user"
        assert original.options == ["fast", "thorough"]

    def test_non_strict_skips_validation(self):
        """Non-strict prompt accepts any answer without re-prompt."""
        wf = _make_workflow([
            PromptStep(name="input", prompt_type="input",
                       message="Enter value", strict=False, result_var="val"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)

        next_action, _ = apply_submit(state, "input", output="anything goes")
        assert state.ctx.variables["val"] == "anything goes"
        assert next_action.action == "completed"

    def test_strict_choice_template_options_validated(self):
        """Template-substituted options are validated correctly."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["{{variables.opt1}}", "{{variables.opt2}}"],
                       result_var="mode"),
        ])
        state = _make_state(wf, variables={"opt1": "alpha", "opt2": "beta"})
        action, _ = advance(state)
        assert action.options == ["alpha", "beta"]

        # Invalid → "try again?"
        retry, _ = apply_submit(state, "mode", output="gamma")
        assert retry.retry_confirm is True

        # yes → original
        original, _ = apply_submit(state, "mode", output="yes")
        assert original.options == ["alpha", "beta"]

        # Valid
        next_action, _ = apply_submit(state, "mode", output="alpha")
        assert state.ctx.variables["mode"] == "alpha"
        assert next_action.action == "completed"

    def test_multiple_retry_cycles_no_stacking(self):
        """Two full invalid→retry→yes cycles: no stacking, always fresh original."""
        wf = _make_workflow([
            PromptStep(name="mode", prompt_type="choice",
                       message="Pick mode", options=["fast", "thorough"],
                       result_var="mode"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.options == ["fast", "thorough"]

        # Cycle 1: invalid → retry_confirm → yes → original
        retry1, _ = apply_submit(state, "mode", output="???")
        assert retry1.retry_confirm is True

        original1, _ = apply_submit(state, "mode", output="yes")
        assert original1.action == "ask_user"
        assert original1.options == ["fast", "thorough"]
        assert original1.retry_confirm is None

        # Cycle 2: invalid again → retry_confirm → yes → original (no stacking)
        retry2, _ = apply_submit(state, "mode", output="nope")
        assert retry2.retry_confirm is True

        original2, _ = apply_submit(state, "mode", output="yes")
        assert original2.action == "ask_user"
        assert original2.options == ["fast", "thorough"]
        assert original2.retry_confirm is None

        # Finally give a valid answer
        done, _ = apply_submit(state, "mode", output="fast")
        assert done.action == "completed"
        assert state.ctx.variables["mode"] == "fast"

    def test_status_cancelled_still_works(self):
        """Legacy status='cancelled' still cancels (backwards compatibility)."""
        wf = _make_workflow([
            PromptStep(name="confirm", prompt_type="confirm",
                       message="Continue?"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)

        cancelled, _ = apply_submit(state, "confirm", output="", status="cancelled")
        assert cancelled.action == "cancelled"
        assert state.status == "cancelled"


# ---------------------------------------------------------------------------
# Tests: GroupBlock
# ---------------------------------------------------------------------------


class TestGroupBlock:
    def test_sequential_group(self):
        wf = _make_workflow([
            GroupBlock(name="setup", blocks=[
                ShellStep(name="a", command="echo a"),
                ShellStep(name="b", command="echo b"),
            ]),
        ])
        state = _make_state(wf)

        action, _ = advance(state)
        assert action.exec_key == "a"

        action2, _ = apply_submit(state, "a", output="a")
        assert action2.exec_key == "b"

        action3, _ = apply_submit(state, "b", output="b")
        assert action3.action == "completed"

    def test_nested_groups(self):
        wf = _make_workflow([
            GroupBlock(name="outer", blocks=[
                GroupBlock(name="inner", blocks=[
                    ShellStep(name="deep", command="echo deep"),
                ]),
                ShellStep(name="after", command="echo after"),
            ]),
        ])
        state = _make_state(wf)

        action, _ = advance(state)
        assert action.exec_key == "deep"

        action2, _ = apply_submit(state, "deep")
        assert action2.exec_key == "after"

        action3, _ = apply_submit(state, "after")
        assert action3.action == "completed"


# ---------------------------------------------------------------------------
# Tests: LoopBlock
# ---------------------------------------------------------------------------


class TestLoopBlock:
    def test_loop_iteration(self):
        wf = _make_workflow([
            LoopBlock(name="items", loop_over="variables.items", loop_var="item",
                      blocks=[ShellStep(name="process", command="echo {{variables.item}}")]),
        ])
        state = _make_state(wf, variables={"items": ["a", "b", "c"]})

        # First iteration
        action, _ = advance(state)
        assert action.exec_key == "loop:items[i=0]/process"
        assert action.command == "echo a"

        action2, _ = apply_submit(state, "loop:items[i=0]/process")
        assert action2.exec_key == "loop:items[i=1]/process"
        assert action2.command == "echo b"

        action3, _ = apply_submit(state, "loop:items[i=1]/process")
        assert action3.exec_key == "loop:items[i=2]/process"
        assert action3.command == "echo c"

        action4, _ = apply_submit(state, "loop:items[i=2]/process")
        assert action4.action == "completed"

    def test_loop_empty_list(self):
        wf = _make_workflow([
            LoopBlock(name="items", loop_over="variables.items", loop_var="item",
                      blocks=[ShellStep(name="process", command="echo")]),
            ShellStep(name="after", command="echo done"),
        ])
        state = _make_state(wf, variables={"items": []})

        action, _ = advance(state)
        assert action.exec_key == "after"

    def test_loop_not_a_list(self):
        wf = _make_workflow([
            LoopBlock(name="items", loop_over="variables.items", loop_var="item",
                      blocks=[ShellStep(name="process", command="echo")]),
            ShellStep(name="after", command="echo done"),
        ])
        state = _make_state(wf, variables={"items": "not-a-list"})

        action, _ = advance(state)
        assert action.exec_key == "after"

    def test_loop_sets_index_var(self):
        wf = _make_workflow([
            LoopBlock(name="items", loop_over="variables.items", loop_var="item",
                      blocks=[ShellStep(name="show", command="echo {{variables.item_index}}")]),
        ])
        state = _make_state(wf, variables={"items": ["x", "y"]})

        action, _ = advance(state)
        assert action.command == "echo 0"

        action2, _ = apply_submit(state, action.exec_key)
        assert action2.command == "echo 1"


# ---------------------------------------------------------------------------
# Tests: RetryBlock
# ---------------------------------------------------------------------------


class TestRetryBlock:
    def test_retry_succeeds_first_try(self):
        wf = _make_workflow([
            RetryBlock(name="check", until=lambda c: True, max_attempts=3,
                       blocks=[ShellStep(name="test", command="run tests")]),
        ])
        state = _make_state(wf)

        action, _ = advance(state)
        assert action.exec_key == "retry:check[attempt=0]/test"

        action2, _ = apply_submit(state, action.exec_key)
        assert action2.action == "completed"

    def test_retry_multiple_attempts(self):
        attempt_count = [0]

        def until(ctx):
            attempt_count[0] += 1
            return attempt_count[0] >= 3  # Succeeds on 3rd check

        wf = _make_workflow([
            RetryBlock(name="check", until=until, max_attempts=5,
                       blocks=[ShellStep(name="test", command="run tests")]),
        ])
        state = _make_state(wf)

        # Attempt 0
        action, _ = advance(state)
        assert action.exec_key == "retry:check[attempt=0]/test"
        action2, _ = apply_submit(state, action.exec_key)
        # until() returns False (attempt_count=1) → retry
        assert action2.exec_key == "retry:check[attempt=1]/test"

        action3, _ = apply_submit(state, action2.exec_key)
        # until() returns False (attempt_count=2) → retry
        assert action3.exec_key == "retry:check[attempt=2]/test"

        action4, _ = apply_submit(state, action3.exec_key)
        # until() returns True (attempt_count=3) → done
        assert action4.action == "completed"

    def test_retry_exhausts_max_attempts(self):
        wf = _make_workflow([
            RetryBlock(name="check", until=lambda c: False, max_attempts=2,
                       blocks=[ShellStep(name="test", command="run tests")]),
        ])
        state = _make_state(wf)

        action, _ = advance(state)
        assert "attempt=0" in action.exec_key

        action2, _ = apply_submit(state, action.exec_key)
        assert "attempt=1" in action2.exec_key

        action3, _ = apply_submit(state, action2.exec_key)
        # Exhausted max_attempts → completed (not retrying)
        assert action3.action == "completed"


# ---------------------------------------------------------------------------
# Tests: ConditionalBlock
# ---------------------------------------------------------------------------


class TestConditionalBlock:
    def test_first_branch_matches(self):
        wf = _make_workflow([
            ConditionalBlock(name="check", branches=[
                Branch(condition=lambda c: True, blocks=[
                    ShellStep(name="branch1", command="echo first"),
                ]),
                Branch(condition=lambda c: True, blocks=[
                    ShellStep(name="branch2", command="echo second"),
                ]),
            ]),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.exec_key == "branch1"

    def test_second_branch_matches(self):
        wf = _make_workflow([
            ConditionalBlock(name="check", branches=[
                Branch(condition=lambda c: False, blocks=[
                    ShellStep(name="branch1", command="echo first"),
                ]),
                Branch(condition=lambda c: True, blocks=[
                    ShellStep(name="branch2", command="echo second"),
                ]),
            ]),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.exec_key == "branch2"

    def test_default_branch(self):
        wf = _make_workflow([
            ConditionalBlock(name="check", branches=[
                Branch(condition=lambda c: False, blocks=[
                    ShellStep(name="branch1", command="echo first"),
                ]),
            ], default=[
                ShellStep(name="fallback", command="echo default"),
            ]),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.exec_key == "fallback"

    def test_no_match_skip(self):
        wf = _make_workflow([
            ConditionalBlock(name="check", branches=[
                Branch(condition=lambda c: False, blocks=[
                    ShellStep(name="branch1", command="echo"),
                ]),
            ]),
            ShellStep(name="after", command="echo after"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.exec_key == "after"


# ---------------------------------------------------------------------------
# Tests: SubWorkflow
# ---------------------------------------------------------------------------


class TestSubWorkflow:
    def test_basic_subworkflow(self):
        helper = WorkflowDef(
            name="helper",
            description="helper workflow",
            blocks=[ShellStep(name="help", command="echo {{variables.input}}")],
        )
        wf = _make_workflow([
            SubWorkflow(name="call-helper", workflow="helper",
                        inject={"input": "variables.task"}),
        ])
        state = _make_state(wf, variables={"task": "build"},
                            registry={"test": wf, "helper": helper})

        action, _ = advance(state)
        assert action.action == "shell"
        assert action.exec_key == "sub:call-helper/help"
        assert action.command == "echo build"

    def test_unknown_workflow_error(self):
        wf = _make_workflow([
            SubWorkflow(name="call-missing", workflow="nonexistent"),
        ])
        state = _make_state(wf)
        action, _ = advance(state)
        assert action.action == "error"
        assert "nonexistent" in action.message

    def test_subworkflow_restores_variables(self):
        helper = WorkflowDef(
            name="helper",
            description="helper",
            blocks=[ShellStep(name="inner", command="echo {{variables.x}}")],
        )
        wf = _make_workflow([
            SubWorkflow(name="sub", workflow="helper",
                        inject={"x": "variables.original"}),
            ShellStep(name="outer", command="echo {{variables.original}}"),
        ])
        state = _make_state(wf, variables={"original": "kept"},
                            registry={"test": wf, "helper": helper})

        action, _ = advance(state)
        assert action.exec_key == "sub:sub/inner"
        assert action.command == "echo kept"

        action2, _ = apply_submit(state, action.exec_key)
        assert action2.exec_key == "outer"
        assert action2.command == "echo kept"


# ---------------------------------------------------------------------------
# Tests: Isolation / Subagent
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_subagent_llm_step(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "review.md").write_text("Review the code")

        wf = _make_workflow([
            LLMStep(name="review", prompt="review.md",
                    isolation="subagent", tools=["Read", "Grep"],
                    context_hint="project files"),
        ], prompt_dir=str(prompt_dir))
        state = _make_state(wf)

        action, children = advance(state)
        assert action.action == "subagent"
        assert action.relay is False
        assert "Review the code" in action.prompt
        assert action.context_hint == "project files"
        assert action.tools == ["Read", "Grep"]
        assert len(children) == 0

    def test_subagent_group_block(self):
        wf = _make_workflow([
            GroupBlock(name="develop", isolation="subagent", blocks=[
                ShellStep(name="lint", command="ruff check ."),
                ShellStep(name="test", command="uv run pytest"),
            ]),
        ])
        state = _make_state(wf)

        action, children = advance(state)
        assert action.action == "subagent"
        assert action.relay is True
        assert action.child_run_id is not None
        assert len(children) == 1

        child = children[0]
        assert child.run_id == action.child_run_id
        assert child.parent_run_id == state.run_id

    def test_subagent_group_block_with_model(self):
        wf = _make_workflow([
            GroupBlock(name="develop", isolation="subagent", model="opus", blocks=[
                ShellStep(name="lint", command="ruff check ."),
            ]),
        ])
        state = _make_state(wf)

        action, children = advance(state)
        assert action.action == "subagent"
        assert action.model == "opus"

    def test_subagent_group_block_without_model(self):
        wf = _make_workflow([
            GroupBlock(name="develop", isolation="subagent", blocks=[
                ShellStep(name="lint", command="ruff check ."),
            ]),
        ])
        state = _make_state(wf)

        action, children = advance(state)
        assert action.action == "subagent"
        assert action.model is None

    def test_no_subagent_from_child(self):
        """Inside a child run, subagent isolation is downgraded to inline."""
        wf = _make_workflow([
            GroupBlock(name="outer", isolation="subagent", blocks=[
                GroupBlock(name="inner", isolation="subagent", blocks=[
                    ShellStep(name="deep", command="echo deep"),
                ]),
            ]),
        ])
        state = _make_state(wf)

        # Get the subagent action for outer group
        action, children = advance(state)
        assert action.action == "subagent"
        assert action.relay is True

        # Work with the child run
        child = children[0]
        child_action, child_children = advance(child)
        # Inner group should be downgraded to inline
        assert child_action.action == "shell"
        assert child_action.exec_key == "deep"
        assert len(child_children) == 0
        assert any("Downgraded" in w for w in child.warnings)

    def test_no_subagent_llm_step_from_child(self, tmp_path):
        """LLMStep with isolation=subagent inside child run is downgraded with warning."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "review.md").write_text("Review the code")

        wf = _make_workflow([
            GroupBlock(name="outer", isolation="subagent", blocks=[
                LLMStep(name="inner-llm", prompt="review.md", isolation="subagent"),
            ]),
        ], prompt_dir=str(prompt_dir))
        state = _make_state(wf)

        action, children = advance(state)
        assert action.action == "subagent"
        child = children[0]

        child_action, child_children = advance(child)
        # LLMStep should be downgraded to inline prompt
        assert child_action.action == "prompt"
        assert child_action.exec_key == "inner-llm"
        assert len(child_children) == 0
        assert any("Downgraded" in w and "inner-llm" in w for w in child.warnings)


# ---------------------------------------------------------------------------
# Tests: ParallelEachBlock
# ---------------------------------------------------------------------------


class TestParallelEachBlock:
    def test_parallel_creates_child_runs(self):
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                template=[ShellStep(name="review", command="echo {{variables.file}}")],
            ),
        ])
        state = _make_state(wf, variables={"files": ["a.py", "b.py"]})

        action, children = advance(state)
        assert action.action == "parallel"
        assert len(action.lanes) == 2
        assert len(children) == 2

        # Each lane has its own child_run_id
        lane0 = action.lanes[0]
        lane1 = action.lanes[1]
        assert lane0.child_run_id != lane1.child_run_id
        assert lane0.relay is True

    def test_parallel_with_model(self):
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                model="opus",
                template=[ShellStep(name="review", command="echo {{variables.file}}")],
            ),
        ])
        state = _make_state(wf, variables={"files": ["a.py", "b.py"]})

        action, children = advance(state)
        assert action.action == "parallel"
        assert action.model == "opus"

    def test_parallel_empty_skips(self):
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                template=[ShellStep(name="review", command="echo")],
            ),
            ShellStep(name="after", command="echo done"),
        ])
        state = _make_state(wf, variables={"files": []})

        action, _ = advance(state)
        assert action.exec_key == "after"

    def test_parallel_child_runs_independently(self):
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                template=[ShellStep(name="check", command="echo {{variables.file}}")],
            ),
        ])
        state = _make_state(wf, variables={"files": ["x", "y"]})

        action, children = advance(state)
        assert len(children) == 2

        # Each child can advance independently
        child0_action, _ = advance(children[0])
        child1_action, _ = advance(children[1])

        # They should have different par scope labels
        assert "par:reviews[i=0]" in child0_action.exec_key
        assert "par:reviews[i=1]" in child1_action.exec_key

    def test_parallel_downgraded_in_child(self):
        """Inside a child run, parallel is downgraded to sequential."""
        inner_parallel = ParallelEachBlock(
            name="inner",
            parallel_for="variables.items",
            item_var="item",
            template=[ShellStep(name="proc", command="echo {{variables.item}}")],
        )
        wf = _make_workflow([
            GroupBlock(name="outer", isolation="subagent", blocks=[inner_parallel]),
        ])
        state = _make_state(wf, variables={"items": ["a", "b"]})

        # Get subagent for outer
        action, children = advance(state)
        child = children[0]

        # Inside child: parallel should be downgraded to sequential loop
        child_action, child_children = advance(child)
        assert child_action.action == "shell"
        assert len(child_children) == 0
        assert any("Downgraded" in w for w in child.warnings)

    def test_max_concurrency_batches(self):
        """max_concurrency splits items into batched parallel blocks."""
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                max_concurrency=2,
                template=[ShellStep(name="check", command="echo {{variables.file}}")],
            ),
        ])
        # 5 items with max_concurrency=2 → 3 batches: [a,b], [c,d], [e]
        state = _make_state(wf, variables={"files": ["a", "b", "c", "d", "e"]})

        # First advance should produce a parallel action for the first batch (2 lanes)
        action, children = advance(state)
        assert action.action == "parallel"
        assert len(action.lanes) == 2
        assert len(children) == 2

    def test_max_concurrency_not_triggered_when_within_limit(self):
        """max_concurrency doesn't batch when items <= limit."""
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                max_concurrency=5,
                template=[ShellStep(name="check", command="echo {{variables.file}}")],
            ),
        ])
        state = _make_state(wf, variables={"files": ["a", "b", "c"]})

        action, children = advance(state)
        assert action.action == "parallel"
        assert len(action.lanes) == 3
        assert len(children) == 3

    def test_max_concurrency_exact_match(self):
        """max_concurrency == len(items) → no batching."""
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                max_concurrency=3,
                template=[ShellStep(name="check", command="echo {{variables.file}}")],
            ),
        ])
        state = _make_state(wf, variables={"files": ["a", "b", "c"]})

        action, children = advance(state)
        assert action.action == "parallel"
        assert len(action.lanes) == 3

    def test_max_concurrency_creates_chunks_variable(self):
        """Batching stores chunk data in ctx.variables."""
        wf = _make_workflow([
            ParallelEachBlock(
                name="reviews",
                parallel_for="variables.files",
                item_var="file",
                max_concurrency=2,
                template=[ShellStep(name="check", command="echo {{variables.file}}")],
            ),
        ])
        state = _make_state(wf, variables={"files": ["a", "b", "c", "d", "e"]})
        advance(state)

        # Synthetic loop variables should be set
        assert "_par_reviews_chunks" in state.ctx.variables
        chunks = state.ctx.variables["_par_reviews_chunks"]
        assert chunks == [["a", "b"], ["c", "d"], ["e"]]


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
