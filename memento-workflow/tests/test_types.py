"""Tests for workflow types — WorkflowContext, isolation fields, DSL stub drift.

Covers types.py and _dsl.py stub consistency.
"""

import ast
from pathlib import Path

import pytest

from conftest import _types_ns, _state_ns

# Types
LLMStep = _types_ns["LLMStep"]
GroupBlock = _types_ns["GroupBlock"]
ShellStep = _types_ns["ShellStep"]
PromptStep = _types_ns["PromptStep"]
WorkflowContext = _types_ns["WorkflowContext"]
StepResult = _types_ns["StepResult"]

# State (for workflow_hash)
workflow_hash = _state_ns["workflow_hash"]

# Paths
WorkflowDef = _types_ns["WorkflowDef"]
TYPES_PY = Path(__file__).resolve().parent.parent / "scripts" / "engine" / "types.py"
DSL_PY = (
    Path(__file__).resolve().parent.parent.parent
    / "memento"
    / "static"
    / "workflows"
    / "_dsl.py"
)


# ============ WorkflowContext ============


class TestWorkflowContext:
    def test_get_var_variables(self):
        ctx = WorkflowContext(variables={"mode": "protocol", "task": "add login"})
        assert ctx.get_var("variables.mode") == "protocol"
        assert ctx.get_var("variables.task") == "add login"

    def test_get_var_nested(self):
        ctx = WorkflowContext(variables={"config": {"debug": True, "level": 3}})
        assert ctx.get_var("variables.config.debug") is True
        assert ctx.get_var("variables.config.level") == 3

    def test_get_var_results(self):
        ctx = WorkflowContext()
        ctx.results["classify"] = StepResult(
            name="classify",
            status="success",
            structured_output={"scope": "backend", "fast_track": False},
        )
        assert ctx.get_var("results.classify.structured_output.scope") == "backend"
        assert ctx.get_var("results.classify.status") == "success"

    def test_get_var_cwd(self):
        ctx = WorkflowContext(cwd="/my/project")
        assert ctx.get_var("cwd") == "/my/project"

    def test_get_var_missing(self):
        ctx = WorkflowContext()
        assert ctx.get_var("results.nonexistent") is None
        assert ctx.get_var("variables.missing") is None
        assert ctx.get_var("unknown.path") is None

    def test_get_var_dotted_results_key(self):
        """SubWorkflow result at 'develop.explore' resolves via longest-prefix match."""
        ctx = WorkflowContext()
        ctx.results["develop.explore"] = StepResult(
            name="explore",
            structured_output={"findings": [{"tag": "DECISION", "text": "use REST"}]},
        )
        val = ctx.get_var("results.develop.explore.structured_output.findings")
        assert isinstance(val, list)
        assert val[0]["tag"] == "DECISION"

    def test_get_var_simple_results_key_still_works(self):
        """Backward compat: simple key like 'classify' still resolves."""
        ctx = WorkflowContext()
        ctx.results["classify"] = StepResult(
            name="classify",
            structured_output={"scope": "backend"},
        )
        assert ctx.get_var("results.classify.structured_output.scope") == "backend"

    def test_get_var_dotted_key_prefers_longer_match(self):
        """When both 'develop' and 'develop.explore' exist, longer match wins."""
        ctx = WorkflowContext()
        ctx.results["develop"] = StepResult(
            name="develop",
            structured_output={"summary": "dev done"},
        )
        ctx.results["develop.explore"] = StepResult(
            name="explore",
            structured_output={"files": ["a.py"]},
        )
        assert ctx.get_var("results.develop.explore.structured_output.files") == [
            "a.py"
        ]
        assert ctx.get_var("results.develop.structured_output.summary") == "dev done"

    def test_get_var_results_returns_structured_output(self):
        """{{results}} returns structured_output when available, not model_dump()."""
        ctx = WorkflowContext()
        ctx.results["scope"] = StepResult(
            name="scope",
            status="success",
            output="raw text that should not appear",
            structured_output={"files": ["a.py"], "competencies": ["python"]},
            exec_key="scope",
            duration=1.5,
            cost_usd=0.01,
            model="haiku",
        )
        result = ctx.get_var("results")
        assert result == {"scope": {"files": ["a.py"], "competencies": ["python"]}}
        assert set(result["scope"].keys()) == {"files", "competencies"}

    def test_get_var_results_falls_back_to_output(self):
        """{{results}} falls back to output when structured_output is None."""
        ctx = WorkflowContext()
        ctx.results["check"] = StepResult(
            name="check",
            status="success",
            output='{"exists": true}',
            structured_output=None,
        )
        result = ctx.get_var("results")
        assert result == {"check": '{"exists": true}'}

    def test_get_var_results_mixed_steps(self):
        """{{results}} handles mix of structured and plain output steps."""
        ctx = WorkflowContext()
        ctx.results["scope"] = StepResult(
            name="scope",
            structured_output={"files": ["a.py"]},
        )
        ctx.results["shell"] = StepResult(
            name="shell",
            output="plain text",
            structured_output=None,
        )
        ctx.results["reviews"] = StepResult(
            name="reviews",
            structured_output=[
                {"competency": "python", "findings": []},
                {"competency": "security", "findings": [{"severity": "CRITICAL"}]},
            ],
        )
        result = ctx.get_var("results")
        assert result["scope"] == {"files": ["a.py"]}
        assert result["shell"] == "plain text"
        assert len(result["reviews"]) == 2
        assert result["reviews"][0]["competency"] == "python"

    def test_get_var_results_dotpath_still_works(self):
        """Specific dotpath access (results.step.field) still works."""
        ctx = WorkflowContext()
        ctx.results["classify"] = StepResult(
            name="classify",
            status="success",
            output="raw output",
            structured_output={"scope": "backend"},
        )
        assert ctx.get_var("results.classify.structured_output.scope") == "backend"
        assert ctx.get_var("results.classify.output") == "raw output"
        assert ctx.get_var("results.classify.status") == "success"

    def test_elapsed(self):
        ctx = WorkflowContext()
        assert ctx.elapsed() >= 0

    def test_result_field(self):
        ctx = WorkflowContext()
        ctx.results["verify-green"] = StepResult(
            name="verify-green",
            structured_output={"status": "green", "failures": []},
        )
        assert ctx.result_field("verify-green", "status") == "green"
        assert ctx.result_field("verify-green", "failures") == []
        assert ctx.result_field("verify-green", "missing") is None
        assert ctx.result_field("nonexistent", "status") is None

    def test_result_field_no_structured_output(self):
        ctx = WorkflowContext()
        ctx.results["step"] = StepResult(name="step")
        assert ctx.result_field("step", "anything") is None

    def test_get_var_variables_bare(self):
        """get_var('variables') returns the full variables dict."""
        ctx = WorkflowContext(variables={"a": 1, "b": 2})
        result = ctx.get_var("variables")
        assert result == {"a": 1, "b": 2}

    def test_get_var_result_attr_missing(self):
        """Traversing into a non-existent attribute on StepResult returns None."""
        ctx = WorkflowContext()
        ctx.results["step"] = StepResult(name="step", output="hi")
        assert ctx.get_var("results.step.nonexistent_field") is None

    def test_get_var_variable_non_dict_traversal(self):
        """Traversing into a non-dict variable returns None."""
        ctx = WorkflowContext(variables={"count": 42})
        assert ctx.get_var("variables.count.nested") is None


