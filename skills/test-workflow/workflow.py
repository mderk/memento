"""Comprehensive test workflow exercising the engine block types.

Covers: ShellStep, PromptStep, ConditionalBlock, LoopBlock, RetryBlock,
SubWorkflow, LLMStep, GroupBlock, ParallelEachBlock — plus condition skipping,
result_var, key≠name, nested combinations (Loop>Retry, Conditional>Parallel),
and LLM ask_user tool in single/group/parallel modes.

Phases 10-13 (LLM without ask_user) are enabled when mode=thorough.
Phases 14-16 (LLM with ask_user) are enabled when mode=thorough.
"""

from pydantic import BaseModel


class SummaryOutput(BaseModel):
    total_items: int
    status: str
    notes: str


WORKFLOW = WorkflowDef(
    name="test-workflow",
    description="Comprehensive engine test: all 9 block types + ask_user, 18 phases",
    blocks=[
        # --- Phase 1: Detection (shell + result_var) ---
        ShellStep(
            name="detect",
            command="echo '{\"items\": [\"alpha\", \"beta\", \"gamma\"], \"count\": 3}'",
            result_var="detect_result",
        ),

        # --- Phase 2: Choice prompt (stop #1) ---
        PromptStep(
            name="mode",
            prompt_type="choice",
            message="Detected {{results.detect.structured_output.count}} items. Choose mode:",
            options=["quick", "thorough"],
            default="quick",
        ),

        # --- Phase 3: Branching on choice ---
        ConditionalBlock(
            name="mode-branch",
            branches=[
                # Branch: quick — single shell step
                Branch(
                    condition=lambda ctx: ctx.results.get("mode") and ctx.results["mode"].output == "quick",
                    blocks=[
                        ShellStep(
                            name="quick-run",
                            command="echo 'Quick mode: processed all items'",
                        ),
                    ],
                ),
                # Branch: thorough — loop over items
                Branch(
                    condition=lambda ctx: ctx.results.get("mode") and ctx.results["mode"].output == "thorough",
                    blocks=[
                        LoopBlock(
                            name="thorough-scan",
                            loop_over="results.detect.structured_output.items",
                            loop_var="scan_item",
                            blocks=[
                                ShellStep(
                                    name="scan",
                                    command="echo 'Thorough scan: {{variables.scan_item}}'",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
            default=[
                ShellStep(
                    name="fallback",
                    command="echo 'Fallback: unknown mode'",
                ),
            ],
        ),

        # --- Phase 4: Loop over detected items ---
        LoopBlock(
            name="process-items",
            loop_over="results.detect.structured_output.items",
            loop_var="current_item",
            blocks=[
                ShellStep(
                    name="process",
                    command="echo 'Processing: {{variables.current_item}}'",
                ),
            ],
        ),

        # --- Phase 5: Error + conditional recovery ---
        ShellStep(
            name="risky-step",
            command="echo 'simulated failure' >&2 && exit 1",
        ),
        ShellStep(
            name="recovery",
            command="echo 'Recovered from failure'",
            condition=lambda ctx: (
                ctx.results.get("risky-step") is not None
                and ctx.results["risky-step"].status == "failure"
            ),
        ),
        ShellStep(
            name="skip-on-success",
            command="echo 'BUG: this should not run'",
            condition=lambda ctx: (
                ctx.results.get("risky-step") is not None
                and ctx.results["risky-step"].status == "success"
            ),
        ),

        # --- Phase 6: Setup counter dir for retry tests ---
        ShellStep(
            name="setup-counter-dir",
            command="mkdir -p {{cwd}}/.workflow-state/{{variables.run_id}}",
        ),

        # --- Phase 7: RetryBlock ---
        RetryBlock(
            name="retry-flaky",
            max_attempts=5,
            until=lambda ctx: (
                ctx.results.get("flaky-cmd") is not None
                and ctx.results["flaky-cmd"].status == "success"
            ),
            blocks=[
                ShellStep(
                    name="flaky-cmd",
                    command=(
                        "DIR={{cwd}}/.workflow-state/{{variables.run_id}} && "
                        "COUNT=$(cat $DIR/retry 2>/dev/null || echo 0) && "
                        "COUNT=$((COUNT + 1)) && "
                        "echo $COUNT > $DIR/retry && "
                        "if [ $COUNT -lt 3 ]; then echo 'fail' >&2 && exit 1; else echo 'OK'; fi"
                    ),
                ),
            ],
        ),

        # --- Phase 8: SubWorkflow ---
        SubWorkflow(
            name="call-helper",
            workflow="test-helper",
            inject={"helper_input": "{{results.detect.structured_output.count}}"},
        ),

        # --- Phase 9: Loop + Retry combo ---
        LoopBlock(
            name="loop-retry-items",
            loop_over="results.detect.structured_output.items",
            loop_var="loop_item",
            blocks=[
                RetryBlock(
                    name="item-retry",
                    max_attempts=4,
                    until=lambda ctx: (
                        ctx.results.get("item-flaky") is not None
                        and ctx.results["item-flaky"].status == "success"
                    ),
                    blocks=[
                        ShellStep(
                            name="item-flaky",
                            command=(
                                "DIR={{cwd}}/.workflow-state/{{variables.run_id}} && "
                                "COUNT=$(cat $DIR/lr-{{variables.loop_item}} 2>/dev/null || echo 0) && "
                                "COUNT=$((COUNT + 1)) && "
                                "echo $COUNT > $DIR/lr-{{variables.loop_item}} && "
                                "if [ $COUNT -lt 2 ]; then echo 'fail' >&2 && exit 1; else echo 'OK'; fi"
                            ),
                        ),
                    ],
                ),
            ],
        ),

        # --- Phase 10: LLMStep — gated ---
        LLMStep(
            name="llm-classify",
            prompt="classify.md",
            model="haiku",
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
        ),

        # --- Phase 11: LLMStep + output_schema — gated ---
        LLMStep(
            name="llm-summarize",
            prompt="summarize.md",
            model="haiku",
            output_schema=SummaryOutput,
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
        ),

        # --- Phase 12: GroupBlock (LLM step segments) — gated ---
        GroupBlock(
            name="llm-session",
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
            llm_session_policy="step_segments",
            blocks=[
                LLMStep(name="session-analyze", prompt="session-step1.md", model="haiku"),
                LLMStep(name="session-summarize", prompt="session-step2.md", model="haiku"),
            ],
        ),

        # --- Phase 13: Conditional + Parallel — gated ---
        ConditionalBlock(
            name="parallel-gate",
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
            branches=[
                Branch(
                    condition=lambda ctx: (
                        ctx.results.get("detect") is not None
                        and ctx.results["detect"].status == "success"
                    ),
                    blocks=[
                        ParallelEachBlock(
                            name="parallel-checks",
                            template=[
                                LLMStep(
                                    name="check",
                                    prompt="parallel-check.md",
                                    model="haiku",
                                )
                            ],
                            parallel_for="results.detect.structured_output.items",
                        ),
                    ],
                ),
            ],
        ),

        # --- Phase 13b: LLMStep — security: denied tools — gated ---
        LLMStep(
            name="llm-denied-tools",
            prompt="test-denied-tools.md",
            model="haiku",
            tools=[],  # No tools allowed — Bash/Read must be denied
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
        ),

        # --- Phase 14: LLMStep + ask_user (single) — gated ---
        LLMStep(
            name="llm-ask-single",
            prompt="ask-single.md",
            model="haiku",
            tools=["ask_user"],
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
        ),

        # --- Phase 15: GroupBlock + ask_user (session segment) — gated ---
        GroupBlock(
            name="llm-ask-group",
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
            llm_session_policy="step_segments",
            blocks=[
                LLMStep(name="group-ask", prompt="ask-group-step1.md", model="haiku", tools=["ask_user"]),
                LLMStep(name="group-use-answer", prompt="ask-group-step2.md", model="haiku"),
            ],
        ),

        # --- Phase 16: ParallelEachBlock + ask_user — gated ---
        ConditionalBlock(
            name="parallel-ask-gate",
            condition=lambda ctx: ctx.variables.get("enable_llm") is True or (ctx.results.get("mode") and ctx.results["mode"].output == "thorough"),
            branches=[
                Branch(
                    condition=lambda ctx: (
                        ctx.results.get("detect") is not None
                        and ctx.results["detect"].status == "success"
                    ),
                    blocks=[
                        ParallelEachBlock(
                            name="parallel-ask-checks",
                            template=[
                                LLMStep(
                                    name="ask-check",
                                    prompt="ask-parallel.md",
                                    model="haiku",
                                    tools=["ask_user"],
                                )
                            ],
                            parallel_for="results.detect.structured_output.items",
                        ),
                    ],
                ),
            ],
        ),

        # --- Phase 17: PromptStep with key!=name ---
        PromptStep(
            name="final-prompt",
            key="final-decision",
            prompt_type="choice",
            message="Final decision on {{results.detect.structured_output.count}} items:",
            options=["accept", "reject"],
            default="accept",
            result_var="decision",
        ),

        # --- Phase 18: Final confirm + finalize + cleanup ---
        PromptStep(
            name="confirm-results",
            prompt_type="confirm",
            message="Decision: {{results.final-decision.output}}. Accept results?",
            default="yes",
        ),
        ShellStep(
            name="finalize",
            command="echo 'Done!'",
            condition=lambda ctx: (
                ctx.results.get("confirm-results") is not None
                and ctx.results["confirm-results"].output != "no"
            ),
        ),
        ShellStep(
            name="cleanup",
            command=(
                "find {{cwd}}/.workflow-state/{{variables.run_id}} "
                "\\( -name 'retry' -o -name 'lr-*' \\) -print0 "
                "| xargs -0 rm -f --"
            ),
            condition=lambda ctx: (
                ctx.results.get("confirm-results") is not None
                and ctx.results["confirm-results"].output != "no"
            ),
        ),
    ],
)
