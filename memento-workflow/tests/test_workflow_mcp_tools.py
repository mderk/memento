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

PLUGIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

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
# Shared workflow factories — reused across TestChildRuns,
# TestChildRunVerification, and similar classes.
# ---------------------------------------------------------------------------


def _make_subagent_workflow(
    tmp_path, *, name="sub-test", with_surrounding_shells=True,
    context_hint=None, extra_blocks_before="", extra_blocks_after="",
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


def _make_parallel_workflow(
    tmp_path, *, name="par-test", items_expr='["x", "y"]',
    with_trailing_shell=True,
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

    trailing = '        ShellStep(name="done", command="echo finished"),\n' if with_trailing_shell else ""
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
            ],
            parallel_for="variables.data.items",
        ),
{trailing}    ],
)
""")
    return tmp_path


def _make_parallel_shell_only_workflow(
    tmp_path, *, name="par-shell", items_expr='["a", "b", "c"]',
    with_trailing_shell=True,
):
    """Create a parallel workflow where lanes contain only shell steps (no LLM).

    Args:
        name: Workflow/directory name.
        items_expr: JSON expression for setup shell output items.
        with_trailing_shell: If True, adds a ShellStep after the parallel block.
    """
    wf_dir = tmp_path / name
    wf_dir.mkdir()

    trailing = f'        ShellStep(name="done", command="echo finished"),\n' if with_trailing_shell else ""
    (wf_dir / "workflow.py").write_text(f"""
