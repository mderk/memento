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

        # Mark protocol as started in develop (committed so worktree inherits it)
        ShellStep(
            name="mark-plan-in-progress",
            command=(
                "git checkout develop && "
                f"{_HELPERS} mark-plan-in-progress {{{{variables.protocol_dir}}}} && "
                "git add -- '{{variables.protocol_dir}}' && "
                'git diff --cached --quiet || git commit -m "chore: mark protocol in-progress"'
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
                'git worktree add "$WT" -b "${BRANCH}" develop >/dev/null 2>&1; '
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
                'find . -name ".env" -o -name ".env.*" | '
                'grep -v node_modules | grep -v .worktrees | '
                'while read -r f; do '
                'mkdir -p "$WD/$(dirname "$f")" && cp "$f" "$WD/$f"; '
                'done; echo "done"'
            ),
        ),

        # Install dependencies in worktree (node_modules, venv, etc. are gitignored)
        ShellStep(
            name="install-deps",
            command="python .workflows/develop/dev-tools.py install --workdir {{variables.worktree.path}}",
        ),

        # Compute worktree-relative protocol path
        ShellStep(
            name="resolve-wt-protocol-dir",
            command=(
                f"{_HELPERS} "
                "resolve-wt-protocol-dir "
                "{{variables.protocol_dir}} "
                "{{variables.worktree.path}}"
            ),
            result_var="wt_protocol",
        ),

        # Discover steps from worktree (reads statuses from where mark-done writes)
        ShellStep(
            name="discover",
            command=f"{_HELPERS} discover-steps {{{{variables.wt_protocol.worktree_protocol_dir}}}}",
            result_var="protocol",
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

                # Mark step in-progress (in worktree)
                ShellStep(
                    name="mark-wip",
                    command=(
                        f"{_HELPERS} "
                        "update-status "
                        "'{{variables.wt_protocol.worktree_protocol_dir}}/{{variables.step.path}}' "
                        "in-progress"
                    ),
                ),

                # Prepare step data from worktree (deterministic — no LLM)
                ShellStep(
                    name="prepare",
                    command=(
                        f"{_HELPERS} "
                        "prepare-step "
                        "{{variables.wt_protocol.worktree_protocol_dir}} "
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
                        "dev_result_path": "/tmp/memento-dev-result-{{variables.step_data.id}}.json",
                    },
                ),

                # Record findings from dev result
                ShellStep(
                    name="record",
                    command=(
                        "cat '/tmp/memento-dev-result-{{variables.step_data.id}}.json' | "
                        f"{_HELPERS} "
                        "record-findings "
                        "'{{variables.step_data.step_file}}'"
                    ),
                ),

                # Load dev result to decide whether to proceed
                ShellStep(
                    name="load-dev-result",
                    command="cat '/tmp/memento-dev-result-{{variables.step_data.id}}.json'",
                    result_var="dev_result",
                ),

                # Halt workflow if development didn't pass
                ShellStep(
                    name="mark-blocked",
                    command=(
                        f"{_HELPERS} "
                        "update-status "
                        "'{{variables.wt_protocol.worktree_protocol_dir}}/{{variables.step.path}}' "
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

                # Fix review findings loop — skip entirely if APPROVE, exit if blockers resolved
                RetryBlock(
                    name="fix-review",
                    condition=lambda ctx: ctx.result_field("review.synthesize", "has_blockers"),
                    until=lambda ctx: (
                        not ctx.result_field("re-review.synthesize", "has_blockers")
                        # Pre-existing issues the LLM can't fix → accept and move on
                        or ctx.variables.get("review_fix_changes", {}).get("changed") is False
                    ),
                    max_attempts=3,
                    halt_on_exhaustion="Review fixes failed after 3 attempts for step {{variables.step.id}}",
                    blocks=[
                        LLMStep(
                            name="fix-issues",
                            prompt="fix-review.md",
                            tools=["Read", "Write", "Edit", "Bash"],
                            model="sonnet",
                        ),
                        # Detect if fix actually changed files
                        ShellStep(
                            name="check-review-fix-changes",
                            command='cd "{{variables.worktree.path}}" && git diff --quiet && echo \'{"changed": false}\' || echo \'{"changed": true}\'',
                            result_var="review_fix_changes",
                        ),
                        SubWorkflow(
                            name="verify-fixes",
                            workflow="verify-fix",
                            inject={"workdir": "{{variables.worktree.path}}"},
                            condition=lambda ctx: ctx.variables.get("review_fix_changes", {}).get("changed") is True,
                        ),
                        SubWorkflow(
                            name="re-review",
                            workflow="code-review",
                            inject={
                                "workdir": "{{variables.worktree.path}}",
                            },
                            condition=lambda ctx: ctx.variables.get("review_fix_changes", {}).get("changed") is True,
                        ),
                    ],
                ),

                # Mark step complete (in worktree, before commit so it's captured)
                ShellStep(
                    name="mark-done",
                    command=(
                        f"{_HELPERS} "
                        "update-status "
                        "'{{variables.wt_protocol.worktree_protocol_dir}}/{{variables.step.path}}' "
                        "done"
                    ),
                ),

                # Commit code + protocol changes together (LLM-composed message)
                SubWorkflow(
                    name="commit",
                    workflow="commit",
                    inject={
                        "workdir": "{{variables.worktree.path}}",
                        "amend": "false",
                    },
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
