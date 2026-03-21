---
title: Workflow Engine Hardening
status: draft
created: 2026-03-21
---

# PRD: Workflow Engine Hardening

## Problem

Protocol 0003 execution revealed workflow-level bugs and confirmed existing engine debt:

1. **Coverage retry wastes ~90s** — develop workflow retries coverage-fill 3 times with identical numbers. exec-based conftest makes pytest-cov unable to trace engine code, so coverage never improves. No stagnation detection.

2. **Acceptance check audits last unit only** — develop workflow's acceptance-check receives context for only the last unit (g4), not all units in the step. Units g1-g3 skip acceptance audit entirely.

3. **_evict_terminal_runs may orphan child runs** — runner.py:156 removes terminal runs from _runs dict without checking if a parent still references them via child_run_ids. Theoretical at threshold=100, but breaks invariant.

4. **MEMENTO_SANDBOX=off has no audit trail** — disabling sandbox leaves no log trace. Security-relevant escape hatch should at minimum log a warning.

5. **Parallel blocks degrade to sequential in SubWorkflow** — ParallelEachBlock inside inline SubWorkflow is silently downgraded to LoopBlock (parallel.py:52). This is an engine limitation, not by design — grandchild runs are feasible but not implemented.

## Goals

- Eliminate wasted retry cycles in develop workflow
- Ensure all units pass acceptance audit
- Harden engine run lifecycle (eviction safety, sandbox audit)
- Enable parallel execution inside SubWorkflow

## Non-Goals

- Rearchitecting exec-based conftest (backlog: exec→import migration)
- Per-file coverage floors or e2e --cov-append merge (backlog)
- ChainMap optimization for parallel lane copies (backlog: B4)
- TypedDict for protocol helpers (backlog: B5)
- Sub-step checkpointing (backlog: B6)

## Solution

### Step 1: Develop workflow fixes

**Coverage stagnation exit**: Add stagnation detection to `coverage-retry` RetryBlock. Store previous `overall_coverage` in a variable; if current == previous → exit early. ~5 lines in `develop/workflow.py`.

**Acceptance check scope**: Change acceptance-check to receive the full step description (all units), not just the last unit's context. Fix context injection or step placement in `develop/workflow.py`.

### Step 2: Engine hardening

**Evict safety**: Before removing a terminal run from `_runs`, check that no other run references it in `child_run_ids`. Skip eviction if referenced.

**Sandbox audit**: Log `logger.warning("Sandbox disabled via MEMENTO_SANDBOX=off")` in `_sandbox_prefix()` when sandbox is off.

### Step 3: Remove parallel downgrade in child runs

`parallel.py:52` has a blanket `if is_child` guard that downgrades ALL ParallelEachBlocks to sequential LoopBlocks inside child runs. This is overly conservative — the engine shouldn't make this decision.

**Analysis**: The guard conflates two cases:
- **Inline SubWorkflow** (`_inline_parent_exec_key` set): actions are transparently proxied to the main relay. ParallelAction passes through — relay launches N agents normally. No limitation.
- **Subagent SubWorkflow** (`spawn_exec_key` set): sub-relay agent receives ParallelAction. It can either launch nested agents or handle lanes sequentially (built-in relay fallback). Either way, engine should return ParallelAction, not decide for the relay.

**Fix**: Remove the `if is_child` downgrade entirely. Let the engine always return ParallelAction. The relay handles degradation if needed (already documented as fallback behavior in relay skill).

**What needs verification**:
- Grandchild run_ids (`parent>child>grandchild`) resolve to correct checkpoint paths — `checkpoint_dir_from_run_id` already handles N-level composite IDs
- `checkpoint_load_children` recursive loading works at depth 3 — already has `max_depth=10`
- `_evict_terminal_runs` handles 3-level hierarchy (covered by step 2 fix)

## Success Criteria

- Coverage retry exits after 1 attempt when numbers don't change (saves ~60s per step)
- Acceptance check covers all units in a protocol step
- _evict_terminal_runs skips runs with active parents
- Sandbox-off logs warning
- ParallelEachBlock inside SubWorkflow spawns parallel agents (not sequential)
- All existing tests pass
