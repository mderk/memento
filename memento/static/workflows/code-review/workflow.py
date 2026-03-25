"""Code review workflow definition.

Determines scope, runs parallel competency reviews, synthesizes findings.
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from _dsl import LLMStep, ParallelEachBlock, ShellStep, WorkflowDef

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class ReviewScope(BaseModel):
    files: list[str]
    competencies: list[str]


class ReviewFinding(BaseModel):
    severity: Literal["CRITICAL", "REQUIRED", "SUGGESTION"]
    competency: str
    description: str
    file: str | None = None
    line: int | None = None
    fix: str | None = None
    pre_existing: bool = False
    verdict: Literal["FIX", "DEFER", "ACCEPT"] | None = None
    rationale: str | None = None


class CompetencyReview(BaseModel):
    competency: str
    findings: list[ReviewFinding]


class ReviewFindings(BaseModel):
    findings: list[ReviewFinding]
    has_blockers: bool
    verdict: Literal["APPROVE", "APPROVE_WITH_COMMENTS", "REQUEST_CHANGES"]
    triage_table: str | None = None


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="code-review",
    description="Competency-based code review with parallel reviews and synthesis",
    blocks=[
        # Resolve scope: auto-detect base branch if not provided, normalize to three-dot
        ShellStep(
            name="resolve-scope",
            command="python .workflows/code-review/resolve-scope.py {{variables.scope}}",
            result_var="resolved_scope",
        ),

        # Determine scope and select competencies
        LLMStep(
            name="scope",
            prompt="01-scope.md",
            tools=["Bash", "Read", "Glob"],
            model="sonnet",
            output_schema=ReviewScope,
            isolation="subagent",
        ),

        # Parallel competency reviews
        ParallelEachBlock(
            name="reviews",
            parallel_for="results.scope.structured_output.competencies",
            template=[
                ShellStep(
                    name="load-competency",
                    command=(
                        "cat .workflows/code-review/competencies/{{variables.item}}.md "
                        ".workflows/code-review/competencies/{{variables.item}}-platforms/*.md "
                        "2>/dev/null; true"
                    ),
                ),
                LLMStep(
                    name="review",
                    prompt="02-review.md",
                    tools=["Read", "Grep", "Glob"],
                    model="opus",
                    output_schema=CompetencyReview,
                ),
            ],
        ),

        # Synthesize into single report
        LLMStep(
            name="synthesize",
            prompt="03-synthesize.md",
            tools=["Read", "ask_user"],
            output_schema=ReviewFindings,
            model="opus",
        ),

        # Create backlog items for DEFER findings
        LLMStep(
            name="defer-findings",
            prompt="04-defer.md",
            model="sonnet",
            isolation="subagent",
            condition=lambda ctx: any(
                f.get("verdict") == "DEFER"
                for f in (ctx.result_field("synthesize", "findings") or [])
            ),
        ),
    ],
)
