---
id: 01-implement-collect-all-loop-and-tree-builder
status: done
estimate: 3h
---
# Implement collect-all loop and tree builder

## Objective

<!-- objective -->
Add the core dry-run collection logic in `runner.py`: when `dry_run=True`, advance repeatedly until completed, build a hierarchical tree from collected actions, and return a `DryRunCompleteAction` with tree and summary stats.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Add DryRunCompleteAction to protocol.py

- [ ] Define `DryRunCompleteAction` Pydantic model
  Fields: `action = "dry_run_complete"`, `tree: list[DryRunNode]`, `summary: DryRunSummary`. `DryRunNode` has: `exec_key`, `type` (shell/llm/prompt/parallel/loop/retry/group/subworkflow/conditional), `name`, `detail` (command for shell, prompt file for llm, message for prompt), `skipped: bool`, `children: list[DryRunNode]`. `DryRunSummary` has: `step_count`, `steps_by_type: dict[str, int]`, `skipped_count`.

- [ ] Register in `action_to_dict()` serialization
<!-- /task -->

<!-- task -->
### Implement collect-all loop in runner.py

- [ ] Add `_collect_dry_run(state)` function
  Loop: call `advance(state)` → `_auto_advance(state, action, children)`, collect each action with its exec_key. Stop when action is `CompletedAction`. Build flat list of `(exec_key, action)` tuples.

- [ ] Skip checkpoint writes and artifact writes in dry-run path
  The `start()` function currently calls `checkpoint_save(state)` after advance. In dry-run mode, skip this. Also skip `write_meta()` and `_store_run()` for child runs.

- [ ] Wire into `start()` — call `_collect_dry_run` when `dry_run=True`, return `DryRunCompleteAction`
<!-- /task -->

<!-- task -->
### Build hierarchical tree from flat action list

- [ ] Add `_build_dry_run_tree(actions)` function
  Convert flat `(exec_key, action)` pairs into nested `DryRunNode` tree. Use exec_key hierarchy: `loop:implement[i=0]/write-tests` → parent node `loop:implement[i=0]` with child `write-tests`. Group by prefix segments.

- [ ] Compute summary stats from collected actions
  `step_count`, `steps_by_type` (count by action type), `skipped_count` (blocks where condition was false).
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- start(dry_run=True) returns a single DryRunCompleteAction — no relay loop needed
- No checkpoint files, meta.json, or artifact files written during dry-run
- Tree correctly nests children under container blocks (loops, retries, groups, parallel)
<!-- /constraints -->

## Implementation Notes

Key files:

- `scripts/runner.py` — `start()` function, add dry-run collection path
- `scripts/engine/protocol.py` — add `DryRunCompleteAction` model
- `scripts/engine/state.py:advance()` — existing dry-run path at line 179-191, returns one action at a time
- `scripts/engine/actions.py:_build_dry_run_action()` — builds placeholder actions per block type
- `scripts/engine/parallel.py:_auto_record_dry_run()` — auto-records synthetic results

The collect loop is essentially: `while action.action != 'completed': action, children = advance(state); action, children = _auto_advance(state, action, children)`. The tricky part is that dry-run actions currently return from advance() one at a time (line 191) — the runner needs to call `submit()` or equivalent to advance past each one. Use `apply_submit()` with synthetic data directly.

## Verification

<!-- verification -->
```bash
uv run pytest memento-workflow/tests/ -q
```
<!-- /verification -->

## Context

<!-- context:files -->
- memento-workflow/docs/DESIGN.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/runner.py
- memento-workflow/scripts/engine/protocol.py
- memento-workflow/scripts/engine/state.py
- memento-workflow/scripts/engine/actions.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
