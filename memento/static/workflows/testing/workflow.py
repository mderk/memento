"""Testing workflow definition.

Executes project tests with coverage via ShellStep (zero LLM tokens).
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


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="testing",
    description="Execute tests with coverage and analyze results",
    blocks=[
        # Step 1: Run tests with coverage (deterministic — zero LLM tokens)
        ShellStep(
            name="run-tests",
            script=_TOOLS,
            args="test --scope all --coverage",
            result_var="test_result",
        ),

        # Step 2: Analyze failures (only when tests fail or coverage gaps exist)
        LLMStep(
            name="analyze",
            prompt="01-analyze.md",
            tools=["Read", "Glob"],
            model="sonnet",
            output_schema=TestResults,
            condition=lambda ctx: (
                ctx.variables.get("test_result", {}).get("status") != "green"
                or ctx.variables.get("test_result", {}).get("coverage_gaps", False)
            ),
        ),
    ],
)
