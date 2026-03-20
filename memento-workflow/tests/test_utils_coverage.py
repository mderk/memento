"""Coverage tests for utils.py functions not covered by other test files.

Covers: record_leaf_result, validate_structured_output, dry_run_structured_output,
merge_child_results, compute_totals, workflow_hash, results_key, schema_dict.
"""

import json
from pathlib import Path
from unittest.mock import patch

from conftest import _state_ns, _types_ns

# Types
WorkflowContext = _types_ns["WorkflowContext"]
WorkflowDef = _types_ns["WorkflowDef"]
StepResult = _types_ns["StepResult"]

# Utils
record_leaf_result = _state_ns["record_leaf_result"]
validate_structured_output = _state_ns["validate_structured_output"]
dry_run_structured_output = _state_ns["dry_run_structured_output"]
merge_child_results = _state_ns["merge_child_results"]
compute_totals = _state_ns["compute_totals"]
workflow_hash = _state_ns["workflow_hash"]
results_key = _state_ns["results_key"]
schema_dict = _state_ns["schema_dict"]


# ---------------------------------------------------------------------------
# results_key
# ---------------------------------------------------------------------------


class TestResultsKey:
    def test_no_scope(self):
        ctx = WorkflowContext()
        assert results_key(ctx, "step1") == "step1"

    def test_with_subworkflow_scope(self):
        ctx = WorkflowContext()
        ctx._scope = ["sub:develop", "loop:impl"]
        assert results_key(ctx, "step1") == "develop.step1"

    def test_with_nested_subworkflow_scope(self):
        ctx = WorkflowContext()
        ctx._scope = ["sub:outer", "sub:inner"]
        assert results_key(ctx, "step1") == "outer.inner.step1"


# ---------------------------------------------------------------------------
# record_leaf_result
# ---------------------------------------------------------------------------


class TestRecordLeafResult:
    def test_records_to_scoped_and_results(self):
        ctx = WorkflowContext()
        result = StepResult(name="test", output="hello", status="success")
        recorded = record_leaf_result(ctx, "test", result)
        assert recorded.results_key == "test"
        assert "test" in ctx.results
        assert ctx.results["test"].output == "hello"

    def test_respects_update_last_false(self):
        ctx = WorkflowContext()
        result = StepResult(name="test", output="hello", status="success")
        record_leaf_result(ctx, "test", result, update_last=False)
        assert "test" not in ctx.results

    def test_explicit_order(self):
        ctx = WorkflowContext()
        result = StepResult(name="test", output="x", status="success")
        recorded = record_leaf_result(ctx, "test", result, order=42)
        assert recorded.order == 42

    def test_auto_order(self):
        ctx = WorkflowContext()
        r1 = record_leaf_result(ctx, "a", StepResult(name="a", status="success"))
        r2 = record_leaf_result(ctx, "b", StepResult(name="b", status="success"))
        assert r2.order > r1.order


# ---------------------------------------------------------------------------
# schema_dict
# ---------------------------------------------------------------------------


class TestSchemaDict:
    def test_none_returns_none(self):
        assert schema_dict(None) is None

    def test_pydantic_model(self):
        from pydantic import BaseModel

        class Foo(BaseModel):
            name: str
            count: int

        result = schema_dict(Foo)
        assert "properties" in result
        assert "name" in result["properties"]


# ---------------------------------------------------------------------------
# validate_structured_output
# ---------------------------------------------------------------------------


