# pyright: reportUndefinedVariable=false
"""Development workflow definition.

Maps to the 5-phase development workflow:
  Phase 0: Classify (top-level, results accessible everywhere)
  Phase 1: Explore (subagent, skipped for fast_track)
  Phase 2: Plan (structured output, skipped for fast_track)
  Phase 3: TDD loop per task / fast-track for trivial changes
  Phase 4: Code review (parallel competency checks)
  Phase 5: Completion report

Engine types (WorkflowDef, LLMStep, etc.) are injected by the loader — no imports needed.
"""

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class ClassifyOutput(BaseModel):
    scope: Literal["backend", "frontend", "fullstack"]
    type: Literal["bug", "feature", "refactor", "documentation"]
    complexity: Literal["trivial", "simple", "complex"]
    fast_track: bool
    relevant_guides: list[str]


class PlanTask(BaseModel):
    id: str
    description: str
    files: list[str]
    test_files: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    tasks: list[PlanTask]


class TestStatus(BaseModel):
    status: Literal["red", "green", "error"]
    failures: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="development",
    description="Full development workflow with TDD, code review, and completion report",
    blocks=[
        # Phase 0: Classify (top-level — results accessible everywhere)
        LLMStep(
            name="classify",
            prompt="00-classify.md",
            tools=["Read", "Glob"],
            model="sonnet",
            output_schema=ClassifyOutput,
        ),

        # Phase 1: Explore (skip for fast_track; subagent preserves main context)
        LLMStep(
            name="explore",
            prompt="01-explore.md",
            tools=["Read", "Glob", "Grep"],
            model="sonnet",
            isolation="subagent",
            condition=lambda ctx: not ctx.result_field("classify", "fast_track"),
        ),

        # Phase 2: Plan (skip for fast_track)
        LLMStep(
            name="plan",
            prompt="02-plan.md",
            tools=["Read"],
            output_schema=PlanOutput,
            condition=lambda ctx: not ctx.result_field("classify", "fast_track"),
        ),

        # Phase 3: TDD loop per task (skip for fast_track)
        LoopBlock(
            name="implement",
            loop_over="results.plan.structured_output.tasks",
            loop_var="unit",
            condition=lambda ctx: not ctx.result_field("classify", "fast_track"),
            blocks=[
                LLMStep(
                    name="write-tests",
                    prompt="03a-write-tests.md",
                    tools=["Read", "Write", "Edit", "Glob", "Grep"],
                ),
                LLMStep(
                    name="verify-red",
                    prompt="03b-verify-red.md",
                    tools=["Bash", "Read"],
                    model="haiku",
                    output_schema=TestStatus,
                    # Skip RED verification for pure refactors (existing tests are spec)
                    condition=lambda ctx: ctx.result_field("classify", "type") != "refactor",
                ),
                LLMStep(
                    name="implement",
                    prompt="03c-implement.md",
                    tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                ),
                RetryBlock(
                    name="green-loop",
                    until=lambda ctx: ctx.result_field("verify-green", "status") == "green",
                    max_attempts=3,
                    blocks=[
                        LLMStep(
                            name="verify-green",
                            prompt="03d-verify-green.md",
                            tools=["Bash", "Read"],
                            model="haiku",
                            output_schema=TestStatus,
                        ),
                        LLMStep(
                            name="fix",
                            prompt="03e-fix.md",
                            tools=["Read", "Write", "Edit", "Bash"],
                            condition=lambda ctx: ctx.result_field("verify-green", "status") != "green",
                        ),
                    ],
                ),
            ],
        ),

        # Phase 3 (fast track): implement trivial change + verify in one step
        LLMStep(
            name="fast-track",
            prompt="04-fast-track.md",
            tools=["Read", "Write", "Edit", "Bash", "Glob"],
            condition=lambda ctx: ctx.result_field("classify", "fast_track") is True,
        ),

        # Phase 4: Code review (sub-workflow; skip in protocol mode)
        SubWorkflow(
            name="review",
            workflow="code-review",
            condition=lambda ctx: ctx.variables.get("mode") != "protocol",
        ),

        # Phase 5: Completion (skip in protocol mode)
        LLMStep(
            name="complete",
            prompt="05-complete.md",
            tools=["Read", "Write"],
            model="haiku",
            condition=lambda ctx: ctx.variables.get("mode") != "protocol",
        ),
    ],
)
