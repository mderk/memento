"""Integration tests for checkpoint persistence and resume.

Tests checkpoint creation, resume from checkpoint, resume fallback behavior,
and cross-conversation resume with inline prompts.
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
    """Create a workflow: shell -> ask_user -> shell (for relay testing)."""
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
        # Start: shell auto-advances -> ask_user
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Submit ask_user -> shell auto-advances -> completed
        _submit(run_id=run_id, exec_key="confirm", output="yes")

        # Verify checkpoint exists
        cp_file = mixed_workflow / ".workflow-state" / run_id / "state.json"
        assert cp_file.exists()

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume completed run -- should start fresh (not replay)
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
        # Start: shell auto-advances -> ask_user
        start_result = json.loads(_start(
            workflow="mixed-test",
            cwd=str(mixed_workflow),
            workflow_dirs=[str(mixed_workflow)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Don't submit -- checkpoint is at ask_user

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume -- should fast-forward past "detect" shell and arrive at ask_user
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
        # Start: detect auto-advances -> confirm ask_user
        start_result = json.loads(_start(
            workflow="rv-test",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"
        assert "42" in start_result["message"]

        # Clear and resume -- should replay detect's result_var
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
        # Completed run -> fresh start (new run_id, completes immediately since shell-only)
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

        # Start -- first action is classify prompt
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
        - classify (inline) -> resume-context (resume_only) -> implement (inline)
        - Fresh run: resume-context is invisible, classify -> implement
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

        # Submit classify -> should skip resume-context, land on implement
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

        # Submit resume-context -> now lands on implement
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
        """Workflow source changed -> old run cancelled, fresh start with warning."""
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
        """Completed run -> fresh start with warning (not an error)."""
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
        """Missing checkpoint file -> fresh start with warning."""
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
        """Invalid run_id format -> error (no fallback)."""
        cwd = str(mixed_workflow.resolve())
        result = json.loads(_start(
            workflow="mixed-test",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume="not-a-valid-id",
        ))
        assert result["action"] == "error"

    def test_resume_unknown_workflow_still_errors(self, mixed_workflow):
        """Unknown workflow -> error (no fallback)."""
        cwd = str(mixed_workflow.resolve())
        result = json.loads(_start(
            workflow="nonexistent-workflow",
            cwd=cwd,
            workflow_dirs=[str(mixed_workflow)],
            resume="aabbccddeeff",
        ))
        assert result["action"] == "error"
