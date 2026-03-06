# pyright: reportUndefinedVariable=false
"""Testing workflow definition.

Executes project tests with coverage and reports results.

Engine types (WorkflowDef, LLMStep, etc.) are injected by the loader — no imports needed.
"""

from typing import Literal

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


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="testing",
    description="Execute tests with coverage and analyze results",
    blocks=[
        LLMStep(
            name="execute",
            prompt="01-execute.md",
            tools=["Bash", "Read", "Glob"],
            model="sonnet",
            output_schema=TestResults,
        ),
    ],
)