class TestValidateStructuredOutput:
    def test_no_schema_passes_through(self):
        val, err = validate_structured_output(None, {"a": 1}, None)
        assert val == {"a": 1}
        assert err is None

    def test_structured_output_validated(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            name: str

        val, err = validate_structured_output(None, {"name": "test"}, Out)
        assert err is None
        assert val["name"] == "test"

    def test_json_string_parsed(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            name: str

        val, err = validate_structured_output('{"name": "from_str"}', None, Out)
        assert err is None
        assert val["name"] == "from_str"

    def test_invalid_json_string(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            name: str

        val, err = validate_structured_output("not json", None, Out)
        assert err is not None
        assert "not valid JSON" in err

    def test_no_output_at_all(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            name: str

        val, err = validate_structured_output(None, None, Out)
        assert err is not None
        assert "No structured output" in err

    def test_schema_validation_failure(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            name: str
            count: int

        val, err = validate_structured_output(None, {"name": "x"}, Out)
        assert err is not None
        assert "validation failed" in err

    def test_non_pydantic_schema_passes_through(self):
        """If schema doesn't have model_validate, data passes through."""
        val, err = validate_structured_output(None, {"a": 1}, object)
        assert val == {"a": 1}
        assert err is None


# ---------------------------------------------------------------------------
# dry_run_structured_output
# ---------------------------------------------------------------------------


class TestDryRunStructuredOutput:
    def test_none_returns_none(self):
        assert dry_run_structured_output(None) is None

    def test_no_model_fields_returns_none(self):
        assert dry_run_structured_output(str) is None

    def test_pydantic_model(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            name: str
            count: int
            flag: bool
            ratio: float

        result = dry_run_structured_output(Out)
        assert result["name"] == ""
        assert result["count"] == 0
        assert result["flag"] is False
        assert result["ratio"] == 0.0

    def test_list_and_dict_fields(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            items: list[str]
            meta: dict[str, int]

        result = dry_run_structured_output(Out)
        assert result["items"] == []
        assert result["meta"] == {}

    def test_default_values_used(self):
        from pydantic import BaseModel

        class Out(BaseModel):
            name: str = "default_name"

        result = dry_run_structured_output(Out)
        assert result["name"] == "default_name"

    def test_literal_field(self):
        from typing import Literal

        from pydantic import BaseModel

        class Out(BaseModel):
            mode: Literal["fast", "slow"]

        result = dry_run_structured_output(Out)
        assert result["mode"] == "fast"

    def test_nested_model(self):
        from pydantic import BaseModel

        class Inner(BaseModel):
            value: str

        class Outer(BaseModel):
            inner: Inner

        result = dry_run_structured_output(Outer)
        assert result["inner"]["value"] == ""


# ---------------------------------------------------------------------------
# merge_child_results
# ---------------------------------------------------------------------------


class TestMergeChildResults:
    def test_merges_new_results(self):
        parent_scoped = {}
        parent_results = {}
        child_scoped = {
            "child/step1": StepResult(
                name="step1", results_key="step1", status="success"
            )
        }
        merge_child_results(parent_scoped, parent_results, child_scoped)
        assert "child/step1" in parent_scoped
        assert "step1" in parent_results

    def test_skips_inherited(self):
        """Keys already in parent are not overwritten."""
        existing = StepResult(name="x", results_key="x", status="success", output="parent")
        parent_scoped = {"shared": existing}
        parent_results = {"x": existing}
        child_scoped = {
            "shared": StepResult(
                name="x", results_key="x", status="success", output="child"
            )
        }
        merge_child_results(parent_scoped, parent_results, child_scoped)
        assert parent_scoped["shared"].output == "parent"

    def test_empty_results_key_skipped(self):
        parent_scoped = {}
        parent_results = {}
        child_scoped = {
            "k": StepResult(name="k", results_key="", status="success")
        }
        merge_child_results(parent_scoped, parent_results, child_scoped)
        assert "k" in parent_scoped
        assert "" not in parent_results


# ---------------------------------------------------------------------------
# compute_totals
# ---------------------------------------------------------------------------


class TestComputeTotals:
    def test_empty(self):
        totals = compute_totals({})
        assert totals["duration"] == 0
        assert totals["step_count"] == 0
        assert "cost_usd" not in totals

    def test_with_results(self):
        results = {
            "a": StepResult(
                name="a", status="success", duration=1.5, cost_usd=0.01, step_type="prompt"
            ),
            "b": StepResult(
                name="b", status="success", duration=2.0, cost_usd=0.02, step_type="shell"
            ),
        }
        totals = compute_totals(results)
        assert totals["duration"] == 3.5
        assert totals["step_count"] == 2
        assert totals["cost_usd"] == 0.03
        assert totals["steps_by_type"]["prompt"] == 1
        assert totals["steps_by_type"]["shell"] == 1

    def test_skipped_excluded(self):
        results = {
            "a": StepResult(name="a", status="skipped", duration=0),
            "b": StepResult(name="b", status="success", duration=1.0),
        }
        totals = compute_totals(results)
        assert totals["step_count"] == 1

    def test_no_cost_if_none(self):
        results = {
            "a": StepResult(name="a", status="success", duration=1.0),
        }
        totals = compute_totals(results)
        assert "cost_usd" not in totals


# ---------------------------------------------------------------------------
# workflow_hash
# ---------------------------------------------------------------------------


class TestWorkflowHash:
    def test_with_source_path(self, tmp_path):
        src = tmp_path / "wf.py"
        src.write_text("workflow code")
        wf = WorkflowDef(name="test", description="test", blocks=[])
        wf.source_path = str(src)
        h = workflow_hash(wf)
        assert len(h) == 64  # sha256 hex

    def test_without_source_path(self):
        wf = WorkflowDef(name="test", description="test", blocks=[])
        assert workflow_hash(wf) == ""

    def test_missing_file(self):
        wf = WorkflowDef(name="test", description="test", blocks=[])
        wf.source_path = "/nonexistent/path.py"
        assert workflow_hash(wf) == ""
