---
id: 03-wire-subagent-isolation-and-verify-red-fix
status: done
estimate: 1h30m
---
# Wire subagent isolation and verify-red fix

## Objective

<!-- objective -->
Connect the new schemas and prompts to the workflow engine:

- Write-tests runs as isolated subagent (no explore/plan context)
- Verify-red reads files from write-tests result instead of unit.test_files
- Acceptance check runs as isolated subagent (no implementation context)
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Isolate write-tests as subagent and fix verify-red

- [ ] Add `isolation="subagent"` and `output_schema=WriteTestsOutput` to write-tests LLMStep
  In `_make_tdd_blocks()` (workflow.py ~line 123-127):

  ```python
  LLMStep(
      name="write-tests",
      prompt="03a-write-tests.md",
      tools=["Read", "Write", "Edit", "Glob", "Grep"],
      output_schema=WriteTestsOutput,
      isolation="subagent",
  ),
  ```

- [ ] Update verify-red to read from write-tests result
  Change `--files-json` from `{{variables.unit.test_files}}` to `{{results.write-tests.structured_output.test_files}}`.

  Update the condition — the current pattern uses `ctx.variables.get()` for loop vars and `ctx.result_field()` for step results. Check which API works for accessing `results.write-tests` inside a LoopBlock. The existing pattern at line 392 uses template strings `{{results.write-acceptance-tests.structured_output.test_files}}` for args, so the template approach is proven. For the condition lambda, verify the correct accessor — likely:

  ```python
  condition=lambda ctx: (
      ctx.result_field("classify", "type") != "refactor"
      and bool(ctx.result_field("write-tests", "test_files"))
  ),
  ```

  This uses `ctx.result_field()` — the proven API for accessing step results in condition lambdas (same pattern as line 135 in workflow.py).
<!-- /task -->

<!-- task -->
### Isolate acceptance check as subagent

- [ ] Add `isolation="subagent"` to acceptance-check LLMStep
  Both the main acceptance-check (line ~364) and the retry one inside acceptance-retry (line ~409) need the isolation flag.
<!-- /task -->

<!-- task -->
### Update workflow tests for new wiring

- [ ] Update tests checking verify-red args reference

- [ ] Add tests verifying write-tests and acceptance-check have isolation="subagent"
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Both acceptance-check instances (main and retry) must have isolation
- verify-red condition must handle case where write-tests returns empty test_files
- All existing tests pass
- Source hashes recomputed after static file changes (workflow.py)
<!-- /constraints -->

## Implementation Notes

The `isolation="subagent"` parameter on LLMStep causes the workflow engine to run the step in a fresh agent context. The subagent receives only the prompt template (with variable substitutions) and the specified tools — no conversation history from prior steps.

`output_schema` + `isolation="subagent"` is a proven pattern — the explore step (workflow.py line 199-200) already uses both together.

For verify-red: `results.write-tests.structured_output.test_files` accesses the structured output from the write-tests step. The workflow engine resolves this template variable from the step's result artifact. Both write-tests and verify-red are inside `_make_tdd_blocks()` within a LoopBlock — results from earlier steps in the same loop iteration are accessible (proven by line 153 accessing `results.classify` from within the loop).

## Verification

<!-- verification -->
```bash
# timeout:120 uv run pytest memento/tests/ -q
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/workflows/develop/workflow.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
