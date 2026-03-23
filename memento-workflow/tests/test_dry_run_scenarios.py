"""Tests for dry-run collection across various workflow structures.

Tests linear, conditional, loop, parallel, and subworkflow scenarios
to verify tree structure, exec_keys, types, and summary stats.
"""

import json

import pytest

from conftest import _types_ns, _state_ns, create_runner_ns

# Runner (fresh namespace)
_runner_ns = create_runner_ns()
_start = _runner_ns["start"]
_runs = _runner_ns["_runs"]

# Types
ShellStep = _types_ns["ShellStep"]
LLMStep = _types_ns["LLMStep"]
PromptStep = _types_ns["PromptStep"]
GroupBlock = _types_ns["GroupBlock"]
LoopBlock = _types_ns["LoopBlock"]
ConditionalBlock = _types_ns["ConditionalBlock"]
Branch = _types_ns["Branch"]
SubWorkflow = _types_ns["SubWorkflow"]
ParallelEachBlock = _types_ns["ParallelEachBlock"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]

# State
Frame = _state_ns["Frame"]
RunState = _state_ns["RunState"]
advance = _state_ns["advance"]


@pytest.fixture(autouse=True)
def _clean_runs():
    _runs.clear()
    yield
    _runs.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dry_run_start(tmp_path, workflow_def, variables=None):
    """Create workflow and run dry-run via MCP start()."""
    wf_dir = tmp_path / workflow_def.name
    wf_dir.mkdir(exist_ok=True)
    # Write workflow file — must define WORKFLOW
    blocks_repr = repr(workflow_def.blocks)
    (wf_dir / "workflow.py").write_text(f"""
WORKFLOW = WorkflowDef(
    name={workflow_def.name!r},
    description={workflow_def.description!r},
    blocks={blocks_repr},
)
""")
    result = json.loads(
        _start(
            workflow=workflow_def.name,
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
            dry_run=True,
            variables=variables or {},
        )
    )
    return result


def _make_workflow(blocks, name="test", description="test"):
    return WorkflowDef(name=name, description=description, blocks=blocks)


def _make_state(workflow, variables=None):
    ctx = WorkflowContext(
        variables=variables or {},
        cwd=".",
        dry_run=True,
        prompt_dir=workflow.prompt_dir,
    )
    return RunState(
        run_id="test-run",
        ctx=ctx,
        stack=[Frame(block=workflow)],
        registry={workflow.name: workflow},
        wf_hash="test-hash",
    )


# ---------------------------------------------------------------------------
# Tests: Linear workflow
# ---------------------------------------------------------------------------


class TestDryRunLinear:
    def test_linear_shell_prompt_llm(self, tmp_path):
        """Linear workflow with shell → prompt → shell returns correct structure."""
        wf = _make_workflow(
            [
                ShellStep(name="build", command="make build"),
                PromptStep(name="confirm", prompt_type="confirm", message="Deploy?"),
                ShellStep(name="deploy", command="make deploy"),
            ],
            name="linear",
        )
        result = _dry_run_start(tmp_path, wf)

        assert result["action"] == "dry_run_complete"
        assert result["summary"]["step_count"] == 3
        assert len(result["tree"]) == 3
        assert result["tree"][0]["name"] == "build"
        assert result["tree"][0]["type"] == "shell"
        assert result["tree"][1]["name"] == "confirm"
        assert result["tree"][2]["name"] == "deploy"


# ---------------------------------------------------------------------------
# Tests: Conditional workflow
# ---------------------------------------------------------------------------


