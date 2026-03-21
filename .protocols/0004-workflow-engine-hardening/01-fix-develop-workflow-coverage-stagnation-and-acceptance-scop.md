---
id: 01-fix-develop-workflow-coverage-stagnation-and-acceptance-scop
status: pending
estimate: 2h
---
# Fix develop workflow: coverage stagnation and acceptance scope

## Objective

<!-- objective -->
Two bugs in the develop workflow definition:

- **Coverage retry stagnation**: `coverage-retry` RetryBlock (workflow.py:310-336) retries 3 times even when coverage numbers don't change between attempts. The `until` condition (line 316) only checks `has_gaps` — doesn't compare with previous attempt.
- **Acceptance check scope**: `acceptance-check` (workflow.py:339) uses prompt template `{{variables.unit}}` which holds only the last LoopBlock iteration value. Earlier units are not audited.
- **create-protocol edit flow**: plan JSON is not persisted. Re-running `/create-protocol` on an existing protocol should allow conversational editing ("add a step for X") rather than regenerating from scratch.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Add stagnation detection to coverage-retry

The `re-coverage-check` shell step (line 329-334) overwrites `variables.coverage` each attempt via `result_var='coverage'`. Previous coverage value is lost — no way to compare.

- [ ] Store previous coverage before re-check
  Add a ShellStep before `re-coverage-check` that copies current `overall_coverage` to `_prev_coverage`:

  ```python
  ShellStep(
      name="save-prev-coverage",
      command='echo {{variables.coverage.overall_coverage}}',
      result_var="_prev_coverage",
  ),
  ```

- [ ] Add stagnation exit to until condition
  Extend the `until` lambda at line 316. Guard against `None == None` (first attempt has no `_prev_coverage`):

  ```python
  until=lambda ctx: (
      not ctx.variables.get('coverage', {}).get('has_gaps', False)
      or (
          ctx.variables.get('_prev_coverage') is not None
          and ctx.variables.get('_prev_coverage') == ctx.variables.get('coverage', {}).get('overall_coverage')
      )
  ),
  ```

  This exits when either: no gaps remain, or coverage didn't improve from previous attempt (but only if we have a previous value to compare).

- [ ] Add test verifying stagnation exit
<!-- /task -->

<!-- task -->
### Fix acceptance-check to audit all units

The prompt `03g-acceptance-check.md` (line 11) reads `{{variables.unit}}` — the LoopBlock loop variable. After the loop completes, `unit` holds only the last iteration's value.

**Note**: `variables.task` does NOT exist in this workflow. The correct variable is `variables.units` (already set in protocol mode from `discover-steps`). For non-protocol mode, `units` must be set from `results.plan.structured_output.tasks`.

- [ ] Set `variables.units` in non-protocol mode
  Before the `implement` LoopBlock, add a ShellStep or use an existing step to copy plan tasks to `variables.units` so both modes have the same variable available:
  ```python
  ShellStep(
      name="set-units-from-plan",
      command='echo \'{{results.plan.structured_output.tasks}}\'',
      result_var="units",
      condition=lambda ctx: ctx.variables.get("mode") != "protocol",
  ),
  ```

- [ ] Change acceptance prompt to use `{{variables.units}}`
  Replace `{{variables.unit}}` with `{{variables.units}}` in `03g-acceptance-check.md`. This contains all units/tasks, not just the last loop iteration.

- [ ] Verify acceptance prompt receives all units in both modes
<!-- /task -->

<!-- task -->
### Add plan.json edit flow to create-protocol workflow

Currently `create-protocol` always generates a fresh plan. Users should be able to re-run `/create-protocol 0004` on an existing protocol and say "add a step for X" or "change task Y" — conversational editing of the plan.

Flow:
1. ShellStep: check if `plan.json` exists in protocol dir
2. **ConditionalBlock**: if exists → edit flow; if not → generate flow (current behavior)
3. Edit flow: load `plan.json` → ask user what to change → LLM edits plan with user instructions → save `plan.json` → re-render markdown
4. Generate flow: LLM generates plan → save `plan.json` → render markdown

- [ ] Save plan.json to protocol directory after generation
  Add a ShellStep after `plan-protocol` that copies structured output to `{{variables.protocol_dir}}/plan.json`.

- [ ] Add ConditionalBlock: detect existing plan.json
  ShellStep checks `test -f {{variables.protocol_dir}}/plan.json`. Branch on result.

- [ ] Add edit flow: load plan.json → ask user → LLM edit → save
  When `plan.json` exists:
  - ShellStep loads it into a variable
  - PromptStep asks user: "Protocol already has a plan. What do you want to change?"
  - LLMStep receives current plan JSON + user instructions, outputs modified plan JSON
  - ShellStep saves updated plan.json

- [ ] Re-render from plan.json
  The render ShellStep should accept plan JSON from either flow (fresh or edited). Verify render_protocol.py reads from stdin or variable — both flows pipe the same format.
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Coverage retry must exit after 1 stagnant attempt (not burn all 3)
- Acceptance check must receive context covering all units in the step
- Existing develop workflow tests pass
- Mirror changes to .workflows/develop/ and .workflows/create-protocol/
- plan.json round-trips through edit flow without data loss
- Re-render from edited plan.json produces valid markdown step files
- Edit flow preserves existing plan structure when no changes requested
<!-- /constraints -->

## Implementation Notes

The `coverage` variable is set by `result_var='coverage'` on the shell step at line 302-308 (initial) and 329-334 (retry). It's a dict with keys: `has_gaps`, `overall_coverage`, `files`.

The `unit` variable is set by the `protocol-implement` LoopBlock's `loop_var` — only holds the last iteration value after the loop. The `units` variable is already set in protocol mode by `discover-steps` shell step. In non-protocol mode, it must be populated from `results.plan.structured_output.tasks` before the implement loop.

For stagnation: `_prev_coverage` will be a string (shell stdout). Compare as string since `overall_coverage` is a float rendered by the shell — exact match is fine for detecting stagnation.

## Verification

<!-- verification -->
```bash
# timeout:120 uv run pytest memento-workflow/tests/ -q
# timeout:120 uv run pytest memento/tests/ -q
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento/static/workflows/develop/workflow.py
- memento/static/workflows/develop/prompts/03g-acceptance-check.md
- memento/static/workflows/create-protocol/workflow.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
