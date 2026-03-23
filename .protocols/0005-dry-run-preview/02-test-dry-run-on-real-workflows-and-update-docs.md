---
id: 02-test-dry-run-on-real-workflows-and-update-docs
status: done
estimate: 2h
---
# Test dry-run on real workflows and update docs

## Objective

<!-- objective -->
Verify dry-run works correctly on all existing workflows (develop, code-review, commit, create-protocol). Add integration tests. Update DESIGN.md dry_run section to match actual implementation.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Add unit tests for dry-run collection

- [ ] Test: simple linear workflow returns tree with correct structure
  Create a workflow with shell → llm → prompt steps. Verify dry-run returns `DryRunCompleteAction` with 3 nodes, correct types, correct exec_keys.

- [ ] Test: conditional branch shows taken/skipped correctly

- [ ] Test: loop shows template for each item (or placeholder if unresolved)

- [ ] Test: parallel block shows lanes in tree

- [ ] Test: subworkflow is recursively expanded

- [ ] Test: no checkpoint or artifact files created

- [ ] Test: summary stats are correct (step_count, steps_by_type, skipped_count)
<!-- /task -->

<!-- task -->
### Integration test: dry-run real workflows via MCP

- [ ] Test start(workflow='commit', dry_run=True) returns valid tree

- [ ] Test start(workflow='code-review', dry_run=True) returns valid tree with parallel node
<!-- /task -->

<!-- task -->
### Update DESIGN.md dry_run section

- [ ] Replace current dry_run section with actual implementation details
  Document: `DryRunCompleteAction` format, tree structure, summary fields, behavior for conditionals/loops/parallel/subworkflows.
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- All existing tests continue to pass
- Dry-run on develop, code-review, commit, create-protocol returns valid tree without errors
- DESIGN.md dry_run section matches implementation
<!-- /constraints -->

## Implementation Notes

For integration tests, use the existing `create_runner_ns()` conftest pattern to load the runner in an isolated namespace. Call `start()` directly with `dry_run=True` and parse the JSON response.

For real workflow tests, some workflows require variables (e.g., `commit` needs `workdir`). Use minimal required variables — dry-run should handle missing variables gracefully (template substitution leaves `{{...}}` as-is).

## Verification

<!-- verification -->
```bash
# timeout:120 uv run pytest memento-workflow/tests/ -q
uv run pytest memento-workflow/tests/test_dry_run.py -v
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/tests/conftest.py
- memento-workflow/docs/DESIGN.md
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-workflow/docs/DESIGN.md
