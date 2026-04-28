"""Integration tests for child runs (subagent relay, SubWorkflow, halt propagation).

Tests subagent group child runs, child run verification (anti-fabrication),
inline SubWorkflow with cascading resume, and transparent SubWorkflow proxying.
"""

import json
from pathlib import Path

import pytest

from conftest import _types_ns, create_runner_ns

# Runner (fresh namespace — tests mutate globals)
_runner_ns = create_runner_ns()

# Extract tool functions
_start = _runner_ns["start"]
_submit = _runner_ns["submit"]
_next = _runner_ns["next"]
_cancel = _runner_ns["cancel"]
_list_workflows = _runner_ns["list_workflows"]
_status = _runner_ns["status"]
_runs = _runner_ns["_runs"]

# Checkpoint utilities
_checkpoint_dir_from_run_id = _runner_ns["checkpoint_dir_from_run_id"]

# Types
ShellStep = _types_ns["ShellStep"]
GroupBlock = _types_ns["GroupBlock"]
LoopBlock = _types_ns["LoopBlock"]
PromptStep = _types_ns["PromptStep"]
LLMStep = _types_ns["LLMStep"]
ParallelEachBlock = _types_ns["ParallelEachBlock"]
WorkflowDef = _types_ns["WorkflowDef"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_runs():
    """Clear in-memory runs between tests."""
    _runs.clear()
    yield
    _runs.clear()


# ---------------------------------------------------------------------------
# Shared workflow factories
# ---------------------------------------------------------------------------


def _make_subagent_workflow(
    tmp_path,
    *,
    name="sub-test",
    with_surrounding_shells=True,
    context_hint=None,
    extra_blocks_before="",
    extra_blocks_after="",
):
    """Create a workflow dir with a subagent-isolated group.

    Args:
        name: Workflow/directory name.
        with_surrounding_shells: If True, adds ShellStep before and after the group.
        context_hint: Optional context_hint for the GroupBlock.
        extra_blocks_before/after: Extra block source to inject.
    """
    wf_dir = tmp_path / name
    wf_dir.mkdir()
    prompts_dir = wf_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "s1.md").write_text("Step 1 prompt")
    (prompts_dir / "s2.md").write_text("Step 2 prompt")

    blocks = []
    if with_surrounding_shells:
        blocks.append('ShellStep(name="before", command="echo pre"),')
    if extra_blocks_before:
        blocks.append(extra_blocks_before)
    hint = f', context_hint="{context_hint}"' if context_hint else ""
    blocks.append(f"""GroupBlock(
            name="sub-group",
            isolation="subagent"{hint},
            blocks=[
                LLMStep(name="inner1", prompt="s1.md", model="haiku"),
                LLMStep(name="inner2", prompt="s2.md", model="haiku"),
            ],
        ),""")
    if extra_blocks_after:
        blocks.append(extra_blocks_after)
    if with_surrounding_shells:
        blocks.append('ShellStep(name="after", command="echo post"),')

    blocks_str = "\n        ".join(blocks)
    (wf_dir / "workflow.py").write_text(f"""
WORKFLOW = WorkflowDef(
    name="{name}",
    description="Subagent group test",
    blocks=[
        {blocks_str}
    ],
)
""")
    return tmp_path


def _make_subagent_loop_workflow(tmp_path, *, name="loop-sub-test"):
    """Create a workflow dir with a subagent-isolated LoopBlock."""
    wf_dir = tmp_path / name
    wf_dir.mkdir()
    prompts_dir = wf_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "inner.md").write_text("Loop item: {{variables.item}}")
    setup_cmd = "echo '{\"items\": [\"a\", \"b\"]}'"

    (wf_dir / "workflow.py").write_text(f"""
WORKFLOW = WorkflowDef(
    name="{name}",
    description="Subagent loop test",
    blocks=[
        ShellStep(
            name="setup",
            command={setup_cmd!r},
            result_var="data",
        ),
        LoopBlock(
            name="sub-loop",
            isolation="subagent",
            loop_over="variables.data.items",
            loop_var="item",
            blocks=[
                LLMStep(name="inner", prompt="inner.md", model="haiku"),
            ],
        ),
        ShellStep(name="after", command="echo post"),
    ],
)
""")
    return tmp_path


def _make_parallel_workflow(
    tmp_path,
    *,
    name="par-test",
    items_expr='["x", "y"]',
    with_trailing_shell=True,
    two_steps=False,
):
    """Create a workflow dir with a ParallelEachBlock.

    Args:
        name: Workflow/directory name.
        items_expr: JSON expression for setup shell output items.
        with_trailing_shell: If True, adds a ShellStep after the parallel block.
    """
    wf_dir = tmp_path / name
    wf_dir.mkdir()
    prompts_dir = wf_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "check.md").write_text("Check item: {{variables.par_item}}")
    if two_steps:
        (prompts_dir / "check2.md").write_text("Second check: {{variables.par_item}}")

    trailing = (
        '        ShellStep(name="done", command="echo finished"),\n'
        if with_trailing_shell
        else ""
    )
    (wf_dir / "workflow.py").write_text(f"""
WORKFLOW = WorkflowDef(
    name="{name}",
    description="Parallel test",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \\'{{\"items\": {items_expr}}}\\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            template=[
                LLMStep(name="check", prompt="check.md", model="haiku"),
                {"LLMStep(name=\"check2\", prompt=\"check2.md\", model=\"haiku\")," if two_steps else ""}
            ],
            parallel_for="variables.data.items",
        ),
{trailing}    ],
)
""")
    return tmp_path


