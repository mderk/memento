# ruff: noqa: E501
"""Create-protocol workflow definition.

Takes a PRD (or task description) and generates a structured protocol:
  Phase 1: Read context (PRD, Memory Bank)
  Phase 2: LLM generates structured ProtocolPlan (JSON)
  Phase 3: Renderer writes step files + plan.md
  Phase 4: LLM reviews generated files + presents summary

Expects variables:
  - protocol_dir: path to protocol directory (contains prd.md or will be created)
  - prd_source: optional — raw task description if no prd.md exists
  - workdir: project root directory
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from _dsl import (
        Branch,
        ConditionalBlock,
        LLMStep,
        PromptStep,
        ShellStep,
        WorkflowDef,
    )

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Output schemas (used as json_schema for LLM structured output)
# ---------------------------------------------------------------------------


class TaskItem(BaseModel):
    """A single item in a task group."""

    title: str = Field(description="Short action-oriented title (plain text, one line)")
    body: str = Field(default="", description="Detailed description: rich text with lists, code blocks, examples")
    subtasks: list["TaskItem"] = Field(default_factory=list, description="Nested sub-items")


class Task(BaseModel):
    """A task group — one unit of work in the TDD loop."""

    heading: str = Field(description="Concise, action-oriented title (plain text, one line)")
    description: str = Field(default="", description="Context or explanation for this task group (rich text)")
    subtasks: list[TaskItem] = Field(default_factory=list, description="Items to implement under this task")
    acceptance_criteria: list[str] = Field(default_factory=list, description="2-5 concrete, verifiable statements about what this task must achieve")


class StepDef(BaseModel):
    """A protocol step — a focused unit of work with its own step file."""

    name: str = Field(description="Step title (plain text, one line)")
    objective: str = Field(description="What this step accomplishes and why (rich text)")
    tasks: list[Task] = Field(description="Task groups (each becomes a TDD unit)")
    constraints: list[str] = Field(default_factory=list, description="Acceptance criteria / DoD items (one per entry)")
    impl_notes: str = Field(default="", description="Key files, patterns, approach (rich text)")
    verification: list[str] = Field(default_factory=list, description="Shell commands to verify step works")
    context_inline: str = Field(default="", description="Inline context notes: references to spec sections, architectural decisions, research summaries (rich text)")
    context_files: list[str] = Field(default_factory=list, description="Reference file paths (Memory Bank, _context)")
    starting_points: list[str] = Field(default_factory=list, description="Key source files to start from")
    memory_bank_impact: list[str] = Field(default_factory=list, description="Memory Bank files to update after step")
    estimate: str = Field(description="Time estimate (e.g., '2h', '30m')")


class GroupDef(BaseModel):
    """A group of related steps — rendered as a subdirectory."""

    title: str = Field(description="Group title (plain text, e.g., 'Infrastructure', 'Auth')")
    steps: list[StepDef] = Field(description="Steps within this group")


class ItemWrapper(BaseModel):
    """Discriminated union wrapper for protocol items."""

    type: Literal["step", "group"] = Field(description="'step' for a single step, 'group' for a directory of steps")
    step: StepDef | None = Field(default=None, description="Present when type='step'")
    group: GroupDef | None = Field(default=None, description="Present when type='group'")


class ProtocolPlan(BaseModel):
    """Complete protocol plan — structured input for the renderer."""

    name: str = Field(description="Protocol name (plain text, e.g., 'Admin Dashboard')")
    context: str = Field(description="Brief problem summary, 1-3 sentences (rich text)")
    decision: str = Field(description="Approach and key architectural choices (rich text)")
    rationale: str = Field(description="Why this approach over alternatives (rich text)")
    consequences_positive: list[str] = Field(description="Positive consequences (one per entry)")
    consequences_negative: list[str] = Field(description="Negative consequences with mitigations (one per entry)")
    items: list[ItemWrapper] = Field(description="Protocol items in execution order: steps and groups")


class PrdOutput(BaseModel):
    """Structured PRD generated from a task description."""

    title: str = Field(description="Feature name")
    problem_statement: str = Field(description="What needs to be solved")
    requirements: list[str] = Field(description="Functional and non-functional requirements")
    constraints: list[str] = Field(description="Technical constraints, timeline, resources")
    acceptance_criteria: list[str] = Field(description="How to verify the feature is complete")


# ---------------------------------------------------------------------------
# Helpers path (relative to workflow dir, resolved by engine)
# ---------------------------------------------------------------------------

_PROTOCOL_MD = "../process-protocol/protocol_md.py"

# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="create-protocol",
    description="Create a protocol structure from a PRD with structured output + renderer",
    blocks=[
        # Step 1: Ensure prd.md exists — generate from task description if needed
        LLMStep(
            name="ensure-prd",
            prompt="01-ensure-prd.md",
            tools=["Read", "Write"],
            output_schema=PrdOutput,
            condition=lambda ctx: bool(ctx.variables.get("prd_source")),
        ),
        ShellStep(
            name="write-prd",
            script="write-prd.py",
            args="{{variables.protocol_dir}}",
            env={"PRD_JSON": "{{results.ensure-prd.structured_output}}"},
            condition=lambda ctx: bool(ctx.variables.get("prd_source")),
        ),

        # Step 2: Check if plan.json already exists
        ShellStep(
            name="check-plan-exists",
            command='test -f "{{variables.protocol_dir}}/plan.json" && echo \'{"exists": true}\' || echo \'{"exists": false}\'',
            result_var="plan_check",
        ),

        # Step 3a: Edit existing plan (when plan.json exists)
        ShellStep(
            name="load-plan-json",
            command='cat "{{variables.protocol_dir}}/plan.json"',
            condition=lambda ctx: ctx.variables.get("plan_check", {}).get("exists") is True,
        ),
        PromptStep(
            name="ask-edit-instructions",
            prompt_type="input",
            message="Protocol already has a plan. What do you want to change? (or 'regenerate' to start fresh)",
            condition=lambda ctx: ctx.variables.get("plan_check", {}).get("exists") is True,
            result_var="edit_instructions",
        ),

        # Step 3a-edit: LLM edits existing plan with user instructions
        LLMStep(
            name="edit-plan",
            prompt="02b-edit-plan.md",
            tools=["Read", "Glob", "Grep"],
            output_schema=ProtocolPlan,
            condition=lambda ctx: (
                ctx.variables.get("plan_check", {}).get("exists") is True
                and ctx.variables.get("edit_instructions", "") != "regenerate"
            ),
        ),

        # Step 3b: Generate fresh plan (when no plan.json or user chose 'regenerate')
        LLMStep(
            name="plan-protocol",
            prompt="02-plan-protocol.md",
            tools=["Read", "Glob", "Grep"],
            output_schema=ProtocolPlan,
            condition=lambda ctx: (
                ctx.variables.get("plan_check", {}).get("exists") is not True
                or ctx.variables.get("edit_instructions", "") == "regenerate"
            ),
        ),

        # Step 4: Save plan.json (from whichever flow produced it)
        # Note: check status == "success", not just `is not None` — skipped steps produce
        # a StepResult with status="skipped" which is truthy but has no structured_output.
        ShellStep(
            name="save-plan-json",
            script="save-plan-json.py",
            args='"{{variables.protocol_dir}}"',
            stdin="{{results.edit-plan.structured_output}}",
            condition=lambda ctx: getattr(ctx.results.get("edit-plan"), "status", None) == "success",
        ),
        ShellStep(
            name="save-plan-json-fresh",
            script="save-plan-json.py",
            args='"{{variables.protocol_dir}}"',
            stdin="{{results.plan-protocol.structured_output}}",
            condition=lambda ctx: (
                getattr(ctx.results.get("edit-plan"), "status", None) != "success"
                and getattr(ctx.results.get("plan-protocol"), "status", None) == "success"
            ),
        ),

        # Step 5: Render protocol files from structured JSON
        ShellStep(
            name="render-protocol",
            script=_PROTOCOL_MD,
            args='render-protocol --stdin "{{variables.protocol_dir}}"',
            stdin="{{results.edit-plan.structured_output}}",
            result_var="render_result",
            condition=lambda ctx: getattr(ctx.results.get("edit-plan"), "status", None) == "success",
        ),
        ShellStep(
            name="render-protocol-fresh",
            script=_PROTOCOL_MD,
            args='render-protocol --stdin "{{variables.protocol_dir}}"',
            stdin="{{results.plan-protocol.structured_output}}",
            result_var="render_result",
            condition=lambda ctx: getattr(ctx.results.get("edit-plan"), "status", None) != "success",
        ),

        # Step 6: Review and present summary
        LLMStep(
            name="review",
            prompt="03-review.md",
            tools=["Read"],
        ),
    ],
)
