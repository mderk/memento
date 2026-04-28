"""Integration tests for workflow engine MCP tools.

Tests tool functions directly (no transport) — start, submit, next, cancel,
list_workflows, status.

Shell steps are executed internally by the MCP server. They never appear as
relay actions — only as _shell_log entries on the next non-shell action.
"""

import json
from pathlib import Path

import pytest

from conftest import _types_ns, create_runner_ns

# Runner (fresh namespace — tests mutate globals)
_runner_ns = create_runner_ns()

# Extract tool functions
_start = _runner_ns["start"]
_resume = _runner_ns["resume"]
_submit = _runner_ns["submit"]
_next = _runner_ns["next"]
_cancel = _runner_ns["cancel"]
_list_workflows = _runner_ns["list_workflows"]
_status = _runner_ns["status"]
_runs = _runner_ns["_runs"]

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


@pytest.fixture
def shell_only_workflow(tmp_path):
    """Create a shell-only 2-step workflow (completes on start)."""
    wf_dir = tmp_path / "shell-only"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="shell-only",
    description="Two shell steps",
    blocks=[
        ShellStep(name="step1", command="echo hello"),
        ShellStep(name="step2", command="echo world"),
    ],
)
""")
    return tmp_path


@pytest.fixture
def ask_user_workflow(tmp_path):
    """Create a workflow with an ask_user step."""
    wf_dir = tmp_path / "ask-test"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="ask-test",
    description="Workflow with ask_user",
    blocks=[
        PromptStep(name="confirm", prompt_type="confirm",
                   message="Continue?", options=["yes", "no"],
                   result_var="answer"),
        ShellStep(name="echo", command="echo done"),
    ],
)
""")
    return tmp_path


