"""Tests for schema hash cache — externalize json_schema to shared _schemas/ dir."""

import json
from pathlib import Path

from pydantic import BaseModel

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
# Test schemas
# ---------------------------------------------------------------------------


class ReviewOutput(BaseModel):
    findings: list[str]
    verdict: str


class ClassifyOutput(BaseModel):
    scope: str
    complexity: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(tmp_path, prompt_dir, variables=None):
    """Create RunState with checkpoint_dir so artifacts_dir is available."""
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


def _make_state_no_artifacts(prompt_dir, variables=None):
    """Create RunState without artifacts_dir."""
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
# Tests: PromptAction schema fields
# ---------------------------------------------------------------------------


class TestSchemaFields:
    def test_schema_file_field_exists(self):
        """PromptAction should have schema_file field."""
        action = PromptAction(
            run_id="test",
            exec_key="step1",
            prompt="hello",
            schema_file="/tmp/schemas/abc123.json",
        )
        assert action.schema_file == "/tmp/schemas/abc123.json"

    def test_schema_id_field_exists(self):
        """PromptAction should have schema_id field."""
        action = PromptAction(
            run_id="test",
            exec_key="step1",
            prompt="hello",
            schema_id="abc123def456",
        )
        assert action.schema_id == "abc123def456"

    def test_schema_fields_default_none(self):
        """schema_file and schema_id default to None."""
        action = PromptAction(run_id="test", exec_key="step1", prompt="hello")
        assert action.schema_file is None
        assert action.schema_id is None


# ---------------------------------------------------------------------------
# Tests: Schema hash caching in _build_prompt_action
# ---------------------------------------------------------------------------


class TestSchemaCacheBehavior:
    def test_same_schema_same_file(self, tmp_path):
        """Two steps with same output_schema get the same schema_file path."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s1.md").write_text("Step 1")
        (prompt_dir / "s2.md").write_text("Step 2")

        state = _make_state(tmp_path, prompt_dir)
        step1 = LLMStep(name="s1", prompt="s1.md", output_schema=ReviewOutput)
        step2 = LLMStep(name="s2", prompt="s2.md", output_schema=ReviewOutput)

        action1 = _build_prompt_action(state, step1, "s1")
        action2 = _build_prompt_action(state, step2, "s2")

        assert action1.schema_file is not None
        assert action1.schema_file == action2.schema_file
        assert action1.schema_id == action2.schema_id

    def test_different_schemas_different_files(self, tmp_path):
        """Two steps with different output_schemas get different schema_file paths."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s1.md").write_text("Step 1")
        (prompt_dir / "s2.md").write_text("Step 2")

        state = _make_state(tmp_path, prompt_dir)
        step1 = LLMStep(name="s1", prompt="s1.md", output_schema=ReviewOutput)
        step2 = LLMStep(name="s2", prompt="s2.md", output_schema=ClassifyOutput)

        action1 = _build_prompt_action(state, step1, "s1")
        action2 = _build_prompt_action(state, step2, "s2")

        assert action1.schema_file != action2.schema_file
        assert action1.schema_id != action2.schema_id

    def test_schema_file_contains_valid_json(self, tmp_path):
        """The cached schema file should contain valid JSON matching the schema."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s.md").write_text("Step")

        state = _make_state(tmp_path, prompt_dir)
        step = LLMStep(name="s", prompt="s.md", output_schema=ReviewOutput)

        action = _build_prompt_action(state, step, "s")

        content = json.loads(Path(action.schema_file).read_text())
        assert "properties" in content
        assert "findings" in content["properties"]
        assert "verdict" in content["properties"]

    def test_json_schema_cleared_when_schema_file_set(self, tmp_path):
        """When schema_file is set, inline json_schema should be None."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s.md").write_text("Step")

        state = _make_state(tmp_path, prompt_dir)
        step = LLMStep(name="s", prompt="s.md", output_schema=ReviewOutput)

        action = _build_prompt_action(state, step, "s")

        assert action.schema_file is not None
        assert action.json_schema is None

    def test_schema_cache_dir_is_shared(self, tmp_path):
        """Schema cache should be in _schemas/, not per-run artifacts."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s.md").write_text("Step")

        state = _make_state(tmp_path, prompt_dir)
        step = LLMStep(name="s", prompt="s.md", output_schema=ReviewOutput)

        action = _build_prompt_action(state, step, "s")

        assert "_schemas" in action.schema_file

    def test_schema_id_is_12_char_hex(self, tmp_path):
        """schema_id should be a 12-character hex string."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s.md").write_text("Step")

        state = _make_state(tmp_path, prompt_dir)
        step = LLMStep(name="s", prompt="s.md", output_schema=ReviewOutput)

        action = _build_prompt_action(state, step, "s")

        assert action.schema_id is not None
        assert len(action.schema_id) == 12
        int(action.schema_id, 16)  # valid hex

    def test_no_schema_no_cache(self, tmp_path):
        """Steps without output_schema should have no schema_file."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s.md").write_text("Step")

        state = _make_state(tmp_path, prompt_dir)
        step = LLMStep(name="s", prompt="s.md")

        action = _build_prompt_action(state, step, "s")

        assert action.schema_file is None
        assert action.schema_id is None

    def test_no_artifacts_dir_keeps_inline_schema(self, tmp_path):
        """Without artifacts_dir, json_schema stays inline."""
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "s.md").write_text("Step")

        state = _make_state_no_artifacts(prompt_dir)
        step = LLMStep(name="s", prompt="s.md", output_schema=ReviewOutput)

        action = _build_prompt_action(state, step, "s")

        assert action.schema_file is None
        assert action.json_schema is not None
        assert "properties" in action.json_schema


# ---------------------------------------------------------------------------
# Tests: Serialization
# ---------------------------------------------------------------------------


class TestSchemaFileSerialization:
    def test_action_to_dict_includes_schema_file(self):
        action = PromptAction(
            run_id="test",
            exec_key="s1",
            prompt="(see prompt_file)",
            schema_file="/tmp/schemas/abc.json",
            schema_id="abc123def456",
        )
        d = action_to_dict(action)
        assert d["schema_file"] == "/tmp/schemas/abc.json"
        assert d["schema_id"] == "abc123def456"

    def test_action_to_dict_omits_schema_fields_when_none(self):
        action = PromptAction(
            run_id="test",
            exec_key="s1",
            prompt="hello",
        )
        d = action_to_dict(action)
        assert "schema_file" not in d
        assert "schema_id" not in d
