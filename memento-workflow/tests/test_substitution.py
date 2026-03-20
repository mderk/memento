"""Tests for template substitution and condition evaluation utilities.

Covers substitute(), substitute_with_files(), evaluate_condition(),
externalization thresholds, placeholder naming, and path containment.
"""

import json
from pathlib import Path

from conftest import _types_ns, _state_ns

# Types
WorkflowContext = _types_ns["WorkflowContext"]
StepResult = _types_ns["StepResult"]

# State
substitute = _state_ns["substitute"]
evaluate_condition = _state_ns["evaluate_condition"]
substitute_with_files = _state_ns["substitute_with_files"]
_EXTERN_THRESHOLD = _state_ns["_EXTERN_THRESHOLD"]


# ---------------------------------------------------------------------------
# Tests: substitute + evaluate_condition
# ---------------------------------------------------------------------------


class TestSubstitute:
    def test_variable_substitution(self):
        ctx = WorkflowContext(variables={"task": "add login", "mode": "protocol"})
        result = substitute("Task: {{variables.task}}, Mode: {{variables.mode}}", ctx)
        assert result == "Task: add login, Mode: protocol"

    def test_result_substitution(self):
        ctx = WorkflowContext()
        ctx.results["detect"] = StepResult(name="detect", output="python")
        result = substitute("Detected: {{results.detect.output}}", ctx)
        assert result == "Detected: python"

    def test_cwd_substitution(self):
        ctx = WorkflowContext(cwd="/my/project")
        result = substitute("Working in {{cwd}}", ctx)
        assert result == "Working in /my/project"

    def test_unresolved_kept(self):
        ctx = WorkflowContext()
        result = substitute("{{results.missing.output}}", ctx)
        assert result == "{{results.missing.output}}"

    def test_dict_substitution(self):
        ctx = WorkflowContext(variables={"config": {"a": 1}})
        result = substitute("Config: {{variables.config}}", ctx)
        assert '"a": 1' in result


class TestSubstituteWithFiles:
    """Unit tests for substitute_with_files — large values externalized to disk."""

    def test_small_value_inlined(self, tmp_path):
        """Values below threshold are inlined as JSON, no files created."""
        ctx = WorkflowContext(variables={"data": {"a": 1}})
        text, files = substitute_with_files("Got: {{variables.data}}", ctx, tmp_path)
        assert files == []
        assert '"a": 1' in text
        assert "externalized" not in text

    def test_large_value_externalized(self, tmp_path):
        """Values exceeding threshold are written to file."""
        big = {"key": "x" * (_EXTERN_THRESHOLD + 100)}
        ctx = WorkflowContext(variables={"big": big})
        text, files = substitute_with_files("Data: {{variables.big}}", ctx, tmp_path)
        assert len(files) == 1
        assert "externalized" in text
        assert "x" * 100 not in text  # not inline
        # File contains the actual data
        data = json.loads(Path(files[0]).read_text())
        assert data == big

    def test_mixed_small_and_large(self, tmp_path):
        """Small values inline, large values externalized in same template."""
        ctx = WorkflowContext(
            variables={
                "small": {"ok": True},
                "large": {"payload": "y" * (_EXTERN_THRESHOLD + 100)},
            }
        )
        text, files = substitute_with_files(
            "S={{variables.small}} L={{variables.large}}",
            ctx,
            tmp_path,
        )
        assert len(files) == 1
        assert '"ok": true' in text  # small inlined
        assert "y" * 100 not in text  # large externalized

    def test_small_string_value_inlined(self, tmp_path):
        """Short string values are inlined."""
        ctx = WorkflowContext(variables={"text": "z" * 100})
        text, files = substitute_with_files("T={{variables.text}}", ctx, tmp_path)
        assert files == []
        assert "z" * 100 in text

    def test_large_string_value_externalized(self, tmp_path):
        """Long string values are externalized to file."""
        ctx = WorkflowContext(variables={"text": "z" * (_EXTERN_THRESHOLD + 100)})
        text, files = substitute_with_files("T={{variables.text}}", ctx, tmp_path)
        assert len(files) == 1
        assert "z" * 100 not in text
        assert "externalized" in text

    def test_unresolved_variables_kept(self, tmp_path):
        """Unresolvable variables are left as-is."""
        ctx = WorkflowContext()
        text, files = substitute_with_files("{{results.missing}}", ctx, tmp_path)
        assert text == "{{results.missing}}"
        assert files == []

    def test_threshold_boundary(self, tmp_path):
        """Value exactly at threshold is inlined (> required, not >=)."""
        filler = "a" * (_EXTERN_THRESHOLD - 20)
        val = {"v": filler}
        serialized = json.dumps(val, indent=2)
        while len(serialized) < _EXTERN_THRESHOLD:
            filler += "a"
            val = {"v": filler}
            serialized = json.dumps(val, indent=2)
        while len(serialized) > _EXTERN_THRESHOLD:
            filler = filler[:-1]
            val = {"v": filler}
            serialized = json.dumps(val, indent=2)

        ctx = WorkflowContext(variables={"exact": val})
        text, files = substitute_with_files("{{variables.exact}}", ctx, tmp_path)
        assert files == []  # exactly at threshold -- not externalized

    def test_results_externalization(self, tmp_path):
        """{{results}} with large structured data is externalized."""
        ctx = WorkflowContext()
        ctx.results["review"] = StepResult(
            name="review",
            structured_output={"findings": [{"desc": "x" * 500} for _ in range(5)]},
        )
        text, files = substitute_with_files("Reviews: {{results}}", ctx, tmp_path)
        assert len(files) == 1
        assert "externalized" in text
        data = json.loads(Path(files[0]).read_text())
        assert "review" in data
        assert len(data["review"]["findings"]) == 5


