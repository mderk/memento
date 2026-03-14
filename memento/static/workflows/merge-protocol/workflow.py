# pyright: reportUndefinedVariable=false
"""Merge protocol workflow definition.

Validates prerequisites, runs code review on the protocol branch,
presents user with merge/wait/review choice, then merges to develop.

Engine types (WorkflowDef, ShellStep, etc.) are injected by the loader — no imports needed.
"""

_HELPERS = "python '{{variables.workflow_dir}}/helpers.py'"

WORKFLOW = WorkflowDef(
    name="merge-protocol",
    description="Merge protocol branch into develop with code review",
    blocks=[
        # 1. Validate prerequisites (plan.md complete, worktree exists, develop clean)
        ShellStep(
            name="prereqs",
            command=f"{_HELPERS} check-prereqs {{{{variables.protocol_dir}}}}",
            result_var="prereqs",
        ),

        # 2. Final verification in worktree (tests + lint)
        ShellStep(
            name="verify",
            command=f"{_HELPERS} verify {{{{variables.prereqs.worktree_path}}}}",
            result_var="verify",
        ),

        # 3–6. Review cycle (repeats if user chooses "review")
        RetryBlock(
            name="review-cycle",
            until=lambda ctx: ctx.variables.get("user_choice") != "review",
            max_attempts=5,
            blocks=[
                # Code review scoped to worktree
                SubWorkflow(
                    name="review",
                    workflow="code-review",
                    inject={
                        "workdir": "{{variables.prereqs.worktree_path}}",
                    },
                ),

                # Fix review findings loop
                RetryBlock(
                    name="fix-review",
                    until=lambda ctx: not ctx.result_field("re-review.synthesize", "has_blockers"),
                    max_attempts=3,
                    blocks=[
                        LLMStep(
                            name="fix-issues",
                            prompt="fix-review.md",
                            tools=["Read", "Write", "Edit", "Bash"],
                        ),
                        SubWorkflow(
                            name="verify-fixes",
                            workflow="verify-fix",
                            inject={"workdir": "{{variables.prereqs.worktree_path}}"},
                        ),
                        SubWorkflow(
                            name="re-review",
                            workflow="code-review",
                            inject={
                                "workdir": "{{variables.prereqs.worktree_path}}",
                            },
                        ),
                    ],
                ),

                # Diff stats
                ShellStep(
                    name="diff-stats",
                    command=f"{_HELPERS} diff-stats {{{{variables.prereqs.worktree_path}}}}",
                    result_var="diff_stats",
                ),

                # User confirmation
                PromptStep(
                    name="confirm",
                    prompt_type="choice",
                    message=(
                        "Protocol ready for merge\n"
                        "─────────────────────────────\n"
                        "Branch: {{variables.prereqs.branch}}\n"
                        "Changes: {{variables.diff_stats.summary}}\n\n"
                        "Code review: PASSED\n"
                        "Tests: {{variables.verify.status}}\n\n"
                        "Options:\n"
                        "1. merge  — Merge now and cleanup\n"
                        "2. wait   — Keep branch, merge later\n"
                        "3. review — Run another code review cycle"
                    ),
                    options=["merge", "wait", "review"],
                    default="wait",
                    result_var="user_choice",
                ),
            ],
        ),

        # 7. Execute based on user choice
        ConditionalBlock(
            name="execute",
            branches=[
                # Merge path: rebase, merge, verify, cleanup
                Branch(
                    condition=lambda ctx: ctx.variables.get("user_choice") == "merge",
                    blocks=[
                        ShellStep(
                            name="merge",
                            command=(
                                f"{_HELPERS} merge "
                                "{{variables.prereqs.worktree_path}} "
                                "{{variables.prereqs.branch}} "
                                "'{{variables.prereqs.protocol_name}}'"
                            ),
                            result_var="merge_result",
                        ),
                        ShellStep(
                            name="verify-develop",
                            command=f"{_HELPERS} verify .",
                            result_var="verify_develop",
                        ),
                        ShellStep(
                            name="cleanup",
                            command=(
                                f"{_HELPERS} cleanup "
                                "{{variables.prereqs.worktree_path}} "
                                "{{variables.prereqs.branch}} "
                                "{{variables.protocol_dir}}"
                            ),
                        ),
                        ShellStep(
                            name="finish",
                            command=(
                                "echo 'Merge complete. "
                                "Run /update-memory-bank-protocol "
                                "{{variables.protocol_dir}} to update the Memory Bank.'"
                            ),
                        ),
                    ],
                ),
                # Wait path: keep branch, exit
                Branch(
                    condition=lambda ctx: ctx.variables.get("user_choice") == "wait",
                    blocks=[
                        ShellStep(
                            name="finish",
                            command=(
                                "echo 'Branch {{variables.prereqs.branch}} kept. "
                                "Run /merge-protocol {{variables.protocol_dir}} "
                                "when ready to merge.'"
                            ),
                        ),
                    ],
                ),
            ],
        ),
    ],
)
