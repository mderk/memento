---
id: 03-remove-parallel-downgrade-in-child-runs
status: pending
estimate: 2h
---
# Remove parallel downgrade in child runs

## Objective

<!-- objective -->
Remove the blanket `if is_child` guard at parallel.py:52-78 that downgrades ALL ParallelEachBlocks to sequential LoopBlocks inside child runs.

Analysis showed this guard is overly conservative:
- **Inline SubWorkflow**: actions are transparently proxied to the main relay. ParallelAction passes through — relay launches N agents. No limitation.
- **Subagent SubWorkflow**: sub-relay agent receives ParallelAction. It can launch nested agents or handle lanes sequentially (built-in relay fallback). Engine shouldn't decide for the relay.

The fix is to remove the guard entirely and let the engine always return ParallelAction.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Remove is_child downgrade and let ParallelAction pass through

The guard at parallel.py:52 checks `if is_child` and creates a synthetic LoopBlock. Remove this block (lines 52-78) entirely. The normal parallel execution path (lines 80+) already creates child runs with composite IDs — this works for grandchild runs too.

- [ ] Remove the is_child downgrade block in _handle_parallel
  Delete lines 52-78 of parallel.py. The function should proceed to the normal parallel execution regardless of whether the current state is a child run.

- [ ] Verify checkpoint_dir_from_run_id handles 3-level composite IDs
  Existing function splits on `>` and nests `children/` directories. Should already work for `parent>child>grandchild` → `.workflow-state/parent/children/child/children/grandchild/`. Write a test to confirm.

- [ ] Add test: ParallelEachBlock inside SubWorkflow returns ParallelAction (not LoopBlock)

- [ ] Add test: grandchild checkpoint save/load roundtrip

- [ ] Add test: 3-level run_id eviction respects parent references (integration with step 2 fix)
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- ParallelEachBlock inside any SubWorkflow must return ParallelAction, not degrade to LoopBlock
- Grandchild composite run_ids resolve to correct checkpoint paths
- Grandchild checkpoint save/load works through recursive checkpoint_load_children
- Existing parallel and SubWorkflow tests still pass
- No warning emitted for non-degraded parallel inside child
<!-- /constraints -->

## Implementation Notes

Start by writing a test that asserts `_handle_parallel` inside a child run returns `ParallelAction` (not advances through a LoopBlock). This test will fail today. Then remove the guard.

Grep for `is_child` references in parallel.py to ensure no other code depends on the downgrade.

The `_handle_parallel_batched` path (line 81) should also work for child runs — verify max_concurrency batching with grandchild runs.

## Verification

<!-- verification -->
```bash
# timeout:120 uv run pytest memento-workflow/tests/ -q
# timeout:120 uv run pytest memento/tests/ -q
```
<!-- /verification -->

## Context

<!-- context:inline -->
The `is_child` variable at parallel.py:46 is computed from `state.parallel_block_name` or `">"` in run_id. The downgrade was added as a safety measure in early implementation.

`checkpoint_dir_from_run_id` (checkpoint.py:39-58) splits run_id on `>` and nests `children/` dirs — already handles N levels.

`checkpoint_load_children` (checkpoint.py:328) has `max_depth=10` recursive loading — grandchild persistence should work.

The relay protocol already documents `ParallelAction` handling and sequential fallback as standard relay behavior.
<!-- /context:inline -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/engine/parallel.py
- memento-workflow/scripts/engine/child_runs.py
- memento-workflow/scripts/infra/checkpoint.py
- memento-workflow/scripts/runner.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
