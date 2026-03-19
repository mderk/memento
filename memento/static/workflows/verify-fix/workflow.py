# ruff: noqa: E501
"""Verify-fix workflow: lint + test + LLM fix retry loop.

Reusable workflow that runs lint and tests, and if either fails,
asks an LLM to fix the issues. Retries up to 3 times.

Expects variables:
  - workdir: working directory for lint/test/fix operations
  - scope: "backend", "frontend", or "fullstack" (filters lint/test commands)
  - test_scope: "all" (default) or "changed" (only changed test/spec files)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _dsl import LLMStep, RetryBlock, ShellStep, WorkflowDef

_DEV_TOOLS = "python .workflows/develop/dev-tools.py"

WORKFLOW = WorkflowDef(
    name="verify-fix",
    description="Lint + test with LLM fix retry loop",
    blocks=[
        ShellStep(
            name="init-test-scope",
            command="echo '\"all\"'",
            result_var="test_scope",
            condition=lambda ctx: not ctx.variables.get("test_scope"),
        ),
        RetryBlock(
            name="fix-loop",
            until=lambda ctx: (
                ctx.variables.get("test_result", {}).get("status") == "green"
                and (
                    ctx.variables.get("lint_result", {}).get("status") in ("clean", "skipped")
                    # Lint errors but fix changed nothing → pre-existing/unfixable → accept
                    or ctx.variables.get("fix_changes", {}).get("changed") is False
                )
            ),
            max_attempts=3,
            blocks=[
                ShellStep(
                    name="format",
                    command=f"{_DEV_TOOLS} format --scope changed --target {{{{variables.scope}}}} --workdir {{{{variables.workdir}}}}",
                    env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="format_result",
                ),
                ShellStep(
                    name="lint",
                    command=f"{_DEV_TOOLS} lint --scope changed --target {{{{variables.scope}}}} --workdir {{{{variables.workdir}}}}",
                    env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="lint_result",
                ),
                ShellStep(
                    name="test",
                    command=f"{_DEV_TOOLS} test --scope {{{{variables.test_scope}}}} --workdir {{{{variables.workdir}}}}",
                    env={"DEV_TOOLS_WORKDIR": "{{variables.workdir}}"},
                    result_var="test_result",
                ),
                LLMStep(
                    name="fix",
                    prompt="fix.md",
                    tools=["Read", "Write", "Edit", "Bash"],
                    condition=lambda ctx: (
                        ctx.variables.get("lint_result", {}).get("status") not in ("clean", "skipped")
                        or ctx.variables.get("test_result", {}).get("status") != "green"
                    ),
                ),
                # Detect if fix actually changed files — pre-existing lint errors
                # that the LLM can't fix shouldn't block the loop
                ShellStep(
                    name="check-fix-changes",
                    command='cd "{{variables.workdir}}" && git diff --quiet && echo \'{"changed": false}\' || echo \'{"changed": true}\'',
                    result_var="fix_changes",
                ),
            ],
        ),
    ],
)
