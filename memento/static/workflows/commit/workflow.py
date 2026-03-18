# ruff: noqa: E501
"""Commit workflow definition.

Internalizes all git shell commands (status, diff, add, commit) so the LLM
is only invoked once — to analyze changes and compose commit messages.

Shell commands run via commit-tools.py (argparse, JSON output).
LLM reads the diff from a temp file and outputs a CommitPlan.

Staging rules:
  - Single commit (1 group): commit whatever is already staged — no re-staging.
  - Split commit (N groups): unstage all, then stage per-group.
    Requires has_partial_staging=false (halt otherwise — whole-file granularity).
  - Auto-stage: only when nothing is staged AND not amending.

Engine types (WorkflowDef, LLMStep, etc.) are injected by the loader at runtime.
Import _dsl for static analysis only (no-op at runtime).
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _dsl import (
        LLMStep,
        LoopBlock,
        ShellStep,
        WorkflowContext,
        WorkflowDef,
    )

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class CommitGroup(BaseModel):
    files: list[str]
    subject: str
    body: str | None = None


class CommitPlan(BaseModel):
    groups: list[CommitGroup]


# commit-tools.py path (resolved relative to workflow_dir by engine)
_TOOLS = "commit-tools.py"


# ---------------------------------------------------------------------------
# Condition helpers
# ---------------------------------------------------------------------------


def _is_amend(ctx: "WorkflowContext") -> bool:
    return ctx.variables.get("amend") == "true"


def _nothing_to_commit(ctx: "WorkflowContext") -> bool:
    if _is_amend(ctx):
        return False  # amend can work with no new changes (message-only rewrite)
    return ctx.variables.get("git_state", {}).get("nothing_to_commit", False)


def _amend_no_head(ctx: "WorkflowContext") -> bool:
    """Can't amend when there's no HEAD commit."""
    return _is_amend(ctx) and ctx.variables.get("git_state", {}).get("no_head", False)


def _needs_auto_stage(ctx: "WorkflowContext") -> bool:
    """Auto-stage when nothing is staged but there are unstaged/untracked files (not in amend mode)."""
    if _is_amend(ctx):
        return False
    s = ctx.variables.get("git_state", {})
    return not s.get("has_staged") and (s.get("has_unstaged") or bool(s.get("untracked_files")))


def _stage_failed(ctx: "WorkflowContext") -> bool:
    return ctx.variables.get("stage_result", {}).get("status") == "error"


def _is_split(ctx: "WorkflowContext") -> bool:
    """Check if the LLM produced multiple commit groups."""
    groups = ctx.result_field("analyze", "groups")
    return groups is not None and len(groups) > 1


def _split_blocked(ctx: "WorkflowContext") -> bool:
    """Split is blocked by partial staging or amend mode."""
    if not _is_split(ctx):
        return False
    if _is_amend(ctx):
        return True
    return ctx.variables.get("git_state", {}).get("has_partial_staging", False)


def _needs_restage(ctx: "WorkflowContext") -> bool:
    """Re-staging needed only when splitting (>1 groups)."""
    return _is_split(ctx)


def _stage_group_failed(ctx: "WorkflowContext") -> bool:
    return ctx.variables.get("stage_group_result", {}).get("status") == "error"


def _commit_failed(ctx: "WorkflowContext") -> bool:
    return ctx.variables.get("commit_result", {}).get("status") == "error"


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

WORKFLOW = WorkflowDef(
    name="commit",
    description="Stage changes and create well-formatted git commits",
    blocks=[
        # 1. Gather git state (status, diff stats, recent log)
        #    workdir passed via env var (not args) to handle paths with spaces
        ShellStep(
            name="gather",
            script=_TOOLS,
            args="gather --amend-mode {{variables.amend}}",
            env={"COMMIT_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="git_state",
        ),

        # 2a. Halt if amend on empty repo
        ShellStep(
            name="check-amend-no-head",
            command='echo \'{"status": "error"}\'',
            condition=_amend_no_head,
            halt="Cannot amend — no commits in this repository yet.",
        ),

        # 2b. Halt if nothing to commit
        ShellStep(
            name="check-empty",
            command='echo \'{"status": "nothing_to_commit"}\'',
            condition=_nothing_to_commit,
            halt="Nothing to commit — working tree is clean.",
        ),

        # 3. Auto-stage all if nothing staged (skip in amend mode)
        ShellStep(
            name="auto-stage",
            script=_TOOLS,
            args="stage --files-json '{{variables.git_state.all_changed_files}}'",
            env={"COMMIT_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="stage_result",
            condition=_needs_auto_stage,
        ),

        # 3b. Halt if auto-stage failed
        ShellStep(
            name="check-stage",
            command='echo \'{"status": "stage_failed"}\'',
            condition=_stage_failed,
            halt="Failed to stage files — check git status.",
        ),

        # 4. Get full diff (writes to temp file for LLM to read)
        #    amend → HEAD commit diff; normal → staged only
        ShellStep(
            name="get-diff",
            script=_TOOLS,
            args="diff --scope {{variables.git_state.diff_mode}}",
            env={"COMMIT_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="diff_info",
        ),

        # 5. LLM analyzes changes and composes commit message(s)
        LLMStep(
            name="analyze",
            prompt="analyze.md",
            tools=["Read"],
            output_schema=CommitPlan,
        ),

        # 6a. Halt if split is blocked (amend mode or partial staging)
        ShellStep(
            name="check-split-blocked",
            command='echo \'{"status": "split_blocked"}\'',
            condition=_split_blocked,
            halt="Cannot split commits — partial staging or amend mode prevents safe re-staging. Commit as a single group instead.",
        ),

        # 6b. Unstage all before split (only when >1 groups)
        ShellStep(
            name="unstage-all",
            script=_TOOLS,
            args="unstage",
            env={"COMMIT_TOOLS_WORKDIR": "{{variables.workdir}}"},
            condition=_needs_restage,
        ),

        # 7. Execute commits (loop handles both single and split)
        LoopBlock(
            name="execute",
            loop_over="results.analyze.structured_output.groups",
            loop_var="group",
            blocks=[
                # 7a. Stage this group's files (only when splitting)
                ShellStep(
                    name="stage-group",
                    script=_TOOLS,
                    args="stage --files-json '{{variables.group.files}}'",
                    env={"COMMIT_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="stage_group_result",
                    condition=_needs_restage,
                ),
                # 7b. Halt if stage failed
                ShellStep(
                    name="check-stage-group",
                    command='echo \'{"status": "stage_group_failed"}\'',
                    condition=_stage_group_failed,
                    halt="Failed to stage files for commit group — check git status.",
                ),
                # 7c. Commit with message from LLM (stdin = group JSON)
                ShellStep(
                    name="do-commit",
                    script=_TOOLS,
                    args="commit --amend-mode {{variables.amend}}",
                    stdin="variables.group",
                    env={"COMMIT_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="commit_result",
                ),
                # 7d. Halt if commit failed
                ShellStep(
                    name="check-commit",
                    command='echo \'{"status": "commit_failed"}\'',
                    condition=_commit_failed,
                    halt="Commit failed — check git status for details.",
                ),
            ],
        ),

        # 8. Verify final state
        ShellStep(
            name="verify",
            script=_TOOLS,
            args="verify --count 5",
            env={"COMMIT_TOOLS_WORKDIR": "{{variables.workdir}}"},
            result_var="verify_result",
        ),

        # 9. Clean up temp diff file
        ShellStep(
            name="cleanup",
            script=_TOOLS,
            args="cleanup --path {{variables.diff_info.diff_path}}",
        ),
    ],
)