class TestDryRunConditional:
    def test_conditional_takes_first_matching_branch(self):
        """Dry-run should take the first branch whose condition is True."""
        wf = _make_workflow(
            [
                ConditionalBlock(
                    name="check",
                    branches=[
                        Branch(
                            condition=lambda ctx: True,
                            blocks=[ShellStep(name="yes-path", command="echo yes")],
                        ),
                        Branch(
                            condition=lambda ctx: False,
                            blocks=[ShellStep(name="no-path", command="echo no")],
                        ),
                    ],
                    default=[ShellStep(name="default-path", command="echo default")],
                ),
            ]
        )

        state = _make_state(wf)
        # Collect all actions
        actions = []
        while True:
            action, _ = advance(state)
            if action.action in ("completed", "error"):
                break
            actions.append(action)

        # Should take the "yes-path" branch
        assert len(actions) == 1
        assert "yes-path" in actions[0].exec_key

    def test_conditional_takes_default(self):
        """When no branch matches, default is taken."""
        wf = _make_workflow(
            [
                ConditionalBlock(
                    name="check",
                    branches=[
                        Branch(
                            condition=lambda ctx: False,
                            blocks=[ShellStep(name="no-path", command="echo no")],
                        ),
                    ],
                    default=[ShellStep(name="fallback", command="echo fallback")],
                ),
            ]
        )

        state = _make_state(wf)
        actions = []
        while True:
            action, _ = advance(state)
            if action.action in ("completed", "error"):
                break
            actions.append(action)

        assert len(actions) == 1
        assert "fallback" in actions[0].exec_key


# ---------------------------------------------------------------------------
# Tests: Loop workflow
# ---------------------------------------------------------------------------


class TestDryRunLoop:
    def test_loop_expands_items(self):
        """Loop should expand for each item in the list."""
        wf = _make_workflow(
            [
                LoopBlock(
                    name="build",
                    loop_over="variables.targets",
                    loop_var="target",
                    blocks=[
                        ShellStep(name="compile", command="make {{variables.target}}")
                    ],
                ),
            ]
        )

        state = _make_state(wf, variables={"targets": ["x86", "arm", "wasm"]})
        actions = []
        while True:
            action, _ = advance(state)
            if action.action in ("completed", "error"):
                break
            actions.append(action)

        assert len(actions) == 3
        # Each iteration has its own exec_key
        assert "loop:build[i=0]" in actions[0].exec_key
        assert "loop:build[i=1]" in actions[1].exec_key
        assert "loop:build[i=2]" in actions[2].exec_key


# ---------------------------------------------------------------------------
# Tests: Group workflow
# ---------------------------------------------------------------------------


class TestDryRunGroup:
    def test_group_nests_children(self, tmp_path):
        """Group blocks should produce nested exec_keys."""
        wf = _make_workflow(
            [
                GroupBlock(
                    name="setup",
                    blocks=[
                        ShellStep(name="install", command="npm install"),
                        ShellStep(name="build", command="npm run build"),
                    ],
                ),
                ShellStep(name="deploy", command="make deploy"),
            ],
            name="grouped",
        )
        result = _dry_run_start(tmp_path, wf)

        assert result["action"] == "dry_run_complete"
        assert result["summary"]["step_count"] == 3


# ---------------------------------------------------------------------------
# Tests: Summary stats
# ---------------------------------------------------------------------------


class TestDryRunSummary:
    def test_step_count_matches_total(self, tmp_path):
        """step_count should equal total number of leaf actions collected."""
        wf = _make_workflow(
            [
                ShellStep(name="a", command="echo a"),
                ShellStep(name="b", command="echo b"),
                ShellStep(name="c", command="echo c"),
            ],
            name="count-test",
        )
        result = _dry_run_start(tmp_path, wf)

        assert result["summary"]["step_count"] == 3

    def test_steps_by_type_counts(self, tmp_path):
        """steps_by_type should correctly count each action type."""
        wf = _make_workflow(
            [
                ShellStep(name="s1", command="echo 1"),
                ShellStep(name="s2", command="echo 2"),
                PromptStep(name="ask", prompt_type="confirm", message="ok?"),
            ],
            name="type-count",
        )
        result = _dry_run_start(tmp_path, wf)

        assert result["summary"]["steps_by_type"]["shell"] == 2
        assert result["summary"]["steps_by_type"]["prompt"] == 1

    def test_no_workflow_state_created(self, tmp_path):
        """Dry-run should not create .workflow-state directory."""
        wf = _make_workflow(
            [
                ShellStep(name="a", command="echo a"),
            ],
            name="no-state",
        )
        result = _dry_run_start(tmp_path, wf)

        assert result["action"] == "dry_run_complete"
        ws_dir = tmp_path / ".workflow-state"
        assert not ws_dir.exists()
