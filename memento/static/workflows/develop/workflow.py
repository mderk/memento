# ruff: noqa: E501
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

Engine types (WorkflowDef, LLMStep, etc.) are injected by the loader at runtime.
Import _dsl for static analysis only (no-op at runtime).
"""
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from _dsl import (
        GroupBlock,
        LLMStep,
        LoopBlock,
        RetryBlock,
        ShellStep,
        SubWorkflow,
        WorkflowDef,
    )

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


def _verify_fix_passed(ctx, prefix: str = "verify-after-custom") -> bool:
    """Check whether the last verify-fix run under a given subworkflow prefix passed.

    Note: SubWorkflow restores variables on exit, so we must read from results.
    Returns True if no such results exist (i.e., verify-fix wasn't run).
    """
    lint_status = ctx.get_var(f"results.{prefix}.lint.structured_output.status")
    test_status = ctx.get_var(f"results.{prefix}.test.structured_output.status")
    if lint_status is None and test_status is None:
        return True
    return lint_status in ("clean", "skipped") and test_status == "green"


def _make_tdd_blocks():
    """Create fresh TDD block instances (write-tests -> verify-red -> implement -> green-loop)."""
    return [
        ShellStep(
            name="init-vars",
            command='echo \'{"status":"skipped","note":"verify-red not yet run"}\'',
            result_var="verify_red",
        ),
        LLMStep(
            name="write-tests",
            prompt="03a-write-tests.md",
            tools=["Read", "Write", "Edit", "Glob", "Grep"],
        ),
        ShellStep(
            name="verify-red",
            script=_TOOLS,
            args="test --scope specific --files-json '{{variables.unit.test_files}}' --workdir {{variables.workdir}}",
            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="verify_red",
            condition=lambda ctx: (
                ctx.result_field("classify", "type") != "refactor"
                and bool(ctx.variables.get("unit", {}).get("test_files"))
            ),
        ),
        LLMStep(
            name="implement",
            prompt="03c-implement.md",
            tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        ),
        SubWorkflow(
            name="green-loop",
            workflow="verify-fix",
            inject={"workdir": "{{variables.workdir}}", "scope": "{{results.classify.structured_output.scope}}"},
        ),
    ]


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

        # Load project commands for use in prompts
        ShellStep(
            name="load-commands",
            script=_TOOLS,
            args="commands --workdir {{variables.workdir}}",
            result_var="commands",
        ),

        # Phase 1: Explore (skip for fast_track and protocol mode)
        LLMStep(
            name="explore",
            prompt="01-explore.md",
            tools=["Read", "Glob", "Grep"],
            model="haiku",
            isolation="subagent",
            output_schema=ExploreOutput,
            condition=lambda ctx: not ctx.result_field("classify", "fast_track") and ctx.variables.get("mode") != "protocol",
        ),

        # Phase 2: Plan (skip for fast_track and protocol mode)
        LLMStep(
            name="plan",
            prompt="02-plan.md",
            tools=["Read"],
            output_schema=PlanOutput,
            condition=lambda ctx: not ctx.result_field("classify", "fast_track") and ctx.variables.get("mode") != "protocol",
        ),

        # Phase 3: TDD loop per task (skip for fast_track and protocol)
        LoopBlock(
            name="implement",
            loop_over="results.plan.structured_output.tasks",
            loop_var="unit",
            condition=lambda ctx: not ctx.result_field("classify", "fast_track") and ctx.variables.get("mode") != "protocol",
            blocks=_make_tdd_blocks(),
        ),

        # Phase 3 (protocol): TDD loop over units parsed from step file
        LoopBlock(
            name="protocol-implement",
            loop_over="variables.units",
            loop_var="unit",
            condition=lambda ctx: ctx.variables.get("mode") == "protocol" and not ctx.result_field("classify", "fast_track"),
            blocks=_make_tdd_blocks(),
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
                SubWorkflow(
                    name="fast-verify",
                    workflow="verify-fix",
                    inject={"workdir": "{{variables.workdir}}", "scope": "{{results.classify.structured_output.scope}}"},
                ),
            ],
        ),

        # Protocol-specific verification (runs after TDD or fast-track completes).
        #
        # Staged structure:
        #   1) Run verify-custom once
        #   2) If failing, retry:
        #        - LLM fixes based on verify_custom output
        #        - run normal verify-fix loop (lint + tests)
        #        - re-run verify-custom
        ShellStep(
            name="verify-custom",
            script=_TOOLS,
            args="verify --commands-json '{{variables.verification_commands}}' --workdir {{variables.workdir}}",
            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="verify_custom",
            condition=lambda ctx: bool(ctx.variables.get("verification_commands")),
        ),
        RetryBlock(
            name="verify-custom-retry",
            condition=lambda ctx: (
                bool(ctx.variables.get("verification_commands"))
                and (
                    ctx.variables.get("verify_custom", {}).get("status") != "pass"
                    or not _verify_fix_passed(ctx)
                )
            ),
            until=lambda ctx: (
                ctx.variables.get("verify_custom", {}).get("status") == "pass"
                and _verify_fix_passed(ctx)
            ),
            max_attempts=3,
            blocks=[
                LLMStep(
                    name="fix-verify-custom",
                    prompt="03f-fix-verify-custom.md",
                    tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                    condition=lambda ctx: ctx.variables.get("verify_custom", {}).get("status") != "pass",
                ),
                SubWorkflow(
                    name="verify-after-custom",
                    workflow="verify-fix",
                    inject={"workdir": "{{variables.workdir}}", "scope": "{{results.classify.structured_output.scope}}"},
                ),
                ShellStep(
                    name="re-verify-custom",
                    script=_TOOLS,
                    args="verify --commands-json '{{variables.verification_commands}}' --workdir {{variables.workdir}}",
                    env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="verify_custom",
                ),
            ],
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
                "VERIFY_CUSTOM": "{{variables.verify_custom}}",
                "VERIFY_AFTER_CUSTOM_LINT": "{{results.verify-after-custom.lint.structured_output}}",
                "VERIFY_AFTER_CUSTOM_TEST": "{{results.verify-after-custom.test.structured_output}}",
            },
            result_var="protocol_result",
            condition=lambda ctx: ctx.variables.get("mode") == "protocol",
        ),
    ],
)
