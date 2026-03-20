"""Tests for cache_prompt template-level hash caching."""

from pathlib import Path

from conftest import _state_ns, _types_ns

# Types
LLMStep = _types_ns["LLMStep"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]

# State / actions
Frame = _state_ns["Frame"]
RunState = _state_ns["RunState"]
_build_prompt_action = _state_ns["_build_prompt_action"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(tmp_path, prompt_dir, variables=None):
    """Create a RunState with checkpoint_dir (so artifacts_dir is available)."""
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


# ---------------------------------------------------------------------------
# Tests: LLMStep cache_prompt field
# ---------------------------------------------------------------------------


class TestCachePromptField:
    def test_llm_step_has_cache_prompt_field(self):
        """LLMStep should have cache_prompt field defaulting to False."""
        step = LLMStep(name="test", prompt="test.md")
        assert step.cache_prompt is False

    def test_llm_step_cache_prompt_true(self):
        """LLMStep accepts cache_prompt=True."""
        step = LLMStep(name="test", prompt="test.md", cache_prompt=True)
        assert step.cache_prompt is True


# ---------------------------------------------------------------------------
# Tests: PromptAction prompt_hash field
# ---------------------------------------------------------------------------


class TestPromptHashField:
    def test_prompt_action_has_prompt_hash(self):
        """PromptAction should have prompt_hash field."""
        PromptAction = _state_ns["PromptAction"]
        action = PromptAction(
            run_id="test",
            exec_key="step1",
            prompt="(see prompt_file)",
            prompt_hash="abc123def456",
        )
        assert action.prompt_hash == "abc123def456"

    def test_prompt_hash_none_by_default(self):
        """prompt_hash defaults to None."""
        PromptAction = _state_ns["PromptAction"]
        action = PromptAction(run_id="test", exec_key="step1", prompt="hello")
        assert action.prompt_hash is None


# ---------------------------------------------------------------------------
# Tests: cache_prompt behavior in _build_prompt_action
# ---------------------------------------------------------------------------


class TestCachePromptBehavior:
    def test_same_template_same_prompt_file(self, tmp_path):
        """Two steps with same template + different variables get the same prompt_file."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "review.md").write_text(
            "Review {{variables.item}} for quality"
        )

        state = _make_state(tmp_path, prompt_dir, variables={"item": "alpha"})
        step1 = LLMStep(name="review1", prompt="review.md", cache_prompt=True)
        action1 = _build_prompt_action(state, step1, "review1")

        # Change variable for second step
        state.ctx.variables["item"] = "beta"
        step2 = LLMStep(name="review2", prompt="review.md", cache_prompt=True)
        action2 = _build_prompt_action(state, step2, "review2")

        # Same template → same prompt_file (cached)
        assert action1.prompt_file == action2.prompt_file
        assert action1.prompt_hash == action2.prompt_hash

    def test_different_templates_different_prompt_file(self, tmp_path):
        """Two steps with different templates get different prompt_file paths."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "analyze.md").write_text("Analyze {{variables.item}}")
        (prompt_dir / "review.md").write_text("Review {{variables.item}}")

        state = _make_state(tmp_path, prompt_dir, variables={"item": "alpha"})
        step1 = LLMStep(name="s1", prompt="analyze.md", cache_prompt=True)
        action1 = _build_prompt_action(state, step1, "s1")

        step2 = LLMStep(name="s2", prompt="review.md", cache_prompt=True)
        action2 = _build_prompt_action(state, step2, "s2")

        assert action1.prompt_file != action2.prompt_file
        assert action1.prompt_hash != action2.prompt_hash

    def test_context_files_contain_per_step_data(self, tmp_path):
        """Each step gets its own context_files with variable data."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        # Use a large variable so it gets externalized to context_files
        (prompt_dir / "work.md").write_text("Do work on {{variables.data}}")

        big_data = {"payload": "x" * 600}  # exceeds 512 threshold
        state = _make_state(tmp_path, prompt_dir, variables={"data": big_data})
        step1 = LLMStep(name="s1", prompt="work.md", cache_prompt=True)
        action1 = _build_prompt_action(state, step1, "s1")

        state.ctx.variables["data"] = {"payload": "y" * 600}
        step2 = LLMStep(name="s2", prompt="work.md", cache_prompt=True)
        action2 = _build_prompt_action(state, step2, "s2")

        # Same prompt_file (cached template)
        assert action1.prompt_file == action2.prompt_file
        # Different context_files (per-step variable data)
        assert action1.context_files != action2.context_files

    def test_cached_template_is_raw(self, tmp_path):
        """The cached file contains the raw template, not substituted text."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "task.md").write_text("Do {{variables.task}}")

        state = _make_state(tmp_path, prompt_dir, variables={"task": "build"})
        step = LLMStep(name="s", prompt="task.md", cache_prompt=True)
        action = _build_prompt_action(state, step, "s")

        cached_content = Path(action.prompt_file).read_text()
        # Raw template preserved (contains {{variables.task}}, not "build")
        assert "{{variables.task}}" in cached_content
        assert "build" not in cached_content

    def test_small_variables_externalized_with_cache_prompt(self, tmp_path):
        """cache_prompt forces all variables to context_files, even small ones."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "greet.md").write_text("Hello {{variables.name}}")

        state = _make_state(tmp_path, prompt_dir, variables={"name": "Alice"})
        step = LLMStep(name="s", prompt="greet.md", cache_prompt=True)
        action = _build_prompt_action(state, step, "s")

        # Even though "Alice" is small, it must be externalized
        assert action.context_files is not None
        assert len(action.context_files) >= 1
        # The context file should contain the value
        content = Path(action.context_files[0]).read_text()
        assert "Alice" in content

    def test_prompt_hash_is_12_char_hex(self, tmp_path):
        """prompt_hash should be a 12-character hex string."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "x.md").write_text("hello")

        state = _make_state(tmp_path, prompt_dir)
        step = LLMStep(name="s", prompt="x.md", cache_prompt=True)
        action = _build_prompt_action(state, step, "s")

        assert action.prompt_hash is not None
        assert len(action.prompt_hash) == 12
        int(action.prompt_hash, 16)  # must be valid hex
