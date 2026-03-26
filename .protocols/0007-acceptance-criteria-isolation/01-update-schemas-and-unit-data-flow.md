---
id: 01-update-schemas-and-unit-data-flow
status: pending
estimate: 2h
---
# Update schemas and unit data flow

## Objective

<!-- objective -->
Change the data model to support acceptance criteria and remove unused fields:

- `PlanTask` gets `acceptance_criteria`, loses `files`/`test_files`
- `AcceptanceOutput` loses `requirements`/`out_of_scope`
- New `WriteTestsOutput` schema for write-tests to return created files
- Protocol parser extracts `<!-- accept -->` blocks into unit dict
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Update PlanTask and AcceptanceOutput schemas

- [ ] Remove `files` and `test_files` from PlanTask, add `acceptance_criteria: list[str]`
  In `develop/workflow.py`:

  ```python
  class PlanTask(BaseModel):
      id: str
      description: str
      depends_on: list[str] = Field(default_factory=list)
      acceptance_criteria: list[str] = Field(default_factory=list)
  ```

- [ ] Remove `requirements` and `out_of_scope` from AcceptanceOutput
  ```python
  class AcceptanceOutput(BaseModel):
      covered: list[str] = Field(description="criterion → evidence (impl + test)")
      missing: list[str] = Field(description="criterion → what's missing")
      passed: bool = Field(description="True only if missing is empty")
  ```

- [ ] Add WriteTestsOutput schema
  ```python
  class WriteTestsOutput(BaseModel):
      test_files: list[str]
  ```

  This mirrors the existing `AcceptanceTestsOutput` pattern.
<!-- /task -->

<!-- task -->
### Parse <!-- accept --> blocks in protocol step files

The parser in `process-protocol/helpers.py` must extract acceptance criteria from `<!-- accept -->` sections inside `<!-- task -->` blocks and add them to the unit dict.

**Important**: `_parse_task_groups` currently strips `<!-- task -->` markers on line 238 before parsing headings. The `<!-- accept -->` extraction must happen **before** this strip, or use a different approach — e.g. split by `<!-- task -->` first, then parse each block for headings and `<!-- accept -->` sections separately.

Also check `parse_units_from_tasks` (line 277) — it parses checklist-style tasks. It should also support `<!-- accept -->` blocks and add `acceptance_criteria` to unit dicts.

- [ ] Add `<!-- accept -->` parsing to `_parse_task_groups`
  Extract bulleted list between `<!-- accept -->` and `<!-- /accept -->` tags within each task block. Store as `acceptance_criteria: list[str]` in the unit dict. Extract accept blocks **before** stripping `<!-- task -->` markers.

  Example step file format:
  ```markdown
  <!-- task -->
  ### Task heading

  - [ ] Checklist item

  <!-- accept -->
  - Criterion 1
  - Criterion 2
  <!-- /accept -->
  <!-- /task -->
  ```

- [ ] Add `<!-- accept -->` parsing to `parse_units_from_tasks`
  Same logic for checklist-style tasks.

- [ ] Handle tasks without `<!-- accept -->` blocks (fallback: empty list)

- [ ] Add `acceptance_criteria` to all unit dicts in both parsers — all three return sites in `_parse_task_groups`: line 235 (empty fallback), line 259 (no-groups fallback), and line 273 (main loop append). Remove `files`/`test_files` from all three. Mirror the same for `parse_units_from_tasks` (lines 293-298)
<!-- /task -->

<!-- task -->
### Update existing tests for schema changes

- [ ] Fix tests that reference `PlanTask.files` or `PlanTask.test_files`

- [ ] Fix tests that reference `AcceptanceOutput.requirements` or `AcceptanceOutput.out_of_scope`

- [ ] Add tests for `<!-- accept -->` parsing in helpers.py
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Protocol mode and normal mode use the same unit format
- Old step files without <!-- accept --> blocks produce units with empty acceptance_criteria
- All existing workflow definition tests pass
- Source hashes recomputed after static file changes (workflow.py, helpers.py)
<!-- /constraints -->

## Implementation Notes

The `_parse_task_groups` function in helpers.py currently strips `<!-- task -->` markers (line 238) before parsing by heading. To support `<!-- accept -->` blocks, split the tasks_text by `<!-- task -->` / `<!-- /task -->` markers first, then within each block extract `<!-- accept -->` content and parse headings.

For `WriteTestsOutput` — follow the same pattern as `AcceptanceTestsOutput` which already exists at line 80-81.

Note: `set-units-from-plan` (workflow.py line 215-218) copies plan tasks to `variables.units`. After removing `files`/`test_files` from PlanTask, the unit format changes — this step should still work since it just passes through the JSON, but verify that downstream consumers don't expect these fields.

## Verification

<!-- verification -->
```bash
# timeout:120 uv run pytest memento/tests/ -q
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/workflows/develop/workflow.py
- memento/static/workflows/process-protocol/helpers.py
- memento/tests/test_workflow_definitions.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
