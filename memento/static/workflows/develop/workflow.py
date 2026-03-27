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
        Branch,
        ConditionalBlock,
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
    depends_on: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    tasks: list[PlanTask]
    findings: list[Finding] = Field(default_factory=list)


class AcceptanceOutput(BaseModel):
    covered: list[str] = Field(description="criterion → evidence (impl + test)")
    missing: list[str] = Field(description="criterion → what's missing")
    passed: bool = Field(description="True only if missing is empty")


class AcceptanceTestsOutput(BaseModel):
    test_files: list[str]


class WriteTestsOutput(BaseModel):
    test_files: list[str]


class EnrichedUnit(BaseModel):
    id: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class EnrichCriteriaOutput(BaseModel):
    units: list[EnrichedUnit]


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


def _acceptance_passed(ctx) -> bool:
    """Check whether the acceptance check passed (all requirements covered)."""
    result = ctx.result_field("acceptance-check", "passed")
    if result is None:
        return True
    return result is True


def _verify(name, changed_only=False, condition=None):
    """Create a verify-fix SubWorkflow with standard inject."""
    inject = {
        "workdir": "{{variables.workdir}}",
        "scope": "{{results.classify.structured_output.scope}}",
    }
    if changed_only:
        inject["test_scope"] = "changed"
    if condition:
        return SubWorkflow(name=name, workflow="verify-fix", inject=inject, condition=condition)
    return SubWorkflow(name=name, workflow="verify-fix", inject=inject)


