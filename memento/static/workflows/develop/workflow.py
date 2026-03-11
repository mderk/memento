# pyright: reportUndefinedVariable=false
"""Development workflow definition.

Maps to the 5-phase development workflow:
  Phase 0: Classify (top-level, results accessible everywhere)
  Phase 1: Explore (subagent, skipped for fast_track)
  Phase 2: Plan (structured output, skipped for fast_track)
  Phase 3: TDD loop per task / fast-track for trivial changes
  Phase 4: Code review (parallel competency checks)
  Phase 5: Completion report / protocol artifact

Lint/test verification runs as ShellStep via dev-tools.py — no LLM tokens spent.
LLM is only invoked for creative work (explore, plan, write tests, implement, fix).

Engine types (WorkflowDef, LLMStep, etc.) are injected by the loader — no imports needed.
"""

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    tag: Literal["DECISION", "GOTCHA", "REUSE"]
    text: str


class ClassifyOutput(BaseModel):
    scope: Literal["backend", "frontend", "fullstack"]
    type: Literal["bug", "feature", "refactor", "documentation"]
    complexity: Literal["trivial", "simple", "complex"]
    fast_track: bool
    relevant_guides: list[str]


class ExploreOutput(BaseModel):
    files_to_modify: list[str]
    reference_files: list[str]
    existing_tests: list[str]
    patterns: list[str]
    findings: list[Finding] = Field(default_factory=list)


class PlanTask(BaseModel):
    id: str
    description: str
    files: list[str]
    test_files: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    tasks: list[PlanTask]
    findings: list[Finding] = Field(default_factory=list)


class DevelopResult(BaseModel):
    summary: str
    files_changed: list[str]
    findings: list[Finding] = Field(default_factory=list)


# dev-tools.py path (resolved relative to workflow_dir by engine)
_TOOLS = "dev-tools.py"


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
            model="haiku",
            isolation="subagent",
            output_schema=ExploreOutput,
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
                # 3a: Write tests (LLM — creative)
                LLMStep(
                    name="write-tests",
                    prompt="03a-write-tests.md",
                    tools=["Read", "Write", "Edit", "Glob", "Grep"],
                ),

                # 3b: Verify RED — tests should fail (ShellStep — zero tokens)
                ShellStep(
                    name="verify-red",
                    script=_TOOLS,
                    args="test --scope specific --files-json '{{variables.unit.test_files}}' --workdir {{variables.workdir}}",
                    env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="verify_red",
                    # Skip for refactors (existing tests are the spec)
                    condition=lambda ctx: ctx.result_field("classify", "type") != "refactor",
                ),

                # 3c: Implement (LLM — creative)
                LLMStep(
                    name="implement",
                    prompt="03c-implement.md",
                    tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                ),

                # 3d-3e: Lint + test green loop (ShellStep + LLM fix)
                RetryBlock(
                    name="green-loop",
                    until=lambda ctx: (
                        ctx.variables.get("lint_result", {}).get("status") == "clean"
                        and ctx.variables.get("verify_green", {}).get("status") == "green"
                    ),
                    max_attempts=3,
                    blocks=[
                        ShellStep(
                            name="lint",
                            script=_TOOLS,
                            args="lint --scope changed --workdir {{variables.workdir}}",
                            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                            result_var="lint_result",
                        ),
                        ShellStep(
                            name="verify-green",
                            script=_TOOLS,
                            args="test --scope all --workdir {{variables.workdir}}",
                            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                            result_var="verify_green",
                        ),
                        LLMStep(
                            name="fix",
                            prompt="03e-fix.md",
                            tools=["Read", "Write", "Edit", "Bash"],
                            condition=lambda ctx: (
                                ctx.variables.get("lint_result", {}).get("status") != "clean"
                                or ctx.variables.get("verify_green", {}).get("status") != "green"
                            ),
                        ),
                    ],
                ),
            ],
        ),

        # Phase 3 (fast track): implement trivial change, verify with retry loop
        GroupBlock(
            name="fast-track",
            condition=lambda ctx: ctx.result_field("classify", "fast_track") is True,
            blocks=[
                LLMStep(
                    name="fast-implement",
                    prompt="04-fast-track.md",
                    tools=["Read", "Write", "Edit", "Glob"],
                ),
                RetryBlock(
                    name="fast-verify",
                    until=lambda ctx: (
                        ctx.variables.get("lint_result", {}).get("status") == "clean"
                        and ctx.variables.get("verify_green", {}).get("status") == "green"
                    ),
                    max_attempts=3,
                    blocks=[
                        ShellStep(
                            name="fast-lint",
                            script=_TOOLS,
                            args="lint --scope changed --workdir {{variables.workdir}}",
                            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                            result_var="lint_result",
                        ),
                        ShellStep(
                            name="fast-test",
                            script=_TOOLS,
                            args="test --scope all --workdir {{variables.workdir}}",
                            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                            result_var="verify_green",
                        ),
                        LLMStep(
                            name="fast-fix",
                            prompt="03e-fix.md",
                            tools=["Read", "Write", "Edit", "Bash"],
                            condition=lambda ctx: (
                                ctx.variables.get("lint_result", {}).get("status") != "clean"
                                or ctx.variables.get("verify_green", {}).get("status") != "green"
                            ),
                        ),
                    ],
                ),
            ],
        ),

        # Protocol-specific verification (runs after TDD or fast-track completes)
        ShellStep(
            name="verify-custom",
            script=_TOOLS,
            args="verify --commands-json '{{variables.verification_commands}}' --workdir {{variables.workdir}}",
            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="verify_custom",
            condition=lambda ctx: bool(ctx.variables.get("verification_commands")),
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

        # Phase 5 (protocol): Collect result artifact for parent workflow
        # Writes JSON to {workdir}/.dev-result.json for parent consumption
        # (subagent boundary means parent can't access child variables directly)
        ShellStep(
            name="protocol-complete",
            script="collect-result.py",
            args="--workdir {{variables.workdir}}",
            env={
                "EXPLORE_FINDINGS": "{{results.explore.structured_output.findings}}",
                "PLAN_FINDINGS": "{{results.plan.structured_output.findings}}",
            },
            result_var="protocol_result",
            condition=lambda ctx: ctx.variables.get("mode") == "protocol",
        ),
    ],
)