@pytest.fixture
def mixed_workflow(tmp_path):
    """Create a workflow: shell → ask_user → shell (for relay testing)."""
    wf_dir = tmp_path / "mixed-test"
    wf_dir.mkdir()
    (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="mixed-test",
    description="Shell + ask_user + shell",
    blocks=[
        ShellStep(
            name="detect",
            command='echo \'{"count": 3}\'',
            result_var="detection",
        ),
        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Found {{variables.detection.count}} items. Proceed?",
            result_var="answer",
        ),
        ShellStep(name="finish", command="echo done"),
    ],
)
""")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: start — shell auto-advance
# ---------------------------------------------------------------------------


class TestStart:
    def test_shell_only_workflow_completes_on_start(self, shell_only_workflow):
        """Shell-only workflows complete immediately — auto-advanced internally."""
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        assert result["action"] == "completed"
        assert "run_id" in result
        # _shell_log carries internally-executed shell steps
        assert "_shell_log" in result
        log = result["_shell_log"]
        assert len(log) == 2
        assert log[0]["exec_key"] == "step1"
        assert log[0]["status"] == "success"
        assert "artifact" in log[0]  # output stored in artifact file
        run_id = result["run_id"]
        art_base = shell_only_workflow / ".workflow-state" / run_id / "artifacts"
        assert "hello" in (art_base / log[0]["artifact"] / "output.txt").read_text()
        assert log[1]["exec_key"] == "step2"
        assert log[1]["status"] == "success"
        assert "world" in (art_base / log[1]["artifact"] / "output.txt").read_text()

    def test_start_stops_at_ask_user(self, ask_user_workflow):
        """Start stops at first non-shell action (ask_user)."""
        result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "confirm"
        assert result["message"] == "Continue?"

    def test_start_auto_advances_shell_before_ask_user(self, mixed_workflow):
        """Shell steps before ask_user are auto-advanced, visible in _shell_log."""
        result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
        ))
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "confirm"
        # Shell step "detect" was auto-advanced — visible in _shell_log
        assert "_shell_log" in result
        assert len(result["_shell_log"]) == 1
        assert result["_shell_log"][0]["exec_key"] == "detect"
        assert result["_shell_log"][0]["status"] == "success"
        # Template substitution should have worked for message
        assert "3" in result["message"]

    def test_start_unknown_workflow(self, shell_only_workflow):
        result = json.loads(_start(
            workflow="nonexistent",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        assert result["action"] == "error"
        assert "not found" in result["message"]

    def test_start_creates_run_in_memory(self, shell_only_workflow):
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        run_id = result["run_id"]
        assert run_id in _runs


# ---------------------------------------------------------------------------
# Tests: submit — auto-advances shell after non-shell action
# ---------------------------------------------------------------------------


class TestSubmit:
    def test_submit_advances_past_trailing_shells(self, mixed_workflow):
        """After submitting ask_user, trailing shells auto-advance to completed."""
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Submit user's answer → shell auto-advances → completed
        result = json.loads(_submit(
            run_id=run_id, exec_key="confirm", output="yes",
        ))
        assert result["action"] == "completed"
        # The trailing shell was auto-advanced
        assert "_shell_log" in result
        assert result["_shell_log"][0]["exec_key"] == "finish"

    def test_submit_wrong_exec_key(self, ask_user_workflow):
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]

        result = json.loads(_submit(run_id=run_id, exec_key="wrong", output="x"))
        assert result["action"] == "error"
        assert result["expected_exec_key"] == "confirm"

    def test_submit_unknown_run_id(self):
        result = json.loads(_submit(run_id="nonexistent", exec_key="x"))
        assert result["action"] == "error"
        assert "Unknown run_id" in result["message"]

    def test_submit_cancelled_cleans_up(self, ask_user_workflow):
        """submit(status='cancelled') cancels workflow and removes run from memory."""
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]
        assert run_id in _runs

        result = json.loads(_submit(
            run_id=run_id, exec_key="confirm", status="cancelled",
        ))
        assert result["action"] == "cancelled"
        # Run should be cleaned up
        assert run_id not in _runs
        # Checkpoint should be cleaned up
        cp_file = ask_user_workflow / ".workflow-state" / run_id / "state.json"
        assert not cp_file.exists()

    def test_submit_strict_invalid_returns_retry_confirm(self, ask_user_workflow):
        """Invalid answer to strict PromptStep returns retry confirm via MCP."""
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Submit invalid answer
        result = json.loads(_submit(
            run_id=run_id, exec_key="confirm", output="garbage",
        ))
        assert result["action"] == "ask_user"
        assert result["_retry_confirm"] is True

        # Run still exists (not cancelled)
        assert run_id in _runs

    def test_display_field_on_actions(self, ask_user_workflow):
        """_display field present on start and submit responses."""
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        assert "_display" in start_result

        run_id = start_result["run_id"]
        result = json.loads(_submit(
            run_id=run_id, exec_key="confirm", output="yes",
        ))
        assert "_display" in result


# ---------------------------------------------------------------------------
# Tests: next
# ---------------------------------------------------------------------------


class TestNext:
    def test_next_returns_pending_action(self, ask_user_workflow):
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]

        result = json.loads(_next(run_id=run_id))
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "confirm"

    def test_next_unknown_run_id(self):
        result = json.loads(_next(run_id="nonexistent"))
        assert result["action"] == "error"


# ---------------------------------------------------------------------------
# Tests: cancel
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_removes_run(self, ask_user_workflow):
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]

        result = json.loads(_cancel(run_id=run_id))
        assert result["action"] == "cancelled"
        assert run_id not in _runs

    def test_cancel_unknown_run_id(self):
        result = json.loads(_cancel(run_id="nonexistent"))
        assert result["action"] == "error"


# ---------------------------------------------------------------------------
# Tests: list_workflows
# ---------------------------------------------------------------------------


class TestListWorkflows:
    def test_list_discovers_workflows(self, shell_only_workflow):
        result = json.loads(_list_workflows(
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        assert "workflows" in result
        names = [w["name"] for w in result["workflows"]]
        assert "shell-only" in names

    def test_list_discovers_plugin_workflows(self):
        result = json.loads(_list_workflows())
        assert "workflows" in result
        # Should find at least the test-workflow from skills/
        names = [w["name"] for w in result["workflows"]]
        assert len(names) > 0


# ---------------------------------------------------------------------------
# Tests: resume
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_without_workflow_name(self, ask_user_workflow):
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        _runs.clear()

        resumed = json.loads(_resume(
            run_id=run_id,
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        assert resumed["action"] == "ask_user"
        assert resumed["run_id"] == run_id
        assert resumed["exec_key"] == "confirm"
        assert resumed.get("_resumed") is True

    def test_resume_unknown_checkpoint(self, ask_user_workflow):
        result = json.loads(_resume(
            run_id="aaaaaaaaaaaa",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        assert result["action"] == "error"
        assert "resume failed" in result["message"] or "Could not determine workflow" in result["message"]


# ---------------------------------------------------------------------------
# Tests: status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_shows_waiting(self, ask_user_workflow):
        """Status shows waiting when blocked on ask_user."""
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]

        result = json.loads(_status(run_id=run_id))
        assert result["status"] == "waiting"
        assert result["pending_exec_key"] == "confirm"

    def test_status_unknown_run_id(self):
        result = json.loads(_status(run_id="nonexistent"))
        assert result["action"] == "error"


# ---------------------------------------------------------------------------
# Tests: Full relay loop
# ---------------------------------------------------------------------------


class TestRelayLoop:
    def test_shell_only_completes_immediately(self, shell_only_workflow):
        """Shell-only workflow completes on start() — no submit needed."""
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        assert result["action"] == "completed"
        assert len(result["_shell_log"]) == 2

    def test_relay_with_ask_user(self, ask_user_workflow):
        """Relay loop: start → ask_user → submit → completed (shell auto-advanced)."""
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"
        assert start_result["message"] == "Continue?"

        # Submit user's answer → trailing shell auto-advances → completed
        final = json.loads(_submit(
            run_id=run_id, exec_key="confirm", output="yes",
        ))
        assert final["action"] == "completed"
        # "echo" shell step was auto-advanced
        assert "_shell_log" in final
        assert final["_shell_log"][0]["exec_key"] == "echo"

    def test_relay_mixed_workflow(self, mixed_workflow):
        """Full relay: shell(auto) → ask_user → shell(auto) → completed."""
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"
        # "detect" shell was auto-advanced
        assert start_result["_shell_log"][0]["exec_key"] == "detect"

        # Submit confirm → "finish" shell auto-advances → completed
        final = json.loads(_submit(
            run_id=run_id, exec_key="confirm", output="yes",
        ))
        assert final["action"] == "completed"
        assert final["_shell_log"][0]["exec_key"] == "finish"


# ---------------------------------------------------------------------------
# Tests: Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_duplicate_submit_returns_same_action(self, ask_user_workflow):
        """Submitting same exec_key twice returns same action type (no double-recording)."""
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]

        result1 = json.loads(_submit(
            run_id=run_id, exec_key="confirm", output="yes",
        ))
        result2 = json.loads(_submit(
            run_id=run_id, exec_key="confirm", output="yes",
        ))
        # Both should return completed (not an error)
        assert result1["action"] == "completed"
        assert result2["action"] == "completed"

    def test_duplicate_submit_no_shell_action(self, tmp_path):
        """Idempotent submit when next action has no auto-advance returns identical results."""
        wf_dir = tmp_path / "two-ask"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="two-ask",
    description="Two ask_user steps",
    blocks=[
        PromptStep(name="q1", prompt_type="confirm", message="First?", result_var="a1"),
        PromptStep(name="q2", prompt_type="confirm", message="Second?", result_var="a2"),
    ],
)
""")
        start_result = json.loads(_start(
            workflow="two-ask",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        run_id = start_result["run_id"]

        result1 = json.loads(_submit(
            run_id=run_id, exec_key="q1", output="yes",
        ))
        result2 = json.loads(_submit(
            run_id=run_id, exec_key="q1", output="yes",
        ))
        # Both should return the exact same ask_user action for q2
        assert result1 == result2
        assert result1["action"] == "ask_user"
        assert result1["exec_key"] == "q2"


# ---------------------------------------------------------------------------
# Tests: Shell _shell_log details
# ---------------------------------------------------------------------------


class TestShellLog:
    def test_shell_log_includes_duration(self, shell_only_workflow):
        """_shell_log entries include duration field."""
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        for entry in result["_shell_log"]:
            assert "duration" in entry
            assert isinstance(entry["duration"], (int, float))
            assert entry["duration"] >= 0

    def test_shell_failure_recorded(self, tmp_path):
        """Failed shell steps are recorded in _shell_log with failure status."""
        wf_dir = tmp_path / "fail-test"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="fail-test",
    description="Failing shell",
    blocks=[
        ShellStep(name="fail-step", command="exit 1"),
        ShellStep(name="after", command="echo after"),
    ],
)
""")
        result = json.loads(_start(
            workflow="fail-test",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        assert result["action"] == "completed"
        log = result["_shell_log"]
        assert log[0]["exec_key"] == "fail-step"
        assert log[0]["status"] == "failure"
        assert log[1]["exec_key"] == "after"
        assert log[1]["status"] == "success"

    def test_shell_result_var_propagates(self, tmp_path):
        """Shell result_var populated from auto-advanced step is available downstream."""
        wf_dir = tmp_path / "rv-prop"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="rv-prop",
    description="Result var propagation",
    blocks=[
        ShellStep(
            name="detect",
            command='echo \'{"items": ["a", "b"]}\'',
            result_var="data",
        ),
        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Found items. Continue?",
            result_var="answer",
        ),
    ],
)
""")
        result = json.loads(_start(
            workflow="rv-prop",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        # Shell auto-advanced, lands on ask_user
        assert result["action"] == "ask_user"
        # The run state should have the result_var populated
        run_id = result["run_id"]
        state = _runs[run_id]
        assert "data" in state.ctx.variables
        assert state.ctx.variables["data"]["items"] == ["a", "b"]


# ============ Terminal constant at module level ============


class TestTerminalModuleLevel:
    """_TERMINAL_ACTION_TYPES frozenset should be a module-level constant."""

    def test_terminal_constant_exists_at_module_level(self):
        assert "_TERMINAL_ACTION_TYPES" in _runner_ns
        assert isinstance(_runner_ns["_TERMINAL_ACTION_TYPES"], frozenset)
        assert "completed" in _runner_ns["_TERMINAL_ACTION_TYPES"]
        assert "error" in _runner_ns["_TERMINAL_ACTION_TYPES"]
        assert "halted" in _runner_ns["_TERMINAL_ACTION_TYPES"]
