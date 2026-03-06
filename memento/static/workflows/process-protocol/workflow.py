# pyright: reportUndefinedVariable=false
"""Process protocol workflow definition.

Parses a protocol plan.md, sets up a worktree, then iterates steps:
  - Per step: execute subtasks via development workflow (protocol mode)
  - After subtasks: validate, code review, fix loop, commit

Engine types (WorkflowDef, LLMStep, etc.) are injected by the loader — no imports needed.
"""

_HELPERS = "python '{{variables.workflow_dir}}/helpers.py'"

WORKFLOW = WorkflowDef(
    name="process-protocol",
    description="Execute protocol steps sequentially with QA checks and commits",
    blocks=[
        # Parse the protocol plan.md
        ShellStep(
            name="parse",
            command=f"{_HELPERS} parse-protocol {{{{variables.protocol_dir}}}}",
        ),

        # Setup worktree
        ShellStep(
            name="worktree",
            command=(
                'BRANCH="protocol-$(basename {{variables.protocol_dir}})" && '
                "mkdir -p .worktrees && "
                'git worktree add ".worktrees/${BRANCH}" -b "${BRANCH}" develop 2>/dev/null || '
                'echo "Worktree exists, reusing"'
            ),
        ),

        # Copy environment files into worktree
        ShellStep(
            name="copy-env",
            command=(
                'BRANCH="protocol-$(basename {{variables.protocol_dir}})" && '
                'WD=".worktrees/${BRANCH}" && '
                '[ -d "$WD" ] && '
                'for f in .env .env.local .env.test .env.development .env.production; do '
                '[ -f "$f" ] && cp "$f" "$WD/$f"; '
                'done; echo "done"'
            ),
        ),

        # Process each pending step
        LoopBlock(
            name="steps",
            loop_over="results.parse.structured_output.pending_steps",
            loop_var="step",
            blocks=[
                # Process subtasks within each step
                LoopBlock(
                    name="subtasks",
                    loop_over="variables.step.subtasks",
                    loop_var="subtask",
                    blocks=[
                        # Mark subtask as in-progress
                        ShellStep(
                            name="mark-wip",
                            command=(
                                f"{_HELPERS} "
                                'update-marker "{{variables.step.link}}" "{{variables.subtask.description}}" "[~]"'
                            ),
                        ),

                        # Load shared context
                        ShellStep(
                            name="load-context",
                            command=(
                                f"{_HELPERS} "
                                "load-context {{variables.protocol_dir}} {{variables.step.link}}"
                            ),
                        ),

                        # Run development workflow in protocol mode
                        SubWorkflow(
                            name="develop",
                            workflow="development",
                            inject={
                                "mode": "protocol",
                                "task": "{{variables.subtask.description}}",
                            },
                        ),

                        # Record findings
                        ShellStep(
                            name="record",
                            command=(
                                f"{_HELPERS} "
                                'append-findings "{{variables.step.link}}" '
                                '"{{results.develop.complete}}"'
                            ),
                        ),

                        # Mark subtask complete
                        ShellStep(
                            name="mark-done",
                            command=(
                                f"{_HELPERS} "
                                'update-marker "{{variables.step.link}}" "{{variables.subtask.description}}" "[x]"'
                            ),
                        ),
                    ],
                ),

                # Validate step
                ShellStep(
                    name="validate",
                    command="python -m pytest --tb=short -q",
                ),

                # Code review
                SubWorkflow(
                    name="review",
                    workflow="code-review",
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
                            name="re-review",
                            workflow="code-review",
                        ),
                    ],
                ),

                # Commit
                ShellStep(
                    name="commit",
                    command='git add -A && git commit -m "feat: complete step {{variables.step.text}}"',
                ),

                # Mark step complete in plan.md
                ShellStep(
                    name="mark-step",
                    command=(
                        f"{_HELPERS} "
                        'update-marker "{{variables.protocol_dir}}/plan.md" "{{variables.step.text}}" "[x]"'
                    ),
                ),
            ],
        ),

        # Signal completion
        ShellStep(
            name="finish",
            command='echo "All protocol steps complete. Run /merge-protocol to finalize."',
        ),
    ],
)
