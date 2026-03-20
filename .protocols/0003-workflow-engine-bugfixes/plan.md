---
status: In Progress
---
# Protocol: Workflow Engine Bug Fixes

**Status**: Draft
**Created**: 2026-03-20
**PRD**: [./prd.md](./prd.md)

## Context

During protocol 0002 execution, 16 observations revealed 7 unique bugs across workflow definitions and the engine. Code review runs blind (competency rules never loaded), re-review wastes LLM prompts on APPROVE, coverage parser corrupts data, and worktree shell steps inherit wrong VIRTUAL_ENV.

## Decision

Fix all 8 actionable items across 3 focused steps:

1. **Workflow correctness** — fix competency_rules loading (A), skip re-review on APPROVE (B), scope git add (H)
2. **Coverage parser** — tighten regex (C)
3. **Engine fixes** — fix stdin template resolution (J), persist _inline_parent_exec_key in checkpoints (K), fix VIRTUAL_ENV (F), add _dsl.py parity test (G)

All workflow changes mirrored to both `memento/static/workflows/` (source of truth) and `.workflows/` (deployed copy).

## Rationale

Grouped by change scope (workflow definitions vs dev-tools vs engine) to minimize context-switching and allow independent verification per step. Workflow fixes are highest priority (A affects every review, B wastes tokens). Engine fix (F) is isolated. _dsl.py test (G) is pure prevention.

## Consequences

### Positive

- Code review actually uses competency rules — reviewers no longer work blind
- Skip re-review on APPROVE saves ~8 LLM prompts per protocol step (~$2-5 per run)
- Coverage parser produces accurate missing_lines data
- Worktree shell steps see correct VIRTUAL_ENV — no more pyright warnings
- _dsl.py drift caught automatically by CI

### Negative

- Workflow file changes must be kept in sync between static/ and .workflows/ — mitigated by protocol workflow doing both

## Progress

- [ ] [Fix workflow correctness bugs](./01-fix-workflow-correctness-bugs.md) <!-- id:01-fix-workflow-correctness-bugs --> — 1h est

- [ ] [Fix coverage report parser](./02-fix-coverage-report-parser.md) <!-- id:02-fix-coverage-report-parser --> — 30m est

- [ ] [Engine fixes: stdin, checkpoint, VIRTUAL_ENV, _dsl.py parity](./03-fix-virtual-env-and-add-dslpy-parity-test.md) <!-- id:03-engine-fixes --> — 2h est
