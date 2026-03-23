"""Tests for dry-run tree building and summary computation.

Tests that the single log-tree built during advance() correctly
nests container and leaf nodes, and that summary stats are accurate.
"""

import json

import pytest

from conftest import _state_ns, create_runner_ns

_runner_ns = create_runner_ns()
_start = _runner_ns["start"]
_runs = _runner_ns["_runs"]
_compute_dry_run_summary = _runner_ns["_compute_dry_run_summary"]
_find_node = _runner_ns["_find_node"]

# Protocol types
DryRunNode = _state_ns["DryRunNode"]


@pytest.fixture(autouse=True)
def _clean_runs():
    _runs.clear()
    yield
    _runs.clear()


class TestComputeDryRunSummary:
    def test_counts_leaf_nodes(self):
        """Should count only leaf nodes (no children)."""
        tree = [
            DryRunNode(exec_key="a", type="shell", name="a"),
            DryRunNode(exec_key="b", type="shell", name="b"),
        ]
        summary = _compute_dry_run_summary(tree)
        assert summary.step_count == 2
        assert summary.steps_by_type == {"shell": 2}

    def test_skips_container_nodes(self):
        """Container nodes (with children) should not be counted."""
        tree = [
            DryRunNode(
                exec_key="grp",
                type="group",
                name="grp",
                children=[
                    DryRunNode(exec_key="grp/a", type="shell", name="a"),
                    DryRunNode(exec_key="grp/b", type="llm", name="b"),
                ],
            ),
        ]
        summary = _compute_dry_run_summary(tree)
        assert summary.step_count == 2
        assert summary.steps_by_type == {"shell": 1, "llm": 1}

    def test_empty_tree(self):
        summary = _compute_dry_run_summary([])
        assert summary.step_count == 0
        assert summary.steps_by_type == {}


class TestFindNode:
    def test_finds_root(self):
        root = DryRunNode(exec_key="root", type="group", name="root")
        assert _find_node(root, "root") is root

    def test_finds_nested(self):
        child = DryRunNode(exec_key="grp/a", type="shell", name="a")
        root = DryRunNode(exec_key="grp", type="group", name="grp", children=[child])
        assert _find_node(root, "grp/a") is child

    def test_returns_none_for_missing(self):
        root = DryRunNode(exec_key="root", type="group", name="root")
        assert _find_node(root, "nonexistent") is None


class TestTreeStructure:
    def test_group_nests_children(self, tmp_path):
        """Group block should produce a container node with children."""
        wf_dir = tmp_path / "grp"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="grp",
    description="group test",
    blocks=[
        GroupBlock(name="setup", blocks=[
            ShellStep(name="a", command="echo a"),
            ShellStep(name="b", command="echo b"),
        ]),
        ShellStep(name="c", command="echo c"),
    ],
)
""")
        result = json.loads(
            _start(
                workflow="grp",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                dry_run=True,
            )
        )
        assert result["action"] == "dry_run_complete"
        assert len(result["tree"]) == 2
        grp = result["tree"][0]
        assert grp["type"] == "group"
        assert grp["name"] == "setup"
        assert len(grp["children"]) == 2
        assert grp["children"][0]["name"] == "a"
        assert grp["children"][1]["name"] == "b"
        assert result["tree"][1]["name"] == "c"

    def test_shell_detail(self, tmp_path):
        """Shell nodes should have command as detail."""
        wf_dir = tmp_path / "det"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="det",
    description="detail test",
    blocks=[ShellStep(name="build", command="npm run build")],
)
""")
        result = json.loads(
            _start(
                workflow="det",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                dry_run=True,
            )
        )
        assert result["tree"][0]["detail"] == "npm run build"

    def test_run_id_present(self, tmp_path):
        """DryRunCompleteAction should have a valid run_id."""
        wf_dir = tmp_path / "rid"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="rid",
    description="run id test",
    blocks=[ShellStep(name="x", command="echo x")],
)
""")
        result = json.loads(
            _start(
                workflow="rid",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                dry_run=True,
            )
        )
        assert result["run_id"]  # non-empty string

    def test_empty_workflow(self, tmp_path):
        """Empty workflow should produce empty tree and zero counts."""
        wf_dir = tmp_path / "empty"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="empty",
    description="empty test",
    blocks=[],
)
""")
        result = json.loads(
            _start(
                workflow="empty",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
                dry_run=True,
            )
        )
        assert result["tree"] == []
        assert result["summary"]["step_count"] == 0
        assert result["summary"]["steps_by_type"] == {}