def _make_inline_subworkflow(tmp_path, *, name="inline-sub"):
    """Create a workflow with an inline SubWorkflow referencing a helper.

    Parent: ShellStep("setup") -> SubWorkflow("call-helper") -> ShellStep("finish")
    Helper: LLMStep("inner-work") with a prompt
    """
    wf_dir = tmp_path / name
    wf_dir.mkdir()
    prompts_dir = wf_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "work.md").write_text("Do the inner work")

    helper_dir = tmp_path / "helper"
    helper_dir.mkdir()
    helper_prompts = helper_dir / "prompts"
    helper_prompts.mkdir()
    (helper_prompts / "work.md").write_text("Inner work prompt")
    (helper_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="helper",
    description="Helper workflow",
    blocks=[
        LLMStep(name="inner-work", prompt="work.md", model="haiku"),
    ],
)
""")

    (wf_dir / "workflow.py").write_text(
        """
WORKFLOW = WorkflowDef(
    name="%s",
    description="Inline SubWorkflow test",
    blocks=[
        ShellStep(name="setup", command="echo ready"),
        SubWorkflow(name="call-helper", workflow="helper",
                    inject={"task": "variables.run_id"}),
        ShellStep(name="finish", command="echo done"),
    ],
)
"""
        % name
    )
    return tmp_path


def _make_shell_only_subworkflow(tmp_path, *, name="shell-sub"):
    """Create a workflow with an inline SubWorkflow whose child is shell-only.

    Parent: SubWorkflow("call-shell-helper") -> ShellStep("after")
    Helper: ShellStep("echo-step") only -- auto-completes
    """
    wf_dir = tmp_path / name
    wf_dir.mkdir()

    helper_dir = tmp_path / "helper-shell"
    helper_dir.mkdir()
    (helper_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="helper-shell",
    description="Shell-only helper",
    blocks=[
        ShellStep(name="echo-step", command="echo hello"),
    ],
)
""")

    (wf_dir / "workflow.py").write_text(
        """
WORKFLOW = WorkflowDef(
    name="%s",
    description="Shell-only SubWorkflow test",
    blocks=[
        SubWorkflow(name="call-shell-helper", workflow="helper-shell"),
        ShellStep(name="after", command="echo post"),
    ],
)
"""
        % name
    )
    return tmp_path


def _make_transparent_sub(tmp_path):
    """Parent: ShellStep -> SubWorkflow(helper with 2 LLM steps) -> ShellStep.

    Used to verify that relay agent only sees parent run_id.
    """
    helper_dir = tmp_path / "t-helper"
    helper_dir.mkdir()
    prompts_dir = helper_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "work1.md").write_text("Do work 1")
    (prompts_dir / "work2.md").write_text("Do work 2")
    (helper_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="t-helper",
    description="Helper with 2 LLM steps",
    blocks=[
        LLMStep(name="step1", prompt="work1.md"),
        LLMStep(name="step2", prompt="work2.md"),
    ],
)
""")

    wf_dir = tmp_path / "t-parent"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="t-parent",
    description="Parent with transparent SubWorkflow",
    blocks=[
        ShellStep(name="setup", command="echo ready"),
        SubWorkflow(name="call-helper", workflow="t-helper"),
        ShellStep(name="finish", command="echo done"),
    ],
)
""")
    return tmp_path


def _make_transparent_loop_sub(tmp_path):
    """Parent: LoopBlock over 2 items, each iteration has a SubWorkflow.

    Used to verify that transparent SubWorkflow works inside loops
    (the process-protocol pattern).
    """
    helper_dir = tmp_path / "loop-helper"
    helper_dir.mkdir()
    prompts_dir = helper_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "impl.md").write_text("Implement: {{variables.item}}")
    (helper_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="loop-helper",
    description="Helper for loop test",
    blocks=[
        LLMStep(name="implement", prompt="impl.md"),
    ],
)
""")

    wf_dir = tmp_path / "loop-parent"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="loop-parent",
    description="Parent with loop + SubWorkflow",
    blocks=[
        LoopBlock(
            name="steps",
            loop_over="variables.items",
            loop_var="item",
            blocks=[
                SubWorkflow(name="develop", workflow="loop-helper",
                            inject={"item": "{{variables.item}}"}),
                ShellStep(name="mark-done", command="echo done {{variables.item}}"),
            ],
        ),
        ShellStep(name="finish", command="echo all done"),
    ],
)
""")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: Child runs (subagent relay)
# ---------------------------------------------------------------------------


