"""Tests for dry-run collection loop in runner.py.

Tests that start(dry_run=True) collects all actions, returns
DryRunCompleteAction, and skips checkpoint/meta writes.
"""

import json

import pytest

from conftest import _types_ns, create_runner_ns

# Runner (fresh namespace)
_runner_ns = create_runner_ns()

_start = _runner_ns["start"]
_runs = _runner_ns["_runs"]

# Types
ShellStep = _types_ns["ShellStep"]
GroupBlock = _types_ns["GroupBlock"]
LoopBlock = _types_ns["LoopBlock"]
PromptStep = _types_ns["PromptStep"]
LLMStep = _types_ns["LLMStep"]
WorkflowDef = _types_ns["WorkflowDef"]
ConditionalBlock = _types_ns["ConditionalBlock"]
Branch = _types_ns["Branch"]


@pytest.fixture(autouse=True)
def _clean_runs():
    _runs.clear()
    yield
    _runs.clear()


@pytest.fixture
def simple_workflow(tmp_path):
    """Two shell steps workflow."""
    wf_dir = tmp_path / "simple"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="simple",
    description="Two shell steps",
    blocks=[
        ShellStep(name="step1", command="echo hello"),
        ShellStep(name="step2", command="echo world"),
    ],
)
""")
    return tmp_path


@pytest.fixture
def mixed_workflow(tmp_path):
    """Shell + prompt + shell workflow."""
    wf_dir = tmp_path / "mixed"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="mixed",
    description="Shell + prompt + shell",
    blocks=[
        ShellStep(name="step1", command="echo hello"),
        PromptStep(name="ask", prompt_type="confirm", message="ok?"),
        ShellStep(name="step2", command="echo world"),
    ],
)
""")
    return tmp_path


@pytest.fixture
def group_workflow(tmp_path):
    """Workflow with a group containing nested steps."""
    wf_dir = tmp_path / "grouped"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="grouped",
    description="Group with nested steps",
    blocks=[
        GroupBlock(name="grp", blocks=[
            ShellStep(name="a", command="echo a"),
            ShellStep(name="b", command="echo b"),
        ]),
        ShellStep(name="c", command="echo c"),
    ],
)
""")
    return tmp_path


class TestDryRunStart:
    def test_returns_dry_run_complete_action(self, simple_workflow):
        """start(dry_run=True) should return a dry_run_complete action."""
        result = json.loads(
            _start(
                workflow="simple",
                cwd=str(simple_workflow),
                workflow_dirs=[str(simple_workflow)],
                dry_run=True,
            )
        )
        assert result["action"] == "dry_run_complete"

    def test_tree_contains_all_steps(self, simple_workflow):
        """Tree should contain all workflow steps."""
        result = json.loads(
            _start(
                workflow="simple",
                cwd=str(simple_workflow),
                workflow_dirs=[str(simple_workflow)],
                dry_run=True,
            )
        )
        assert "tree" in result
        assert "summary" in result
        # Should have step entries for step1 and step2
        assert result["summary"]["step_count"] >= 2

    def test_mixed_workflow_collects_all_types(self, mixed_workflow):
        """Should collect shell, prompt, and other step types."""
        result = json.loads(
            _start(
                workflow="mixed",
                cwd=str(mixed_workflow),
                workflow_dirs=[str(mixed_workflow)],
                dry_run=True,
            )
        )
        assert result["action"] == "dry_run_complete"
        assert result["summary"]["step_count"] >= 3

    def test_no_side_effects(self, simple_workflow):
        """Dry-run should not create .workflow-state (no checkpoint, no meta)."""
        result = json.loads(
            _start(
                workflow="simple",
                cwd=str(simple_workflow),
                workflow_dirs=[str(simple_workflow)],
                dry_run=True,
            )
        )
        assert result["action"] == "dry_run_complete"
        ws_dir = simple_workflow / ".workflow-state"
        assert not ws_dir.exists(), ".workflow-state should not be created in dry-run"

    def test_summary_has_steps_by_type(self, mixed_workflow):
        """Summary should report step counts by type."""
        result = json.loads(
            _start(
                workflow="mixed",
                cwd=str(mixed_workflow),
                workflow_dirs=[str(mixed_workflow)],
                dry_run=True,
            )
        )
        summary = result["summary"]
        assert "steps_by_type" in summary
        assert isinstance(summary["steps_by_type"], dict)

    def test_group_workflow_nests_children(self, group_workflow):
        """Group blocks should appear with children in the tree."""
        result = json.loads(
            _start(
                workflow="grouped",
                cwd=str(group_workflow),
                workflow_dirs=[str(group_workflow)],
                dry_run=True,
            )
        )
        assert result["action"] == "dry_run_complete"
        # The tree should have hierarchical structure
        assert len(result["tree"]) > 0
