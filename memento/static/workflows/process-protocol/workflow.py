# pyright: reportUndefinedVariable=false
"""Process protocol workflow definition (v2).

Parses protocol steps via frontmatter + HTML markers, sets up a worktree,
then iterates steps (not subtasks):
  - Per step: prepare → develop (subagent) → record findings → review → commit
  - Single LoopBlock over steps; subtasks are internal to the dev subagent

Engine types (WorkflowDef, LLMStep, etc.) are injected by the loader — no imports needed.
"""

_HELPERS = "python '{{variables.workflow_dir}}/helpers.py'"

WORKFLOW = WorkflowDef(
    name="process-protocol",
    description="Execute protocol steps sequentially with QA checks and commits",
    blocks=[
        # Discover steps from frontmatter
        ShellStep(
            name="discover",
            command=f"{_HELPERS} discover-steps {{{{variables.protocol_dir}}}}",
            result_var="protocol",
        ),

        # Setup worktree
        ShellStep(
            name="worktree",
            command=(
                'BRANCH="protocol-$(basename {{variables.protocol_dir}})" && '
                "mkdir -p .worktrees && "
                'git worktree add ".worktrees/${BRANCH}" -b "${BRANCH}" develop 2>/dev/null || '
                'echo "Worktree exists, reusing" && '
                'echo "{\\"path\\": \\".worktrees/${BRANCH}\\"}"'
            ),
            result_var="worktree",
        ),

        # Copy environment files into worktree
        ShellStep(
            name="copy-env",
            command=(
                'WD="{{variables.worktree.path}}" && '
                '[ -d "$WD" ] && '
                'for f in .env .env.local .env.test .env.development .env.production; do '
                '[ -f "$f" ] && cp "$f" "$WD/$f"; '
                'done; echo "done"'
            ),
        ),

        # Process each pending step (single loop — no nested subtask loop)
        LoopBlock(
            name="steps",
            loop_over="variables.protocol.pending_steps",
            loop_var="step",
            blocks=[
                # Mark step in-progress
                ShellStep(
                    name="mark-wip",
                    command=(
                        f"{_HELPERS} "
                        "update-status "
                        "'{{variables.protocol_dir}}/{{variables.step.path}}' "
                        "in-progress"
                    ),
                ),

                # Prepare step data (deterministic — no LLM)
                ShellStep(
                    name="prepare",
                    command=(
                        f"{_HELPERS} "
                        "prepare-step "
                        "{{variables.protocol_dir}} "
                        "'{{variables.step.path}}'"
                    ),
                    result_var="step_data",
                ),

                # Run development workflow as isolated subagent
                SubWorkflow(
                    name="develop",
                    workflow="development",
                    isolation="subagent",
                    inject={
                        "mode": "protocol",
                        "task": "{{variables.step_data.task_full_md}}",
                        "task_compact": "{{variables.step_data.task_compact_md}}",
                        "step_file": "{{variables.step_data.step_file}}",
                        "context_files": "variables.step_data.context_files",
                        "mb_refs": "variables.step_data.mb_refs",
                        "starting_points": "variables.step_data.starting_points",
                        "verification_commands": "variables.step_data.verification_commands",
                        "workdir": "{{variables.worktree.path}}",
                    },
                ),

                # Record findings from dev result (file-based handoff:
                # subagent writes .dev-result.json, parent reads it)
                ShellStep(
                    name="record",
                    command=(
                        f"{_HELPERS} "
                        "record-findings "
                        "'{{variables.step_data.step_file}}' "
                        '"$(cat {{variables.worktree.path}}/.dev-result.json)"'
                    ),
                ),

                # Code review (scoped to worktree)
                SubWorkflow(
                    name="review",
                    workflow="code-review",
                    inject={
                        "workdir": "{{variables.worktree.path}}",
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
                            name="re-review",
                            workflow="code-review",
                            inject={
                                "workdir": "{{variables.worktree.path}}",
                            },
                        ),
                    ],
                ),

                # Commit
                ShellStep(
                    name="commit",
                    command=(
                        'cd "{{variables.worktree.path}}" && '
                        'git add -A && '
                        'git commit -m "feat: complete step {{variables.step.id}}"'
                    ),
                ),

                # Mark step complete
                ShellStep(
                    name="mark-done",
                    command=(
                        f"{_HELPERS} "
                        "update-status "
                        "'{{variables.protocol_dir}}/{{variables.step.path}}' "
                        "done"
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
