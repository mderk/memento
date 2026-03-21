"""Tests for _evict_terminal_runs parent-reference safety (protocol 0004, step 02).

Verifies that terminal child runs referenced by a parent's child_run_ids
are NOT evicted, while unreferenced terminal runs ARE evicted.
"""

import pytest

from conftest import create_runner_ns, _types_ns

_ns = create_runner_ns()
_runs = _ns["_runs"]
_evict_terminal_runs = _ns["_evict_terminal_runs"]
RunState = _ns["RunState"]
Frame = _ns["Frame"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]


def _make_run(run_id, status="completed", child_run_ids=None):
    """Create a minimal RunState for eviction testing."""
    wf = WorkflowDef(name="test", description="test")
    ctx = WorkflowContext(cwd=".")
    state = RunState(
        run_id=run_id,
        ctx=ctx,
        stack=[Frame(block=wf)],
        registry={"test": wf},
        status=status,
        child_run_ids=child_run_ids or [],
    )
    return state


@pytest.fixture(autouse=True)
def _clean():
    _runs.clear()
    yield
    _runs.clear()


class TestEvictionSafety:
    def test_unreferenced_terminal_run_evicted(self):
        """A completed run with no parent references should be evicted."""
        _runs["orphan"] = _make_run("orphan", status="completed")
        _evict_terminal_runs()
        assert "orphan" not in _runs

    def test_referenced_child_not_evicted(self):
        """A completed child run referenced by parent's child_run_ids must NOT be evicted."""
        _runs["parent"] = _make_run("parent", status="running", child_run_ids=["parent>child"])
        _runs["parent>child"] = _make_run("parent>child", status="completed")

        _evict_terminal_runs()
        assert "parent>child" in _runs, (
            "Child run was evicted despite parent referencing it in child_run_ids"
        )

    def test_parent_with_children_not_evicted(self):
        """A completed parent with child_run_ids should not be evicted (existing behavior)."""
        _runs["parent"] = _make_run("parent", status="completed", child_run_ids=["parent>child"])
        _runs["parent>child"] = _make_run("parent>child", status="running")

        _evict_terminal_runs()
        assert "parent" in _runs

    def test_unreferenced_terminal_child_evicted(self):
        """A completed child whose parent already completed and was evicted — should be evictable."""
        # Parent already gone, child is terminal with no references
        _runs["child"] = _make_run("child", status="completed")
        _evict_terminal_runs()
        assert "child" not in _runs

    def test_running_run_not_evicted(self):
        """Running runs are never evicted."""
        _runs["active"] = _make_run("active", status="running")
        _evict_terminal_runs()
        assert "active" in _runs