class TestChildRuns:
    @pytest.fixture
    def subagent_workflow(self, tmp_path):
        return _make_subagent_workflow(tmp_path, context_hint="test context")

    def test_subagent_group_emits_child_run(self, subagent_workflow):
        """Shell auto-advances, then subagent action with child_run_id."""
        start_result = json.loads(
            _start(
                workflow="sub-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        # "before" shell was auto-advanced -> subagent action
        assert start_result["action"] == "subagent"
        assert start_result["relay"] is True
        assert "child_run_id" in start_result
        assert "_shell_log" in start_result
        assert start_result["_shell_log"][0]["exec_key"] == "before"

        child_run_id = start_result["child_run_id"]
        assert child_run_id in _runs

    def test_child_relay_loop(self, subagent_workflow):
        """Child run driven via next() + submit(), parent completes after."""
        start_result = json.loads(
            _start(
                workflow="sub-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]
        parent_exec_key = start_result["exec_key"]

        # Drive child relay: next -> inner1 -> submit -> inner2 -> submit -> completed
        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "inner1"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="inner1",
                output="done1",
            )
        )
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "inner2"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="inner2",
                output="done2",
            )
        )
        assert child_action["action"] == "completed"

        # Submit parent with child summary -> "after" shell auto-advances -> completed
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="child completed",
            )
        )
        assert result["action"] == "completed"
        assert "_shell_log" in result
        assert result["_shell_log"][0]["exec_key"] == "after"

    def test_status_shows_child_runs(self, subagent_workflow):
        """Status tool shows child run information."""
        start_result = json.loads(
            _start(
                workflow="sub-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]

        status = json.loads(_status(run_id=run_id))
        assert child_run_id in status["child_run_ids"]
        assert "children" in status
        assert child_run_id in status["children"]

    def test_group_subagent_child_checkpoint_includes_resume_metadata(self, subagent_workflow):
        """GroupBlock(isolation=subagent) child checkpoints persist resume metadata."""
        start_result = json.loads(
            _start(
                workflow="sub-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]
        child_segment = child_run_id.split(">", 1)[1]

        cp_file = subagent_workflow / ".workflow-state" / run_id / "children" / child_segment / "state.json"
        data = json.loads(cp_file.read_text())
        assert data["subagent_block_name"] == "sub-group"
        assert data["subagent_exec_key"] == start_result["exec_key"]
        assert data["relay_parent_exec_key"] == start_result["exec_key"]
        assert data["relay_block_kind"] == "group"
        assert data["relay_block_name"] == "sub-group"

    def test_resume_group_subagent_reuses_child_and_continues_at_next_step(self, subagent_workflow):
        """Resume reuses the same GroupBlock child run and continues from the next child prompt."""
        start_result = json.loads(
            _start(
                workflow="sub-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]
        child_run_id = start_result["child_run_id"]

        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "inner1"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="inner1",
                output="done1",
            )
        )
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "inner2"

        _runs.clear()  # simulate server restart

        resumed = json.loads(
            _start(
                workflow="sub-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
                resume=run_id,
            )
        )
        assert resumed["action"] == "subagent"
        assert resumed["child_run_id"] == child_run_id
        assert resumed.get("_resumed") is True

        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "inner2"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="inner2",
                output="done2",
            )
        )
        assert child_action["action"] == "completed"

        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="child completed",
            )
        )
        assert result["action"] == "completed"

    def test_loop_subagent_child_checkpoint_includes_resume_metadata(self, tmp_path):
        """LoopBlock(isolation=subagent) child checkpoints persist generic relay metadata."""
        workflow_root = _make_subagent_loop_workflow(tmp_path)
        start_result = json.loads(
            _start(
                workflow="loop-sub-test",
                cwd=str(workflow_root),
                workflow_dirs=[str(workflow_root)],
            )
        )
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]
        child_segment = child_run_id.split(">", 1)[1]

        cp_file = workflow_root / ".workflow-state" / run_id / "children" / child_segment / "state.json"
        data = json.loads(cp_file.read_text())
        assert data["relay_parent_exec_key"] == start_result["exec_key"]
        assert data["relay_block_kind"] == "loop"
        assert data["relay_block_name"] == "sub-loop"

    def test_resume_loop_subagent_reuses_child_and_continues_at_next_iteration(self, tmp_path):
        """Resume reuses the same LoopBlock child run and continues at the next loop iteration."""
        workflow_root = _make_subagent_loop_workflow(tmp_path)
        start_result = json.loads(
            _start(
                workflow="loop-sub-test",
                cwd=str(workflow_root),
                workflow_dirs=[str(workflow_root)],
            )
        )
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]
        child_run_id = start_result["child_run_id"]

        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "loop:sub-loop[i=0]/inner"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="loop:sub-loop[i=0]/inner",
                output="done-a",
            )
        )
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "loop:sub-loop[i=1]/inner"

        _runs.clear()

        resumed = json.loads(
            _start(
                workflow="loop-sub-test",
                cwd=str(workflow_root),
                workflow_dirs=[str(workflow_root)],
                resume=run_id,
            )
        )
        assert resumed["action"] == "subagent"
        assert resumed["child_run_id"] == child_run_id
        assert resumed.get("_resumed") is True

        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "loop:sub-loop[i=1]/inner"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="loop:sub-loop[i=1]/inner",
                output="done-b",
            )
        )
        assert child_action["action"] == "completed"

        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="child completed",
            )
        )
        assert result["action"] == "completed"


# ---------------------------------------------------------------------------
# Tests: Child run verification (anti-fabrication)
# ---------------------------------------------------------------------------


class TestChildRunVerification:
    """Verify that submitting to parent fails if child runs didn't actually complete."""

    @pytest.fixture
    def subagent_workflow(self, tmp_path):
        return _make_subagent_workflow(
            tmp_path,
            name="sv-test",
            with_surrounding_shells=False,
        )

    @pytest.fixture
    def parallel_workflow(self, tmp_path):
        return _make_parallel_workflow(
            tmp_path,
            name="pv-test",
            items_expr='["a", "b"]',
            with_trailing_shell=False,
        )

    def test_subagent_submit_rejected_without_child_completion(self, subagent_workflow):
        """Submit to parent rejected when child run hasn't completed."""
        start_result = json.loads(
            _start(
                workflow="sv-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]

        # Agent fabricates without running child relay
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="fabricated answer",
            )
        )
        assert result["action"] == "error"
        assert "not completed" in result["message"] or "status" in result["message"]

    def test_subagent_submit_accepted_after_child_completion(self, subagent_workflow):
        """Submit to parent succeeds after child relay finishes."""
        start_result = json.loads(
            _start(
                workflow="sv-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]
        child_run_id = start_result["child_run_id"]

        # Drive child to completion
        child_action = json.loads(_next(run_id=child_run_id))
        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output="done1",
            )
        )
        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output="done2",
            )
        )
        assert child_action["action"] == "completed"

        # Now parent submit succeeds
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="child completed",
            )
        )
        assert result["action"] == "completed"

    def test_subagent_failure_status_bypasses_verification(self, subagent_workflow):
        """Submit with status=failure accepted without child completion check."""
        start_result = json.loads(
            _start(
                workflow="sv-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]

        # Agent reports failure -- should be accepted (not fabricating success)
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="child relay failed",
                status="failure",
            )
        )
        # Failure status should be accepted and advance the workflow (completed or halted)
        assert result["action"] in ("completed", "halted"), (
            f"Expected workflow to advance on failure status, got action={result['action']}"
        )

    def test_parallel_submit_rejected_without_lane_completion(self, parallel_workflow):
        """Submit to parent rejected when parallel lanes haven't completed."""
        start_result = json.loads(
            _start(
                workflow="pv-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive only first lane
        first_lane = lanes[0]
        child_action = json.loads(_next(run_id=first_lane["child_run_id"]))
        json.loads(
            _submit(
                run_id=first_lane["child_run_id"],
                exec_key=child_action["exec_key"],
                output="done",
            )
        )

        # Submit parent -- second lane not completed
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="fabricated",
            )
        )
        assert result["action"] == "error"
        assert "not completed" in result["message"] or "status" in result["message"]

    def test_parallel_submit_accepted_after_all_lanes(self, parallel_workflow):
        """Submit to parent succeeds after all parallel lanes complete."""
        start_result = json.loads(
            _start(
                workflow="pv-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive all lanes to completion
        for lane in lanes:
            child_action = json.loads(_next(run_id=lane["child_run_id"]))
            child_result = json.loads(
                _submit(
                    run_id=lane["child_run_id"],
                    exec_key=child_action["exec_key"],
                    output="done",
                )
            )
            assert child_result["action"] == "completed"

        # Submit parent succeeds
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="all done",
            )
        )
        assert result["action"] == "completed"

    def test_wrong_exec_key_not_masked_by_child_verification(self, subagent_workflow):
        """Wrong exec_key should return 'Wrong exec_key' error, not a child verification error."""
        start_result = json.loads(
            _start(
                workflow="sv-test",
                cwd=str(subagent_workflow),
                workflow_dirs=[str(subagent_workflow)],
            )
        )
        run_id = start_result["run_id"]

        # Submit with wrong exec_key while parent awaits relay
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key="bogus-key",
                output="fabricated",
            )
        )
        assert result["action"] == "error"
        assert "Wrong exec_key" in result["message"]


