---
status: In Progress
---
# Protocol: Dry-Run Preview

**Status**: Draft
**Created**: 2026-03-22
**PRD**: [./prd.md](./prd.md)

## Context

The workflow engine has partial dry-run infrastructure (`WorkflowContext.dry_run`, `_build_dry_run_action`, `_auto_record_dry_run`) but the runner returns actions one at a time, requiring a full relay loop. DESIGN.md documents "returns ALL actions as a flat list" but this is not implemented. The feature needs completion: collect all actions in the runner, return a tree+summary in a single response.

## Decision

Complete the collect-all loop in `runner.py` — when `dry_run=True`, call `advance()` + `_auto_advance()` repeatedly until `completed`, collect actions into a tree, return a `dry_run_complete` action with `tree` and `summary`. Reuse existing `_build_dry_run_action` and `_auto_record_dry_run` infrastructure. Skip checkpoint/artifact writes. No new action types needed for the relay — `dry_run_complete` is a terminal action like `completed`.

## Rationale

The partial infrastructure already handles the hard parts (synthetic structured output, condition evaluation with placeholders, parallel expansion). The main gap is just the collection loop and tree formatting in the runner. Alternatives considered:

- **New MCP tool `preview()`**: rejected — `start()` already accepts `dry_run`, adding another tool is unnecessary
- **Client-side collection**: rejected — requires relay loop, wastes tokens, adds complexity for no benefit

## Consequences

### Positive

- Single MCP call returns full execution preview — no relay loop needed
- Reuses existing dry-run infrastructure (no new state machine logic)
- Tree format is compact and mirrors exec_key hierarchy

### Negative

- Conditions depending on `results.*` get synthetic values — preview may differ from actual execution for data-dependent branches
- Loops over unresolved lists can only show template — actual iteration count unknown until runtime

## Progress

- [x] [Implement collect-all loop and tree builder](./01-implement-collect-all-loop-and-tree-builder.md) <!-- id:01-implement-collect-all-loop-and-tree-builder --> — 3h est

- [ ] [Test dry-run on real workflows and update docs](./02-test-dry-run-on-real-workflows-and-update-docs.md) <!-- id:02-test-dry-run-on-real-workflows-and-update-docs --> — 2h est
