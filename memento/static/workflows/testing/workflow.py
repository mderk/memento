"""Testing workflow definition.

Executes project tests (optionally with coverage) via ShellStep (zero LLM tokens).
LLM is only invoked when failures or coverage gaps need analysis.
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from _dsl import LLMStep, ShellStep, WorkflowDef

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class FileCoverage(BaseModel):
    """Per-file coverage data for changed files."""
    file: str
    coverage_pct: float
    missing_lines: list[str] = Field(default_factory=list)


class FailureDetail(BaseModel):
    test: str
    error: str
    file: str | None = None
    line: int | None = None
    suggested_fix: str | None = None
    priority: Literal["CRITICAL", "REQUIRED", "SUGGESTION"] | None = None


class TestResults(BaseModel):
    passed: int
    failed: int
    errors: int
    skipped: int = 0
    coverage_pct: float | None = None
    coverage_details: list[FileCoverage] = Field(default_factory=list)
    failure_details: list[FailureDetail] = Field(default_factory=list)


# dev-tools.py lives in the develop workflow (always deployed together)
_TOOLS = "../develop/dev-tools.py"


def _truthy(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "disable", "disabled", "none", "")
    return bool(value)


def _normalize_test_scope(value) -> str:
    if value is None:
        return "all"
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("all", "changed", "specific"):
            return v
    return "all"


def _normalize_target(value) -> str:
    if value is None:
        return "all"
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("all", "backend", "frontend"):
            return v
        if v == "fullstack":
            return "all"
    return "all"


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="testing",
    description="Execute tests (optional coverage) and analyze results",
    blocks=[
        # Default: no coverage (faster and works without pytest-cov)
        ShellStep(
            name="init-coverage",
            command="echo false",
            result_var="coverage",
            condition=lambda ctx: ctx.variables.get("coverage") is None,
        ),
        ShellStep(
            name="init-test-scope",
            command="echo '\"all\"'",
            result_var="test_scope",
            condition=lambda ctx: ctx.variables.get("test_scope") is None,
        ),
        ShellStep(
            name="init-target",
            command="echo '\"all\"'",
            result_var="target",
            condition=lambda ctx: ctx.variables.get("target") is None,
        ),

        # Step 1: Run tests with coverage (deterministic — zero LLM tokens)
        ShellStep(
            name="run-tests-with-coverage",
            script=_TOOLS,
            args="test --scope {{variables.test_scope}} --target {{variables.target}} --coverage",
            result_var="test_result",
            condition=lambda ctx: (
                _truthy(ctx.variables.get("coverage"))
                and _normalize_test_scope(ctx.variables.get("test_scope")) != "specific"
            ),
        ),
        ShellStep(
            name="run-tests-with-coverage-specific",
            script=_TOOLS,
            args="test --scope specific --target {{variables.target}} --files-json '{{variables.test_files}}' --coverage",
            result_var="test_result",
            condition=lambda ctx: (
                _truthy(ctx.variables.get("coverage"))
                and _normalize_test_scope(ctx.variables.get("test_scope")) == "specific"
            ),
        ),
        ShellStep(
            name="run-tests",
            script=_TOOLS,
            args="test --scope {{variables.test_scope}} --target {{variables.target}}",
            result_var="test_result",
            condition=lambda ctx: (
                not _truthy(ctx.variables.get("coverage"))
                and _normalize_test_scope(ctx.variables.get("test_scope")) != "specific"
            ),
        ),
        ShellStep(
            name="run-tests-specific",
            script=_TOOLS,
            args="test --scope specific --target {{variables.target}} --files-json '{{variables.test_files}}'",
            result_var="test_result",
            condition=lambda ctx: (
                not _truthy(ctx.variables.get("coverage"))
                and _normalize_test_scope(ctx.variables.get("test_scope")) == "specific"
            ),
        ),

        # Step 2: Analyze failures (only when tests fail or coverage gaps exist)
        LLMStep(
            name="analyze",
            prompt="01-analyze.md",
            tools=["Read", "Glob"],
            model="sonnet",
            output_schema=TestResults,
            isolation="subagent",
            condition=lambda ctx: (
                ctx.variables.get("test_result", {}).get("status") != "green"
                or ctx.variables.get("test_result", {}).get("coverage_gaps", False)
            ),
        ),
    ],
)