# ---------------------------------------------------------------------------
# Tests: SubWorkflow child run (inline + cascading resume)
# ---------------------------------------------------------------------------


class TestSubWorkflowChildRun:
    """Tests for inline SubWorkflow child run with cascading resume."""

    @pytest.fixture
    def inline_sub_workflow(self, tmp_path):
        return _make_inline_subworkflow(tmp_path)

    @pytest.fixture
    def shell_only_sub_workflow(self, tmp_path):
        return _make_shell_only_subworkflow(tmp_path)

    def test_subworkflow_inline_returns_child_action(self, inline_sub_workflow):
        """Inline SubWorkflow returns the child's prompt action with parent run_id (transparent)."""
        start_result = json.loads(
            _start(
                workflow="inline-sub",
                cwd=str(inline_sub_workflow),
                workflow_dirs=[str(inline_sub_workflow)],
            )
        )
        # "setup" shell auto-advances, then inline SubWorkflow should
        # return the child's prompt action (not a subagent action)
        assert start_result["action"] == "prompt"
        assert "inner-work" in start_result["exec_key"]
        # Shell log should contain the setup step
        assert "_shell_log" in start_result
        assert any(e["exec_key"] == "setup" for e in start_result["_shell_log"])
        # Transparent: run_id is parent's (no composite ">")
        assert ">" not in start_result["run_id"]

    def test_subworkflow_inline_submit_cascade(self, inline_sub_workflow):
        """Submit to parent (transparent child), child completes, cascade returns parent's next action."""
        start_result = json.loads(
            _start(
                workflow="inline-sub",
                cwd=str(inline_sub_workflow),
                workflow_dirs=[str(inline_sub_workflow)],
            )
        )
        parent_run_id = start_result["run_id"]
        child_exec_key = start_result["exec_key"]

        # Submit to parent (routes to child) -> child completes -> cascade to parent ->
        # parent's "finish" shell auto-advances -> completed
        result = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=child_exec_key,
                output="inner work done",
            )
        )
        assert result["action"] == "completed"
        # The "finish" shell should appear in shell_log
        assert "_shell_log" in result
        assert any(e["exec_key"] == "finish" for e in result["_shell_log"])

    def test_subworkflow_shell_only_invisible(self, shell_only_sub_workflow):
        """Shell-only inline child auto-completes; relay gets parent's next action."""
        start_result = json.loads(
            _start(
                workflow="shell-sub",
                cwd=str(shell_only_sub_workflow),
                workflow_dirs=[str(shell_only_sub_workflow)],
            )
        )
        # Shell-only child auto-completes and cascades to parent.
        # Parent's "after" shell also auto-advances -> completed
        assert start_result["action"] == "completed"
        # Shell log should include both the child's echo-step and parent's after step
        assert "_shell_log" in start_result
        exec_keys = [e["exec_key"] for e in start_result["_shell_log"]]
        assert "after" in exec_keys

    def test_subworkflow_child_checkpoint_structure(self, inline_sub_workflow):
        """Child checkpoint lives in children/ directory with composite run_id."""
        start_result = json.loads(
            _start(
                workflow="inline-sub",
                cwd=str(inline_sub_workflow),
                workflow_dirs=[str(inline_sub_workflow)],
            )
        )
        # Transparent: run_id is parent's, but child checkpoint still exists
        parent_run_id = start_result["run_id"]
        assert ">" not in parent_run_id

        # Get child run_id from parent state
        parent_state = _runs[parent_run_id]
        assert parent_state._active_inline_child_id
        child_run_id = parent_state._active_inline_child_id
        child_segment = child_run_id.split(">")[1]

        # Verify children/ directory structure
        parent_cp_dir = inline_sub_workflow / ".workflow-state" / parent_run_id
        assert parent_cp_dir.exists()
        children_dir = parent_cp_dir / "children"
        assert children_dir.exists()
        child_cp_dir = children_dir / child_segment
        assert child_cp_dir.exists()
        assert (child_cp_dir / "state.json").exists()

        # Verify checkpoint_dir_from_run_id resolves correctly
        resolved = _checkpoint_dir_from_run_id(
            Path(inline_sub_workflow),
            child_run_id,
        )
        assert resolved == child_cp_dir

    def test_checkpoint_version_mismatch_restarts(self, tmp_path):
        """Checkpoint with old version triggers fresh start with warning.

        Uses a simple (non-SubWorkflow) workflow so the warning is visible
        on the returned action dict (inline SubWorkflow returns child action,
        which would not carry parent-level warnings).
        """
        wf_dir = tmp_path / "simple-ver"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="simple-ver",
    description="Simple version test",
    blocks=[
        PromptStep(name="ask", prompt_type="confirm", message="Continue?"),
    ],
)
""")

        # Start normally to create a checkpoint
        start_result = json.loads(
            _start(
                workflow="simple-ver",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
            )
        )
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Clear in-memory state
        _runs.clear()

        # Tamper with checkpoint: set wrong checkpoint_version
        cp_file = tmp_path / ".workflow-state" / run_id / "state.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text())
        data["checkpoint_version"] = 999
        cp_file.write_text(json.dumps(data))

        # Resume with tampered checkpoint -> should fall back to fresh start
        result = json.loads(
            _start(
                workflow="simple-ver",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                resume=run_id,
            )
        )
        # Fresh start -> new run_id
        assert result["run_id"] != run_id
        # Should have a warning about the version mismatch
        assert "warnings" in result
        warnings = result["warnings"]
        assert any(
            "version mismatch" in w.lower() or "mismatch" in w.lower() for w in warnings
        )

    def test_composite_run_id_filesystem_layout(self, tmp_path):
        """Verify children/ path resolution for composite IDs at multiple levels."""
        cwd = tmp_path

        # Simple ID
        simple_dir = _checkpoint_dir_from_run_id(cwd, "aaa111bbb222")
        assert simple_dir == cwd / ".workflow-state" / "aaa111bbb222"

        # One-level composite
        composite_dir = _checkpoint_dir_from_run_id(cwd, "aaa111bbb222>ccc333ddd444")
        assert composite_dir == (
            cwd / ".workflow-state" / "aaa111bbb222" / "children" / "ccc333ddd444"
        )

        # Nested composite
        nested_dir = _checkpoint_dir_from_run_id(
            cwd, "aaa111bbb222>ccc333ddd444>eee555fff666"
        )
        assert nested_dir == (
            cwd
            / ".workflow-state"
            / "aaa111bbb222"
            / "children"
            / "ccc333ddd444"
            / "children"
            / "eee555fff666"
        )

        # Invalid segment raises ValueError (path traversal)
        with pytest.raises(ValueError, match="Invalid run_id segment"):
            _checkpoint_dir_from_run_id(cwd, "aaa111bbb222>../../../etc")
        with pytest.raises(ValueError, match="Invalid run_id segment"):
            _checkpoint_dir_from_run_id(cwd, "aaa111bbb222>")
        # Simple alphanumeric segments are OK (even non-hex, for backward compat)
        _checkpoint_dir_from_run_id(cwd, "test-run")

    def test_multistep_inline_subworkflow_cascade(self, tmp_path):
        """Multi-step inline SubWorkflow: each submit returns child's next action,
        final submit cascades to parent."""
        wf_dir = tmp_path / "multi-step"
        wf_dir.mkdir()
        helper_dir = tmp_path / "multi-helper"
        helper_dir.mkdir()
        prompts_dir = helper_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "step1.md").write_text("Do step 1")
        (prompts_dir / "step2.md").write_text("Do step 2")
        (helper_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="multi-helper",
    description="Helper with 2 LLM steps",
    blocks=[
        LLMStep(name="step1", prompt="step1.md"),
        LLMStep(name="step2", prompt="step2.md"),
    ],
)
""")
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="multi-step",
    description="Parent with inline multi-step SubWorkflow",
    blocks=[
        SubWorkflow(name="call-multi", workflow="multi-helper"),
        ShellStep(name="finish", command="echo done"),
    ],
)
""")

        # Start workflow
        start_result = json.loads(
            _start(
                workflow="multi-step",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
            )
        )
        # Should get child's first prompt (step1) with parent run_id (transparent)
        assert start_result["action"] == "prompt"
        assert "step 1" in Path(start_result["prompt_file"]).read_text().lower()
        parent_run_id = start_result["run_id"]
        assert ">" not in parent_run_id  # transparent: parent run_id

        # Submit step1 -> should get child's step2
        result2 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=start_result["exec_key"],
                output="step1 done",
            )
        )
        assert result2["action"] == "prompt"
        assert "step 2" in Path(result2["prompt_file"]).read_text().lower()
        assert result2["run_id"] == parent_run_id  # still parent

        # Submit step2 -> child completes -> cascade -> parent's shell "finish" auto-runs -> completed
        result3 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=result2["exec_key"],
                output="step2 done",
            )
        )
        # Should cascade to parent and complete (finish is a shell, auto-advanced)
        assert result3["action"] == "completed"
        assert result3["run_id"] == parent_run_id
        # Shell log should contain the "finish" step
        shell_log = result3.get("_shell_log", [])
        assert any("finish" in s.get("exec_key", "") for s in shell_log)

    def test_resume_with_completed_subworkflow_child(self, tmp_path):
        """Resume a workflow where one SubWorkflow child has completed.

        Regression test: completed SubWorkflow children had their scope
        (sub:X) popped on completion.  The checkpoint saved the shorter
        scope, so on resume the replay generated wrong exec_keys and
        tried to re-execute blocks, causing FileNotFoundError on prompts.
        """
        # Parent: SubWorkflow("first") -> LLMStep("second-prompt")
        # Helper: LLMStep("inner")
        helper_dir = tmp_path / "helper-resume"
        helper_dir.mkdir()
        helper_prompts = helper_dir / "prompts"
        helper_prompts.mkdir()
        (helper_prompts / "inner.md").write_text("Do inner work")
        (helper_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="helper-resume",
    description="Helper for resume test",
    blocks=[
        LLMStep(name="inner", prompt="inner.md"),
    ],
)
""")

        wf_dir = tmp_path / "resume-sub"
        wf_dir.mkdir()
        wf_prompts = wf_dir / "prompts"
        wf_prompts.mkdir()
        (wf_prompts / "second.md").write_text("Do second work")
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="resume-sub",
    description="Resume with completed SubWorkflow child",
    blocks=[
        SubWorkflow(name="first", workflow="helper-resume"),
        LLMStep(name="second-prompt", prompt="second.md"),
    ],
)
""")

        # Start workflow -> gets child's inner prompt (transparent: parent run_id)
        start_result = json.loads(
            _start(
                workflow="resume-sub",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
            )
        )
        assert start_result["action"] == "prompt"
        parent_run_id = start_result["run_id"]
        assert ">" not in parent_run_id  # transparent

        # Submit inner -> child completes -> cascade -> parent's "second-prompt"
        result2 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=start_result["exec_key"],
                output="inner done",
            )
        )
        assert result2["action"] == "prompt"
        assert "second" in Path(result2["prompt_file"]).read_text().lower()

        # Clear in-memory state to simulate MCP server restart
        _runs.clear()

        # Resume -- this is where the bug manifested: advance(completed_child)
        # would fail because the sub:first scope was lost
        resumed = json.loads(
            _start(
                workflow="resume-sub",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                resume=parent_run_id,
            )
        )
        assert resumed.get("action") != "error", (
            f"Resume failed: {resumed.get('message', resumed)}"
        )
        assert resumed["action"] == "prompt"
        assert "second" in Path(resumed["prompt_file"]).read_text().lower()
        assert resumed.get("_resumed") is True


# ---------------------------------------------------------------------------
# Tests: Transparent SubWorkflow
# ---------------------------------------------------------------------------


class TestTransparentSubWorkflow:
    """Transparent SubWorkflow: child LLM actions use parent run_id.

    The relay agent should never need to manage child run_ids. All actions
    from inline SubWorkflow children are proxied through the parent run_id.
    submit() to parent auto-routes to the active child. When child completes,
    parent auto-advances.
    """

    @pytest.fixture
    def transparent_sub(self, tmp_path):
        return _make_transparent_sub(tmp_path)

    @pytest.fixture
    def transparent_loop_sub(self, tmp_path):
        return _make_transparent_loop_sub(tmp_path)

    def test_child_action_uses_parent_run_id(self, transparent_sub):
        """Inline SubWorkflow child actions should carry parent run_id."""
        start_result = json.loads(
            _start(
                workflow="t-parent",
                cwd=str(transparent_sub),
                workflow_dirs=[str(transparent_sub)],
            )
        )
        # Should get child's first prompt
        assert start_result["action"] == "prompt"
        assert "work 1" in Path(start_result["prompt_file"]).read_text().lower()
        # Key assertion: run_id is parent's (no ">" composite)
        assert ">" not in start_result["run_id"]

    def test_submit_to_parent_routes_to_child(self, transparent_sub):
        """submit() with parent run_id routes to active child and returns next child action."""
        start_result = json.loads(
            _start(
                workflow="t-parent",
                cwd=str(transparent_sub),
                workflow_dirs=[str(transparent_sub)],
            )
        )
        parent_run_id = start_result["run_id"]
        assert ">" not in parent_run_id

        # Submit step1 to parent -> should get child's step2
        result2 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=start_result["exec_key"],
                output="step1 done",
            )
        )
        assert result2["action"] == "prompt"
        assert "work 2" in Path(result2["prompt_file"]).read_text().lower()
        assert result2["run_id"] == parent_run_id  # still parent

    def test_child_completion_cascades_to_parent(self, transparent_sub):
        """When child completes, parent auto-advances to next block."""
        start_result = json.loads(
            _start(
                workflow="t-parent",
                cwd=str(transparent_sub),
                workflow_dirs=[str(transparent_sub)],
            )
        )
        parent_run_id = start_result["run_id"]

        # Submit step1
        result2 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=start_result["exec_key"],
                output="step1 done",
            )
        )
        # Submit step2 -> child completes -> cascade -> parent's "finish" shell -> completed
        result3 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=result2["exec_key"],
                output="step2 done",
            )
        )
        assert result3["action"] == "completed"
        assert result3["run_id"] == parent_run_id
        # finish shell should be in shell_log
        shell_log = result3.get("_shell_log", [])
        assert any("finish" in s.get("exec_key", "") for s in shell_log)

    def test_next_returns_child_action_with_parent_id(self, transparent_sub):
        """next() on parent returns child's pending action with parent run_id."""
        start_result = json.loads(
            _start(
                workflow="t-parent",
                cwd=str(transparent_sub),
                workflow_dirs=[str(transparent_sub)],
            )
        )
        parent_run_id = start_result["run_id"]

        # next() should return same action with parent run_id
        next_result = json.loads(_next(run_id=parent_run_id))
        assert next_result["action"] == "prompt"
        assert next_result["run_id"] == parent_run_id
        assert next_result["exec_key"] == start_result["exec_key"]

    def test_loop_with_subworkflow_processes_all_items(self, transparent_loop_sub):
        """SubWorkflow inside LoopBlock: each iteration's child is transparent,
        loop continues after child completion."""
        start_result = json.loads(
            _start(
                workflow="loop-parent",
                cwd=str(transparent_loop_sub),
                workflow_dirs=[str(transparent_loop_sub)],
                variables={"items": ["step-A", "step-B"]},
            )
        )
        parent_run_id = start_result["run_id"]
        assert ">" not in parent_run_id

        # Iteration 0: child prompt for step-A
        assert start_result["action"] == "prompt"

        # Submit iteration 0 -> child completes -> cascade -> mark-done shell ->
        # loop advances -> iteration 1 child prompt
        result2 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=start_result["exec_key"],
                output="step-A implemented",
            )
        )
        # Should get iteration 1's child prompt (not completed)
        assert result2["action"] == "prompt"
        assert result2["run_id"] == parent_run_id

        # Submit iteration 1 -> child completes -> cascade -> mark-done ->
        # loop done -> finish shell -> completed
        result3 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=result2["exec_key"],
                output="step-B implemented",
            )
        )
        assert result3["action"] == "completed"
        assert result3["run_id"] == parent_run_id

    def test_child_results_accessible_in_parent(self, transparent_sub):
        """Child results are merged into parent context after completion."""
        start_result = json.loads(
            _start(
                workflow="t-parent",
                cwd=str(transparent_sub),
                workflow_dirs=[str(transparent_sub)],
            )
        )
        parent_run_id = start_result["run_id"]

        # Complete both child steps
        result2 = json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=start_result["exec_key"],
                output="step1 done",
            )
        )
        json.loads(
            _submit(
                run_id=parent_run_id,
                exec_key=result2["exec_key"],
                output="step2 done",
            )
        )

        # Check parent state has merged child results
        parent_state = _runs[parent_run_id]
        # Child results should be accessible via dotted notation
        assert any("call-helper" in k for k in parent_state.ctx.results_scoped)