def _make_acceptance_check():
    """Create an acceptance-check LLMStep (used in initial check and retry loop)."""
    return LLMStep(
        name="acceptance-check",
        prompt="03g-acceptance-check.md",
        tools=["Read", "Glob", "Grep", "Bash"],
        model="sonnet",
        output_schema=AcceptanceOutput,
        isolation="subagent",
    )


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
            model="sonnet",
            output_schema=WriteTestsOutput,
            isolation="subagent",
        ),
        ShellStep(
            name="verify-red",
            script=_TOOLS,
            args="test --scope specific --files-json '{{results.write-tests.structured_output.test_files}}' --workdir {{variables.workdir}}",
            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="verify_red",
            condition=lambda ctx: (
                ctx.result_field("classify", "type") != "refactor"
                and bool(ctx.result_field("write-tests", "test_files"))
            ),
        ),
        LLMStep(
            name="implement",
            model="opus",
            prompt="03c-implement.md",
            tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        ),
        # Check if implement actually changed files — skip verify if no-op
        ShellStep(
            name="check-changes",
            command='cd "{{variables.workdir}}" && git diff --quiet && echo \'{"changed": false}\' || echo \'{"changed": true}\'',
            result_var="impl_changes",
        ),
        _verify("green-loop", changed_only=True, condition=lambda ctx: (
            ctx.variables.get("impl_changes", {}).get("changed") is True
        )),
    ]


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="development",
    description="Full development workflow with TDD, code review, and completion report",
    blocks=[
        # ── Phase 0: Classify ────────────────────────────────────────────
        LLMStep(
            name="classify",
            prompt="00-classify.md",
            tools=["Read", "Glob"],
            model="sonnet",
            output_schema=ClassifyOutput,
        ),
        # Inject task + classification on cross-conversation resume
        LLMStep(
            name="resume-context",
            prompt="00r-resume-context.md",
            tools=[],
            model="haiku",
            resume_only="true",
        ),
        # Load project commands for use in prompts
        ShellStep(
            name="load-commands",
            script=_TOOLS,
            args="commands --workdir {{variables.workdir}}",
            result_var="commands",
        ),

        # ── Phase 1-3: Development (three-way branch) ───────────────────
        ConditionalBlock(
            name="develop",
            branches=[
                # Fast track: trivial change → implement + verify
                Branch(
                    condition=lambda ctx: ctx.result_field("classify", "fast_track") is True,
                    blocks=[
                        LLMStep(
                            name="fast-implement",
                            prompt="04-fast-track.md",
                            tools=["Read", "Write", "Edit", "Glob"],
                            model="sonnet",
                        ),
                        _verify("fast-verify"),
                    ],
                ),
                # Protocol: enrich criteria if missing + TDD loop over protocol units
                Branch(
                    condition=lambda ctx: ctx.variables.get("mode") == "protocol",
                    blocks=[
                        # Enrich units with acceptance criteria when step files lack them.
                        # Skipped when all units already have criteria (e.g. from create-protocol).
                        LLMStep(
                            name="enrich-criteria",
                            prompt="02p-enrich-criteria.md",
                            tools=["Read"],
                            model="sonnet",
                            output_schema=EnrichCriteriaOutput,
                            isolation="subagent",
                            result_var="units",
                            condition=lambda ctx: any(
                                not u.get("acceptance_criteria")
                                for u in (ctx.variables.get("units") or [])
                            ),
                        ),
                        # TDD loop over units parsed from step file
                        LoopBlock(
                            name="protocol-implement",
                            loop_over="variables.units",
                            loop_var="unit",
                            blocks=_make_tdd_blocks(),
                        ),
                    ],
                ),
            ],
            # Default: normal mode — explore → plan → TDD loop
            default=[
                # Phase 1: Explore codebase (subagent)
                LLMStep(
                    name="explore",
                    prompt="01-explore.md",
                    tools=["Read", "Glob", "Grep"],
                    model="haiku",
                    isolation="subagent",
                    output_schema=ExploreOutput,
                ),
                # Phase 2: Plan implementation tasks
                LLMStep(
                    name="plan",
                    prompt="02-plan.md",
                    tools=["Read"],
                    model="opus",
                    output_schema=PlanOutput,
                ),
                ShellStep(
                    name="set-units-from-plan",
                    command="cat",
                    stdin="{{results.plan.structured_output.tasks}}",
                    result_var="units",
                ),
                # Phase 3: TDD loop per task
                LoopBlock(
                    name="implement",
                    loop_over="results.plan.structured_output.tasks",
                    loop_var="unit",
                    blocks=_make_tdd_blocks(),
                ),
            ],
        ),

        # ── Protocol-specific verification (orthogonal to mode branch) ──
        ShellStep(
            name="verify-custom",
            script=_TOOLS,
            args="verify --workdir {{variables.workdir}}",
            env={
                "DEV_TOOLS_WORKDIR": "{{variables.workdir}}",
                "VERIFY_COMMANDS_JSON": "{{variables.verification_commands}}",
            },
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
                    model="sonnet",
                    condition=lambda ctx: (
                        ctx.variables.get("verify_custom", {}).get("status") != "pass"
                    ),
                ),
                _verify("verify-after-custom", changed_only=True),
                ShellStep(
                    name="re-verify-custom",
                    script=_TOOLS,
                    args="verify --commands-json '{{variables.verification_commands}}' --workdir {{variables.workdir}}",
                    env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="verify_custom",
                ),
            ],
        ),

        # ── Quality gates (skip for fast_track) ─────────────────────────
        GroupBlock(
            name="quality-gates",
            condition=lambda ctx: not ctx.result_field("classify", "fast_track"),
            blocks=[
                # Coverage: check + retry loop until gaps closed or stagnation
                ShellStep(
                    name="coverage-check",
                    script=_TOOLS,
                    args="coverage --workdir {{variables.workdir}}",
                    result_var="coverage",
                ),
                RetryBlock(
                    name="coverage-retry",
                    condition=lambda ctx: ctx.variables.get("coverage", {}).get("has_gaps", False),
                    until=lambda ctx: (
                        not ctx.variables.get("coverage", {}).get("has_gaps", False)
                        or (
                            ctx.variables.get("_prev_coverage") is not None
                            and ctx.variables.get("_prev_coverage")
                            == ctx.variables.get("coverage", {}).get("overall_coverage")
                        )
                    ),
                    max_attempts=3,
                    blocks=[
                        ShellStep(
                            name="save-prev-coverage",
                            command="echo {{variables.coverage.overall_coverage}}",
                            result_var="_prev_coverage",
                        ),
                        LLMStep(
                            name="coverage-fill",
                            prompt="03d-coverage.md",
                            tools=["Read", "Write", "Edit", "Glob", "Grep"],
                            model="sonnet",
                        ),
                        _verify("verify-after-coverage"),
                        ShellStep(
                            name="re-coverage-check",
                            script=_TOOLS,
                            args="coverage --workdir {{variables.workdir}}",
                            result_var="coverage",
                        ),
                    ],
                ),
                # Acceptance: audit diff against task requirements
                _make_acceptance_check(),
                RetryBlock(
                    name="acceptance-retry",
                    condition=lambda ctx: not _acceptance_passed(ctx),
                    until=lambda ctx: (
                        _acceptance_passed(ctx)
                        and _verify_fix_passed(ctx, prefix="verify-after-acceptance")
                    ),
                    max_attempts=2,
                    blocks=[
                        LLMStep(
                            name="write-acceptance-tests",
                            prompt="03h-acceptance-tests.md",
                            tools=["Read", "Write", "Edit", "Glob", "Grep"],
                            model="sonnet",
                            output_schema=AcceptanceTestsOutput,
                        ),
                        ShellStep(
                            name="verify-acceptance-red",
                            script=_TOOLS,
                            args="test --scope specific --files-json '{{results.write-acceptance-tests.structured_output.test_files}}' --workdir {{variables.workdir}}",
                            env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                            result_var="verify_acceptance_red",
                        ),
                        LLMStep(
                            name="implement-acceptance",
                            prompt="03i-acceptance-impl.md",
                            tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                            model="sonnet",
                            condition=lambda ctx: (
                                ctx.variables.get("verify_acceptance_red", {}).get("status")
                                != "green"
                            ),
                        ),
                        _verify("verify-after-acceptance", changed_only=True),
                        _make_acceptance_check(),
                    ],
                ),
                # Final full verification — single gate before review/completion.
                # All intermediate verify-fix calls use test_scope="changed" for speed;
                # this is the only full lint+test run.
                _verify("full-verify"),
            ],
        ),

        # ── Phase 4-5: Review & Completion ───────────────────────────────
        ConditionalBlock(
            name="completion",
            branches=[
                # Protocol: collect result artifact for parent workflow
                Branch(
                    condition=lambda ctx: ctx.variables.get("mode") == "protocol",
                    blocks=[
                        # Writes JSON to --output path for parent workflow consumption
                        # (subagent boundary means parent can't access child variables directly)
                        ShellStep(
                            name="protocol-complete",
                            script="collect-result.py",
                            args="--workdir {{variables.workdir}} --output {{variables.dev_result_path}}",
                            env={
                                "EXPLORE_FINDINGS": "{{results.explore.structured_output.findings}}",
                                "PLAN_FINDINGS": "{{results.plan.structured_output.findings}}",
                                "VERIFY_CUSTOM": "{{variables.verify_custom}}",
                                "VERIFY_AFTER_CUSTOM_LINT": "{{results.verify-after-custom.lint.structured_output}}",
                                "VERIFY_AFTER_CUSTOM_TEST": "{{results.verify-after-custom.test.structured_output}}",
                                "ACCEPTANCE_RESULT": "{{results.acceptance-check.structured_output}}",
                            },
                            result_var="protocol_result",
                        ),
                    ],
                ),
            ],
            # Default: code review + fix loop + completion report
            default=[
                # Phase 4: Code review (parallel competency checks)
                SubWorkflow(
                    name="review",
                    workflow="code-review",
                ),
                # Fix review findings loop — skip if APPROVE, exit if blockers resolved
                RetryBlock(
                    name="fix-review",
                    condition=lambda ctx: ctx.result_field("review.synthesize", "has_blockers"),
                    until=lambda ctx: (
                        not ctx.result_field("re-review.synthesize", "has_blockers")
                        or ctx.variables.get("review_fix_changes", {}).get("changed") is False
                    ),
                    max_attempts=3,
                    blocks=[
                        LLMStep(
                            name="fix-issues",
                            prompt="fix-review.md",
                            model="opus",
                            tools=["Read", "Write", "Edit", "Bash"],
                        ),
                        ShellStep(
                            name="check-review-fix-changes",
                            command='cd "{{variables.workdir}}" && git diff --quiet && echo \'{"changed": false}\' || echo \'{"changed": true}\'',
                            result_var="review_fix_changes",
                        ),
                        _verify("verify-fixes", changed_only=True, condition=lambda ctx: (
                            ctx.variables.get("review_fix_changes", {}).get("changed")
                            is True
                        )),
                        SubWorkflow(
                            name="re-review",
                            workflow="code-review",
                            inject={"workdir": "{{variables.workdir}}"},
                            condition=lambda ctx: (
                                ctx.variables.get("review_fix_changes", {}).get("changed")
                                is True
                            ),
                        ),
                    ],
                ),
                # Phase 5: Completion report
                LLMStep(
                    name="complete",
                    prompt="05-complete.md",
                    tools=["Read", "Write"],
                    model="haiku",
                ),
            ],
        ),
    ],
)
