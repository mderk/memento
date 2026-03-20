"""Tests for prompt_file externalization on PromptAction."""

from conftest import _state_ns, _types_ns

# Types
LLMStep = _types_ns["LLMStep"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]

# State / actions
Frame = _state_ns["Frame"]
RunState = _state_ns["RunState"]
PromptAction = _state_ns["PromptAction"]
action_to_dict = _state_ns["action_to_dict"]
_build_prompt_action = _state_ns["_build_prompt_action"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state_with_artifacts(tmp_path, prompt_dir, variables=None):
    """Create a RunState with checkpoint_dir so artifacts_dir is derived."""
    wf = WorkflowDef(
        name="test", description="test", blocks=[], prompt_dir=str(prompt_dir),
    )
    ctx = WorkflowContext(
        variables=variables or {},
        cwd=".",
        prompt_dir=str(prompt_dir),
    )
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return RunState(
        run_id="test-run",
        ctx=ctx,
        stack=[Frame(block=wf)],
        registry={"test": wf},
        wf_hash="test-hash",
        checkpoint_dir=checkpoint_dir,
    )


def _make_state_without_artifacts(prompt_dir, variables=None):
    """Create a RunState without artifacts_dir."""
    wf = WorkflowDef(
        name="test", description="test", blocks=[], prompt_dir=str(prompt_dir),
    )
    ctx = WorkflowContext(
        variables=variables or {},
        cwd=".",
        prompt_dir=str(prompt_dir),
    )
    return RunState(
        run_id="test-run",
        ctx=ctx,
        stack=[Frame(block=wf)],
        registry={"test": wf},
        wf_hash="test-hash",
    )


# ---------------------------------------------------------------------------
# Tests: prompt_file on PromptAction
# ---------------------------------------------------------------------------


class TestPromptFileField:
    def test_prompt_action_has_prompt_file_when_artifacts_dir_set(self, tmp_path):
        """When artifacts_dir is available, prompt_file should point to the prompt.md file."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "analyze.md").write_text("Analyze the code for {{variables.task}}")

        state = _make_state_with_artifacts(tmp_path, prompt_dir, variables={"task": "bugs"})
        step = LLMStep(name="analyze", prompt="analyze.md")

        action = _build_prompt_action(state, step, "analyze")

        assert action.prompt_file is not None
        assert action.prompt_file.endswith("prompt.md")
        # The file should exist
        from pathlib import Path
        assert Path(action.prompt_file).exists()

    def test_prompt_is_stub_when_prompt_file_set(self, tmp_path):
        """When prompt_file is set, inline prompt should be a short stub, not the full text."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "review.md").write_text("Review this code thoroughly and provide feedback")

        state = _make_state_with_artifacts(tmp_path, prompt_dir)
        step = LLMStep(name="review", prompt="review.md")

        action = _build_prompt_action(state, step, "review")

        # Prompt should be a short stub, not the full text
        assert action.prompt_file is not None
        assert len(action.prompt) < 100  # stub should be short
        assert "Review this code" not in action.prompt  # not the full text
        assert action.prompt != ""  # not empty — backward compat

    def test_prompt_file_is_none_without_artifacts_dir(self, tmp_path):
        """When artifacts_dir is None, prompt_file should be None and prompt should be full text."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "plan.md").write_text("Make a plan for {{variables.goal}}")

        state = _make_state_without_artifacts(prompt_dir, variables={"goal": "shipping"})
        step = LLMStep(name="plan", prompt="plan.md")

        action = _build_prompt_action(state, step, "plan")

        assert action.prompt_file is None
        assert "Make a plan for shipping" in action.prompt


# ---------------------------------------------------------------------------
# Tests: action_to_dict serialization with prompt_file
# ---------------------------------------------------------------------------


class TestPromptFileSerialization:
    def test_action_to_dict_includes_prompt_file_when_set(self):
        """action_to_dict should include prompt_file when it's set."""
        action = PromptAction(
            run_id="test",
            exec_key="analyze",
            prompt="(see prompt_file)",
            prompt_file="/tmp/test/prompt.md",
        )
        d = action_to_dict(action)
        assert "prompt_file" in d
        assert d["prompt_file"] == "/tmp/test/prompt.md"

    def test_action_to_dict_omits_prompt_file_when_none(self):
        """action_to_dict should omit prompt_file when it's None (exclude_none)."""
        action = PromptAction(
            run_id="test",
            exec_key="analyze",
            prompt="Full prompt text here",
        )
        d = action_to_dict(action)
        assert "prompt_file" not in d
