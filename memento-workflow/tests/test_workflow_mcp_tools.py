"""Integration tests for workflow engine MCP tools.

Tests tool functions directly (no transport) — start, submit, next, cancel,
list_workflows, status.

Shell steps are executed internally by the MCP server. They never appear as
relay actions — only as _shell_log entries on the next non-shell action.
"""

import json
import re
from pathlib import Path

import pytest

# Load modules via exec (same pattern as other test files)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

PLUGIN_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills"
)


def _strip_relative_imports(code: str) -> str:
    code = re.sub(r"from \.+\w+ import \(.*?\)", "", code, flags=re.DOTALL)
    code = re.sub(r"from \.+\w+ import .+", "", code)
    return code


# Load types
_types_code = (SCRIPTS_DIR / "types.py").read_text()
_types_ns: dict = {"__name__": "types", "__annotations__": {}}
exec(compile(_types_code, str(SCRIPTS_DIR / "types.py"), "exec"), _types_ns)

# Load state modules (split into core, utils, actions, checkpoint, state)
_state_ns: dict = {
    "__name__": "state",
    "__annotations__": {},
    **{k: v for k, v in _types_ns.items() if not k.startswith("_")},
}
for _fname in ["protocol.py", "core.py", "utils.py", "actions.py", "checkpoint.py", "state.py"]:
    _code = _strip_relative_imports((SCRIPTS_DIR / _fname).read_text())
    exec(compile(_code, str(SCRIPTS_DIR / _fname), "exec"), _state_ns)

# Load compiler
_compiler_code = _strip_relative_imports((SCRIPTS_DIR / "compiler.py").read_text())
_compiler_ns: dict = {
    "__name__": "compiler",
    "__annotations__": {},
    "__builtins__": __builtins__,
    **{k: v for k, v in _types_ns.items() if not k.startswith("_")},
}
exec(compile(_compiler_code, str(SCRIPTS_DIR / "compiler.py"), "exec"), _compiler_ns)

# Load loader
_loader_code = _strip_relative_imports((SCRIPTS_DIR / "loader.py").read_text())
_loader_ns: dict = {
    "__name__": "loader",
    "__annotations__": {},
    "__builtins__": __builtins__,
    "Path": Path,
    "compile_workflow": _compiler_ns["compile_workflow"],
    **{k: v for k, v in _types_ns.items() if not k.startswith("_")},
}
exec(compile(_loader_code, str(SCRIPTS_DIR / "loader.py"), "exec"), _loader_ns)

# Load runner — inject dependencies
_runner_code = _strip_relative_imports((SCRIPTS_DIR / "runner.py").read_text())
_runner_ns: dict = {
    "__name__": "runner",
    "__annotations__": {},
    "__builtins__": __builtins__,
    "__file__": str(SCRIPTS_DIR / "runner.py"),
    "Path": Path,
    **{k: v for k, v in _types_ns.items() if not k.startswith("_")},
    **{k: v for k, v in _state_ns.items() if not k.startswith("_")},
    **{k: v for k, v in _loader_ns.items() if not k.startswith("_")},
}

# Need FastMCP
from mcp.server.fastmcp import FastMCP
_runner_ns["FastMCP"] = FastMCP

exec(compile(_runner_code, str(SCRIPTS_DIR / "runner.py"), "exec"), _runner_ns)

# Extract tool functions (they're registered on the mcp instance, but we
# can call the underlying Python functions directly)
_start = _runner_ns["start"]
_submit = _runner_ns["submit"]
_next = _runner_ns["next"]
_cancel = _runner_ns["cancel"]
_list_workflows = _runner_ns["list_workflows"]
_status = _runner_ns["status"]
_runs = _runner_ns["_runs"]

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
        assert "hello" in log[0]["output"]
        assert log[1]["exec_key"] == "step2"
        assert log[1]["status"] == "success"
        assert "world" in log[1]["output"]

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
# Tests: Checkpoint persistence
# ---------------------------------------------------------------------------


