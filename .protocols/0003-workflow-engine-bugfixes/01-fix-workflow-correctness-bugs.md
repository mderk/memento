---
id: 01-fix-workflow-correctness-bugs
status: pending
estimate: 1h
---
# Fix workflow correctness bugs

## Objective

<!-- objective -->
Fix three workflow-level bugs that affect correctness and efficiency:

- **A. competency_rules empty**: code review prompts never see competency rules because the shell step's `result_var` fails (non-zero exit + non-JSON output)
- **B. Re-review on APPROVE**: `fix-review` RetryBlock enters even when initial review verdict is APPROVE, wasting 5-8 LLM prompts
- **H. git add -A scope**: `mark-plan-in-progress` stages all changes, not just the protocol directory
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Fix competency_rules loading in code-review workflow

Root cause: `cat ... -platforms/*.md 2>/dev/null` returns non-zero when glob fails. `_apply_result_var` requires `status=="success"` for ShellStep AND valid JSON output. Competency rules are markdown text, not JSON — double failure.

- [ ] Fix cat exit code in code-review/workflow.py
  Add `; true` to the shell command so it always exits 0, even when platform-specific glob finds no files.

  Remove `result_var="competency_rules"` — it can't work with non-JSON text output.

  ```python
  # Before:
  ShellStep(
      name="load-competency",
      command="cat .workflows/code-review/competencies/{{variables.item}}.md "
              ".workflows/code-review/competencies/{{variables.item}}-platforms/*.md "
              "2>/dev/null",
      result_var="competency_rules",
  ),

  # After:
  ShellStep(
      name="load-competency",
      command="cat .workflows/code-review/competencies/{{variables.item}}.md "
              ".workflows/code-review/competencies/{{variables.item}}-platforms/*.md "
              "2>/dev/null; true",
  ),
  ```

- [ ] Update 02-review.md prompt to reference results.output
  Change `{{variables.competency_rules}}` to `{{results.load-competency.output}}` which reads the shell step's stdout directly from recorded results.

  This works because the shell step and the LLM step share the same scope inside the parallel lane.

- [ ] Mirror changes to .workflows/code-review/
<!-- /task -->

<!-- task -->
### Skip re-review when initial review is APPROVE

The `fix-review` RetryBlock in process-protocol/workflow.py unconditionally enters the fix → re-review loop. When the initial review verdict is APPROVE, `fix-issues` has nothing to fix, but the loop still runs `re-review` (another full code-review SubWorkflow).

- [ ] Add condition to fix-review RetryBlock
  Add `condition=lambda ctx: ctx.result_field("review.synthesize", "has_blockers")` to the RetryBlock. This skips the entire fix loop when the initial review approved without blockers.

  ```python
  RetryBlock(
      name="fix-review",
      condition=lambda ctx: ctx.result_field("review.synthesize", "has_blockers"),
      until=lambda ctx: (
          not ctx.result_field("re-review.synthesize", "has_blockers")
          or ctx.variables.get("review_fix_changes", {}).get("changed") is False
      ),
      ...
  )
  ```

- [ ] Mirror to .workflows/process-protocol/workflow.py
<!-- /task -->

<!-- task -->
### Scope git add in mark-plan-in-progress

- [ ] Change 'git add -A' to 'git add -- {{variables.protocol_dir}}'
  In process-protocol/workflow.py `mark-plan-in-progress` step, replace broad `git add -A` with targeted add scoped to the protocol directory. This prevents staging user's unrelated uncommitted work.

- [ ] Mirror to .workflows/process-protocol/workflow.py
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Code review prompt must contain actual competency rules text, not empty string
- fix-review RetryBlock must be skipped entirely when review verdict is APPROVE
- mark-plan-in-progress must only stage files in the protocol directory
- Both static/ and .workflows/ copies must be identical
<!-- /constraints -->

## Implementation Notes

Key insight: `_apply_result_var` (state.py:565) for ShellStep requires both `status=="success"` and valid JSON output. For plain text output, use `results.<step-name>.output` in prompt templates instead.

The `result_field()` method on WorkflowContext navigates scoped results — `review.synthesize` means the `synthesize` step inside the `review` SubWorkflow.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest
diff memento/static/workflows/code-review/workflow.py .workflows/code-review/workflow.py
diff memento/static/workflows/code-review/prompts/02-review.md .workflows/code-review/prompts/02-review.md
diff memento/static/workflows/process-protocol/workflow.py .workflows/process-protocol/workflow.py
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/workflows/code-review/workflow.py
- memento/static/workflows/code-review/prompts/02-review.md
- memento/static/workflows/process-protocol/workflow.py
- memento-workflow/scripts/engine/state.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