# ============ Isolation Field ============


class TestIsolationField:
    def test_default_is_inline(self):
        step = ShellStep(name="test", command="echo")
        assert step.isolation == "inline"

    def test_set_subagent(self):
        step = LLMStep(name="test", prompt="test.md", isolation="subagent")
        assert step.isolation == "subagent"

    def test_context_hint(self):
        step = LLMStep(
            name="test",
            prompt="test.md",
            isolation="subagent",
            context_hint="project files",
        )
        assert step.context_hint == "project files"

    def test_group_block_no_llm_session_policy(self):
        """GroupBlock should no longer have llm_session_policy."""
        g = GroupBlock(name="test", blocks=[])
        assert (
            not hasattr(g, "llm_session_policy")
            or g.model_fields.get("llm_session_policy") is None
        )

    def test_workflow_context_no_io_handler(self):
        """WorkflowContext should no longer have io_handler."""
        ctx = WorkflowContext()
        assert "io_handler" not in ctx.model_fields


# ============ Workflow Hash ============


class TestWorkflowHash:
    def test_hash_with_source(self, tmp_path):
        (tmp_path / "workflow.py").write_text("# v1")
        wf = WorkflowDef(
            name="test",
            description="test",
            source_path=str(tmp_path / "workflow.py"),
        )
        h = workflow_hash(wf)
        assert len(h) == 64  # SHA256 hex

    def test_hash_no_source(self):
        wf = WorkflowDef(name="test", description="test")
        assert workflow_hash(wf) == ""

    def test_hash_changes_on_source_change(self, tmp_path):
        src = tmp_path / "workflow.py"
        src.write_text("# v1")
        wf = WorkflowDef(name="test", description="test", source_path=str(src))
        h1 = workflow_hash(wf)

        src.write_text("# v2")
        h2 = workflow_hash(wf)
        assert h1 != h2