WORKFLOW = WorkflowDef(
    name="{name}",
    description="Parallel shell-only test",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \\'{{\"items\": {items_expr}}}\\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            item_var="par_item",
            template=[
                ShellStep(name="process", command="echo \\'{{{{variables.par_item}}}}\\'"),
            ],
            parallel_for="variables.data.items",
        ),
{trailing}    ],
)
""")
    return tmp_path


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
    def test_resume_completed_run_starts_fresh(self, mixed_workflow):
        """Resume a completed run falls back to a fresh start."""
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

        # Resume completed run — should start fresh (not replay)
        result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
            resume=run_id,
        ))
        assert result["run_id"] != run_id
        assert result["action"] == "ask_user"  # fresh run starts from beginning

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
            resume=run_id,
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
            resume=run_id,
        ))
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "confirm"
        # Variable from detect should be replayed
        assert "42" in result["message"]

    def test_resume_nonexistent_checkpoint_starts_fresh(self, shell_only_workflow):
        """Resume with nonexistent run_id falls back to fresh start."""
        result = json.loads(_start(
            workflow="shell-only",
            cwd=str(shell_only_workflow),
            workflow_dirs=[str(shell_only_workflow)],
            resume="aabbccddeeff",
        ))
        assert result["action"] == "completed"  # shell-only completes immediately
        assert result["run_id"] != "aabbccddeeff"

    def test_resume_already_completed(self, shell_only_workflow):
        """Resume a completed workflow falls back to fresh start."""
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
            resume=run_id,
        ))
        # Completed run → fresh start (new run_id, completes immediately since shell-only)
        assert result["run_id"] != run_id
        assert result["action"] == "completed"
    def test_resume_inline_prompt_loses_conversation_context(self, tmp_path):
        """Simulate dev workflow: task in variables, classify inline, then implement inline.

        After resume in a new conversation, the implement step's prompt template
        has access to variables and results, but the LLM does NOT see prior
        conversation turns (classify's output as conversation history).

        This test verifies:
        1. variables.task IS available via template substitution after resume
        2. results.classify IS available via template substitution after resume
        3. The prompt text contains the substituted values (so LLM can work)
        """
        wf_dir = tmp_path / "ctx-test"
        wf_dir.mkdir()
        prompts = wf_dir / "prompts"
        prompts.mkdir()

        # classify prompt uses task from variables
        (prompts / "classify.md").write_text(
            "# Classify\nTask: {{variables.task}}\nOutput JSON.\n"
        )
        # implement prompt uses results from classify (not variables.task)
        (prompts / "implement.md").write_text(
            "# Implement\n"
            "Task type: {{results.classify.structured_output.type}}\n"
            "Task: {{variables.task}}\n"
        )

        (wf_dir / "workflow.py").write_text(r"""
from pydantic import BaseModel

class ClassifyOut(BaseModel):
    type: str
    scope: str

WORKFLOW = WorkflowDef(
    name="ctx-test",
    description="Context resume test",
    blocks=[
        LLMStep(
            name="classify",
            prompt="classify.md",
            tools=["Read"],
            output_schema=ClassifyOut,
        ),
        LLMStep(
            name="implement",
            prompt="implement.md",
            tools=["Read", "Write"],
        ),
    ],
)
""")
        cwd = str(wf_dir.resolve())

        # Start — first action is classify prompt
        start_result = json.loads(_start(
            workflow="ctx-test",
            cwd=cwd,
            workflow_dirs=[str(wf_dir)],
            variables={"task": "Add user authentication"},
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "prompt"
        assert start_result["exec_key"] == "classify"
        # Task is in the prompt via template
        assert "Add user authentication" in start_result["prompt"]

        # Submit classify result
        classify_result = json.loads(_submit(
            run_id=run_id,
            exec_key="classify",
            output="classified",
            structured_output={"type": "feature", "scope": "backend"},
        ))
        assert classify_result["action"] == "prompt"
        assert classify_result["exec_key"] == "implement"
        # In the same conversation, implement prompt has both:
        assert "feature" in classify_result["prompt"]  # from results.classify
        assert "Add user authentication" in classify_result["prompt"]  # from variables.task

        # --- Simulate crash + resume in new conversation ---
        _runs.clear()

        result = json.loads(_start(
            workflow="ctx-test",
            cwd=cwd,
            workflow_dirs=[str(wf_dir)],
            resume=run_id,
        ))
        assert result["action"] == "prompt"
        assert result["exec_key"] == "implement"
        assert result.get("_resumed") is True

        # KEY ASSERTION: template-substituted values survive resume
        assert "feature" in result["prompt"]  # results.classify restored from checkpoint
        assert "Add user authentication" in result["prompt"]  # variables.task restored

    def test_resume_only_context_step_injects_task_on_resume(self, tmp_path):
        """resume_only LLM step injects task context on cross-conversation resume.

        Simulates the develop workflow pattern:
        - classify (inline) → resume-context (resume_only) → implement (inline)
        - Fresh run: resume-context is invisible, classify → implement
        - Resume: resume-context fires before implement, injecting task + classify results
        """
        wf_dir = tmp_path / "resume-ctx"
        wf_dir.mkdir()
        prompts = wf_dir / "prompts"
        prompts.mkdir()

        (prompts / "classify.md").write_text(
            "# Classify\nTask: {{variables.task}}\n"
        )
        (prompts / "resume-context.md").write_text(
            "# Resumed Task\n"
            "Task: {{variables.task}}\n"
            "Type: {{results.classify.structured_output.type}}\n"
            "Scope: {{results.classify.structured_output.scope}}\n"
        )
        (prompts / "implement.md").write_text(
            "# Implement\nDo the work.\n"
        )

        (wf_dir / "workflow.py").write_text(r"""
from pydantic import BaseModel

class ClassifyOut(BaseModel):
    type: str
    scope: str

WORKFLOW = WorkflowDef(
    name="resume-ctx",
    description="Resume context injection test",
    blocks=[
        LLMStep(
            name="classify",
            prompt="classify.md",
            tools=["Read"],
            output_schema=ClassifyOut,
        ),
        LLMStep(
            name="resume-context",
            prompt="resume-context.md",
            tools=[],
            resume_only="true",
        ),
        LLMStep(
            name="implement",
            prompt="implement.md",
            tools=["Read", "Write"],
        ),
    ],
)
""")
        cwd = str(wf_dir.resolve())

        # --- Fresh run: resume-context is invisible ---
        start_result = json.loads(_start(
            workflow="resume-ctx",
            cwd=cwd,
            workflow_dirs=[str(wf_dir)],
            variables={"task": "Add user authentication"},
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "prompt"
        assert start_result["exec_key"] == "classify"

        # Submit classify → should skip resume-context, land on implement
        classify_result = json.loads(_submit(
            run_id=run_id,
            exec_key="classify",
            output="classified",
            structured_output={"type": "feature", "scope": "backend"},
        ))
        assert classify_result["action"] == "prompt"
        assert classify_result["exec_key"] == "implement"  # skipped resume-context

        # --- Simulate crash + resume in new conversation ---
        _runs.clear()

        result = json.loads(_start(
            workflow="resume-ctx",
            cwd=cwd,
            workflow_dirs=[str(wf_dir)],
            resume=run_id,
        ))
        assert result["action"] == "prompt"
        assert result.get("_resumed") is True

        # KEY: resume-context fires BEFORE implement, injecting task context
        assert result["exec_key"] == "resume-context"
        assert "Add user authentication" in result["prompt"]
        assert "feature" in result["prompt"]
        assert "backend" in result["prompt"]

        # Submit resume-context → now lands on implement
        impl_result = json.loads(_submit(
            run_id=run_id,
            exec_key="resume-context",
            output="context acknowledged",
        ))
        assert impl_result["action"] == "prompt"
        assert impl_result["exec_key"] == "implement"


# ---------------------------------------------------------------------------
# Tests: Resume fallback (resume graceful degradation)
# ---------------------------------------------------------------------------


class TestResumeFallback:
    """Test that resume falls back to fresh start on failure."""

    def test_resume_success_has_resumed_flag(self, mixed_workflow):
        """Successful resume sets _resumed: true on the first action."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        _runs.clear()

        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=run_id,
        ))
        assert result["action"] == "ask_user"
        assert result["run_id"] == run_id
        assert result.get("_resumed") is True

    def test_resume_drift_falls_back_to_fresh(self, mixed_workflow):
        """Workflow source changed → old run cancelled, fresh start with warning."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
        ))
        old_run_id = start_result["run_id"]

        _runs.clear()

        wf_file = mixed_workflow / "mixed-test" / "workflow.py"
        wf_file.write_text(wf_file.read_text() + "\n# changed\n")

        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=old_run_id,
        ))
        assert result["action"] == "ask_user"
        assert result["run_id"] != old_run_id
        assert result.get("_resumed") is None

    def test_resume_drift_preserves_old_directory(self, mixed_workflow):
        """Old run directory is preserved (not deleted) after drift fallback."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
        ))
        old_run_id = start_result["run_id"]
        old_state_dir = Path(cwd) / ".workflow-state" / old_run_id

        _runs.clear()

        wf_file = mixed_workflow / "mixed-test" / "workflow.py"
        wf_file.write_text(wf_file.read_text() + "\n# changed\n")

        json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=old_run_id,
        ))
        assert old_state_dir.exists()
        meta = json.loads((old_state_dir / "meta.json").read_text())
        assert meta["status"] == "cancelled"

    def test_resume_completed_starts_fresh(self, mixed_workflow):
        """Completed run → fresh start with warning (not an error)."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        result = json.loads(_submit(run_id=run_id, exec_key="confirm", output="yes"))
        assert result["action"] == "completed"

        _runs.clear()

        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=run_id,
        ))
        assert result["run_id"] != run_id
        assert result.get("_resumed") is None
        assert result["warnings"] is not None
        assert any(run_id in w for w in result["warnings"])

    def test_resume_missing_checkpoint_starts_fresh(self, mixed_workflow):
        """Missing checkpoint file → fresh start with warning."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]

        _runs.clear()

        cp_file = Path(cwd) / ".workflow-state" / run_id / "state.json"
        cp_file.unlink()

        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=run_id,
        ))
        assert result["run_id"] != run_id
        assert result.get("_resumed") is None

    def test_resume_fallback_emits_warning(self, mixed_workflow):
        """Fallback fresh start includes a warning about the failed resume."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]

        _runs.clear()

        cp_file = Path(cwd) / ".workflow-state" / run_id / "state.json"
        cp_file.unlink()

        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=run_id,
        ))
        assert result["warnings"] is not None
        assert any(run_id in w for w in result["warnings"])

    def test_resume_fallback_preserves_variables(self, mixed_workflow):
        """Fresh start after fallback uses caller's variables, not checkpoint's."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            variables={"custom": "old_value"},
        ))
        run_id = start_result["run_id"]

        _runs.clear()

        cp_file = Path(cwd) / ".workflow-state" / run_id / "state.json"
        cp_file.unlink()

        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=run_id,
            variables={"custom": "new_value"},
        ))
        new_run_id = result["run_id"]
        assert new_run_id != run_id
        state = _runs[new_run_id]
        assert state.ctx.variables["custom"] == "new_value"

    def test_resume_corrupt_meta_still_falls_back(self, mixed_workflow):
        """Corrupt meta.json doesn't prevent fallback to fresh start."""
        cwd = str(mixed_workflow.resolve())
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]

        _runs.clear()

        # Corrupt both state.json and meta.json
        state_dir = Path(cwd) / ".workflow-state" / run_id
        (state_dir / "state.json").unlink()
        (state_dir / "meta.json").write_text("NOT VALID JSON{{{")

        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume=run_id,
        ))
        assert result["run_id"] != run_id
        assert result["action"] == "ask_user"

    def test_resume_invalid_format_still_errors(self, mixed_workflow):
        """Invalid run_id format → error (no fallback)."""
        cwd = str(mixed_workflow.resolve())
        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume="not-a-valid-id",
        ))
        assert result["action"] == "error"

    def test_resume_unknown_workflow_still_errors(self, mixed_workflow):
        """Unknown workflow → error (no fallback)."""
        cwd = str(mixed_workflow.resolve())
        result = json.loads(_start(
            workflow="nonexistent-workflow",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume="aabbccddeeff",
        ))
        assert result["action"] == "error"