class TestEvaluateCondition:
    def test_none_is_true(self):
        ctx = WorkflowContext()
        assert evaluate_condition(None, ctx) is True

    def test_true_condition(self):
        ctx = WorkflowContext(variables={"mode": "fast"})
        assert (
            evaluate_condition(lambda c: c.get_var("variables.mode") == "fast", ctx)
            is True
        )

    def test_false_condition(self):
        ctx = WorkflowContext(variables={"mode": "slow"})
        assert (
            evaluate_condition(lambda c: c.get_var("variables.mode") == "fast", ctx)
            is False
        )

    def test_exception_is_false(self):
        def bad(ctx):
            raise ValueError("boom")

        ctx = WorkflowContext()
        assert evaluate_condition(bad, ctx) is False


# ============ Externalization: placeholders, large strings, containment ============


class TestPlaceholderIncludesVarname:
    """Externalized placeholder should include the variable name."""

    def test_placeholder_contains_varname(self, tmp_path):
        big = {"key": "x" * (_EXTERN_THRESHOLD + 100)}
        ctx = WorkflowContext(variables={"big_data": big})
        text, files = substitute_with_files(
            "Data: {{variables.big_data}}",
            ctx,
            tmp_path,
        )
        assert len(files) == 1
        assert "big_data" in text

    def test_placeholder_contains_filename(self, tmp_path):
        big = {"key": "x" * (_EXTERN_THRESHOLD + 100)}
        ctx = WorkflowContext(variables={"my_var": big})
        text, files = substitute_with_files(
            "{{variables.my_var}}",
            ctx,
            tmp_path,
        )
        assert "context_variables_my_var.json" in text


class TestExternalizeLargeStrings:
    """substitute_with_files should externalize large strings too."""

    def test_large_string_externalized(self, tmp_path):
        big_str = "z" * (_EXTERN_THRESHOLD + 100)
        ctx = WorkflowContext(variables={"log": big_str})
        text, files = substitute_with_files(
            "Log: {{variables.log}}",
            ctx,
            tmp_path,
        )
        assert len(files) == 1
        assert "z" * 100 not in text
        content = Path(files[0]).read_text()
        assert big_str in content

    def test_small_string_still_inlined(self, tmp_path):
        ctx = WorkflowContext(variables={"msg": "hello"})
        text, files = substitute_with_files(
            "Msg: {{variables.msg}}",
            ctx,
            tmp_path,
        )
        assert files == []
        assert "hello" in text


class TestThreshold512:
    """Threshold should be 512 chars — the break-even for file externalization."""

    def test_threshold_is_512(self):
        """The externalization threshold should be exactly 512."""
        assert _EXTERN_THRESHOLD == 512

    def test_600_char_value_externalized(self, tmp_path):
        """A 600-char value exceeds 512 threshold and should be externalized."""
        val = {"data": "x" * 580}  # JSON serialized will be >600 chars
        ctx = WorkflowContext(variables={"medium": val})
        text, files = substitute_with_files("{{variables.medium}}", ctx, tmp_path)
        assert len(files) == 1
        assert "externalized" in text

    def test_400_char_value_inlined(self, tmp_path):
        """A 400-char value is below 512 threshold and should be inlined."""
        val = {"data": "x" * 380}  # JSON serialized will be <512 chars
        ctx = WorkflowContext(variables={"small": val})
        text, files = substitute_with_files("{{variables.small}}", ctx, tmp_path)
        assert files == []


class TestSubstituteContainment:
    """File paths must stay within artifacts_dir."""

    def test_normal_varname_stays_within_dir(self, tmp_path):
        big = {"key": "x" * (_EXTERN_THRESHOLD + 100)}
        ctx = WorkflowContext(variables={"safe_name": big})
        text, files = substitute_with_files(
            "{{variables.safe_name}}",
            ctx,
            tmp_path,
        )
        for f in files:
            assert Path(f).resolve().is_relative_to(tmp_path.resolve())