# ============ DSL Stub Drift Detection ============


# Classes that appear in both types.py and _dsl.py
STUB_CLASSES = [
    "WorkflowDef",
    "LLMStep",
    "ShellStep",
    "SubWorkflow",
    "LoopBlock",
    "RetryBlock",
    "GroupBlock",
    "ParallelEachBlock",
    "ConditionalBlock",
    "Branch",
    "PromptStep",
]

# Fields intentionally excluded from stubs (internal/discriminator fields)
INTERNAL_FIELDS = {
    "type",  # discriminator — not user-facing
    "model_config",  # pydantic config
    "resume_only",  # advanced feature, rarely used
    "context_hint",  # only on LLMStep via BlockBase
    "prompt_dir",  # set by loader, not user
    "source_path",  # set by loader, not user
}


def _parse_dsl_stub_params() -> dict[str, set[str]]:
    """Parse _dsl.py and extract __init__ parameter names per class."""
    source = DSL_PY.read_text()
    tree = ast.parse(source)
    result: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    params = set()
                    for arg in item.args.args + item.args.kwonlyargs:
                        if arg.arg != "self":
                            params.add(arg.arg)
                    result[node.name] = params
    return result


def _get_types_fields(cls_name: str) -> set[str]:
    """Get all model fields for a types.py class."""
    cls = _types_ns.get(cls_name)
    if cls is None:
        return set()
    fields = set()
    for name in cls.model_fields:
        fields.add(name)
    return fields


class TestDslStubsMatchTypes:
    """Verify _dsl.py stubs cover all user-facing types.py fields."""

    @pytest.fixture(autouse=True)
    def _load_stubs(self):
        self.stub_params = _parse_dsl_stub_params()

    @pytest.mark.parametrize("cls_name", STUB_CLASSES)
    def test_stub_covers_all_fields(self, cls_name):
        """Every non-internal field in types.py must appear in _dsl.py stub."""
        types_fields = _get_types_fields(cls_name) - INTERNAL_FIELDS
        stub_params = self.stub_params.get(cls_name, set())

        missing = types_fields - stub_params
        assert not missing, (
            f"_dsl.py stub for {cls_name} is missing fields: {sorted(missing)}. "
            f"Add them to the __init__ signature in _dsl.py."
        )

    @pytest.mark.parametrize("cls_name", STUB_CLASSES)
    def test_stub_has_no_phantom_params(self, cls_name):
        """Stub params (excluding kwargs) should exist in types.py."""
        types_fields = _get_types_fields(cls_name)
        stub_params = self.stub_params.get(cls_name, set())

        phantom = stub_params - types_fields - {"kwargs"}
        assert not phantom, (
            f"_dsl.py stub for {cls_name} has params not in types.py: {sorted(phantom)}. "
            f"Remove them or add the field to types.py."
        )

    def test_all_stub_classes_exist_in_types(self):
        """Every class in _dsl.py should exist in types.py."""
        for cls_name in self.stub_params:
            assert cls_name in _types_ns or cls_name == "WorkflowContext", (
                f"_dsl.py defines {cls_name} but types.py doesn't"
            )