# ---------------------------------------------------------------------------
# Tests: Child runs (subagent relay)
# ---------------------------------------------------------------------------


class TestChildRuns:
    @pytest.fixture
    def subagent_workflow(self, tmp_path):
        return _make_subagent_workflow(tmp_path, context_hint="test context")

    def test_subagent_group_emits_child_run(self, subagent_workflow):
        """Shell auto-advances, then subagent action with child_run_id."""
        start_result = json.loads(_start(
            workflow="sub-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
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
        return _make_parallel_workflow(tmp_path)

    def test_parallel_emits_lanes(self, parallel_workflow):
        """Shell auto-advances, then parallel action with per-lane child_run_ids."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
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

    def test_parallel_auto_merges_structured_output(self, parallel_workflow):
        """Parallel submit auto-merges structured_output from child lanes."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane with structured output
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            child_result = json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output=f"checked item {i}",
                structured_output={"item_index": i, "findings": [f"finding-{i}"]},
            ))
            assert child_result["action"] == "completed"

        # Submit parent — engine should auto-merge child structured outputs
        result = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="all lanes done",
        ))
        assert result["action"] == "completed"

        # Verify the parent's result has merged structured_output
        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        assert isinstance(checks_result.structured_output, list)
        assert len(checks_result.structured_output) == 2
        # Verify all lane data is present
        indices = {item["item_index"] for item in checks_result.structured_output}
        assert indices == {0, 1}

    def test_parallel_auto_merge_fallback_to_output(self, parallel_workflow):
        """Parallel merge falls back to output when structured_output is None."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane with only text output (no structured_output)
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            child_result = json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output=f"result for item {i}",
            ))
            assert child_result["action"] == "completed"

        result = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="done",
        ))
        assert result["action"] == "completed"

        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        assert isinstance(checks_result.structured_output, list)
        assert len(checks_result.structured_output) == 2
        # Falls back to output strings with actual content
        assert set(checks_result.structured_output) == {"result for item 0", "result for item 1"}

    def test_parallel_merge_with_no_structured_output(self, parallel_workflow):
        """Lanes producing neither structured_output nor output yield None merge."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive lanes with empty output
        for lane in lanes:
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output="",
            ))

        result = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="done",
        ))
        assert result["action"] == "completed"

        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        # Empty outputs still collected (empty string is truthy-ish but falsy — should not appear)
        # _collect_parallel_results skips when both structured_output is None and output is falsy
        assert checks_result.structured_output is None

    def test_parallel_merge_mixed_structured_and_text(self, parallel_workflow):
        """Lanes with mix of structured_output and plain text are both collected."""
        start_result = json.loads(_start(
            workflow="par-test",
            cwd=str(parallel_workflow),
            workflow_dirs=[str(parallel_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Lane 0: structured output
        child0 = lanes[0]["child_run_id"]
        action0 = json.loads(_next(run_id=child0))
        json.loads(_submit(
            run_id=child0,
            exec_key=action0["exec_key"],
            output="text fallback",
            structured_output={"type": "structured", "score": 42},
        ))

        # Lane 1: text only
        child1 = lanes[1]["child_run_id"]
        action1 = json.loads(_next(run_id=child1))
        json.loads(_submit(
            run_id=child1,
            exec_key=action1["exec_key"],
            output="plain text result",
        ))

        result = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="done",
        ))
        assert result["action"] == "completed"

        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        merged = checks_result.structured_output
        assert isinstance(merged, list)
        assert len(merged) == 2
        # One structured, one text fallback
        structured_items = [m for m in merged if isinstance(m, dict)]
        text_items = [m for m in merged if isinstance(m, str)]
        assert len(structured_items) == 1
        assert structured_items[0]["score"] == 42
        assert len(text_items) == 1
        assert text_items[0] == "plain text result"

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
        return _make_subagent_workflow(
            tmp_path, name="sv-test", with_surrounding_shells=False,
        )

    @pytest.fixture
    def parallel_workflow(self, tmp_path):
        return _make_parallel_workflow(
            tmp_path, name="pv-test", items_expr='["a", "b"]',
            with_trailing_shell=False,
        )

    def test_subagent_submit_rejected_without_child_completion(self, subagent_workflow):
        """Submit to parent rejected when child run hasn't completed."""
        start_result = json.loads(_start(
            workflow="sv-test",
            cwd=str(subagent_workflow),
            workflow_dirs=[str(subagent_workflow)],
        ))
        run_id = start_result["run_id"]
        parent_exec_key = start_result["exec_key"]

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
        # Failure status should be accepted and advance the workflow (completed or halted)
        assert result["action"] in ("completed", "halted"), (
            f"Expected workflow to advance on failure status, got action={result['action']}"
        )

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


# ---------------------------------------------------------------------------
# Tests: Parallel results available in downstream prompts
# ---------------------------------------------------------------------------


class TestParallelResultsInPrompts:
    """Verify that {{results}} in a step after ParallelEachBlock contains merged lane data."""

    @pytest.fixture
    def parallel_synthesize_workflow(self, tmp_path):
        wf_dir = tmp_path / "par-synth"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "review.md").write_text("Review item: {{variables.par_item}}")
        # Synthesize prompt uses {{results}} — should contain merged parallel data
        (prompts_dir / "synthesize.md").write_text("All results:\n{{results}}")
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="par-synth",
    description="Parallel + synthesize",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["alpha", "beta"]}\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="reviews",
            template=[
                LLMStep(name="review", prompt="review.md"),
            ],
            parallel_for="variables.data.items",
        ),
        LLMStep(name="synthesize", prompt="synthesize.md"),
    ],
)
""")
        return tmp_path

    def test_synthesize_prompt_contains_parallel_structured_data(self, parallel_synthesize_workflow):
        """Synthesize step prompt contains structured data from all parallel lanes."""
        start_result = json.loads(_start(
            workflow="par-synth",
            cwd=str(parallel_synthesize_workflow),
            workflow_dirs=[str(parallel_synthesize_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane with structured output
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output=f"reviewed item {i}",
                structured_output={"item": i, "score": 90 + i},
            ))

        # Submit parallel → should get synthesize prompt action
        synth_action = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="all lanes done",
        ))
        assert synth_action["action"] == "prompt"

        # The synthesize prompt should contain the merged parallel data
        prompt_text = synth_action["prompt"]
        assert '"item"' in prompt_text
        assert '"score"' in prompt_text
        # Should contain data from BOTH lanes
        assert "90" in prompt_text
        assert "91" in prompt_text
        # Should NOT contain StepResult metadata
        assert "exec_key" not in prompt_text
        assert "cost_usd" not in prompt_text
        assert "duration" not in prompt_text

    def test_synthesize_prompt_no_raw_output_noise(self, parallel_synthesize_workflow):
        """{{results}} does not include raw output text when structured_output exists."""
        start_result = json.loads(_start(
            workflow="par-synth",
            cwd=str(parallel_synthesize_workflow),
            workflow_dirs=[str(parallel_synthesize_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output="this raw text should NOT appear in synthesize prompt",
                structured_output={"clean_data": True},
            ))

        synth_action = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="done",
        ))
        assert synth_action["action"] == "prompt"
        prompt_text = synth_action["prompt"]
        # Raw output from lanes should not appear
        assert "this raw text should NOT appear" not in prompt_text
        # Structured data should appear (inline — small enough)
        assert "clean_data" in prompt_text

    def test_large_results_externalized_to_context_files(self, parallel_synthesize_workflow):
        """Large {{results}} data is written to context_files instead of inline."""
        start_result = json.loads(_start(
            workflow="par-synth",
            cwd=str(parallel_synthesize_workflow),
            workflow_dirs=[str(parallel_synthesize_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Submit large structured outputs to exceed externalization threshold
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output=f"reviewed {i}",
                structured_output={
                    "competency": f"comp-{i}",
                    "findings": [
                        {"description": f"finding {j} " + "x" * 200, "severity": "SUGGESTION"}
                        for j in range(5)
                    ],
                },
            ))

        synth_action = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="done",
        ))
        assert synth_action["action"] == "prompt"

        # Large data should be externalized to context_files
        assert synth_action.get("context_files") is not None
        assert len(synth_action["context_files"]) >= 1

        # Prompt text should NOT contain the large inline data
        prompt_text = synth_action["prompt"]
        assert "x" * 200 not in prompt_text
        assert "externalized" in prompt_text

        # Context file should contain the actual data
        data = json.loads(Path(synth_action["context_files"][0]).read_text())
        assert isinstance(data, dict)

    def test_file_based_submit_reads_result_from_disk(self, parallel_synthesize_workflow):
        """When relay writes result to result_dir and submits without inline data, engine reads from file."""
        start_result = json.loads(_start(
            workflow="par-synth",
            cwd=str(parallel_synthesize_workflow),
            workflow_dirs=[str(parallel_synthesize_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(_submit(
                run_id=child_run_id,
                exec_key=child_action["exec_key"],
                output=f"reviewed {i}",
                structured_output={"item": i, "ok": True},
            ))

        synth_action = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="done",
        ))
        assert synth_action["action"] == "prompt"
        synth_exec_key = synth_action["exec_key"]
        result_dir = synth_action.get("result_dir")
        assert result_dir is not None

        # Write result to result_dir (as relay would do)
        result_data = {"verdict": "APPROVE", "findings": []}
        Path(result_dir).mkdir(parents=True, exist_ok=True)
        (Path(result_dir) / "result.json").write_text(
            json.dumps(result_data), encoding="utf-8"
        )

        # Submit WITHOUT output or structured_output — engine reads from file
        completed = json.loads(_submit(
            run_id=run_id,
            exec_key=synth_exec_key,
            status="success",
        ))
        assert completed["action"] == "completed"

        # Verify the result was read from file
        state = _runs[run_id]
        synth_result = state.ctx.results.get("synthesize")
        assert synth_result is not None
        assert synth_result.structured_output == result_data


# ---------------------------------------------------------------------------
# Tests: Parallel child resume from checkpoint
# ---------------------------------------------------------------------------


class TestParallelChildResume:
    """Test resume of parallel workflows with child runs persisted to disk."""

    @pytest.fixture
    def parallel_prompt_workflow(self, tmp_path):
        """Parallel workflow with LLM steps (requires relay, not auto-advanced)."""
        wf_dir = tmp_path / "par-resume"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "check.md").write_text("Check item: {{variables.par_item}}")
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="par-resume",
    description="Parallel resume test",
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

    def test_child_checkpoints_created(self, parallel_prompt_workflow):
        """Starting a parallel workflow creates checkpoint files for children."""
        start_result = json.loads(_start(
            workflow="par-resume",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "parallel"

        # Child checkpoint dirs should exist
        children_dir = parallel_prompt_workflow / ".workflow-state" / run_id / "children"
        assert children_dir.exists()
        child_dirs = list(children_dir.iterdir())
        assert len(child_dirs) == 2
        for cd in child_dirs:
            assert (cd / "state.json").exists()

    def test_resume_parallel_all_children_completed(self, parallel_prompt_workflow):
        """Resume after all children completed fast-forwards past parallel block."""
        start_result = json.loads(_start(
            workflow="par-resume",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
        ))
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive all lanes to completion
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

        # Submit parent parallel
        result = json.loads(_submit(
            run_id=run_id,
            exec_key=parallel_exec_key,
            output="all lanes done",
        ))
        assert result["action"] == "completed"

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume completed run — falls back to fresh start
        result = json.loads(_start(
            workflow="par-resume",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
            resume=run_id,
        ))
        assert result["run_id"] != run_id
        assert result["action"] == "parallel"  # fresh run hits parallel block

    def test_resume_parallel_children_in_progress(self, parallel_prompt_workflow):
        """Resume with in-progress children returns parallel action with resumed lanes."""
        start_result = json.loads(_start(
            workflow="par-resume",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
        ))
        run_id = start_result["run_id"]
        lanes = start_result["lanes"]

        # Complete first lane only
        first_child_id = lanes[0]["child_run_id"]
        child_action = json.loads(_next(run_id=first_child_id))
        json.loads(_submit(
            run_id=first_child_id,
            exec_key=child_action["exec_key"],
            output="checked first",
        ))

        # Leave second lane in-progress (not submitted to)
        # Its checkpoint exists from _action_response auto-advance

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume — should return parallel action with resumed children
        result = json.loads(_start(
            workflow="par-resume",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
            resume=run_id,
        ))
        assert result["action"] == "parallel"
        assert len(result["lanes"]) == 2

        # Children should be in _runs
        for lane in result["lanes"]:
            assert lane["child_run_id"] in _runs

        # Drive remaining lane to completion
        second_child_id = None
        for lane in result["lanes"]:
            child = _runs[lane["child_run_id"]]
            if child.status != "completed":
                second_child_id = lane["child_run_id"]
                break
        assert second_child_id is not None

        child_action = json.loads(_next(run_id=second_child_id))
        assert child_action["action"] == "prompt"
        child_result = json.loads(_submit(
            run_id=second_child_id,
            exec_key=child_action["exec_key"],
            output="checked second",
        ))
        assert child_result["action"] == "completed"

        # Submit parent parallel
        result = json.loads(_submit(
            run_id=run_id,
            exec_key=result["exec_key"],
            output="all lanes done",
        ))
        assert result["action"] == "completed"

    def test_resume_no_children_dir(self, parallel_prompt_workflow):
        """Resume works gracefully when no children/ directory exists (completed before parallel)."""
        # Create a simple non-parallel workflow to get a checkpoint without children
        wf_dir = parallel_prompt_workflow / "simple-cp"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="simple-cp",
    description="Simple checkpoint test",
    blocks=[
        PromptStep(name="ask", prompt_type="confirm", message="OK?", result_var="a"),
        ShellStep(name="fin", command="echo done"),
    ],
)
""")
        start_result = json.loads(_start(
            workflow="simple-cp",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Clear and resume — no children dir, should work normally
        _runs.clear()
        result = json.loads(_start(
            workflow="simple-cp",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
            resume=run_id,
        ))
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "ask"

    def test_child_checkpoint_has_parallel_metadata(self, parallel_prompt_workflow):
        """Child checkpoints contain parallel_block_name and lane_index."""
        start_result = json.loads(_start(
            workflow="par-resume",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
        ))
        run_id = start_result["run_id"]
        lanes = start_result["lanes"]

        children_dir = parallel_prompt_workflow / ".workflow-state" / run_id / "children"
        for i, lane in enumerate(lanes):
            child_id = lane["child_run_id"]
            # Composite ID: parent>child_hex → child dir is just the segment after >
            child_segment = child_id.split(">")[-1]
            cp_file = children_dir / child_segment / "state.json"
            data = json.loads(cp_file.read_text())
            assert data["parallel_block_name"] == "checks"
            assert data["lane_index"] == i
            # Composite run_id encodes parent
            assert ">" in data["run_id"]

    def test_child_meta_has_block_label(self, parallel_prompt_workflow):
        """Child meta.json should have the block name with lane index."""
        start_result = json.loads(_start(
            workflow="par-resume",
            cwd=str(parallel_prompt_workflow),
            workflow_dirs=[str(parallel_prompt_workflow)],
        ))
        run_id = start_result["run_id"]
        lanes = start_result["lanes"]

        children_dir = parallel_prompt_workflow / ".workflow-state" / run_id / "children"
        for i, lane in enumerate(lanes):
            child_id = lane["child_run_id"]
            child_segment = child_id.split(">")[-1]
            meta_file = children_dir / child_segment / "meta.json"
            assert meta_file.exists(), f"meta.json missing for child {child_id}"
            meta = json.loads(meta_file.read_text())
            assert meta["workflow"] == f"checks[{i}]"
            assert meta["status"] == "running"
            assert meta["run_id"] == child_id


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
        start_result = json.loads(_start(
            workflow="halt-sub",
            cwd=str(subagent_halt_workflow),
            workflow_dirs=[str(subagent_halt_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "subagent"
        child_run_id = start_result["child_run_id"]
        parent_exec_key = start_result["exec_key"]

        # Drive child: work → submit → check → submit → halted
        child_action = json.loads(_next(run_id=child_run_id))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "work"

        child_action = json.loads(_submit(
            run_id=child_run_id, exec_key="work", output="done",
        ))
        assert child_action["action"] == "prompt"
        assert child_action["exec_key"] == "check"

        child_action = json.loads(_submit(
            run_id=child_run_id, exec_key="check", output="checked",
        ))
        assert child_action["action"] == "halted"
        assert child_action["reason"] == "Verification failed in child"

        # Submit to parent → halt propagates
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key, output="child done",
        ))
        assert result["action"] == "halted"
        assert result["reason"] == "Verification failed in child"
        assert "check" in result["halted_at"]
        assert parent_exec_key in result["halted_at"]

        # Parent is halted — further submits rejected
        error = json.loads(_submit(
            run_id=run_id, exec_key="after", output="x",
        ))
        assert error["action"] == "error"

    def test_halt_propagates_from_parallel_lane(self, parallel_halt_workflow):
        """When a parallel lane halts, parent submit propagates the halt."""
        start_result = json.loads(_start(
            workflow="halt-par",
            cwd=str(parallel_halt_workflow),
            workflow_dirs=[str(parallel_halt_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "parallel"
        lanes = start_result["lanes"]
        parent_exec_key = start_result["exec_key"]

        # Drive lane 0: process → verify → halted
        lane0_id = lanes[0]["child_run_id"]
        child_action = json.loads(_next(run_id=lane0_id))
        assert child_action["action"] == "prompt"
        child_action = json.loads(_submit(
            run_id=lane0_id, exec_key=child_action["exec_key"], output="processed",
        ))
        assert child_action["action"] == "prompt"
        child_action = json.loads(_submit(
            run_id=lane0_id, exec_key=child_action["exec_key"], output="verified",
        ))
        assert child_action["action"] == "halted"
        assert "Lane a failed" in child_action["reason"]

        # Drive lane 1 to completion
        lane1_id = lanes[1]["child_run_id"]
        child_action = json.loads(_next(run_id=lane1_id))
        child_action = json.loads(_submit(
            run_id=lane1_id, exec_key=child_action["exec_key"], output="processed",
        ))
        child_action = json.loads(_submit(
            run_id=lane1_id, exec_key=child_action["exec_key"], output="verified",
        ))
        # Lane 1 also halts (both have halt on verify)
        assert child_action["action"] == "halted"

        # Submit to parent → halt propagates
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key, output="lanes done",
        ))
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
        start_result = json.loads(_start(
            workflow="halt-mix",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "parallel"
        lanes = start_result["lanes"]
        parent_exec_key = start_result["exec_key"]

        # Lane 0 (item="a"): process → verify (halt fires) → halted
        lane0_id = lanes[0]["child_run_id"]
        child_action = json.loads(_next(run_id=lane0_id))
        child_action = json.loads(_submit(
            run_id=lane0_id, exec_key=child_action["exec_key"], output="processed",
        ))
        child_action = json.loads(_submit(
            run_id=lane0_id, exec_key=child_action["exec_key"], output="verified",
        ))
        assert child_action["action"] == "halted"

        # Lane 1 (item="b"): process → verify skipped (condition false) → completed
        lane1_id = lanes[1]["child_run_id"]
        child_action = json.loads(_next(run_id=lane1_id))
        child_action = json.loads(_submit(
            run_id=lane1_id, exec_key=child_action["exec_key"], output="processed",
        ))
        assert child_action["action"] == "completed"

        # Submit to parent → halt propagates from lane 0
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key, output="lanes done",
        ))
        assert result["action"] == "halted"
        assert "Lane a failed" in result["reason"]

    def test_no_propagation_on_failure_status(self, subagent_halt_workflow):
        """If relay submits with status=failure, halt is NOT propagated."""
        start_result = json.loads(_start(
            workflow="halt-sub",
            cwd=str(subagent_halt_workflow),
            workflow_dirs=[str(subagent_halt_workflow)],
        ))
        run_id = start_result["run_id"]
        child_run_id = start_result["child_run_id"]
        parent_exec_key = start_result["exec_key"]

        # Drive child to halt
        child_action = json.loads(_next(run_id=child_run_id))
        json.loads(_submit(run_id=child_run_id, exec_key="work", output="done"))
        child_action = json.loads(_submit(
            run_id=child_run_id, exec_key="check", output="checked",
        ))
        assert child_action["action"] == "halted"

        # Submit to parent with status=failure → no halt propagation
        result = json.loads(_submit(
            run_id=run_id, exec_key=parent_exec_key,
            output="agent failed", status="failure",
        ))
        # Should advance past the subagent (not halt)
        # "after" shell auto-advances → completed
        assert result["action"] == "completed"


# ---------------------------------------------------------------------------
# Tests: SubWorkflow child run (inline + cascading resume)
# ---------------------------------------------------------------------------

# Extract checkpoint utilities from runner namespace
_checkpoint_dir_from_run_id = _runner_ns["checkpoint_dir_from_run_id"]


def _make_inline_subworkflow(tmp_path, *, name="inline-sub"):
    """Create a workflow with an inline SubWorkflow referencing a helper.

    Parent: ShellStep("setup") → SubWorkflow("call-helper") → ShellStep("finish")
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

    (wf_dir / "workflow.py").write_text("""
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
""" % name)
    return tmp_path


def _make_shell_only_subworkflow(tmp_path, *, name="shell-sub"):
    """Create a workflow with an inline SubWorkflow whose child is shell-only.

    Parent: SubWorkflow("call-shell-helper") → ShellStep("after")
    Helper: ShellStep("echo-step") only — auto-completes
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

    (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="%s",
    description="Shell-only SubWorkflow test",
    blocks=[
        SubWorkflow(name="call-shell-helper", workflow="helper-shell"),
        ShellStep(name="after", command="echo post"),
    ],
)
""" % name)
    return tmp_path


class TestSubWorkflowChildRun:
    """Tests for inline SubWorkflow child run with cascading resume."""

    @pytest.fixture
    def inline_sub_workflow(self, tmp_path):
        return _make_inline_subworkflow(tmp_path)

    @pytest.fixture
    def shell_only_sub_workflow(self, tmp_path):
        return _make_shell_only_subworkflow(tmp_path)

    def test_subworkflow_inline_returns_child_action(self, inline_sub_workflow):
        """Inline SubWorkflow returns the child's prompt action directly."""
        start_result = json.loads(_start(
            workflow="inline-sub",
            cwd=str(inline_sub_workflow),
            workflow_dirs=[str(inline_sub_workflow)],
        ))
        # "setup" shell auto-advances, then inline SubWorkflow should
        # return the child's prompt action (not a subagent action)
        assert start_result["action"] == "prompt"
        assert "inner-work" in start_result["exec_key"]
        # Shell log should contain the setup step
        assert "_shell_log" in start_result
        assert any(e["exec_key"] == "setup" for e in start_result["_shell_log"])
        # The run_id should be the child's composite ID (contains ">")
        assert ">" in start_result["run_id"]

    def test_subworkflow_inline_submit_cascade(self, inline_sub_workflow):
        """Submit to inline child, child completes, cascade returns parent's next action."""
        start_result = json.loads(_start(
            workflow="inline-sub",
            cwd=str(inline_sub_workflow),
            workflow_dirs=[str(inline_sub_workflow)],
        ))
        child_run_id = start_result["run_id"]
        child_exec_key = start_result["exec_key"]

        # Submit to child → child completes → cascade to parent →
        # parent's "finish" shell auto-advances → completed
        result = json.loads(_submit(
            run_id=child_run_id,
            exec_key=child_exec_key,
            output="inner work done",
        ))
        assert result["action"] == "completed"
        # The "finish" shell should appear in shell_log
        assert "_shell_log" in result
        assert any(e["exec_key"] == "finish" for e in result["_shell_log"])

    def test_subworkflow_shell_only_invisible(self, shell_only_sub_workflow):
        """Shell-only inline child auto-completes; relay gets parent's next action."""
        start_result = json.loads(_start(
            workflow="shell-sub",
            cwd=str(shell_only_sub_workflow),
            workflow_dirs=[str(shell_only_sub_workflow)],
        ))
        # Shell-only child auto-completes and cascades to parent.
        # Parent's "after" shell also auto-advances → completed
        assert start_result["action"] == "completed"
        # Shell log should include both the child's echo-step and parent's after step
        assert "_shell_log" in start_result
        exec_keys = [e["exec_key"] for e in start_result["_shell_log"]]
        assert "after" in exec_keys

    def test_subworkflow_child_checkpoint_structure(self, inline_sub_workflow):
        """Child checkpoint lives in children/ directory with composite run_id."""
        start_result = json.loads(_start(
            workflow="inline-sub",
            cwd=str(inline_sub_workflow),
            workflow_dirs=[str(inline_sub_workflow)],
        ))
        child_run_id = start_result["run_id"]
        assert ">" in child_run_id

        parent_run_id = child_run_id.split(">")[0]
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
            Path(inline_sub_workflow), child_run_id,
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
        start_result = json.loads(_start(
            workflow="simple-ver",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
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

        # Resume with tampered checkpoint → should fall back to fresh start
        result = json.loads(_start(
            workflow="simple-ver",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
            resume=run_id,
        ))
        # Fresh start → new run_id
        assert result["run_id"] != run_id
        # Should have a warning about the version mismatch
        assert "warnings" in result
        warnings = result["warnings"]
        assert any("version mismatch" in w.lower() or "mismatch" in w.lower()
                    for w in warnings)

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
            cwd / ".workflow-state" / "aaa111bbb222"
            / "children" / "ccc333ddd444" / "children" / "eee555fff666"
        )

        # Invalid segment raises ValueError (path traversal)
        import pytest
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
        start_result = json.loads(_start(
            workflow="multi-step",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        # Should get child's first prompt (step1)
        assert start_result["action"] == "prompt"
        assert "step 1" in start_result["prompt"].lower()
        child_run_id = start_result["run_id"]
        assert ">" in child_run_id  # composite ID

        # Submit step1 → should get child's step2
        result2 = json.loads(_submit(
            run_id=child_run_id,
            exec_key=start_result["exec_key"],
            output="step1 done",
        ))
        assert result2["action"] == "prompt"
        assert "step 2" in result2["prompt"].lower()
        assert result2["run_id"] == child_run_id  # still child

        # Submit step2 → child completes → cascade → parent's shell "finish" auto-runs → completed
        result3 = json.loads(_submit(
            run_id=child_run_id,
            exec_key=result2["exec_key"],
            output="step2 done",
        ))
        # Should cascade to parent and complete (finish is a shell, auto-advanced)
        assert result3["action"] == "completed"
        # run_id should now be the parent's
        assert ">" not in result3["run_id"]
        # Shell log should contain the "finish" step
        shell_log = result3.get("_shell_log", [])
        assert any("finish" in s.get("exec_key", "") for s in shell_log)


# ---------------------------------------------------------------------------
# Tests: Parallel auto-advance (shell-only lanes skip relay)
# ---------------------------------------------------------------------------


class TestParallelAutoAdvance:
    """Tests for parallel auto-advance: shell-only lanes complete without relay."""

    @pytest.fixture
    def par_shell_workflow(self, tmp_path):
        return _make_parallel_shell_only_workflow(tmp_path)

    @pytest.fixture
    def par_shell_no_trailing(self, tmp_path):
        return _make_parallel_shell_only_workflow(
            tmp_path, name="par-shell-nt", with_trailing_shell=False,
        )

    @pytest.fixture
    def par_shell_5_lanes(self, tmp_path):
        return _make_parallel_shell_only_workflow(
            tmp_path, name="par-shell-5",
            items_expr='["a", "b", "c", "d", "e"]',
        )

    def test_parallel_shell_only_skips_relay(self, par_shell_workflow):
        """Shell-only parallel lanes complete without emitting ParallelAction."""
        result = json.loads(_start(
            workflow="par-shell",
            cwd=str(par_shell_workflow),
            workflow_dirs=[str(par_shell_workflow)],
        ))
        # Should NOT be "parallel" — all lanes are shell-only, auto-completed
        # Instead should advance past the parallel block to either the trailing
        # shell or completed
        assert result["action"] != "parallel", (
            f"Expected auto-advance past parallel block, got: {result['action']}"
        )
        # Should be completed (trailing shell auto-advances too)
        assert result["action"] == "completed"
        # Shell logs should include setup + all lane processes + trailing "done"
        shell_log = result.get("_shell_log", [])
        exec_keys = [s["exec_key"] for s in shell_log]
        assert "setup" in exec_keys
        assert "done" in exec_keys

    def test_parallel_mixed_returns_parallel_action(self, tmp_path):
        """Parallel with LLM template still returns ParallelAction for relay."""
        _make_parallel_workflow(tmp_path, name="par-mixed")
        result = json.loads(_start(
            workflow="par-mixed",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        assert result["action"] == "parallel"
        assert len(result["lanes"]) == 2

    def test_parallel_shell_only_results_collected(self, par_shell_no_trailing):
        """Parent results_scoped has merged child results after auto-completion."""
        result = json.loads(_start(
            workflow="par-shell-nt",
            cwd=str(par_shell_no_trailing),
            workflow_dirs=[str(par_shell_no_trailing)],
        ))
        assert result["action"] == "completed"
        run_id = result["run_id"]
        state = _runs[run_id]
        # The parallel block "checks" should have a result
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None

    def test_parallel_shell_only_lane_failure(self, tmp_path):
        """One lane fails → parent auto-submits but with status=failure in result."""
        wf_dir = tmp_path / "par-fail"
        wf_dir.mkdir()
        # Use a 2-step template: first step always succeeds, second always fails.
        # Items list has 2 entries; the template has a step that uses 'false' to fail.
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="par-fail",
    description="Parallel with failing lane",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["a", "b"]}\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            template=[
                ShellStep(name="process", command="false"),
            ],
            parallel_for="variables.data.items",
        ),
    ],
)
""")
        result = json.loads(_start(
            workflow="par-fail",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        # Workflow should still complete (failure doesn't halt by default)
        assert result["action"] == "completed"
        run_id = result["run_id"]
        state = _runs[run_id]
        # The parallel block result should capture the failure
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        assert checks_result.status == "failure"

    def test_parallel_shell_log_deterministic_order(self, par_shell_5_lanes):
        """Shell logs from 5+ lanes are ordered by lane_index."""
        result = json.loads(_start(
            workflow="par-shell-5",
            cwd=str(par_shell_5_lanes),
            workflow_dirs=[str(par_shell_5_lanes)],
        ))
        assert result["action"] == "completed"
        shell_log = result.get("_shell_log", [])
        # Extract lane shell logs (exclude "setup" and "done")
        lane_logs = [s for s in shell_log if s["exec_key"] not in ("setup", "done")]
        # Should have 5 lane entries
        assert len(lane_logs) == 5
        # Exec keys should be in lane order: par:checks[i=0]/process, par:checks[i=1]/process, ...
        for i, log_entry in enumerate(lane_logs):
            assert log_entry["exec_key"] == f"par:checks[i={i}]/process"

    def test_parallel_child_meta_written(self, par_shell_workflow):
        """After fast-path, each child has a meta.json with terminal status."""
        result = json.loads(_start(
            workflow="par-shell",
            cwd=str(par_shell_workflow),
            workflow_dirs=[str(par_shell_workflow)],
        ))
        assert result["action"] == "completed"
        run_id = result["run_id"]

        # Check child meta.json files
        children_dir = par_shell_workflow / ".workflow-state" / run_id / "children"
        assert children_dir.exists(), "children dir must exist after parallel fast-path"
        child_dirs = list(children_dir.iterdir())
        assert len(child_dirs) == 3  # items: a, b, c
        for child_dir in child_dirs:
            meta_path = child_dir / "meta.json"
            assert meta_path.exists(), f"meta.json missing in {child_dir}"
            meta = json.loads(meta_path.read_text())
            assert meta["status"] in ("completed", "error", "halted")

    def test_parallel_parent_meta_updated(self, par_shell_no_trailing):
        """After fast-path, parent meta.json has terminal status (not stuck at running)."""
        result = json.loads(_start(
            workflow="par-shell-nt",
            cwd=str(par_shell_no_trailing),
            workflow_dirs=[str(par_shell_no_trailing)],
        ))
        assert result["action"] == "completed"
        run_id = result["run_id"]

        meta_path = par_shell_no_trailing / ".workflow-state" / run_id / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["status"] == "completed"

    def test_parallel_auto_advance_disabled(self, par_shell_workflow, monkeypatch):
        """MEMENTO_PARALLEL_AUTO_ADVANCE=off → returns ParallelAction even for shell-only."""
        # Need a fresh runner namespace with the env var set
        monkeypatch.setenv("MEMENTO_PARALLEL_AUTO_ADVANCE", "off")
        ns = create_runner_ns()
        assert ns["_PARALLEL_AUTO_ADVANCE"] is False
        _start_off = ns["start"]
        _runs_off = ns["_runs"]

        result = json.loads(_start_off(
            workflow="par-shell",
            cwd=str(par_shell_workflow),
            workflow_dirs=[str(par_shell_workflow)],
        ))
        assert result["action"] == "parallel"
        assert len(result["lanes"]) == 3  # 3 items: a, b, c
        _runs_off.clear()

    def test_parallel_lane_exception_isolated(self, tmp_path):
        """One lane throws during advance → ErrorAction, others complete, parent status=failure."""
        _make_parallel_shell_only_workflow(tmp_path, name="par-exc")

        # Patch advance() to throw for lane_index == 1
        original_advance = _runner_ns["advance"]

        def patched_advance(state):
            if state.parallel_block_name == "checks" and state.lane_index == 1:
                raise RuntimeError("synthetic lane failure")
            return original_advance(state)

        _runner_ns["advance"] = patched_advance
        try:
            result = json.loads(_start(
                workflow="par-exc",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
            ))
            # Should still complete (fast path handles ErrorAction lanes)
            assert result["action"] == "completed"
            run_id = result["run_id"]
            state = _runs[run_id]
            # The parallel block result should have failure status
            checks_result = state.ctx.results.get("checks")
            assert checks_result is not None
            assert checks_result.status == "failure"
        finally:
            _runner_ns["advance"] = original_advance