class TestCheckpointPersistence:
    def test_checkpoint_created_on_start(self, ask_user_workflow):
        """Checkpoint is created when start() processes initial actions."""
        start_result = json.loads(_start(
            workflow="ask-test",
            cwd=str(ask_user_workflow),
            workflow_dirs=[str(ask_user_workflow)],
        ))
        run_id = start_result["run_id"]

        state_dir = ask_user_workflow / ".workflow-state" / run_id
        assert state_dir.exists()
        assert (state_dir / "state.json").exists()

    def test_checkpoint_created_for_shell_only(self, shell_only_workflow):
        """Even shell-only workflows that complete immediately create a checkpoint."""
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        run_id = result["run_id"]

        state_dir = shell_only_workflow / ".workflow-state" / run_id
        assert state_dir.exists()
        assert (state_dir / "state.json").exists()


# ---------------------------------------------------------------------------
# Tests: Resume from checkpoint
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_skips_completed_steps(self, mixed_workflow):
        """Resume from checkpoint fast-forwards past completed shell + ask_user."""
        # Start: shell auto-advances → ask_user
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Submit ask_user → shell auto-advances → completed
        _submit(run_id=run_id, exec_key="confirm", output="yes")

        # Verify checkpoint exists
        cp_file = mixed_workflow / ".workflow-state" / run_id / "state.json"
        assert cp_file.exists()

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume — everything already completed
        result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
            resume_run_id=run_id,
        ))
        assert result["action"] == "completed"

    def test_resume_midpoint_at_ask_user(self, mixed_workflow):
        """Resume mid-workflow: fast-forwards past shells, lands on ask_user."""
        # Start: shell auto-advances → ask_user
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Don't submit — checkpoint is at ask_user

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume — should fast-forward past "detect" shell and arrive at ask_user
        result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
            resume_run_id=run_id,
        ))
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "confirm"

    def test_resume_replays_result_var(self, tmp_path):
        """Resume replays result_var from auto-advanced shells for downstream use."""
        wf_dir = tmp_path / "rv-test"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="rv-test",
    description="Result var resume test",
    blocks=[
        ShellStep(
            name="detect",
            command='echo \'{"count": 42}\'',
            result_var="detection",
        ),
        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Count is {{variables.detection.count}}. OK?",
            result_var="answer",
        ),
        ShellStep(
            name="use-var",
            command="echo 'count={{variables.detection.count}}'",
        ),
    ],
)
""")
        # Start: detect auto-advances → confirm ask_user
        start_result = json.loads(_start(
            workflow="rv-test",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"
        assert "42" in start_result["message"]

        # Clear and resume — should replay detect's result_var
        _runs.clear()
        result = json.loads(_start(
            workflow="rv-test",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
            resume_run_id=run_id,
        ))
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "confirm"
        # Variable from detect should be replayed
        assert "42" in result["message"]

    def test_resume_nonexistent_checkpoint(self, shell_only_workflow):
        """Resume with nonexistent run_id returns error."""
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
            resume_run_id="nonexistent",
        ))
        assert result["action"] == "error"
        assert "Checkpoint not found" in result["message"]

    def test_resume_already_completed(self, shell_only_workflow):
        """Resume a completed workflow arrives at completed."""
        start_result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "completed"

        _runs.clear()
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
            resume_run_id=run_id,
        ))
        assert result["action"] == "completed"


# ---------------------------------------------------------------------------
# Tests: Child runs (subagent relay)
# ---------------------------------------------------------------------------


class TestChildRuns:
    @pytest.fixture
    def subagent_workflow(self, tmp_path):
        """Create a workflow with subagent-isolated group."""
        wf_dir = tmp_path / "sub-test"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "s1.md").write_text("Step 1 prompt")
        (prompts_dir / "s2.md").write_text("Step 2 prompt")
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="sub-test",
    description="Subagent group test",
    blocks=[
        ShellStep(name="before", command="echo pre"),
        GroupBlock(
            name="sub-group",
            isolation="subagent",
            context_hint="test context",
            blocks=[
                LLMStep(name="inner1", prompt="s1.md", model="haiku"),
                LLMStep(name="inner2", prompt="s2.md", model="haiku"),
            ],
        ),
        ShellStep(name="after", command="echo post"),
    ],
)
""")
        return tmp_path

    def test_subagent_group_emits_child_run(self, subagent_workflow):
        """Shell auto-advances, then subagent action with child_run_id."""
        start_result = json.loads(_start(
            workflow="sub-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]
        # "before" shell was auto-advanced → subagent action
        assert start_result["action"] == "subagent"
        assert start_result["relay"] is True
        assert "child_run_id" in start_result
        assert "_shell_log" in start_result
        assert start_result["_shell_log"][0]["exec_key"] == "before"

        child_run_id = start_result["child_run_id"]
        assert child_run_id in _runs

    def test_child_relay_loop(self, subagent_workflow):
        """Child run driven via next() + submit(), parent completes after."""
        start_result = json.loads(_start(
            workflow="sub-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]
        parent_exec_key = start_result["exec_key"]

        # Drive child relay: next → inner1 → submit → inner2 → submit → completed
        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "inner1"

        child_action = json.loads(_submit(
            run_id=child_run_id, exec_key="inner1", output="done1",
        ))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "inner2"

        child_action = json.loads(_submit(
            run_id=child_run_id, exec_key="inner2", output="done2",
        ))
        assert child_action["action"] == "completed"

        # Submit parent with child summary → "after" shell auto-advances → completed
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key, output="child completed",
        ))
        assert result["action"] == "completed"
        assert "_shell_log" in result
        assert result["_shell_log"][0]["exec_key"] == "after"

    def test_status_shows_child_runs(self, subagent_workflow):
        """Status tool shows child run information."""
        start_result = json.loads(_start(
            workflow="sub-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]

        status = json.loads(_status(run_id=run_id))
        assert child_run_id in status["child_run_ids"]
        assert "children" in status
        assert child_run_id in status["children"]


# ---------------------------------------------------------------------------
# Tests: Parallel child runs
# ---------------------------------------------------------------------------


class TestParallelChildRuns:
    @pytest.fixture
    def parallel_workflow(self, tmp_path):
        """Create a workflow with ParallelEachBlock."""
        wf_dir = tmp_path / "par-test"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "check.md").write_text("Check item: {{variables.par_item}}")
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="par-test",
    description="Parallel test",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["x", "y"]}\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            template=[
                LLMStep(name="check", prompt="check.md", model="haiku"),
            ],
            parallel_for="variables.data.items",
        ),
        ShellStep(name="done", command="echo finished"),
    ],
)
""")
        return tmp_path

    def test_parallel_emits_lanes(self, parallel_workflow):
        """Shell auto-advances, then parallel action with per-lane child_run_ids."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        # "setup" shell was auto-advanced → parallel action
        assert start_result["action"] == "parallel"
        assert "_shell_log" in start_result
        assert start_result["_shell_log"][0]["exec_key"] == "setup"
        assert len(start_result["lanes"]) == 2
        for lane in start_result["lanes"]:
            assert "child_run_id" in lane
            assert lane["relay"] is True

    def test_parallel_lane_relay(self, parallel_workflow):
        """Each parallel lane driven independently, parent completes after all lanes."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane
        lane_summaries = []
        for lane in lanes:
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            assert child_action["action"] == "prompt"

            child_result = json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output=f"checked {child_run_id}",
            ))
            assert child_result["action"] == "completed"
            lane_summaries.append(f"lane done: {child_run_id}")

        # Submit parent → "done" shell auto-advances → completed
        result = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output=json.dumps(lane_summaries),
        ))
        assert result["action"] == "completed"
        assert "_shell_log" in result
        assert result["_shell_log"][0]["exec_key"] == "done"

    def test_cancel_cleans_child_runs(self, parallel_workflow):
        """Cancel cleans up both parent and child runs."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        child_ids = [lane["child_run_id"] for lane in start_result["lanes"]]

        # All runs should exist
        assert run_id in _runs
        for cid in child_ids:
            assert cid in _runs

        # Cancel parent
        cancel_result = json.loads(_cancel(run_id=run_id))
        assert cancel_result["action"] == "cancelled"

        # All should be cleaned up
        assert run_id not in _runs
        for cid in child_ids:
            assert cid not in _runs