# ---------------------------------------------------------------------------
# Tests: Parallel child resume metadata
# ---------------------------------------------------------------------------


class TestParallelChildResume:
    def test_parallel_lane_checkpoint_includes_resume_metadata(self, tmp_path):
        """Parallel lane checkpoints persist generic relay metadata."""
        workflow_root = _make_parallel_workflow(tmp_path, name="par-resume-meta")
        start_result = json.loads(
            _start(
                workflow="par-resume-meta",
                cwd=str(workflow_root),
                workflow_dirs=[str(workflow_root)],
            )
        )
        assert start_result["action"] == "parallel"
        lane0_id = start_result["lanes"][0]["child_run_id"]
        lane0_segment = lane0_id.split(">", 1)[1]

        cp_file = workflow_root / ".workflow-state" / start_result["run_id"] / "children" / lane0_segment / "state.json"
        data = json.loads(cp_file.read_text())
        assert data["parallel_block_name"] == "checks"
        assert data["lane_index"] == 0
        assert data["relay_parent_exec_key"] == start_result["exec_key"]
        assert data["relay_block_kind"] == "parallel_each"
        assert data["relay_block_name"] == "checks"

    def test_resume_parallel_reuses_lane_children_and_continues(self, tmp_path):
        """Resume reuses parallel lane children and preserves each lane's progress."""
        workflow_root = _make_parallel_workflow(
            tmp_path,
            name="par-resume-flow",
            two_steps=True,
            with_trailing_shell=False,
        )
        start_result = json.loads(
            _start(
                workflow="par-resume-flow",
                cwd=str(workflow_root),
                workflow_dirs=[str(workflow_root)],
            )
        )
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]
        assert start_result["action"] == "parallel"
        lanes = start_result["lanes"]
        lane0_id = lanes[0]["child_run_id"]
        lane1_id = lanes[1]["child_run_id"]

        child_action = json.loads(_next(run_id=lane0_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "par:checks[i=0]/check"

        child_action = json.loads(
            _submit(
                run_id=lane0_id,
                exec_key="par:checks[i=0]/check",
                output="done-x",
            )
        )
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "par:checks[i=0]/check2"

        _runs.clear()

        resumed = json.loads(
            _start(
                workflow="par-resume-flow",
                cwd=str(workflow_root),
                workflow_dirs=[str(workflow_root)],
                resume=run_id,
            )
        )
        assert resumed["action"] == "parallel"
        assert resumed["exec_key"] == parent_exec_key
        assert [lane["child_run_id"] for lane in resumed["lanes"]] == [lane0_id, lane1_id]
        assert resumed.get("_resumed") is True

        lane0_action = json.loads(_next(run_id=lane0_id))
        assert lane0_action["action"] == "prompt"
        assert lane0_action["exec_key"] == "par:checks[i=0]/check2"

        lane1_action = json.loads(_next(run_id=lane1_id))
        assert lane1_action["action"] == "prompt"
        assert lane1_action["exec_key"] == "par:checks[i=1]/check"


# ---------------------------------------------------------------------------
# Tests: Halt propagation from child runs
# ---------------------------------------------------------------------------


class TestHaltPropagation:
    @pytest.fixture
    def subagent_halt_workflow(self, tmp_path):
        """Workflow where child subagent group contains a step with halt."""
        wf_dir = tmp_path / "halt-sub"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "work.md").write_text("Do work")
        (prompts_dir / "check.md").write_text("Check results")
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="halt-sub",
    description="Subagent with halt",
    blocks=[
        ShellStep(name="setup", command="echo ready"),
        GroupBlock(
            name="worker",
            isolation="subagent",
            blocks=[
                LLMStep(name="work", prompt="work.md"),
                LLMStep(
                    name="check",
                    prompt="check.md",
                    halt="Verification failed in child",
                ),
            ],
        ),
        ShellStep(name="after", command="echo should-not-run"),
    ],
)
""")
        return tmp_path

    @pytest.fixture
    def parallel_halt_workflow(self, tmp_path):
        """Workflow with parallel lanes where one lane hits halt."""
        wf_dir = tmp_path / "halt-par"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "lane.md").write_text("Lane work")
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="halt-par",
    description="Parallel with halt in lane",
    blocks=[
        ShellStep(name="setup", command='echo \\'{\"items\": [\"a\", \"b\"]}\\'',
                  result_var="data"),
        ParallelEachBlock(
            name="lanes",
            parallel_for="variables.data.items",
            item_var="item",
            template=[
                LLMStep(name="process", prompt="lane.md"),
                LLMStep(
                    name="verify",
                    prompt="lane.md",
                    halt="Lane {{variables.item}} failed",
                ),
            ],
        ),
        ShellStep(name="after", command="echo should-not-run"),
    ],
)
""")
        return tmp_path

    def test_halt_propagates_from_subagent(self, subagent_halt_workflow):
        """When a child run halts, parent submit propagates the halt."""
        start_result = json.loads(
            _start(
                workflow="halt-sub",
                cwd=str(subagent_halt_workflow),
                workflow_dirs=[str(subagent_halt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        assert start_result["action"] == "subagent"
        child_run_id = start_result["child_run_id"]
        parent_exec_key = start_result["exec_key"]

        # Drive child: work -> submit -> check -> submit -> halted
        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "work"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="work",
                output="done",
            )
        )
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "check"

        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="check",
                output="checked",
            )
        )
        assert child_action["action"] == "halted"
        assert child_action["reason"] == "Verification failed in child"

        # Submit to parent -> halt propagates
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="child done",
            )
        )
        assert result["action"] == "halted"
        assert result["reason"] == "Verification failed in child"
        assert "check" in result["halted_at"]
        assert parent_exec_key in result["halted_at"]

        # Parent is halted -- further submits rejected
        error = json.loads(
            _submit(
                run_id=run_id,
                exec_key="after",
                output="x",
            )
        )
        assert error["action"] == "error"

    def test_halt_propagates_from_parallel_lane(self, parallel_halt_workflow):
        """When a parallel lane halts, parent submit propagates the halt."""
        start_result = json.loads(
            _start(
                workflow="halt-par",
                cwd=str(parallel_halt_workflow),
                workflow_dirs=[str(parallel_halt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        assert start_result["action"] == "parallel"
        lanes = start_result["lanes"]
        parent_exec_key = start_result["exec_key"]

        # Drive lane 0: process -> verify -> halted
        lane0_id = lanes[0]["child_run_id"]
        child_action = json.loads(_next(run_id=lane0_id))
        assert child_action["action"] == "prompt"
        child_action = json.loads(
            _submit(
                run_id=lane0_id,
                exec_key=child_action["exec_key"],
                output="processed",
            )
        )
        assert child_action["action"] == "prompt"
        child_action = json.loads(
            _submit(
                run_id=lane0_id,
                exec_key=child_action["exec_key"],
                output="verified",
            )
        )
        assert child_action["action"] == "halted"
        assert "Lane a failed" in child_action["reason"]

        # Drive lane 1 to completion
        lane1_id = lanes[1]["child_run_id"]
        child_action = json.loads(_next(run_id=lane1_id))
        child_action = json.loads(
            _submit(
                run_id=lane1_id,
                exec_key=child_action["exec_key"],
                output="processed",
            )
        )
        child_action = json.loads(
            _submit(
                run_id=lane1_id,
                exec_key=child_action["exec_key"],
                output="verified",
            )
        )
        # Lane 1 also halts (both have halt on verify)
        assert child_action["action"] == "halted"

        # Submit to parent -> halt propagates
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="lanes done",
            )
        )
        assert result["action"] == "halted"
        assert parent_exec_key in result["halted_at"]

    def test_halt_propagates_from_one_halted_lane(self, tmp_path):
        """When one parallel lane halts and the other completes, halt propagates."""
        wf_dir = tmp_path / "halt-mix"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "lane.md").write_text("Lane work")
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="halt-mix",
    description="Parallel with halt in one lane only",
    blocks=[
        ShellStep(name="setup", command='echo \\'{\"items\": [\"a\", \"b\"]}\\'',
                  result_var="data"),
        ParallelEachBlock(
            name="lanes",
            parallel_for="variables.data.items",
            item_var="item",
            template=[
                LLMStep(name="process", prompt="lane.md"),
                LLMStep(
                    name="verify",
                    prompt="lane.md",
                    halt="Lane {{variables.item}} failed",
                    condition=lambda ctx: ctx.variables.get("item") == "a",
                ),
            ],
        ),
    ],
)
""")
        start_result = json.loads(
            _start(
                workflow="halt-mix",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
            )
        )
        run_id = start_result["run_id"]
        assert start_result["action"] == "parallel"
        lanes = start_result["lanes"]
        parent_exec_key = start_result["exec_key"]

        # Lane 0 (item="a"): process -> verify (halt fires) -> halted
        lane0_id = lanes[0]["child_run_id"]
        child_action = json.loads(_next(run_id=lane0_id))
        child_action = json.loads(
            _submit(
                run_id=lane0_id,
                exec_key=child_action["exec_key"],
                output="processed",
            )
        )
        child_action = json.loads(
            _submit(
                run_id=lane0_id,
                exec_key=child_action["exec_key"],
                output="verified",
            )
        )
        assert child_action["action"] == "halted"

        # Lane 1 (item="b"): process -> verify skipped (condition false) -> completed
        lane1_id = lanes[1]["child_run_id"]
        child_action = json.loads(_next(run_id=lane1_id))
        child_action = json.loads(
            _submit(
                run_id=lane1_id,
                exec_key=child_action["exec_key"],
                output="processed",
            )
        )
        assert child_action["action"] == "completed"

        # Submit to parent -> halt propagates from lane 0
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="lanes done",
            )
        )
        assert result["action"] == "halted"
        assert "Lane a failed" in result["reason"]

    def test_no_propagation_on_failure_status(self, subagent_halt_workflow):
        """If relay submits with status=failure, halt is NOT propagated."""
        start_result = json.loads(
            _start(
                workflow="halt-sub",
                cwd=str(subagent_halt_workflow),
                workflow_dirs=[str(subagent_halt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]
        parent_exec_key = start_result["exec_key"]

        # Drive child to halt
        child_action = json.loads(_next(run_id=child_run_id))
        json.loads(_submit(run_id=child_run_id, exec_key="work", output="done"))
        child_action = json.loads(
            _submit(
                run_id=child_run_id,
                exec_key="check",
                output="checked",
            )
        )
        assert child_action["action"] == "halted"

        # Submit to parent with status=failure -> no halt propagation
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parent_exec_key,
                output="agent failed",
                status="failure",
            )
        )
        # Should advance past the subagent (not halt)
        # "after" shell auto-advances -> completed
        assert result["action"] == "completed"
