# ruff: noqa: E501
"""Process protocol workflow definition (v2).

Parses protocol steps via frontmatter + HTML markers, sets up a worktree,
then iterates steps (not subtasks):
  - Per step: prepare → develop (subagent) → record findings → review → commit
  - Single LoopBlock over steps; subtasks are internal to the dev subagent
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _dsl import (
        LLMStep,
        LoopBlock,
        RetryBlock,
        ShellStep,
        SubWorkflow,
        WorkflowDef,
    )

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

        # Ensure develop branch exists (integration branch for protocol merges).
        # Creates from main/master/HEAD if missing.
        ShellStep(
            name="ensure-develop",
            command=(
                'if ! git rev-parse --verify develop >/dev/null 2>&1; then '
                'BASE=""; '
                'for b in main master; do '
                'if git rev-parse --verify "$b" >/dev/null 2>&1; then BASE="$b"; break; fi; '
                'done; '
                'git branch develop ${BASE:-HEAD}; '
                'fi && echo "ok"'
            ),
        ),

        # Setup worktree (extract leading number to match merge-protocol expectations)
        ShellStep(
            name="worktree",
            command=(
                'PROTO_DIR="$(basename "{{variables.protocol_dir}}")" && '
                'PROTO_NUM="${PROTO_DIR%%[!0-9]*}" && '
                'BRANCH="protocol-${PROTO_NUM:-$PROTO_DIR}" && '
                'WT=".worktrees/${BRANCH}" && '
                'mkdir -p .worktrees && '
                'if [ ! -d "$WT" ]; then '
                'git worktree add "$WT" -b "${BRANCH}" develop; '
                'fi && '
                'echo "{\\"path\\": \\"${WT}\\"}"'
            ),
            result_var="worktree",
        ),

        # Guard: halt if worktree was not created (e.g. git worktree add failed)
        ShellStep(
            name="check-worktree",
            command='echo "Worktree not created — git worktree add may have failed"',
            halt="Worktree creation failed. Check git branches and worktree state.",
            condition=lambda ctx: not isinstance(ctx.variables.get("worktree"), dict),
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
                # Reset dev_result to safe default at start of each iteration
                ShellStep(
                    name="reset-dev-result",
                    command='echo \'{"passed": false}\'',
                    result_var="dev_result",
                ),

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

                # Run development workflow inline (no subagent for debugging)
                SubWorkflow(
                    name="develop",
                    workflow="development",
                    inject={
                        "mode": "protocol",
                        "task": "{{variables.step_data.task_full_md}}",
                        "task_compact": "{{variables.step_data.task_compact_md}}",
                        "step_file": "{{variables.step_data.step_file}}",
                        "context_files": "variables.step_data.context_files",
                        "mb_refs": "variables.step_data.mb_refs",
                        "starting_points": "variables.step_data.starting_points",
                        "verification_commands": "variables.step_data.verification_commands",
                        "units": "variables.step_data.units",
                        "workdir": "{{variables.worktree.path}}",
                    },
                ),

                # Record findings from dev result
                ShellStep(
                    name="record",
                    command=(
                        "cat '{{variables.worktree.path}}/.dev-result.json' | "
                        f"{_HELPERS} "
                        "record-findings "
                        "'{{variables.step_data.step_file}}'"
                    ),
                ),

                # Load dev result to decide whether to proceed
                ShellStep(
                    name="load-dev-result",
                    command="cat '{{variables.worktree.path}}/.dev-result.json'",
                    result_var="dev_result",
                ),

                # Halt workflow if development didn't pass
                ShellStep(
                    name="mark-blocked",
                    command=(
                        f"{_HELPERS} "
                        "update-status "
                        "'{{variables.protocol_dir}}/{{variables.step.path}}' "
                        "blocked"
                    ),
                    halt="Step {{variables.step.id}} failed verification",
                    condition=lambda ctx: ctx.variables.get("dev_result", {}).get("passed") is not True,
                ),

                # Code review (scoped to worktree)
                SubWorkflow(
                    name="review",
                    workflow="code-review",
                    inject={
                        "workdir": "{{variables.worktree.path}}",
                    },
                ),

                # Fix review findings loop — halt if exhausted
                RetryBlock(
                    name="fix-review",
                    until=lambda ctx: not ctx.result_field("re-review.synthesize", "has_blockers"),
                    max_attempts=3,
                    halt_on_exhaustion="Review fixes failed after 3 attempts for step {{variables.step.id}}",
                    blocks=[
                        LLMStep(
                            name="fix-issues",
                            prompt="fix-review.md",
                            tools=["Read", "Write", "Edit", "Bash"],
                        ),
                        SubWorkflow(
                            name="verify-fixes",
                            workflow="verify-fix",
                            inject={"workdir": "{{variables.worktree.path}}"},
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