# ---------------------------------------------------------------------------
# Tests: Child run verification (anti-fabrication)
# ---------------------------------------------------------------------------


class TestChildRunVerification:
    """Verify that submitting to parent fails if child runs didn't actually complete."""

    @pytest.fixture
    def subagent_workflow(self, tmp_path):
        wf_dir = tmp_path / "sv-test"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "s1.md").write_text("Step 1")
        (prompts_dir / "s2.md").write_text("Step 2")
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="sv-test",
    description="Subagent verification test",
    blocks=[
        GroupBlock(
            name="sub-group",
            isolation="subagent",
            blocks=[
                LLMStep(name="inner1", prompt="s1.md", model="haiku"),
                LLMStep(name="inner2", prompt="s2.md", model="haiku"),
            ],
        ),
    ],
)
""")
        return tmp_path

    @pytest.fixture
    def parallel_workflow(self, tmp_path):
        wf_dir = tmp_path / "pv-test"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "check.md").write_text("Check")
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="pv-test",
    description="Parallel verification test",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["a", "b"]}\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            template=[
                LLMStep(name="check", prompt="check.md", model="haiku"),
            ],
            parallel_for="variables.data.items",
        ),
    ],
)
""")
        return tmp_path

    def test_subagent_submit_rejected_without_child_completion(self, subagent_workflow):
        """Submit to parent rejected when child run hasn't completed."""
        start_result = json.loads(_start(
            workflow="sv-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]
        child_run_id = start_result["child_run_id"]

        # Agent fabricates without running child relay
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key, output="fabricated answer",
        ))
        assert result["action"] == "error"
        assert "not completed" in result["message"] or "status" in result["message"]

    def test_subagent_submit_accepted_after_child_completion(self, subagent_workflow):
        """Submit to parent succeeds after child relay finishes."""
        start_result = json.loads(_start(
            workflow="sv-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]
        child_run_id = start_result["child_run_id"]

        # Drive child to completion
        child_action = json.loads(_next(run_id=child_run_id))
        child_action = json.loads(_submit(
            run_id=child_run_id, exec_key=child_action["exec_key"], output="done1",
        ))
        child_action = json.loads(_submit(
            run_id=child_run_id, exec_key=child_action["exec_key"], output="done2",
        ))
        assert child_action["action"] == "completed"

        # Now parent submit succeeds
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key, output="child completed",
        ))
        assert result["action"] == "completed"

    def test_subagent_failure_status_bypasses_verification(self, subagent_workflow):
        """Submit with status=failure accepted without child completion check."""
        start_result = json.loads(_start(
            workflow="sv-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]

        # Agent reports failure — should be accepted (not fabricating success)
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key,
            output="child relay failed", status="failure",
        ))
        # Should advance (not error), since failure is honest
        assert result["action"] != "error" or "not completed" not in result.get("message", "")

    def test_parallel_submit_rejected_without_lane_completion(self, parallel_workflow):
        """Submit to parent rejected when parallel lanes haven't completed."""
        start_result = json.loads(_start(
            workflow="pv-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive only first lane
        first_lane = lanes[0]
        child_action = json.loads(_next(run_id=first_lane["child_run_id"]))
        json.loads(_submit(
            run_id=first_lane["child_run_id"],
            exec_key=child_action["exec_key"],
            output="done",
        ))

        # Submit parent — second lane not completed
        result = json.loads(_submit(
            run_id=run_id, exec_key=parallel_exec_key, output="fabricated",
        ))
        assert result["action"] == "error"
        assert "not completed" in result["message"] or "status" in result["message"]

    def test_parallel_submit_accepted_after_all_lanes(self, parallel_workflow):
        """Submit to parent succeeds after all parallel lanes complete."""
        start_result = json.loads(_start(
            workflow="pv-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive all lanes to completion
        for lane in lanes:
            child_action = json.loads(_next(run_id=lane["child_run_id"]))
            child_result = json.loads(_submit(
                run_id=lane["child_run_id"],
                exec_key=child_action["exec_key"],
                output="done",
            ))
            assert child_result["action"] == "completed"

        # Submit parent succeeds
        result = json.loads(_submit(
            run_id=run_id, exec_key=parallel_exec_key, output="all done",
        ))
        assert result["action"] == "completed"

    def test_wrong_exec_key_not_masked_by_child_verification(self, subagent_workflow):
        """Wrong exec_key should return 'Wrong exec_key' error, not a child verification error."""
        start_result = json.loads(_start(
            workflow="sv-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]

        # Submit with wrong exec_key while parent awaits relay
        result = json.loads(_submit(
            run_id=run_id, exec_key="bogus-key", output="fabricated",
        ))
        assert result["action"] == "error"
        assert "Wrong exec_key" in result["message"]


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
