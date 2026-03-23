"""Integration tests for dry-run on real workflows via MCP start().

Tests that start(workflow=..., dry_run=True) returns a valid
DryRunCompleteAction for bundled and project workflows.
"""

import json
from pathlib import Path

import pytest

from conftest import create_runner_ns

# Fresh runner namespace
_runner_ns = create_runner_ns()
_start = _runner_ns["start"]
_runs = _runner_ns["_runs"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Project-level workflows may not exist in worktrees
_WORKFLOWS_DIR = PROJECT_ROOT / ".workflows"
_HAS_PROJECT_WORKFLOWS = (
    _WORKFLOWS_DIR.is_dir() and (_WORKFLOWS_DIR / "commit").is_dir()
)


@pytest.fixture(autouse=True)
def _clean_runs():
    _runs.clear()
    yield
    _runs.clear()


class TestDryRunTestWorkflow:
    """Dry-run the bundled test-workflow (exercises all 9 block types)."""

    def test_returns_dry_run_complete(self):
        """test-workflow dry-run returns a dry_run_complete action."""
        result = json.loads(
            _start(
                workflow="test-workflow",
                cwd=str(PROJECT_ROOT),
                dry_run=True,
            )
        )
        assert result["action"] == "dry_run_complete"
        assert result["summary"]["step_count"] > 0
        assert len(result["tree"]) > 0

    def test_summary_has_multiple_types(self):
        """test-workflow covers multiple block types."""
        result = json.loads(
            _start(
                workflow="test-workflow",
                cwd=str(PROJECT_ROOT),
                dry_run=True,
            )
        )
        # Should have at least shell and prompt types
        types = result["summary"]["steps_by_type"]
        assert len(types) >= 2


@pytest.mark.skipif(not _HAS_PROJECT_WORKFLOWS, reason=".workflows/ not available")
class TestDryRunCommitWorkflow:
    """Dry-run the commit workflow (project-level, requires workdir variable)."""

    def test_returns_dry_run_complete(self, tmp_path):
        """commit workflow dry-run returns dry_run_complete."""
        result = json.loads(
            _start(
                workflow="commit",
                cwd=str(PROJECT_ROOT),
                workflow_dirs=[str(_WORKFLOWS_DIR)],
                dry_run=True,
                variables={"workdir": str(tmp_path)},
            )
        )
        assert result["action"] == "dry_run_complete"
        assert result["summary"]["step_count"] > 0

    def test_tree_is_not_empty(self, tmp_path):
        """commit workflow should produce a non-empty tree."""
        result = json.loads(
            _start(
                workflow="commit",
                cwd=str(PROJECT_ROOT),
                workflow_dirs=[str(_WORKFLOWS_DIR)],
                dry_run=True,
                variables={"workdir": str(tmp_path)},
            )
        )
        assert len(result["tree"]) > 0


@pytest.mark.skipif(not _HAS_PROJECT_WORKFLOWS, reason=".workflows/ not available")
class TestDryRunCodeReviewWorkflow:
    """Dry-run the code-review workflow (should include parallel node)."""

    def test_returns_dry_run_complete(self):
        """code-review dry-run returns dry_run_complete."""
        result = json.loads(
            _start(
                workflow="code-review",
                cwd=str(PROJECT_ROOT),
                workflow_dirs=[str(_WORKFLOWS_DIR)],
                dry_run=True,
                variables={"workdir": "."},
            )
        )
        assert result["action"] == "dry_run_complete"
        assert result["summary"]["step_count"] > 0
