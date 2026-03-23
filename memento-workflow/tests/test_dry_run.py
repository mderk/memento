"""Basic dry-run smoke tests.

This file exists so `pytest memento-workflow/tests/test_dry_run.py`
works as specified in the protocol verification command.
Comprehensive tests are in test_dry_run_*.py files.
"""

import json

import pytest

from conftest import _types_ns, _state_ns, create_runner_ns

# Runner
_runner_ns = create_runner_ns()
_start = _runner_ns["start"]
_runs = _runner_ns["_runs"]

# Types
ShellStep = _types_ns["ShellStep"]
PromptStep = _types_ns["PromptStep"]
WorkflowDef = _types_ns["WorkflowDef"]

# Protocol
DryRunCompleteAction = _state_ns["DryRunCompleteAction"]
DryRunNode = _state_ns["DryRunNode"]
DryRunSummary = _state_ns["DryRunSummary"]
action_to_dict = _state_ns["action_to_dict"]


@pytest.fixture(autouse=True)
def _clean_runs():
    _runs.clear()
    yield
    _runs.clear()


class TestDryRunSmoke:
    def test_model_exists(self):
        assert DryRunCompleteAction is not None
        assert DryRunNode is not None
        assert DryRunSummary is not None

    def test_simple_workflow(self, tmp_path):
        wf_dir = tmp_path / "simple"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="simple",
    description="Two steps",
    blocks=[
        ShellStep(name="a", command="echo a"),
        ShellStep(name="b", command="echo b"),
    ],
)
""")
        result = json.loads(
            _start(
                workflow="simple",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                dry_run=True,
            )
        )
        assert result["action"] == "dry_run_complete"
        assert result["summary"]["step_count"] == 2
        assert len(result["tree"]) == 2

    def test_serialization(self):
        s = DryRunSummary(
            step_count=1,
            steps_by_type={"shell": 1},
        )
        a = DryRunCompleteAction(run_id="r1", tree=[], summary=s)
        d = action_to_dict(a)
        assert d["action"] == "dry_run_complete"

    def test_no_side_effects(self, tmp_path):
        wf_dir = tmp_path / "noop"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="noop",
    description="One step",
    blocks=[ShellStep(name="x", command="echo x")],
)
""")
        json.loads(
            _start(
                workflow="noop",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                dry_run=True,
            )
        )
        assert not (tmp_path / ".workflow-state").exists()
