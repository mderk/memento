---
id: 02-rewrite-prompts-for-criteria-driven-flow
status: done
estimate: 1h30m
---
# Rewrite prompts for criteria-driven flow

## Objective

<!-- objective -->
Update three prompts to work with the new data flow:

- Plan prompt generates acceptance criteria per task
- Write-tests prompt returns created file list via output schema
- Acceptance check prompt verifies against provided criteria instead of extracting own
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Update plan prompt to generate acceptance criteria

- [ ] Add acceptance criteria instructions to 02-plan.md
  Add to the task definition section:

  > For each task, write 2-5 **acceptance criteria** — concrete, verifiable statements about what the implementation must do. Focus on observable behavior, not implementation details. These criteria will be checked by an independent evaluator after implementation.
<!-- /task -->

<!-- task -->
### Update write-tests prompt to return file list

- [ ] Add output schema instructions to 03a-write-tests.md
  Add output section instructing the model to return `WriteTestsOutput` JSON with the list of test files created or modified.
<!-- /task -->

<!-- task -->
### Rewrite acceptance check prompt

- [ ] Rewrite 03g-acceptance-check.md for criteria-driven verification
  The prompt receives `{{variables.units}}` — a JSON array of all units. Each unit may have `acceptance_criteria`. The prompt must:

  1. Collect all `acceptance_criteria` from all units into a flat list
  2. Run `git diff HEAD` in the workdir to see all changes
  3. For each criterion, find evidence in the diff (implementation + test)
  4. No evidence → missing
  5. `passed` = missing is empty

  Remove all references to `out_of_scope`. Remove instruction to extract requirements.

- [ ] Add fallback for units without acceptance_criteria
  If all units have empty `acceptance_criteria`, fall back to the old behavior: extract requirements from description. This preserves compatibility with old step files.
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Prompts must reference the correct schema names
- Fallback behavior must be explicitly documented in the prompt
- Source hashes recomputed after prompt changes
<!-- /constraints -->

## Implementation Notes

The write-tests output schema follows the same pattern as the existing acceptance-tests step which already uses `AcceptanceTestsOutput { test_files: list[str] }` at workflow.py line 385-388.

For acceptance check fallback: check if any unit in `{{variables.units}}` has non-empty `acceptance_criteria`. If none do, use old extraction logic.

## Verification

<!-- verification -->
```bash
# timeout:120 uv run pytest memento/tests/ -q
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/workflows/develop/prompts/02-plan.md
- memento/static/workflows/develop/prompts/03a-write-tests.md
- memento/static/workflows/develop/prompts/03g-acceptance-check.md
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
