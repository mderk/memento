# Workflow Engine Bug Fixes (Protocol 0002 Observations) — Requirements

## Problem Statement

During protocol 0002 execution, 16 observations revealed 7 unique bugs in the workflow engine and workflows. The most critical: code review runs blind (competency rules never reach prompts), re-review wastes 5-8 LLM prompts on APPROVE verdicts, coverage parser assigns wrong file's missing lines, and shell steps inherit incorrect VIRTUAL_ENV in worktrees.

## Requirements

- A. Fix competency_rules: load-competency shell step must deliver rules text to the review prompt. Root cause: cat exit code + result_var requires JSON. Fix: remove result_var, use results.output in prompt, fix exit code with '; true'
- B. Skip re-review on APPROVE: add condition to fix-review RetryBlock checking review.synthesize.has_blockers. Saves ~8 LLM prompts per APPROVE
- C. Fix coverage parser regex: change (.*?)$ to ([\d\-,\s]*)$ to only capture valid line-range syntax, preventing cross-file contamination
- F. Fix VIRTUAL_ENV in worktree: shell_exec.py should detect .venv in cwd and override VIRTUAL_ENV, or remove it when cwd is outside inherited venv
- H. Scope git add in mark-plan-in-progress: change 'git add -A' to 'git add -- {{variables.protocol_dir}}' to avoid staging unrelated changes
- G. Add _dsl.py stub parity test: verify types.py block definitions match _dsl.py stubs, catch drift automatically
- J. Fix stdin template resolution: actions.py passes step.stdin raw without stripping {{}} wrapper, runner.py resolves via get_var() expecting bare dotpath — stdin arrives empty
- K. Persist _inline_parent_exec_key in checkpoints: field is set on inline SubWorkflow children but not saved/restored — breaks cascade completion on resume

## Constraints

- Workflow-level fixes (A, B, H) must be mirrored in both memento/static/workflows/ and .workflows/
- Engine fix (F) must not break existing shell steps that rely on inherited VIRTUAL_ENV
- Coverage regex fix (C) must handle both with-branch and without-branch pytest output formats
- No architectural changes to parallel execution or shell visibility (deferred)

## Acceptance Criteria

- A. Code review prompt contains competency rules text (not empty placeholder)
- B. fix-review RetryBlock is skipped when initial review verdict is APPROVE
- C. parse_coverage_report returns empty missing_lines for 100% coverage files
- F. Shell steps in worktree see VIRTUAL_ENV pointing to worktree's .venv/, not main tree
- H. mark-plan-in-progress only stages files in the protocol directory
- G. Test fails when _dsl.py is missing a block type defined in types.py
- J. ShellStep with stdin={{results.x.structured_output}} correctly passes JSON to subprocess
- K. Resumed inline SubWorkflow child preserves _inline_parent_exec_key and cascades correctly
- All existing tests pass (uv run pytest)

## Source

Generated from task description: 2026-03-20
